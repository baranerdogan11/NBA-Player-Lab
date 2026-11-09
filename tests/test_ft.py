"""ft.py: free throws are sorted into their kind of trip (technicals and flagrants under other), an and-one is the one
shot after the shooter's own basket at the same clock, a pressure free throw is judged on the score before it, the file
read from the warehouse adds up to the box scores, and a game whose free throws differ from the box score is left out.
usage: python tests/test_ft.py
"""
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
from ft import KINDS, attempts, check_ft, from_warehouse, kind, write_ft  # noqa: E402
from site_data import write_site  # noqa: E402

checks = {}
checks["kinds"] = [kind("1 of 2", None), kind("2 of 2", None), kind("1 of 1", None), kind("2 of 3", None), kind("1 of 1", "technical"),
                   kind("1 of 2", "flagrant"), kind("other", "flagrant")] == [0, 1, 2, 3, 4, 4, 4]


def ev(t, **k):
    return {"action_type": t, "sub_type": None, "descriptor": None, "result": None, "player": None, "team": None, "period": 4,
            "clock": 100.0, "score_home": None, "score_away": None, "fg": t in ("2pt", "3pt"), **k}


# HOM 98-100 AWY with 1:40 left: an and-one (made layup, then his 1 of 1 at the same clock), a one-shot at another clock,
# then a trip of two down seven (five after it, but six before the second): the margin before each attempt decides pressure
es = [ev("period", score_home=96, score_away=100),
      ev("2pt", player=1, team="HOM", result="Made", score_home=98, score_away=100),
      ev("freethrow", sub_type="1 of 1", player=1, team="HOM", result="Made", score_home=99, score_away=100),
      ev("freethrow", sub_type="1 of 1", player=2, team="AWY", result="Missed", clock=90.0, score_home=99, score_away=100),
      ev("2pt", player=2, team="AWY", result="Made", clock=80.0, score_home=99, score_away=106),   # a margin of 7
      ev("freethrow", sub_type="1 of 2", player=1, team="HOM", result="Made", clock=70.0, score_home=100, score_away=106),
      ev("freethrow", sub_type="2 of 2", player=1, team="HOM", result="Made", clock=70.0, score_home=101, score_away=106),
      ev("freethrow", sub_type="1 of 1", descriptor="technical", player=3, team="AWY", result="Made", period=3, clock=10.0, score_home=101, score_away=107)]
rows = attempts(es, "HOM")
checks["and-one and pressure"] = [(r["pid"], r["kind"], r["andone"], r["press"], r["made"]) for r in rows] == [
    ("1", 2, True, True, True), ("2", 2, False, True, False), ("1", 0, False, False, True), ("1", 1, False, False, True), ("3", 4, False, False, True)]

# the fixture league: every box line's free throws as attempts, written and checked against the game files
teams, players, games, lines = site_fixture.make(random.Random(7))
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_site(direct, "2026-27", "2026-27", "2026-10-26T06:00:00Z", teams, players, games, lines)
made = site_fixture.free_throws(random.Random(19), games, lines)
write_ft(direct, teams, made)
check_ft(direct)
ft = json.load(open(os.path.join(direct, "ft.json")))
checks["fixture adds up"] = sum(a for _, a in ft["league"][:5]) == sum(x["fta"] for x in lines) > 500 and ft["kinds"] == KINDS

# a tampered file fails its check
bad = json.loads(json.dumps(ft))
pid = next(iter(bad["players"]))
bad["players"][pid][0][1] += 1
json.dump(bad, open(os.path.join(direct, "ft.json"), "w"))
try:
    check_ft(direct)
    checks["tampered file fails"] = False
except ValueError:
    checks["tampered file fails"] = True

# the warehouse: the fixture's attempts as play-by-play actions (a made field goal before every and-one, at its clock),
# one game with a free throw the box score does not have, and a preseason game, both left out
by = {}
for r in made:
    by.setdefault(r["gid"], []).append(r)
home = {g["gid"]: g["home"] for g in games}
events, n = [], 0
sub = {0: "1 of 2", 1: "2 of 2", 2: "1 of 1", 3: "1 of 3", 4: "1 of 1"}
for gid, rs in by.items():
    for i, r in enumerate(rs):   # a clock of its own for every attempt, inside the last two minutes; pressure ones in the fourth
        clock, period = round(119 - 0.1 * i, 1), 4 if r["press"] else 2
        n += 1
        if r["andone"]:
            events.append({"game": gid, "action": n, "order_no": n, "period": period, "clock": clock, "team": r["team"], "player": int(r["pid"]),
                           "action_type": "2pt", "sub_type": None, "descriptor": None, "result": "Made", "score_home": 0, "score_away": 0})
            n += 1
        events.append({"game": gid, "action": n, "order_no": n, "period": period, "clock": clock, "team": r["team"],
                       "player": int(r["pid"]), "action_type": "freethrow", "sub_type": sub[r["kind"]], "descriptor": "technical" if r["kind"] == 4 else None,
                       "result": "Made" if r["made"] else "Missed", "score_home": 0, "score_away": 0})
broken = games[0]["gid"]
x = next(x for x in lines if x["gid"] == broken)
events.append({"game": broken, "action": 99999, "order_no": 99999, "period": 1, "clock": 1.0, "team": x["team"], "player": int(x["pid"]),
               "action_type": "freethrow", "sub_type": "1 of 1", "descriptor": None, "result": "Made", "score_home": 0, "score_away": 0})
events.append({"game": "0012600001", "action": 1, "order_no": 1, "period": 1, "clock": 1.0, "team": x["team"], "player": int(x["pid"]),
               "action_type": "freethrow", "sub_type": "1 of 1", "descriptor": None, "result": "Made", "score_home": 0, "score_away": 0})
tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "home": g["home"], "away": g["away"], "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "home": games[0]["home"], "away": games[0]["away"], "tipoff_utc": "2026-10-10T23:00:00", "final": True}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "ftm": x["ftm"], "fta": x["fta"]} for x in lines],
    "events": events,
}
con = duckdb.connect()
for name, rs in tables.items():
    path = os.path.join(wh, name)
    with open(path + ".jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rs)
    con.execute(f"copy (select * from read_json_auto('{path}.jsonl')) to '{path}.parquet' (format parquet)")
rows, left, nbad, checked = from_warehouse(wh)
checks["broken game left out"] = set(left) == {broken} and nbad == 1 and checked == len(lines)
kept = [r for r in made if r["gid"] != broken]
got = sorted((r["gid"], r["pid"], r["kind"], r["made"], r["andone"], r["press"]) for r in rows)
checks["warehouse rows are the attempts"] = got == sorted((r["gid"], r["pid"], r["kind"], r["made"], r["andone"], r["press"]) for r in kept)
write_site(read, "2026-27", "2026-27", "2026-10-26T06:00:00Z", teams, players, games, lines)
write_ft(read, teams, rows, left)
check_ft(read)
checks["left-out game listed"] = json.load(open(os.path.join(read, "ft.json")))["out"] == [broken]

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
