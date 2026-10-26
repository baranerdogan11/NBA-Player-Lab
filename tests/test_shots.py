"""shots.py: the shot files read from the warehouse are the shot files written from the same shots directly, a
player-game whose shots differ from his box-score line (FG or 3P) stops the build, and the zones split the FG column
along the 3P column.
usage: python tests/test_shots.py
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
from shots import ZONES, from_warehouse, write_shots, zone  # noqa: E402

teams, players, games, lines = site_fixture.make(random.Random(7))
shots = site_fixture.spots(random.Random(13), games, lines)
first = next(i for i, s in enumerate(shots) if s["pts"] == 2 and zone(2, None, s["x"], s["y"]) != 2)
shots[first]["area"] = "Mid-Range"   # the feed's area names the zone over the spot
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_shots(direct, teams, shots)

tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "tipoff_utc": "2026-10-10T23:00:00", "final": True}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "fga": x["fga"], "fgm": x["fgm"],
             "fg3a": x["fg3a"], "fg3m": x["fg3m"]} for x in lines]
    + [{"game": "0012600001", "player": int(lines[0]["pid"]), "status": "ACTIVE", "fga": 1, "fgm": 1, "fg3a": 0, "fg3m": 0}],
    "shots": [{"game": s["gid"], "action": i, "player": int(s["pid"]), "team": s["team"], "x": s["x"], "y": s["y"], "made": s["made"],
               "pts": s["pts"], "area": s.get("area")} for i, s in enumerate(shots)]
    + [{"game": "0012600001", "action": 1, "player": int(lines[0]["pid"]), "team": "BOS", "x": 0, "y": 10, "made": True, "pts": 2, "area": None}],
}
con = duckdb.connect()


def store(name, rows):
    path = os.path.join(wh, name)
    with open(path + ".jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    con.execute(f"copy (select * from read_json_auto('{path}.jsonl')) to '{path}.parquet' (format parquet)")


for name, rows in tables.items():
    store(name, rows)
con.execute(f"copy (select * replace (tipoff_utc::timestamp as tipoff_utc) from '{wh}/games.parquet') to '{wh}/g.parquet' (format parquet)")
os.replace(f"{wh}/g.parquet", f"{wh}/games.parquet")
write_shots(read, teams, from_warehouse(wh))

diff = filecmp.dircmp(os.path.join(direct, "shots"), os.path.join(read, "shots")).diff_files
one = json.load(open(os.path.join(read, "shots", f"{lines[0]['team']}.json")))
mine = [s for s in shots if s["pid"] == lines[0]["pid"] and s["gid"] == lines[0]["gid"]]
files = [json.load(open(os.path.join(read, "shots", f"{t['code']}.json"))) for t in teams]
league = json.load(open(os.path.join(read, "shots", "league.json")))["zones"]
rows = [r for f in files for p in f["players"].values() for r in p]
zoned = {}
for f in files:
    for pid, rs in f["players"].items():
        for r in rs:
            z = zoned.setdefault((f["games"][r[0]], pid), [0, 0, 0, 0])
            z[0] += r[3]
            z[1] += 1
            z[2] += r[3] if r[4] >= 3 else 0
            z[3] += r[4] >= 3
box = {(x["gid"], x["pid"]): [x["fgm"], x["fga"], x["fg3m"], x["fg3a"]] for x in lines if x["fga"]}
checks = {
    "zones: a three by its shot value, then the feed's area, then the spot":
        [zone(3, "Left Corner 3", 0, 300), zone(3, "Above the Break 3", 230, 0), zone(3, "Backcourt", 0, 600), zone(3, None, -230, 40),
         zone(3, None, 0, 250), zone(2, "Restricted Area", 100, 100), zone(2, "In The Paint (Non-RA)", 0, 0), zone(2, "Mid-Range", 0, 10),
         zone(2, "Left Corner 3", 230, 0), zone(2, None, 10, 30), zone(2, None, 60, 120), zone(2, None, 150, 50), zone(2, None, None, None)]
        == [3, 4, 4, 3, 4, 0, 1, 2, 2, 0, 1, 2, 2],
    "every player-game's zones add up to his FG and his two three-point zones to his 3P": zoned == box,
    "every zone has shots in the fixture": all(n for _, n in league),
    "the league file is every club's shots by zone": len(league) == len(ZONES)
        and league == [[sum(r[3] for r in rows if r[4] == z), sum(1 for r in rows if r[4] == z)] for z in range(len(ZONES))],
    "the feed's area wins over the spot": sum(r[4] == 2 for r in files[[t["code"] for t in teams].index(shots[first]["team"])]["players"][shots[first]["pid"]])
        == 1 + sum(zone(s["pts"], None, s["x"], s["y"]) == 2 for s in shots if s["pid"] == shots[first]["pid"]),
    "warehouse tables give the same shot files" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(os.path.join(read, "shots"))) == 31,
    "a player's shots in a game are his box-score FGA, his makes his FGM":
        len(mine) == lines[0]["fga"] and sum(s["made"] for s in mine) == lines[0]["fgm"],
    "the file lists each final once, in game order": one["games"] == sorted(set(one["games"]), key=lambda g: (next(x["time"] for x in games if x["gid"] == g), g)),
}



def stops(name, rows):
    store("shots", rows)
    try:
        from_warehouse(wh)
        checks[name] = False
    except ValueError as e:
        checks[name] = "differ from the box score" in str(e)


i = next(i for i, s in enumerate(tables["shots"]) if s["pts"] == 3)
stops("a three counted as a two stops the build", [{**s, "pts": 2} if j == i else s for j, s in enumerate(tables["shots"])])
stops("a missing shot stops the build", tables["shots"][1:])   # one attempt fewer than the box score

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
