"""The site's JSON: what the page reads, written from plain rows (games, box-score lines, players).

Every file is derived from the same box-score lines, so a player's game log, his season row, the game page and the
leaders agree by construction. Only integer totals are written; the page turns them into averages and percentages
with rdiv in template.html, the same formula as rounding.avg, the site's one rounding rule. The one exception is
RAPM (rapm.py), a model's estimate rather than a ratio of totals, written already rounded by rounding.rnd.

Files under <out>/ (out is teams/<season>/):
  index.json        season, label, build time, the 30 clubs with colours and games played
  games.json        every game of the schedule: date, tip time, clubs, and the score (and its periods) once final
  <CODE>.json       the club's players, each with a log of his box-score lines (any club, newest last), each line with
                    its Game Score gs in tenths (game_score())
  games/<gid>.json  one final: score by period, both box scores and, from the play-by-play, its flow: [[ds, home, away],
                    ...], the score after every change, ds the tenths of a second of game time played; it ends on the
                    final and passes through every period's score; and its rotation: {pid: [[from, to, pm], ...]}, the
                    stretches each player was on the floor (from the lineup stints, lineups.py), from and to in the same
                    tenths of game time, pm the score margin while he was out there; a player stays on across a period's
                    end until he is subbed out, as lineups.py carries the five over
  lineups/<CODE>.json  the club's fives (lineups.py): {"code", "games": [gid, ...], "fives": [[pid x 5], ...], "rows":
                    [[g, f, ds, pts, opp_pts, fga, oreb, tov, fta, opp_fga, opp_oreb, opp_tov, opp_fta], ...]}, one row
                    per five per game: g indexes games (tip-off order), f fives, ds is tenths of a second; the page sums
                    the rows and derives every rating with rdiv
  ratings.json      each club's season totals and its opponents' over its finals, from the official team box scores:
                    {"teams": [{"code", "gp", "sec", "for": {RT keys}, "against": {RT keys}}, ...]}, sec the club's
                    seconds (five players' worth, 14400 a regulation game), tov with the team turnovers; the page
                    derives ratings, pace and the Four Factors with rdiv
  night.json        the latest night with a final: {"date", "rows": [{gid, pid, name, team, gs, pts, reb, ast, fgm, fga},
                    ...]}, its five best lines by Hollinger's Game Score, gs in tenths (game_score()), best first
  highs.json        the season's best single games: {"stats": {stat: [{gid, date, pid, name, team, club, opp, home, v},
                    ...]}} for each of HIGHS, its ten best lines, v the line's value (gs in tenths), team his club that
                    night and club his current one; best first, then the earlier game, then the name; check_highs()
                    holds it to the game box scores
  leaders.json      every player's season totals, under his current club, his clubs' totals over the same games
                    (tm_fga, tm_fta, tm_tov, tm_sec, for usage), his country and rookie flag, his RAPM, O-RAPM and D-RAPM (null without one), and
                    for form his Game Score total gs and gs5 and sec5 over his last five games played, and his season's
                    double-doubles dd, triple-doubles td and streaks run: {key: [active, longest]} for each of STREAKS
                    (streaks()); check_streaks() holds them to the game box scores, and check_totals() every total
  cal/<CODE>.ics    the club's schedule as an iCalendar feed (write_calendars()): one event per game, tip-off in UTC, a
                    UID per gid so a moved game moves in subscribed calendars, the final score once there is one

from_warehouse() turns the warehouse tables (warehouse/<season>/*.parquet, see warehouse.py) into those rows: regular
season games only, and box lines of every player who was active (a coach's decision is a line with 0 seconds; inactive
players have none). Every player on a club's roster is listed under that club, with an empty log until his first game;
a player no longer on any roster stays under the club of his last box score.
usage: python site_data.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/)
"""
import json
import os
from rounding import rnd

STATS = ["pts", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf",
         "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm", "fd", "pf_off", "tech"]
# fd: fouls drawn (offensive fouls drawn on defense too), pf_off: offensive fouls committed (part of pf), tech: technical
# fouls (not part of pf), all as the box score counts them
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://baranerdogan11.github.io/NBA-Player-Lab/"


def load_teams():
    with open(os.path.join(HERE, "teams.json")) as f:
        return json.load(f)["teams"]


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def _line(r):
    return {"start": bool(r["start"]), "sec": int(r["sec"]), **{k: int(r[k]) for k in STATS}}


def period_start(p):
    """Tenths of a second of game time before period p: four 12-minute quarters, then 5-minute overtimes."""
    return 7200 * (p - 1) if p <= 5 else 28800 + 3000 * (p - 5)


def game_flow(events):
    """events: (period, clock, score_home, score_away) in play-by-play order, clock in seconds left in the period.
    The game's flow: [[ds, home, away], ...], one point per change of score, in game time (a free throw logged after
    the buzzer goes back to its clock)."""
    timed = sorted(((period_start(p + 1) - round(10 * clock), h, a) for p, clock, h, a in events
                    if h is not None and a is not None and clock is not None), key=lambda e: e[0])
    out, last = [], (0, 0)
    for ds, h, a in timed:
        if (h, a) != last:
            out.append([ds, h, a])
            last = (h, a)
    return out


def check_flow(g):
    """Raises unless the game's flow ends on its final and holds each period's score at the period's end."""
    f, h, a = g["flow"], 0, 0
    for i, (qh, qa) in enumerate(g["periods"]):
        h, a = h + qh, a + qa
        at = [x[1:] for x in f if x[0] <= period_start(i + 2)]
        if (at[-1] if at else [0, 0]) != [h, a]:
            raise ValueError(f"game {g['gid']}: play-by-play score after period {i + 1} is {at[-1] if at else [0, 0]}, periods say {[h, a]}")
    if (f[-1][1:] if f else [0, 0]) != [g["hs"], g["as"]]:
        raise ValueError(f"game {g['gid']}: play-by-play ends at {f[-1][1:] if f else [0, 0]}, final is {[g['hs'], g['as']]}")


def played(periods):
    """The number of periods played: an overtime the feed lists with no score is its game-end marker in a period of its
    own (PHX-GSW, 24 Oct), not five minutes nobody scored in, as lineups.plays() reads it."""
    n = len(periods)
    while n > 4 and periods[n - 1] == [0, 0]:
        n -= 1
    return n


def rotation(stints):
    """stints: one club's stints of one game in order, (players, sec, pts, opp_pts). {pid: [[from, to, pm], ...]}, the
    player's stretches on the floor in tenths of game time, back-to-back stints joined (also when he went out and came
    back at the same moment, as at a period's break). A stretch of no time is kept only when the score moved in it
    (subbed in at a stoppage for a free throw the other side made)."""
    out, t, prev = {}, 0.0, set()
    for players, sec, pts, opp in stints:
        a, t = round(10 * t), t + sec
        b = round(10 * t)
        for p in players:
            k = str(p)
            if p in prev or (k in out and out[k][-1][1] == a):
                out[k][-1][1] = b
                out[k][-1][2] += pts - opp
            else:
                out.setdefault(k, []).append([a, b, pts - opp])
        prev = set(players)
    return {k: [x for x in r if x[0] < x[1] or x[2]] for k, r in out.items()}


def check_rotation(g):
    """Raises unless each player's stretches add up to his box-score seconds within one second (the box score keeps
    whole seconds and the play-by-play clock tenths: 1668.8 s on the floor can be 1668 or 1669 in the box score) and
    to his box plus-minus, nobody is on the floor twice at once, and every club has
    five on the floor for the whole game."""
    end = period_start(played(g["periods"]) + 1)
    for c in (g["home"], g["away"]):
        lines = {x["pid"]: x for x in g["box"][c]}
        rot = {p: r for p, r in g["rotation"].items() if p in lines}
        if sum(b - a for r in rot.values() for a, b, _ in r) != 5 * end:
            raise ValueError(f"game {g['gid']}: {c} rotation covers {sum(b - a for r in rot.values() for a, b, _ in r)} ds, five players' game is {5 * end}")
        for p, x in lines.items():
            r = rot.get(p, [])
            ds = sum(b - a for a, b, _ in r)
            if abs(ds - 10 * x["sec"]) > 10:
                raise ValueError(f"game {g['gid']}: {p} on the floor {ds / 10} s by the rotation, box {x['sec']} s")
            if sum(m for *_, m in r) != x["pm"]:
                raise ValueError(f"game {g['gid']}: {p} rotation +/- {sum(m for *_, m in r)}, box {x['pm']}")
            if any(a > b or a < 0 or b > end for a, b, _ in r) or any(r[i][1] > r[i + 1][0] for i in range(len(r) - 1)):
                raise ValueError(f"game {g['gid']}: {p} rotation out of order {r}")
    if set(g["rotation"]) - {x["pid"] for c in (g["home"], g["away"]) for x in g["box"][c]}:
        raise ValueError(f"game {g['gid']}: rotation names players without a box line")


def game_score(x):
    """Hollinger's Game Score in tenths, an integer: PTS + 0.4 FG - 0.7 FGA - 0.4 (FTA - FT) + 0.7 ORB + 0.3 DRB + STL
    + 0.7 AST + 0.7 BLK - 0.4 PF - TOV, times ten."""
    return (10 * x["pts"] + 4 * x["fgm"] - 7 * x["fga"] - 4 * (x["fta"] - x["ftm"]) + 7 * x["oreb"] + 3 * x["dreb"]
            + 10 * x["stl"] + 7 * x["ast"] + 7 * x["blk"] - 4 * x["pf"] - 10 * x["tov"])


def write_site(out, season, label, built, teams, players, games, lines):
    """teams: load_teams() rows. players: pid, team (current), name, jersey, pos, height, born, country, rookie (his first
    NBA season is this one), and optionally
    o_rapm, d_rapm (unrounded, from rapm.py).
    games: gid, date, time (UTC ISO), home, away, final, hs, as, periods ([[home, away], ...]) and optionally flow
    (game_flow()) and rotation (rotation(), both clubs' together) for finals.
    lines: one per player per final: gid, team, pid, name, start, sec and every key in STATS."""
    final = {g["gid"]: g for g in games if g["final"]}
    gp = {t["code"]: 0 for t in teams}
    for g in final.values():
        gp[g["home"]] += 1
        gp[g["away"]] += 1
    _dump(os.path.join(out, "index.json"), {
        "season": season, "label": label, "built": built,
        "teams": [{**{k: t[k] for k in ("code", "id", "city", "name", "conf", "div", "colors")}, "gp": gp[t["code"]]} for t in teams]})
    _dump(os.path.join(out, "games.json"), {"games": [
        {"gid": g["gid"], "date": g["date"], "time": g["time"], "home": g["home"], "away": g["away"],
         "hs": g["hs"] if g["final"] else None, "as": g["as"] if g["final"] else None,
         **({"periods": g["periods"]} if g["final"] else {})} for g in sorted(games, key=lambda g: (g["time"], g["gid"]))]})

    by_game = {}
    for r in lines:
        by_game.setdefault(r["gid"], []).append(r)
    for gid, g in final.items():
        box = {c: [{"pid": r["pid"], "name": r["name"], **_line(r)} for r in by_game.get(gid, []) if r["team"] == c]
               for c in (g["home"], g["away"])}
        for c, side in ((g["home"], "hs"), (g["away"], "as")):
            if sum(x["pts"] for x in box[c]) != g[side]:
                raise ValueError(f"game {gid}: {c} box score adds up to {sum(x['pts'] for x in box[c])}, final says {g[side]}")
        if "flow" in g:
            check_flow(g)
        if "rotation" in g:
            check_rotation({**g, "box": box})
        _dump(os.path.join(out, "games", f"{gid}.json"), {
            "gid": gid, "date": g["date"], "home": g["home"], "away": g["away"], "hs": g["hs"], "as": g["as"],
            "periods": g["periods"], "box": box, **{k: g[k] for k in ("flow", "rotation") if k in g}})

    logs = {}
    for r in sorted(lines, key=lambda r: (final[r["gid"]]["time"], r["gid"])):
        g = final[r["gid"]]
        home = r["team"] == g["home"]
        ts, os_ = (g["hs"], g["as"]) if home else (g["as"], g["hs"])
        logs.setdefault(r["pid"], []).append({
            "gid": r["gid"], "date": g["date"], "team": r["team"], "opp": g["away"] if home else g["home"], "home": home,
            "ts": ts, "os": os_, **_line(r), "gs": game_score(_line(r))})
    team_tot = {}
    for r in lines:
        t = team_tot.setdefault((r["gid"], r["team"]), {"fga": 0, "fta": 0, "tov": 0, "sec": 0})
        for k in t:
            t[k] += int(r[k])
    roster = {}
    leaders = []
    for p in players:
        log = logs.get(p["pid"], [])
        played = [x for x in log if x["sec"] > 0]
        last5 = played[-5:]
        info = {k: p[k] for k in ("pid", "name", "jersey", "pos", "height", "born", "country", "rookie")}
        roster.setdefault(p["team"], []).append({**info, "log": log})
        o, d = p.get("o_rapm"), p.get("d_rapm")
        has = o is not None and d is not None
        leaders.append({"pid": p["pid"], "name": p["name"], "team": p["team"], "pos": p["pos"], "country": p["country"], "rookie": p["rookie"], "gp": len(played),
                        "sec": sum(x["sec"] for x in played), **{k: sum(x[k] for x in played) for k in STATS},
                        **{f"tm_{k}": sum(team_tot[(x["gid"], x["team"])][k] for x in played) for k in ("fga", "fta", "tov", "sec")},
                        "rapm": rnd(o + d) if has else None, "orapm": rnd(o) if has else None, "drapm": rnd(d) if has else None,
                        "gs": sum(x["gs"] for x in played), "gs5": sum(x["gs"] for x in last5), "sec5": sum(x["sec"] for x in last5),
                        **streaks(played)})
    for t in teams:
        _dump(os.path.join(out, f"{t['code']}.json"), {"code": t["code"], "players": roster.get(t["code"], [])})
    _dump(os.path.join(out, "leaders.json"), {"players": leaders})
    last = max(final.values(), key=lambda g: (g["time"], g["gid"]))["date"] if final else None
    night = sorted(({"gid": r["gid"], "pid": r["pid"], "name": r["name"], "team": r["team"], "gs": game_score(_line(r)),
                     **{k: int(r[k]) for k in ("pts", "reb", "ast", "fgm", "fga")}}
                    for r in lines if final[r["gid"]]["date"] == last and int(r["sec"]) > 0), key=lambda x: (-x["gs"], x["name"], x["pid"]))
    _dump(os.path.join(out, "night.json"), {"date": last, "rows": night[:5]})
    club = {p["pid"]: p["team"] for p in players}
    played = [x | {"pid": pid} for pid, log in logs.items() for x in log if x["sec"] > 0]
    name = {r["pid"]: r["name"] for r in lines}
    _dump(os.path.join(out, "highs.json"), {"stats": {k: [
        {"gid": x["gid"], "date": x["date"], "pid": x["pid"], "name": name[x["pid"]], "team": x["team"], "club": club.get(x["pid"], x["team"]),
         "opp": x["opp"], "home": x["home"], "v": x[k]}
        for x in sorted((x for x in played if x[k] > 0), key=lambda x: (-x[k], final[x["gid"]]["time"], x["gid"], name[x["pid"]], x["pid"]))[:10]]
        for k in HIGHS}})
    check_highs(out, final)
    check_totals(out)
    check_streaks(out)
    write_calendars(out, teams, games)


def _ics(s):   # TEXT escaping (RFC 5545 3.3.11)
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def write_calendars(out, teams, games):
    """cal/<CODE>.ics for every club: its games in tip-off order, each two and a half hours long. The files change only
    when the schedule or a score does (DTSTAMP is the tip-off), so a data update leaves them alone."""
    names = {t["code"]: t["name"] for t in teams}
    for t in teams:
        ev = []
        for g in sorted(games, key=lambda g: (g["time"], g["gid"])):
            if t["code"] not in (g["home"], g["away"]):
                continue
            at = g["time"].replace("-", "").replace(":", "")
            a, h = names[g["away"]], names[g["home"]]
            url = f"{SITE}?l#game/{g['gid']}"
            note = f"Final: {a} {g['as']}, {h} {g['hs']}\n{url}" if g["final"] else url
            ev += ["BEGIN:VEVENT", f"UID:{g['gid']}@nba-player-lab", f"DTSTAMP:{at}", f"DTSTART:{at}", "DURATION:PT2H30M",
                   f"SUMMARY:{_ics(f'{a} @ {h}')}", f"DESCRIPTION:{_ics(note)}", f"URL:{url}", "END:VEVENT"]
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NBA Player Lab//Schedule//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                 f"X-WR-CALNAME:{_ics(t['city'] + ' ' + t['name'])}", "X-PUBLISHED-TTL:PT6H", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
                 *ev, "END:VCALENDAR"]
        path = os.path.join(out, "cal", f"{t['code']}.ics")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            f.write("".join("\r\n ".join(x[i:i + 74] for i in range(0, len(x), 74)) + "\r\n" for x in lines))   # folded at 75 octets


HIGHS = ("pts", "reb", "ast", "stl", "blk", "fg3m", "gs")


def check_highs(out, gids):
    """Raises unless every line in highs.json is its game's box-score line (games/<gid>.json), and no line of the
    finals gids beats the last one shown for its stat, or is left out of a board with fewer than ten."""
    hs = json.load(open(os.path.join(out, "highs.json")))["stats"]
    box = {}
    for gid in gids:
        g = json.load(open(os.path.join(out, "games", f"{gid}.json")))
        for side in g["box"].values():
            for x in side:
                if x["sec"] > 0:
                    box[(g["gid"], x["pid"])] = {**x, "gs": game_score(x)}
    for k in HIGHS:
        rows = hs[k]
        for r in rows:
            x = box.get((r["gid"], r["pid"]))
            if x is None or x[k] != r["v"]:
                raise ValueError(f"highs.json {k}: {r['name']} {r['v']} in {r['gid']}, the box score says {x and x[k]}")
        floor = rows[-1]["v"] if len(rows) == 10 else 0
        shown = {(r["gid"], r["pid"]) for r in rows}
        over = [key for key, x in box.items() if x[k] > floor and key not in shown]
        if over:
            raise ValueError(f"highs.json {k}: {len(over)} box-score lines beat the board, {over[0]} among them")


# double-doubles: ten or more in two of these (three for a triple-double)
DOUBLES = ("pts", "reb", "ast", "stl", "blk")
# streaks: consecutive games played meeting the test, this season only. A game he sat out (no line, or 0 seconds) does
# not break a run, as Basketball-Reference counts them
STREAKS = {"p20": lambda x: x["pts"] >= 20, "p10": lambda x: x["pts"] >= 10,
           "dd": lambda x: doubles(x) >= 2, "t3": lambda x: x["fg3m"] >= 1}


def doubles(x):
    """How many of DOUBLES the line reached ten in."""
    return sum(x[k] >= 10 for k in DOUBLES)


def streaks(played):
    """played: a player's lines with seconds, oldest first. {dd, td, run: {key: [active, longest]}}: his double-doubles
    and triple-doubles (a triple-double is a double-double too), and for each of STREAKS the run he is on now and his
    season's longest."""
    run = {}
    for k, test in STREAKS.items():
        cur = best = 0
        for x in played:
            cur = cur + 1 if test(x) else 0
            best = max(best, cur)
        run[k] = [cur, best]
    return {"dd": sum(doubles(x) >= 2 for x in played), "td": sum(doubles(x) >= 3 for x in played), "run": run}


def finals_lines(out):
    """{pid: [box line, ...]}: every player's lines with seconds in the finals' game files (games/<gid>.json), in
    tip-off order (games.json lists the schedule in that order; a final has its score)."""
    lines = {}
    for g in json.load(open(os.path.join(out, "games.json")))["games"]:
        if g["hs"] is None:
            continue
        for side in json.load(open(os.path.join(out, "games", f"{g['gid']}.json")))["box"].values():
            for x in side:
                if x["sec"] > 0:
                    lines.setdefault(x["pid"], []).append(x)
    return lines


def check_totals(out):
    """Raises unless every player's season totals in leaders.json (games, seconds and every key in STATS, fouls drawn
    among them) are the sums of his box-score lines in the finals' game files, his offensive fouls are part of his
    personal fouls in every game, and no line has a negative count."""
    lines = finals_lines(out)
    for x in (x for ls in lines.values() for x in ls):
        if x["pf_off"] > x["pf"] or any(x[k] < 0 for k in STATS if k != "pm"):
            raise ValueError(f"box line {x['name']}: pf {x['pf']}, pf_off {x['pf_off']}, fd {x['fd']}, tech {x['tech']}")
    for p in json.load(open(os.path.join(out, "leaders.json")))["players"]:
        ls = lines.get(p["pid"], [])
        want = {"gp": len(ls), "sec": sum(x["sec"] for x in ls), **{k: sum(x[k] for x in ls) for k in STATS}}
        got = {k: p.get(k) for k in want}
        if got != want:
            raise ValueError(f"leaders.json: {p['name']} totals {[(k, got[k], want[k]) for k in want if got[k] != want[k]]} (leaders, box)")


def check_streaks(out):
    """Raises unless every player's dd, td and streaks in leaders.json are those of his box-score lines in the finals'
    game files (games/<gid>.json), counted over his games played in tip-off order."""
    lines = finals_lines(out)
    for p in json.load(open(os.path.join(out, "leaders.json")))["players"]:
        want = streaks(lines.get(p["pid"], []))
        got = {k: p.get(k) for k in want}
        if got != want:
            raise ValueError(f"leaders.json: {p['name']} has {got}, his box scores say {want}")


LU_COUNTS = ("fga", "oreb", "tov", "fta")
RT = ("pts", "fgm", "fga", "fg3m", "ftm", "fta", "oreb", "dreb", "tov")


def write_ratings(out, teams, rows):
    """teams: load_teams() rows. rows: one per club per final (team_lines()): gid, team, opp, sec and every key in RT."""
    tot = {t["code"]: {"code": t["code"], "gp": 0, "sec": 0, "for": dict.fromkeys(RT, 0), "against": dict.fromkeys(RT, 0)} for t in teams}
    by = {(r["gid"], r["team"]): r for r in rows}
    for r in rows:
        c, o = tot[r["team"]], by[(r["gid"], r["opp"])]
        c["gp"] += 1
        c["sec"] += int(r["sec"])
        for k in RT:
            c["for"][k] += int(r[k])
            c["against"][k] += int(o[k])
    _dump(os.path.join(out, "ratings.json"), {"teams": list(tot.values())})


def check_ratings(out, rows=(), held=()):
    """Raises unless every club's totals behind its ratings (points, FGA, OREB, TOV and FTA, its own and its
    opponents') are the sums of its lineup rows, over the same games: its finals but those held out of the lineups
    (quarantine.py), whose write_ratings() rows are taken off the totals first."""
    by = {(r["gid"], r["team"]): r for r in rows}
    for c in json.load(open(os.path.join(out, "ratings.json")))["teams"]:
        path = os.path.join(out, "lineups", f"{c['code']}.json")
        lu = json.load(open(path)) if os.path.exists(path) else {"games": [], "rows": []}
        got = [sum(r[i] for r in lu["rows"]) for i in range(3, 13)]
        box = [c["for"]["pts"], c["against"]["pts"], *(c["for"][k] for k in LU_COUNTS), *(c["against"][k] for k in LU_COUNTS)]
        gp = c["gp"]
        for r in (r for r in rows if r["team"] == c["code"] and r["gid"] in held):
            o = by[(r["gid"], r["opp"])]
            gp -= 1
            box = [b - x for b, x in zip(box, [r["pts"], o["pts"], *(r[k] for k in LU_COUNTS), *(o[k] for k in LU_COUNTS)])]
        if len(lu["games"]) != gp or got != box:
            raise ValueError(f"{c['code']}: lineups add up to {len(lu['games'])} games {got}, box scores {c['gp']} games {box} "
                             f"(pts, opp_pts, {', '.join(LU_COUNTS)}, opp_...)")


def write_lineups(out, teams, rows):
    """teams: site_data.load_teams() rows. rows: stints with gid, time (tip-off, for game order), team, players, sec,
    pts, opp_pts and the LU_COUNTS of both sides."""
    keys = ["pts", "opp_pts", *LU_COUNTS, *(f"opp_{k}" for k in LU_COUNTS)]
    by_team = {t["code"]: [] for t in teams}
    for r in rows:
        by_team[r["team"]].append(r)
    os.makedirs(os.path.join(out, "lineups"), exist_ok=True)
    for code, rs in by_team.items():
        rs.sort(key=lambda r: (r["time"], r["gid"]))
        games = list(dict.fromkeys(r["gid"] for r in rs))
        fives, units = {}, {}
        for r in rs:
            five = tuple(sorted(str(p) for p in r["players"]))
            u = units.setdefault((r["gid"], fives.setdefault(five, len(fives))), {"ds": 0, **{k: 0 for k in keys}})
            u["ds"] += int(round(10 * r["sec"]))
            for k in keys:
                u[k] += int(r[k])
        with open(os.path.join(out, "lineups", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "fives": [list(x) for x in fives],
                       "rows": [[games.index(g), i, u["ds"], *(u[k] for k in keys)] for (g, i), u in units.items()]}, f, separators=(",", ":"))


# the league's best units (Leaders): every club's five-man and two-man units over the season, summed from its lineup
# rows, kept when they reach the floor in minutes. The floor rises with the games the clubs have played (the middle
# club's count), so early boards are not topped by a few lucky minutes, up to 100 for a five and 400 for a pair
LEAGUE_FLOOR = {5: (6, 100), 2: (20, 400)}   # size: (minutes per game played, cap)


def league_units(out, teams):
    """{5: {...}, 2: {...}} keyed (code, pids): [games, ds, pts, opp_pts, LU_COUNTS, opp LU_COUNTS], and the clubs'
    games played, from teams/<season>/lineups/<CODE>.json."""
    from itertools import combinations
    units, gp = {5: {}, 2: {}}, []
    for t in teams:
        path = os.path.join(out, "lineups", f"{t['code']}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            lu = json.load(f)
        gp.append(len(lu["games"]))
        for g, i, *vals in lu["rows"]:
            five = lu["fives"][i]
            for n, keys in ((5, [tuple(five)]), (2, combinations(five, 2))):
                for k in keys:
                    u = units[n].setdefault((t["code"], k), [set(), *[0] * len(vals)])
                    u[0].add(g)
                    for j, v in enumerate(vals):
                        u[1 + j] += v
    return {n: {k: [len(u[0]), *u[1:]] for k, u in us.items()} for n, us in units.items()}, gp


def league_floor(gp):
    """The minutes floor for a five and a pair, from the clubs' games played."""
    g = sorted(gp)[(len(gp) - 1) // 2] if gp else 0
    return g, {n: min(per * g, cap) for n, (per, cap) in LEAGUE_FLOOR.items()}


def write_league_lineups(out, teams):
    """teams/<season>/lineups/league.json: {games, floor: {5, 2} minutes, fives and pairs: [code, pids, games, ds, pts,
    opp_pts, LU_COUNTS, opp LU_COUNTS]}, the units at or above the floor, most minutes first."""
    units, gp = league_units(out, teams)
    g, floor = league_floor(gp)
    pick = lambda n: sorted(([c, list(k), *u] for (c, k), u in units[n].items() if u[1] >= 600 * floor[n]),  # noqa: E731
                            key=lambda r: (-r[3], r[0], r[1]))
    _dump(os.path.join(out, "lineups", "league.json"), {"games": g, "floor": {str(n): f for n, f in floor.items()},
                                                         "fives": pick(5), "pairs": pick(2)})


def check_league_lineups(out, teams):
    """Raises unless league.json holds exactly the units at or above the floor, each the sum of its club's lineup rows:
    a five's rows are its own, a pair's every row of a five with both in it."""
    lu = {}
    for t in teams:
        path = os.path.join(out, "lineups", f"{t['code']}.json")
        if os.path.exists(path):
            with open(path) as f:
                lu[t["code"]] = json.load(f)
    with open(os.path.join(out, "lineups", "league.json")) as f:
        lg = json.load(f)
    gp = sorted(len(x["games"]) for x in lu.values())
    g = gp[(len(gp) - 1) // 2] if gp else 0
    if lg["games"] != g or lg["floor"] != {str(n): min(per * g, cap) for n, (per, cap) in LEAGUE_FLOOR.items()}:
        raise ValueError(f"league lineups: floor {lg['games']} games {lg['floor']}, clubs' middle {g} games")
    for key, n in (("fives", 5), ("pairs", 2)):
        want = {}
        for code, x in lu.items():
            for r in x["rows"]:
                five = x["fives"][r[1]]
                for pids in ([five] if n == 5 else [[a, b] for a in five for b in five if a < b]):
                    w = want.setdefault((code, ",".join(pids)), [set(), [0] * (len(r) - 2)])
                    w[0].add(r[0])
                    w[1] = [a + b for a, b in zip(w[1], r[2:])]
        want = {k: [len(gs), *v] for k, (gs, v) in want.items() if v[0] >= 600 * lg["floor"][str(n)]}
        got = {(r[0], ",".join(r[1])): r[2:] for r in lg[key]}
        if len(got) != len(lg[key]) or got != want:
            diff = sorted({*got} ^ {*want}) or [k for k in sorted(got) if got[k] != want[k]]
            raise ValueError(f"league lineups: {key} differ from the club files at {diff[:3]}")


def from_warehouse(wh):
    """players, games, lines for write_site() from the Parquet tables in the directory wh. A game whose box score is
    quarantined (quarantine.py) is read as not final yet; one held out of the game flow has no flow, and one held out of
    the lineups or the rotation has no rotation."""
    import duckdb
    import quarantine
    con = duckdb.connect()
    for t in ("box", "players", "periods"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    con.execute(f"create view games as select * from {quarantine.games_sql(wh)}")
    no_flow = quarantine.held(wh, "flow", gate="flow")
    no_rot = quarantine.held(wh, "rotation", gate="rotation")
    if os.path.exists(os.path.join(wh, "roster.parquet")):
        con.execute(f"create view roster as select * from read_parquet('{os.path.join(wh, 'roster.parquet')}')")
    else:   # an earlier season, or a warehouse built before rosters were fetched: players come from box scores only
        con.execute("create view roster as select null::int as player, '' as team, '' as name, '' as jersey, '' as position, '' as height, "
                    "'' as country, null::int as from_year where false")

    def rows(sql):
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    played = "from box b join games g using (game) join players p using (player) where g.game_type = 'regular' and g.final and b.status = 'ACTIVE'"
    qtr = {}
    for r in rows("select q.game, q.period, sum(q.pts) filter (where q.team = g.home) as h, sum(q.pts) filter (where q.team = g.away) as a "
                  "from periods q join games g using (game) group by all order by q.game, q.period"):
        qtr.setdefault(r["game"], []).append([int(r["h"] or 0), int(r["a"] or 0)])
    flows = {}
    if os.path.exists(os.path.join(wh, "events.parquet")):
        for r in con.execute(f"select e.game, e.period, e.clock, e.score_home, e.score_away from read_parquet('{os.path.join(wh, 'events.parquet')}') e "
                             "join games g using (game) where g.game_type = 'regular' and g.final order by e.game, e.order_no").fetchall():
            flows.setdefault(r[0], []).append(r[1:])
    rots = {}
    if os.path.exists(os.path.join(wh, "stints.parquet")):   # lineups.py writes only the games that pass its gates
        cur = {}
        for r in con.execute(f"select game, team, players, sec, pts, opp_pts from read_parquet('{os.path.join(wh, 'stints.parquet')}') "
                             "order by game, team, stint").fetchall():
            cur.setdefault(r[0], {}).setdefault(r[1], []).append(r[2:])
        rots = {gid: {p: r for st in clubs.values() for p, r in rotation(st).items()} for gid, clubs in cur.items() if gid not in no_rot}
    games = [{**g, "final": bool(g["final"]), **({"periods": qtr.get(g["gid"], [])} if g["final"] else {}),
              **({"flow": game_flow(flows[g["gid"]])} if g["gid"] in flows and g["gid"] not in no_flow else {}),
              **({"rotation": rots[g["gid"]]} if g["gid"] in rots and g["final"] else {})}
             for g in rows("select game as gid, strftime(date, '%Y-%m-%d') as \"date\", strftime(tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as \"time\", "
                           "home, away, final, home_score as hs, away_score as \"as\" from games where game_type = 'regular'")]
    stat = ", ".join(f"coalesce(b.{'plus_minus' if k == 'pm' else k}, 0) as {k}" for k in STATS)
    lines = rows(f"select b.game as gid, b.team, b.player::varchar as pid, p.name, b.starter as start, round(b.seconds)::int as sec, {stat} {played}")
    boxed = rows("select b.player::varchar as pid, arg_max(b.team, g.tipoff_utc) as team, any_value(p.name) as \"name\", "
                 "arg_max(b.jersey, g.tipoff_utc) as jersey, arg_max(b.position, g.tipoff_utc) filter (where b.position is not null) as pos, "
                 f"null as height, null as born, null as country, false as rookie {played} group by b.player")
    # the roster gives the current club, the jersey, the height (6-8 in the feed, shown as 6'8"), the country and whether
    # this is his first NBA season (from_year the year the season's regular season began); box scores have none of them
    players = {p["pid"]: p for p in boxed}
    for r in rows("select player::varchar as pid, team, name, jersey, position as pos, height, country, coalesce(from_year = "
                  "(select year(min(date)) from games where game_type = 'regular'), false) as rookie from roster"):
        b = players.get(r["pid"], {})
        ft, _, inch = (r["height"] or "").partition("-")
        players[r["pid"]] = {**r, "jersey": r["jersey"] or b.get("jersey"), "pos": r["pos"] or b.get("pos"),
                             "height": f"{ft}'{inch}\"" if inch else r["height"], "born": None}
    if os.path.exists(os.path.join(wh, "rapm.parquet")):
        for r in rows(f"select player::varchar as pid, o, d from read_parquet('{os.path.join(wh, 'rapm.parquet')}')"):
            if r["pid"] in players:
                players[r["pid"]].update(o_rapm=r["o"], d_rapm=r["d"])
    return sorted(players.values(), key=lambda p: p["pid"]), games, lines


def team_lines(wh):
    """write_ratings() rows from the warehouse's team box scores, regular-season finals only. Turnovers count the
    team's own (a shot-clock violation, say) as the play-by-play does; rebounds are the players', as in lineups.py."""
    import duckdb
    import quarantine
    cur = duckdb.connect().execute(
        f"select t.game as gid, t.team, t.opponent as opp, round(t.seconds)::int as sec, {', '.join(f't.{k}' for k in RT if k != 'tov')}, "
        f"t.tov + coalesce(t.team_tov, 0) as tov from read_parquet('{os.path.join(wh, 'team_box.parquet')}') t "
        f"join {quarantine.games_sql(wh)} g using (game) where g.game_type = 'regular' and g.final")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


if __name__ == "__main__":
    import datetime
    from season import ROOT, season
    SEASON = season()
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "box.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    import quarantine
    teams = load_teams()
    players, games, lines = from_warehouse(wh)
    bad, bad_rot, box = {}, {}, {}
    for r in lines:
        box.setdefault(r["gid"], {}).setdefault(r["team"], []).append(r)
    for g in games:   # a game whose flow or rotation fails its check is quarantined and drawn without one
        try:
            if "flow" in g:
                check_flow(g)
        except ValueError as e:
            bad[g["gid"]] = ("flow", str(e))
            del g["flow"]
        try:
            if "rotation" in g:
                check_rotation({**g, "box": {c: box.get(g["gid"], {}).get(c, []) for c in (g["home"], g["away"])}})
        except ValueError as e:
            bad_rot[g["gid"]] = ("rotation", str(e))
            del g["rotation"]
    quarantine.record(wh, "flow", bad)
    quarantine.record(wh, "rotation", bad_rot)
    write_site(out, SEASON, SEASON, built, teams, players, games, lines)
    rows = team_lines(wh)
    write_ratings(out, teams, rows)
    check_ratings(out, rows, quarantine.held(wh, "lineups"))   # lineups.py has written teams/<season>/lineups/ by now
    write_league_lineups(out, teams)
    check_league_lineups(out, teams)
    print(f"{SEASON}: site JSON written to {out}")
    raise SystemExit(quarantine.exit_code(wh))
