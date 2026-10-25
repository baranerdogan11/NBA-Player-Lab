"""The site's JSON: what the page reads, written from plain rows (games, box-score lines, players).

Every file is derived from the same box-score lines, so a player's game log, his season row, the game page and the
leaders agree by construction. Only integer totals are written; the page turns them into averages and percentages
with rdiv in template.html, the same formula as rounding.avg, the site's one rounding rule. The one exception is
RAPM (rapm.py), a model's estimate rather than a ratio of totals, written already rounded by rounding.rnd.

Files under <out>/ (out is teams/<season>/):
  index.json        season, label, build time, the 30 clubs with colours and games played
  games.json        every game of the schedule: date, tip time, clubs, and the score once final
  <CODE>.json       the club's players, each with a log of his box-score lines (any club, newest last), each line with
                    its Game Score gs in tenths (game_score())
  games/<gid>.json  one final: score by period, both box scores and, from the play-by-play, its flow: [[ds, home, away],
                    ...], the score after every change, ds the tenths of a second of game time played; it ends on the
                    final and passes through every period's score
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
  leaders.json      every player's season totals, under his current club, his clubs' totals over the same games
                    (tm_fga, tm_fta, tm_tov, tm_sec, for usage), his RAPM, O-RAPM and D-RAPM (null without one), and
                    for form his Game Score total gs and gs5 and sec5 over his last five games played

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
         "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm"]
HERE = os.path.dirname(os.path.abspath(__file__))


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


def game_score(x):
    """Hollinger's Game Score in tenths, an integer: PTS + 0.4 FG - 0.7 FGA - 0.4 (FTA - FT) + 0.7 ORB + 0.3 DRB + STL
    + 0.7 AST + 0.7 BLK - 0.4 PF - TOV, times ten."""
    return (10 * x["pts"] + 4 * x["fgm"] - 7 * x["fga"] - 4 * (x["fta"] - x["ftm"]) + 7 * x["oreb"] + 3 * x["dreb"]
            + 10 * x["stl"] + 7 * x["ast"] + 7 * x["blk"] - 4 * x["pf"] - 10 * x["tov"])


def write_site(out, season, label, built, teams, players, games, lines):
    """teams: load_teams() rows. players: pid, team (current), name, jersey, pos, height, born, and optionally
    o_rapm, d_rapm (unrounded, from rapm.py).
    games: gid, date, time (UTC ISO), home, away, final, hs, as, periods ([[home, away], ...]) and optionally flow
    (game_flow()) for finals.
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
         "hs": g["hs"] if g["final"] else None, "as": g["as"] if g["final"] else None} for g in sorted(games, key=lambda g: (g["time"], g["gid"]))]})

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
        _dump(os.path.join(out, "games", f"{gid}.json"), {
            "gid": gid, "date": g["date"], "home": g["home"], "away": g["away"], "hs": g["hs"], "as": g["as"],
            "periods": g["periods"], "box": box, **({"flow": g["flow"]} if "flow" in g else {})})

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
        info = {k: p[k] for k in ("pid", "name", "jersey", "pos", "height", "born")}
        roster.setdefault(p["team"], []).append({**info, "log": log})
        o, d = p.get("o_rapm"), p.get("d_rapm")
        has = o is not None and d is not None
        leaders.append({"pid": p["pid"], "name": p["name"], "team": p["team"], "pos": p["pos"], "gp": len(played),
                        "sec": sum(x["sec"] for x in played), **{k: sum(x[k] for x in played) for k in STATS},
                        **{f"tm_{k}": sum(team_tot[(x["gid"], x["team"])][k] for x in played) for k in ("fga", "fta", "tov", "sec")},
                        "rapm": rnd(o + d) if has else None, "orapm": rnd(o) if has else None, "drapm": rnd(d) if has else None,
                        "gs": sum(x["gs"] for x in played), "gs5": sum(x["gs"] for x in last5), "sec5": sum(x["sec"] for x in last5)})
    for t in teams:
        _dump(os.path.join(out, f"{t['code']}.json"), {"code": t["code"], "players": roster.get(t["code"], [])})
    _dump(os.path.join(out, "leaders.json"), {"players": leaders})
    last = max(final.values(), key=lambda g: (g["time"], g["gid"]))["date"] if final else None
    night = sorted(({"gid": r["gid"], "pid": r["pid"], "name": r["name"], "team": r["team"], "gs": game_score(_line(r)),
                     **{k: int(r[k]) for k in ("pts", "reb", "ast", "fgm", "fga")}}
                    for r in lines if final[r["gid"]]["date"] == last and int(r["sec"]) > 0), key=lambda x: (-x["gs"], x["name"], x["pid"]))
    _dump(os.path.join(out, "night.json"), {"date": last, "rows": night[:5]})


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


def check_ratings(out):
    """Raises unless every club's totals behind its ratings (points, FGA, OREB, TOV and FTA, its own and its
    opponents') are the sums of its lineup rows, over the same games."""
    for c in json.load(open(os.path.join(out, "ratings.json")))["teams"]:
        path = os.path.join(out, "lineups", f"{c['code']}.json")
        lu = json.load(open(path)) if os.path.exists(path) else {"games": [], "rows": []}
        got = [sum(r[i] for r in lu["rows"]) for i in range(3, 13)]
        box = [c["for"]["pts"], c["against"]["pts"], *(c["for"][k] for k in LU_COUNTS), *(c["against"][k] for k in LU_COUNTS)]
        if len(lu["games"]) != c["gp"] or got != box:
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


def from_warehouse(wh):
    """players, games, lines for write_site() from the Parquet tables in the directory wh."""
    import duckdb
    con = duckdb.connect()
    for t in ("games", "box", "players", "periods"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    if os.path.exists(os.path.join(wh, "roster.parquet")):
        con.execute(f"create view roster as select * from read_parquet('{os.path.join(wh, 'roster.parquet')}')")
    else:   # an earlier season, or a warehouse built before rosters were fetched: players come from box scores only
        con.execute("create view roster as select null::int as player, '' as team, '' as name, '' as jersey, '' as position, '' as height where false")

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
    games = [{**g, "final": bool(g["final"]), **({"periods": qtr.get(g["gid"], [])} if g["final"] else {}),
              **({"flow": game_flow(flows[g["gid"]])} if g["gid"] in flows else {})}
             for g in rows("select game as gid, strftime(date, '%Y-%m-%d') as \"date\", strftime(tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as \"time\", "
                           "home, away, final, home_score as hs, away_score as \"as\" from games where game_type = 'regular'")]
    stat = ", ".join(f"coalesce(b.{'plus_minus' if k == 'pm' else k}, 0) as {k}" for k in STATS)
    lines = rows(f"select b.game as gid, b.team, b.player::varchar as pid, p.name, b.starter as start, round(b.seconds)::int as sec, {stat} {played}")
    boxed = rows("select b.player::varchar as pid, arg_max(b.team, g.tipoff_utc) as team, any_value(p.name) as \"name\", "
                 "arg_max(b.jersey, g.tipoff_utc) as jersey, arg_max(b.position, g.tipoff_utc) filter (where b.position is not null) as pos, "
                 f"null as height, null as born {played} group by b.player")
    # the roster gives the current club, the jersey and the height (6-8 in the feed, shown as 6'8"); box scores have no height
    players = {p["pid"]: p for p in boxed}
    for r in rows("select player::varchar as pid, team, name, jersey, position as pos, height from roster"):
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
    cur = duckdb.connect().execute(
        f"select t.game as gid, t.team, t.opponent as opp, round(t.seconds)::int as sec, {', '.join(f't.{k}' for k in RT if k != 'tov')}, "
        f"t.tov + coalesce(t.team_tov, 0) as tov from read_parquet('{os.path.join(wh, 'team_box.parquet')}') t "
        f"join read_parquet('{os.path.join(wh, 'games.parquet')}') g using (game) where g.game_type = 'regular' and g.final")
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
    teams = load_teams()
    write_site(out, SEASON, SEASON, built, teams, *from_warehouse(wh))
    write_ratings(out, teams, team_lines(wh))
    check_ratings(out)   # lineups.py has written teams/<season>/lineups/ by now
    print(f"{SEASON}: site JSON written to {out}")
