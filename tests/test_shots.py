"""shots.py: the shot files read from the warehouse are the shot files written from the same shots directly, and a
player-game whose shots differ from his box-score line stops the build.
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
from shots import from_warehouse, write_shots  # noqa: E402

teams, players, games, lines = site_fixture.make(random.Random(7))
shots = site_fixture.spots(random.Random(13), games, lines)
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_shots(direct, teams, shots)

tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "tipoff_utc": "2026-10-10T23:00:00", "final": True}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "fga": x["fga"], "fgm": x["fgm"]} for x in lines]
    + [{"game": "0012600001", "player": int(lines[0]["pid"]), "status": "ACTIVE", "fga": 1, "fgm": 1}],
    "shots": [{"game": s["gid"], "action": i, "player": int(s["pid"]), "team": s["team"], "x": s["x"], "y": s["y"], "made": s["made"]}
              for i, s in enumerate(shots)]
    + [{"game": "0012600001", "action": 1, "player": int(lines[0]["pid"]), "team": "BOS", "x": 0, "y": 10, "made": True}],
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
checks = {
    "warehouse tables give the same shot files" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(os.path.join(read, "shots"))) == 30,
    "a player's shots in a game are his box-score FGA, his makes his FGM":
        len(mine) == lines[0]["fga"] and sum(s["made"] for s in mine) == lines[0]["fgm"],
    "the file lists each final once, in game order": one["games"] == sorted(set(one["games"]), key=lambda g: (next(x["time"] for x in games if x["gid"] == g), g)),
}

tables["shots"] = tables["shots"][1:]   # one attempt fewer than the box score
store("shots", tables["shots"])
try:
    from_warehouse(wh)
    checks["a missing shot stops the build"] = False
except ValueError as e:
    checks["a missing shot stops the build"] = "differ from the box score" in str(e)

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
