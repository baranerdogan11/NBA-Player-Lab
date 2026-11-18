"""Clutch splits: what every player and club did in the clutch, the NBA's definition: the last five minutes of the fourth
quarter or of any overtime with the score within five points.

<out>/clutch.json  {"stats": STATS, "out": [gid, ...], "players": {pid: [g, ds, pts, fgm, fga, fg3m, fg3a, ftm, fta, ast, tov, pm]},
                    "teams": {code: [g, w, l, ds, pts, opp]},
                    "games": {gid: {"ds": ds, home: [pts, fgm, fga, fg3m, fg3a, ftm, fta], away: [...]}}}
  ds is time in tenths of a second. Time is clutch while the clock is in the window and the score, as it stands, is within
  the margin; a play is clutch when it happens in the window with the score within the margin just before it. A player's
  ds is his time on the floor in clutch time (who was on the floor comes from the substitution log, as for the lineups),
  his counts are his own clutch plays (an assist is his pass on a clutch basket) and pm is the clutch points scored for
  his club minus against while he was on the floor. g counts the finals in which he played clutch time or made a clutch
  play, a traded player's clubs summed. A club's g counts its finals with any clutch time or clutch play, w and l its
  results in those finals; pts and opp are clutch points for and against. games holds each such final's clutch time and
  both clubs' clutch scoring. out lists the finals left out: those an earlier gate holds and those failing this one.

from_warehouse() reads warehouse/<season>/events.parquet and the box score, regular-season finals only, and checks every
game: each club's clutch points from the running score equal its players' clutch baskets and free throws, each player's
time on the floor over the whole game equals the lineup stints' (lineups.stints) and is never more than his box-score
minutes, and no clutch count exceeds his box-score line. A game that fails is quarantined (quarantine.py, scope clutch)
and the run fails when the quarantine is systemic. check_clutch() then holds the written file to games.json (results),
the game box scores (games/<gid>.json), the shot charts (shots/<CODE>.json: each club's clutch field goals in a game are
the shots taken in the window with the score within the margin before them) and leaders.json.
usage: python clutch.py [2026-27]   (reads warehouse/<season>/, after shots.py has written teams/<season>/; writes teams/<season>/clutch.json)
"""
import json
import os

import quarantine
from rounding import rnd

CLUTCH_DS, CLUTCH_MARGIN = 3000, 5    # the window, tenths of a second left in the fourth quarter or an overtime; the margin
STATS = ["g", "ds", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "ast", "tov", "pm"]
SHOTS = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta"]   # a club's clutch scoring in one game, in games
BOX = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "ast", "tov"]   # the counts held to the box score


def in_clutch(period, ds, margin):
    """Whether a moment ds tenths of a second before the end of period, the score margin apart, is clutch."""
    return period >= 4 and ds is not None and ds <= CLUTCH_DS and abs(margin) <= CLUTCH_MARGIN


def walk(actions, starters, home):
    """One game's clutch splits from its events (dicts, warehouse names), {team: set of five} and the home club's code.
    Returns {"ds": clutch time, "teams": {team: {"pts", "opp"}}, "players": {(team, pid): {stat: n}}, "on": {(team, pid):
    seconds on the floor over the game}, "credit": {team: clutch points of its players' own plays}}."""
    from lineups import PERIOD_SEC, _v, play_order, plays   # pandas, which the browser tests' fixture does without
    teams = list(starters)
    on = {t: set(starters[t]) for t in teams}
    away = next((t for t in teams if t != home), None)
    pl, floor = {}, {}
    tm = {t: {"pts": 0, "opp": 0} for t in teams}
    credit = {t: 0 for t in teams}
    out = {"ds": 0, "teams": tm, "players": pl, "on": floor, "credit": credit}
    per, clock, score = 1, PERIOD_SEC(1) * 10, (0, 0)

    def stat(team, p):
        return pl.setdefault((team, p), {k: 0 for k in STATS[1:]})

    def elapse(lo):
        """The clock runs from clock down to lo: everyone on the floor gets the time, and the clutch part of it."""
        nonlocal clock
        if lo >= clock:
            return
        cl = max(0, min(clock, CLUTCH_DS) - lo) if in_clutch(per, lo, score[0] - score[1]) else 0
        out["ds"] += cl
        for t in teams:
            for p in on[t]:
                floor[(t, p)] = floor.get((t, p), 0) + (clock - lo)
                if cl:
                    stat(t, p)["ds"] += cl
        clock = lo

    for a in play_order(plays(actions)):
        kind, team, p = a["action_type"], _v(a.get("team")), _v(a.get("player"))
        a_per, c = int(a["period"]), _v(a.get("clock"))
        if a_per != per:
            elapse(0)
            per, clock = a_per, PERIOD_SEC(a_per) * 10
        ds = clock if c is None else round(rnd(c, 1) * 10)   # as the shot charts have it
        if ds < clock:
            elapse(ds)
        if kind == "substitution" and team in on and p:
            (on[team].add if a.get("sub_type") == "in" else on[team].discard)(p)
            continue
        sh, sa = _v(a.get("score_home")), _v(a.get("score_away"))
        s = (int(sh), int(sa)) if sh is not None and sa is not None else score
        made = a.get("result") == "Made"
        own = (3 if kind == "3pt" else 2 if kind == "2pt" else 1) * made if kind in ("2pt", "3pt", "freethrow") else 0
        before = s[0] - s[1] - (own if team == home else -own)   # the margin just before the play, from its own row
        if s != score and in_clutch(per, ds, score[0] - score[1]):
            for t, f, g in ((home, s[0] - score[0], s[1] - score[1]), (away, s[1] - score[1], s[0] - score[0])):
                tm[t]["pts"] += f
                tm[t]["opp"] += g
                for q in on[t]:
                    stat(t, q)["pm"] += f - g
        score = s
        if team not in on or not p or not in_clutch(per, ds, before):
            continue
        if kind in ("2pt", "3pt", "freethrow"):
            x = stat(team, p)
            pre = "ft" if kind == "freethrow" else "fg"
            x[pre + "a"] += 1
            x[pre + "m"] += made
            if kind == "3pt":
                x["fg3a"] += 1
                x["fg3m"] += made
            x["pts"] += own
            credit[team] += own
            ast = _v(a.get("assist_player"))
            if kind != "freethrow" and made and ast:
                stat(team, ast)["ast"] += 1
        elif kind == "turnover":
            stat(team, p)["tov"] += 1
    elapse(0)
    return out


def problems(game, starters, home, box):
    """What fails the gate in one game's walk(): box is {(team, pid): box-score line with sec and the BOX counts}."""
    from lineups import seconds_on, stints
    bad = []
    for t, v in game["teams"].items():
        if v["pts"] != game["credit"][t]:
            bad.append(f"{t} clutch points {v['pts']} from the score, {game['credit'][t]} from its players' plays")
    lineup = seconds_on(stints(game["actions"], starters)[0])
    for k in set(lineup) | set(game["on"]):
        if abs(lineup.get(k, 0) - game["on"].get(k, 0) / 10) > 1:
            bad.append(f"{k[1]} on the floor {game['on'].get(k, 0) / 10:.0f} s, stints {lineup.get(k, 0):.0f} s")
        if k in box and game["on"].get(k, 0) > box[k]["sec"] * 10 + 600:
            bad.append(f"{k[1]} on the floor {game['on'][k] / 10:.0f} s, box {box[k]['sec']} s")
    for k, x in game["players"].items():
        b = box.get(k)
        if b is None:
            bad.append(f"{k[1]} has clutch plays and no box-score line")
            continue
        if x["ds"] > b["sec"] * 10 + 600:
            bad.append(f"{k[1]} clutch time {x['ds'] / 10:.0f} s, box {b['sec']} s")
        over = [s for s in BOX if x[s] > b[s]]
        if over:
            bad.append(f"{k[1]} clutch {over} above the box score")
    return bad


def write_clutch(out, teams, results, left_out=()):
    """teams: site_data.load_teams() rows. results: [(gid, home, away, hs, as, walk() result)] of the finals kept."""
    players, clubs, games = {}, {t["code"]: [0] * 6 for t in teams}, {}
    for gid, home, away, hs, as_, g in sorted(results, key=lambda r: r[0]):
        played = {k for k, x in g["players"].items() if any(x.values())}
        side = {t: [0] * len(SHOTS) for t in (home, away)}
        for (t, p), x in g["players"].items():
            if (t, p) not in played:
                continue
            row = players.setdefault(str(p), [0] * len(STATS))
            row[0] += 1
            for i, s in enumerate(STATS[1:], 1):
                row[i] += x[s]
            for i, s in enumerate(SHOTS):
                side[t][i] += x[s]
        if not g["ds"] and not played:
            continue
        games[gid] = {"ds": g["ds"], **side}
        for t, us, them in ((home, hs, as_), (away, as_, hs)):
            c = clubs[t]
            c[0] += 1
            c[1 if us > them else 2] += 1
            c[3] += g["ds"]
            c[4] += g["teams"][t]["pts"]
            c[5] += g["teams"][t]["opp"]
    with open(os.path.join(out, "clutch.json"), "w") as f:
        json.dump({"stats": STATS, "out": sorted(left_out), "players": dict(sorted(players.items())), "teams": clubs, "games": games},
                  f, separators=(",", ":"))


def shot_clutch(row):
    """Whether a shot chart row [g, x, y, made, zone, type, dist, period, clock, own, opp] is clutch, None without a score."""
    if row[9] is None or row[10] is None:
        return None
    return in_clutch(row[7], row[8], row[9] - row[3] * (3 if row[4] >= 3 else 2) - row[10])


def check_clutch(out):
    """Raises unless clutch.json holds together and agrees with the rest of the site: each club's record is its results in
    games.json, its time and points the sum of its games, each game's clutch time at most the window of its fourth quarter
    and overtimes and its scoring at most the box score's, the players' counts add up to the games' and their time to five
    on the floor, every player's counts are within his leaders.json season line, and each club's clutch field goals in a
    game are what its shot chart has in the window, wherever the chart has that game's scores."""
    cl = json.load(open(os.path.join(out, "clutch.json")))
    finals = {g["gid"]: g for g in json.load(open(os.path.join(out, "games.json")))["games"] if g["hs"] is not None}
    clubs = {c: [0] * 6 for c in cl["teams"]}
    for gid, gm in cl["games"].items():
        f = finals.get(gid)
        if f is None or gid in cl["out"]:
            raise ValueError(f"clutch.json: game {gid} is not a final it keeps")
        if not 0 <= gm["ds"] <= CLUTCH_DS * (1 + len(f["periods"]) - 4):
            raise ValueError(f"clutch.json: game {gid} has {gm['ds']} ds of clutch time")
        box = json.load(open(os.path.join(out, "games", f"{gid}.json")))["box"]
        for t, us, them in ((f["home"], f["hs"], f["as"]), (f["away"], f["as"], f["hs"])):
            c = clubs[t]
            c[0] += 1
            c[1 if us > them else 2] += 1
            c[3] += gm["ds"]
            c[4] += gm[t][0]
            c[5] += gm[f["away"] if t == f["home"] else f["home"]][0]
            tot = [sum(x[s] for x in box[t]) for s in SHOTS]
            if any(a > b for a, b in zip(gm[t], tot)) or gm[t][2] < gm[t][1] or gm[t][4] < gm[t][3] or gm[t][6] < gm[t][5]:
                raise ValueError(f"clutch.json: game {gid} {t} clutch scoring {gm[t]}, box {tot}")
            if gm[t][0] != 2 * gm[t][1] + gm[t][3] + gm[t][5]:
                raise ValueError(f"clutch.json: game {gid} {t} clutch points {gm[t][0]} are not its baskets and free throws")
    if clubs != cl["teams"]:
        bad = [c for c in clubs if clubs[c] != cl["teams"][c]]
        raise ValueError(f"clutch.json: clubs {[(c, cl['teams'][c], clubs[c]) for c in bad[:3]]} (file, from its games)")
    pl = cl["players"].values()
    for i, s in enumerate(SHOTS):
        if sum(x[STATS.index(s)] for x in pl) != sum(gm[t][i] for gm in cl["games"].values() for t in gm if t != "ds"):
            raise ValueError(f"clutch.json: the players' {s} do not add up to the games'")
    if sum(x[1] for x in pl) != 5 * 2 * sum(gm["ds"] for gm in cl["games"].values()):
        raise ValueError("clutch.json: the players' clutch time is not five on the floor for each club")
    if sum(x[-1] for x in pl) != 5 * sum(c[4] - c[5] for c in cl["teams"].values()):
        raise ValueError("clutch.json: the players' +/- does not add up to five times the clubs' net points")
    season = {p["pid"]: p for p in json.load(open(os.path.join(out, "leaders.json")))["players"]}
    for pid, x in cl["players"].items():
        s = season.get(pid)
        if s is None or x[0] > s["gp"] or x[1] > s["sec"] * 10 + 600 * x[0] or any(x[STATS.index(k)] > s[k] for k in BOX) \
                or x[4] < x[3] or x[6] < x[5] or x[8] < x[7] or x[2] != 2 * x[3] + x[5] + x[7]:
            raise ValueError(f"clutch.json: player {pid} {x} against his season line")
    for code in cl["teams"]:
        path = os.path.join(out, "shots", f"{code}.json")
        if not os.path.exists(path):
            continue
        sh = json.load(open(path))
        got, scored = {}, set()
        for rows in sh["players"].values():
            for r in rows:
                gid = sh["games"][r[0]]
                c = shot_clutch(r)
                if c is None:
                    continue
                scored.add(gid)
                if c:
                    v = got.setdefault(gid, [0, 0, 0, 0])
                    three = r[4] >= 3
                    for i, n in enumerate((r[3], 1, r[3] * three, three)):
                        v[i] += n
        for gid in scored - set(cl["out"]):
            want = cl["games"].get(gid, {}).get(code, [0] * len(SHOTS))[1:5]
            if got.get(gid, [0, 0, 0, 0]) != want:
                raise ValueError(f"clutch.json: game {gid} {code} clutch FG {want}, shot chart {got.get(gid, [0, 0, 0, 0])}")


def from_warehouse(wh, skip=()):
    """([(gid, home, away, hs, as, walk())] of the finals that pass, {game: what fails}) from the Parquet tables in the
    directory wh; the games in skip are left out."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"create view games as select * from {quarantine.games_sql(wh)}")
    finals = con.execute("select game, home, away, home_score, away_score from games where game_type = 'regular' and final order by game").fetchall()
    finals = [f for f in finals if f[0] not in skip]
    ids = ", ".join(repr(f[0]) for f in finals) or "''"
    ev = con.execute(f"""select game, action, order_no, period, clock, team, player, action_type, sub_type, result, assist_player,
                                score_home, score_away
                         from read_parquet('{os.path.join(wh, 'events.parquet')}') where game in ({ids})""").df()
    ev["player"] = ev.player.astype("Int64")
    ev["assist_player"] = ev.assist_player.astype("Int64")
    box = con.execute(f"""select game, team, player, starter, coalesce(seconds, 0) as sec, {', '.join(f'coalesce({c}, 0) as {s}' for c, s in (
                              ('pts', 'pts'), ('fgm', 'fgm'), ('fga', 'fga'), ('fg3m', 'fg3m'), ('fg3a', 'fg3a'), ('ftm', 'ftm'), ('fta', 'fta'),
                              ('ast', 'ast'), ('tov', 'tov')))}
                          from read_parquet('{os.path.join(wh, 'box.parquet')}') where game in ({ids})""").df()
    box["player"] = box.player.astype(int)
    lines = {g: d for g, d in box.groupby("game")}
    acts = {g: d.to_dict("records") for g, d in ev.groupby("game")}
    results, bad = [], {}
    for gid, home, away, hs, as_ in finals:
        b = lines.get(gid)
        if b is None or gid not in acts:
            bad[gid] = "no box score or play-by-play"
            continue
        starters = {t: set(d.player) for t, d in b[b.starter].groupby("team")}
        g = walk(acts[gid], starters, home)
        g["actions"] = acts[gid]
        pr = problems(g, starters, home, {(r.team, r.player): r._asdict() for r in b.itertuples()})
        del g["actions"]
        if pr:
            bad[gid] = "; ".join(pr[:3]) + (f" (+{len(pr) - 3} more)" if len(pr) > 3 else "")
        else:
            results.append((gid, home, away, int(hs), int(as_), g))
    return results, bad


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "events.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    skip = quarantine.held(wh, "clutch", gate="clutch")
    results, bad = from_warehouse(wh, skip)
    for g, r in sorted(bad.items()):
        print(f"FAIL game {g}: clutch: {r}")
    quarantine.record(wh, "clutch", {g: ("clutch", r) for g, r in bad.items()})
    write_clutch(out, load_teams(), results, set(skip) | set(bad))
    check_clutch(out)
    cl = json.load(open(os.path.join(out, "clutch.json")))
    print(f"{SEASON}: clutch splits written to {os.path.join(out, 'clutch.json')}: {len(cl['games'])} of {len(results)} finals with clutch "
          f"time, {len(cl['players'])} players; {len(bad)} games quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
