"""The site JSON written from the warehouse tables is the site JSON written from the same lines directly.

The fixture league is stored as warehouse Parquet (the columns warehouse.py writes, plus a preseason game, an inactive
player and a coach's decision), read back with from_warehouse(), and both outputs are compared file by file.
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
from site_data import from_warehouse, write_site  # noqa: E402

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
    "periods": [{"game": g["gid"], "team": c, "period": i + 1, "pts": q[side]} for g in games if g["final"]
                for i, q in enumerate(g["periods"]) for side, c in enumerate((g["home"], g["away"]))],
}
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
checks = {"warehouse tables give the same site JSON" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(read)) == 34}

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
