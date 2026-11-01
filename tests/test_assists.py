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
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_assists(direct, teams, baskets)

# every made field goal as a shot, assisted or not: a team-mate's credit on the first of his assisted makes
made = []
for x in lines:
    made += [{"gid": x["gid"], "team": x["team"], "pid": x["pid"], "pts": 3}] * x["fg3m"] + [{"gid": x["gid"], "team": x["team"], "pid": x["pid"], "pts": 2}] * (x["fgm"] - x["fg3m"])
left = list(baskets)
shots = []
for i, s in enumerate(made):
    b = next((b for b in left if (b["gid"], b["scorer"], b["pts"]) == (s["gid"], s["pid"], s["pts"])), None)
    if b:
        left.remove(b)
    shots.append({"game": s["gid"], "action": i, "player": int(s["pid"]), "team": s["team"], "made": True, "pts": s["pts"],
                  "assist_player": int(b["passer"]) if b else None})
shots += [{"game": "0012600001", "action": 1, "player": int(lines[1]["pid"]), "team": lines[1]["team"], "made": True, "pts": 2,
           "assist_player": int(lines[0]["pid"])}]   # preseason: left out
tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "tipoff_utc": "2026-10-10T23:00:00", "final": True}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "ast": x["ast"]} for x in lines],
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
checks = {
    "the fixture has assists to pair": len(baskets) > 500 and not bad and n == 0 and checked == len(lines),
    "warehouse tables give the same pair files" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(os.path.join(read, "assists"))) == 30,
    "every passer's pairs in a game add up to his box-score AST": given == box,
    "a pair's points are two or three a basket": pts_ok,
    "passer and scorer are team-mates, never the same player": all(team[p] == team[s] == c and p != s for c, f in files.items() for _, p, s, *_ in f["pairs"]),
    "each club's file lists its finals in game order": all(f["games"] == sorted(f["games"], key=lambda g: (next(x["time"] for x in games if x["gid"] == g), g)) for f in files.values()),
    "the corrections allowed: one per thousand box lines, at least two": (allowed(500), allowed(2389), allowed(4100)) == (2, 2, 4),
}

# a post-game correction: an assist moved from one team-mate to another in the box score only
x = next(x for x in lines if x["ast"])
y = next(y for y in lines if y["gid"] == x["gid"] and y["team"] == x["team"] and y["pid"] != x["pid"])
store("box", [{**r, "ast": r["ast"] - 1} if r["player"] == int(x["pid"]) and r["game"] == x["gid"] else
              {**r, "ast": r["ast"] + 1} if r["player"] == int(y["pid"]) and r["game"] == x["gid"] else r for r in tables["box"]])
rows, bad, n, _ = from_warehouse(wh)
checks["a game whose credits differ from the box score is left out of the pairs, and named"] = \
    list(bad) == [x["gid"]] and n == 2 and not any(r["gid"] == x["gid"] for r in rows) and len(rows) == len(baskets) - sum(b["gid"] == x["gid"] for b in baskets)
rows, bad, n, _ = from_warehouse(wh, skip={x["gid"]})
checks["a game held by an earlier gate is left out and not checked"] = not bad and not any(r["gid"] == x["gid"] for r in rows)

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
