"""The site JSON written from the warehouse tables is the site JSON written from the same lines directly.

The fixture league is stored as warehouse Parquet (the columns warehouse.py writes, plus a preseason game, an inactive
player and a coach's decision), read back with from_warehouse(), and both outputs are compared file by file; so are
the ratings, from its team box scores with team_lines().
usage: python tests/test_site_warehouse.py
"""
import filecmp
import json
import os
import random
import sys
import tempfile

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures"))
import site_fixture  # noqa: E402
from site_data import from_warehouse, period_start, team_lines, write_ratings, write_site  # noqa: E402

ARGS = ("2026-27", "2026-27", "2026-10-26T06:00:00Z")
teams, players, games, lines = site_fixture.make(random.Random(7))
for p in players:   # the feeds carry no height or birth date
    p["height"] = p["born"] = None
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_site(direct, *ARGS, teams, players, games, lines)

pl = {p["pid"]: p for p in players}
when = {g["gid"]: g["time"] for g in games}
t = {
    "games": [{"game": g["gid"], "game_type": "regular", "date": g["date"], "tipoff_utc": g["time"].rstrip("Z"), "home": g["home"], "away": g["away"],
               "home_score": g.get("hs"), "away_score": g.get("as"), "status": 3 if g["final"] else 1, "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "date": "2026-10-10", "tipoff_utc": "2026-10-10T23:00:00", "home": "BOS", "away": "NYK",
        "home_score": 2, "away_score": 0, "status": 3, "final": True}],
    "players": [{"player": int(p["pid"]), "name": p["name"]} for p in players] + [{"player": 99, "name": "Not Playing"}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "team": x["team"], "jersey": pl[x["pid"]]["jersey"], "position": pl[x["pid"]]["pos"],
             "starter": x["start"], "status": "ACTIVE", "seconds": x["sec"] + .4, "plus_minus": x["pm"], **{k: x[k] for k in x if k not in ("pm", "gid", "pid", "team", "name", "start", "sec")}}
            for x in lines]
    + [{"game": lines[0]["gid"], "player": 99, "team": lines[0]["team"], "status": "INACTIVE", "seconds": 0.0},
       {"game": "0012600001", "player": int(players[0]["pid"]), "team": "BOS", "status": "ACTIVE", "seconds": 60.0, "pts": 2}],
    "rapm": [{"player": int(p["pid"]), "o": p["o_rapm"], "d": p["d_rapm"]} for p in players if "o_rapm" in p],
    "periods": [{"game": g["gid"], "team": c, "period": i + 1, "pts": q[side]} for g in games if g["final"]
                for i, q in enumerate(g["periods"]) for side, c in enumerate((g["home"], g["away"]))],
    # the club's totals, a team turnover apart from the players' (team_lines() adds them back), and a preseason game
    "team_box": [{"game": r["gid"], "team": r["team"], "opponent": r["opp"], "home": True, "score": r["pts"], "seconds": 14400.0,
                  **{k: r[k] for k in r if k not in ("gid", "team", "opp", "sec", "tov")}, "tov": r["tov"] - 1, "team_tov": 1}
                 for r in site_fixture.team_lines(games, lines)]
    + [{"game": "0012600001", "team": c, "opponent": o, "home": c == "BOS", "score": 2, "seconds": 14400.0, "pts": 2, "fgm": 1, "fga": 1, "fg3m": 0,
        "ftm": 0, "fta": 0, "oreb": 0, "dreb": 0, "tov": 0, "team_tov": 0} for c, o in (("BOS", "NYK"), ("NYK", "BOS"))],
}


def event(g, n, ds, h, a):
    """A play-by-play row at ds tenths of game time: its period and the seconds left on the clock."""
    p = next(p for p in range(1, 20) if ds <= period_start(p + 1))
    return {"game": g, "order_no": n, "period": p, "clock": (period_start(p + 1) - ds) / 10, "score_home": h, "score_away": a}


# every scoring play, a rebound after each (the score unchanged) and the tip-off at 0-0, plus a preseason basket
t["events"] = [e for g in games if g["final"] for i, (ds, h, a) in enumerate(g["flow"])
               for e in ([event(g["gid"], 0, 0, 0, 0)] if i == 0 else []) + [event(g["gid"], 2 * i + 1, ds, h, a), event(g["gid"], 2 * i + 2, ds, h, a)]] \
    + [event("0012600001", 1, 300, 2, 0)]
con = duckdb.connect()
for name, rows in t.items():
    path = os.path.join(wh, name)
    with open(path + ".jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    con.execute(f"copy (select * from read_json_auto('{path}.jsonl')) to '{path}.parquet' (format parquet)")
con.execute(f"create table g as select * replace (date::date as date, tipoff_utc::timestamp as tipoff_utc) from '{wh}/games.parquet'")
con.execute(f"copy g to '{wh}/games.parquet' (format parquet)")
write_site(read, *ARGS, teams, *from_warehouse(wh))

cmp = filecmp.dircmp(direct, read)
diff = [*cmp.left_only, *cmp.right_only, *cmp.diff_files, *(f"games/{f}" for f in cmp.subdirs["games"].diff_files + cmp.subdirs["games"].left_only)]
checks = {"warehouse tables give the same site JSON" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(read)) == 36}
rt_direct, rt_read = tempfile.mkdtemp(), tempfile.mkdtemp()
write_ratings(rt_direct, teams, site_fixture.team_lines(games, lines))
write_ratings(rt_read, teams, team_lines(wh))
checks["team box scores give the same ratings, team turnovers counted"] = filecmp.cmp(*(os.path.join(d, "ratings.json") for d in (rt_direct, rt_read)), shallow=False)

# with a roster: a signed player who has not played is listed under his club with an empty log, and a player who has
# played moves to the club that rosters him now, keeping his game log and taking the roster's height
moved = players[0]
to = next(t["code"] for t in teams if t["code"] != moved["team"])
with open(os.path.join(wh, "roster.jsonl"), "w") as f:
    f.write(json.dumps({"player": 98, "team": "BOS", "name": "New Signing", "jersey": "7", "position": "G", "height": "6-3"}) + "\n")
    f.write(json.dumps({"player": int(moved["pid"]), "team": to, "name": moved["name"], "jersey": None, "position": None, "height": "6-11"}) + "\n")
con.execute(f"copy (select * from read_json_auto('{wh}/roster.jsonl')) to '{wh}/roster.parquet' (format parquet)")
rost = tempfile.mkdtemp()
write_site(rost, *ARGS, teams, *from_warehouse(wh))
bos = {p["pid"]: p for p in json.load(open(os.path.join(rost, "BOS.json")))["players"]}
dest = {p["pid"]: p for p in json.load(open(os.path.join(rost, f"{to}.json")))["players"]}
old = json.load(open(os.path.join(read, f"{moved['team']}.json")))["players"]
checks["a rostered player without a game is listed with an empty log"] = bos.get("98", {}).get("log") == [] and bos["98"]["height"] == "6'3\""
checks["a rostered player is under his current club with his log"] = (
    moved["pid"] in dest and dest[moved["pid"]]["log"] == next(p["log"] for p in old if p["pid"] == moved["pid"])
    and dest[moved["pid"]]["jersey"] == moved["jersey"] and dest[moved["pid"]]["height"] == "6'11\""
    and (to == moved["team"] or moved["pid"] not in {p["pid"] for p in json.load(open(os.path.join(rost, f"{moved['team']}.json")))["players"]}))
for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
