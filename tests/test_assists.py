"""assists.py: the pair files read from the warehouse are the pair files written from the same baskets directly, every
passer's pairs in a game add up to his box-score AST, and a game whose assist credits differ from the box score is left
out of the pairs (and quarantined only when more differ than the stat corrections allowed).
usage: python tests/test_assists.py
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
from assists import allowed, from_warehouse, write_assists  # noqa: E402

teams, players, games, lines = site_fixture.make(random.Random(7))
baskets = site_fixture.passes(random.Random(17), games, lines)
spots = site_fixture.spots(random.Random(13), games, lines)
made = site_fixture.makes(spots, baskets)
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_assists(direct, teams, made)

# every made field goal as a shot of the warehouse, with its spot and its passer (if any); misses are left out
shots = [{"game": m["gid"], "action": i, "player": int(m["scorer"]), "team": m["team"], "made": True, "pts": m["pts"], "area": None,
          "x": s["x"], "y": s["y"], "assist_player": None if m["passer"] is None else int(m["passer"])}
         for i, (m, s) in enumerate(zip(made, (s for s in spots if s["made"])))]
shots += [{"game": "0012600001", "action": 1, "player": int(lines[1]["pid"]), "team": lines[1]["team"], "made": True, "pts": 2,
           "area": None, "x": 0, "y": 0, "assist_player": int(lines[0]["pid"])}]   # preseason: left out
tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "tipoff_utc": "2026-10-10T23:00:00", "final": True}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "ast": x["ast"], "fgm": x["fgm"], "fg3m": x["fg3m"]} for x in lines],
    "shots": shots,
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
rows, bad, n, checked = from_warehouse(wh)
write_assists(read, teams, rows)

diff = filecmp.dircmp(os.path.join(direct, "assists"), os.path.join(read, "assists")).diff_files
files = {t["code"]: json.load(open(os.path.join(read, "assists", f"{t['code']}.json"))) for t in teams}
given = {}
for f in files.values():
    for g, passer, scorer, ast, pts in f["pairs"]:
        given[(f["games"][g], passer)] = given.get((f["games"][g], passer), 0) + ast
box = {(x["gid"], x["pid"]): x["ast"] for x in lines if x["ast"]}
pts_ok = all(f["pairs"] and all(2 * ast <= pts <= 3 * ast for *_, ast, pts in f["pairs"]) for f in files.values())
team = {x["pid"]: x["team"] for x in lines}
mades, got, scored = {}, {}, {}
for f in files.values():
    for g, pid, z, ast, m in f["made"]:
        k = (f["games"][g], pid)
        v = mades.setdefault(k, [0, 0])
        v[0] += m
        v[1] += m * (z >= 3)
        got[k] = got.get(k, 0) + ast
    for g, _, scorer, ast, _ in f["pairs"]:
        scored[(f["games"][g], scorer)] = scored.get((f["games"][g], scorer), 0) + ast
got = {k: v for k, v in got.items() if v}
fgm = {(x["gid"], x["pid"]): [x["fgm"], x["fg3m"]] for x in lines}
league = json.load(open(os.path.join(read, "assists", "league.json")))
checks = {
    "the fixture has assists to pair": len(baskets) > 500 and not bad and n == 0 and checked == len(lines),
    "warehouse tables give the same pair files" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(os.path.join(read, "assists"))) == 31,
    "every passer's pairs in a game add up to his box-score AST": given == box,
    "a pair's points are two or three a basket": pts_ok,
    "passer and scorer are team-mates, never the same player": all(team[p] == team[s] == c and p != s for c, f in files.items() for _, p, s, *_ in f["pairs"]),
    "each club's file lists its finals in game order": all(f["games"] == sorted(f["games"], key=lambda g: (next(x["time"] for x in games if x["gid"] == g), g)) for f in files.values()),
    "each player's makes in a game add up to his box-score FGM, his three-point zones to his 3PM":
        mades == {k: v for k, v in fgm.items() if v[0]},
    "a scorer's assisted makes in a game are the pairs naming him as scorer": got == scored,
    "the league file sums the clubs' made rows, by zone and by player":
        league["zones"] == [[sum(r[3] for f in files.values() for r in f["made"] if r[2] == z), sum(r[4] for f in files.values() for r in f["made"] if r[2] == z)] for z in range(5)]
        and league["players"] == {p: [sum(r[3] for f in files.values() for r in f["made"] if r[1] == p), sum(r[4] for f in files.values() for r in f["made"] if r[1] == p)] for p in league["players"]}
        and 0 < sum(a for a, _ in league["zones"]) < sum(m for _, m in league["zones"]),
    "the corrections allowed: one per thousand box lines, at least two": (allowed(500), allowed(2389), allowed(4100)) == (2, 2, 4),
}

# a post-game correction: an assist moved from one team-mate to another in the box score only
x = next(x for x in lines if x["ast"])
y = next(y for y in lines if y["gid"] == x["gid"] and y["team"] == x["team"] and y["pid"] != x["pid"])
store("box", [{**r, "ast": r["ast"] - 1} if r["player"] == int(x["pid"]) and r["game"] == x["gid"] else
              {**r, "ast": r["ast"] + 1} if r["player"] == int(y["pid"]) and r["game"] == x["gid"] else r for r in tables["box"]])
rows, bad, n, _ = from_warehouse(wh)
checks["a game whose credits differ from the box score is left out of the pairs, and named"] = \
    list(bad) == [x["gid"]] and n == 2 and not any(r["gid"] == x["gid"] for r in rows) and len(rows) == len(made) - sum(m["gid"] == x["gid"] for m in made)
store("box", tables["box"])
z = next(z for z in lines if z["fgm"] and z["gid"] != x["gid"])
store("box", [{**r, "fgm": r["fgm"] + 1} if r["player"] == int(z["pid"]) and r["game"] == z["gid"] else r for r in tables["box"]])
rows, bad, n, _ = from_warehouse(wh)
checks["a game whose makes differ from the box-score FGM is left out, and named"] = list(bad) == [z["gid"]] and n == 1 and not any(r["gid"] == z["gid"] for r in rows)
rows, bad, n, _ = from_warehouse(wh, skip={x["gid"], z["gid"]})
checks["a game held by an earlier gate is left out and not checked"] = not bad and not any(r["gid"] == x["gid"] for r in rows)

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
