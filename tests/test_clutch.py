"""clutch.py: clutch time runs while the clock is in the last five minutes of the fourth quarter or an overtime and the
score is within five, a play is clutch on the score just before it, the five on the floor get the time and the +/-, the
fixture league's file holds together with the rest of its site, and a game whose score does not follow its plays is left
out of the file read from the warehouse.
usage: python tests/test_clutch.py
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
from clutch import STATS, check_clutch, from_warehouse, in_clutch, walk, write_clutch  # noqa: E402
from shots import write_shots  # noqa: E402
from site_data import write_site  # noqa: E402

checks = {}
checks["window"] = [in_clutch(4, 3000, 5), in_clutch(4, 3001, 0), in_clutch(3, 100, 0), in_clutch(5, 2999, -5), in_clutch(4, 100, 6)] == \
    [True, False, False, True, False]

HOME, AWAY = list(range(1, 6)), list(range(11, 16))


def game(gid="0022600001", broken=False):
    """HOM 80-78 AWY into the fourth: a basket at 6:40 (before the window), a three at 5:00 down four (clutch, assisted),
    a change at 4:10, a turnover, two HOM baskets (the second from three makes it six), a miss up six (not clutch), then
    two free throws at 0:50: the first, up six, is not clutch, the second, up five, is; 87-83. broken: the HOM three only
    moves the score by two (86-83)."""
    rows = [("period", None, None, None, 720.0, 1, 0, 0), ("period", None, None, None, 720.0, 2, 40, 40),
            ("period", None, None, None, 720.0, 3, 60, 60), ("period", None, None, None, 720.0, 4, 80, 78),
            ("2pt", "HOM", 1, "Made", 400.0, 4, 82, 78), ("3pt", "AWY", 11, "Made", 300.0, 4, 82, 81),
            ("substitution", "HOM", 5, "out", 250.0, 4, 82, 81), ("substitution", "HOM", 6, "in", 250.0, 4, 82, 81),
            ("turnover", "HOM", 1, None, 200.0, 4, 82, 81), ("2pt", "HOM", 6, "Made", 150.0, 4, 84, 81),
            ("3pt", "HOM", 2, "Made", 100.0, 4, 87, 81), ("2pt", "AWY", 11, "Missed", 60.0, 4, 87, 81),
            ("freethrow", "AWY", 13, "Made", 50.0, 4, 87, 82), ("freethrow", "AWY", 13, "Made", 50.0, 4, 87, 83)]
    out = []
    for i, (t, team, p, res, clock, per, h, a) in enumerate(rows):
        h -= broken and i >= 10
        sub = res if t == "substitution" else "1 of 2" if t == "freethrow" and i == 12 else "2 of 2" if t == "freethrow" else None
        out.append({"game": gid, "action": i + 1, "order_no": i + 1, "period": per, "clock": clock, "team": team, "player": p,
                    "action_type": t, "sub_type": sub, "result": None if t == "substitution" else res,
                    "assist_player": 12 if i == 5 else None, "score_home": h, "score_away": a})
    return out


g = walk(game(), {"HOM": set(HOME), "AWY": set(AWAY)}, "HOM")
pl = {p: x for (t, p), x in g["players"].items()}
checks["clutch time"] = g["ds"] == 2500 and pl[5]["ds"] == 500 and pl[6]["ds"] == 2000 and pl[1]["ds"] == pl[11]["ds"] == 2500
checks["clutch points"] = g["teams"] == {"HOM": {"pts": 5, "opp": 4}, "AWY": {"pts": 4, "opp": 5}} and g["credit"] == {"HOM": 5, "AWY": 4}
checks["plays on the score before"] = (pl[11]["fga"], pl[11]["fg3m"], pl[12]["ast"], pl[13]["fta"], pl[13]["ftm"], pl[2]["pts"], pl[1]["tov"], pl[1]["fga"]) \
    == (1, 1, 1, 1, 1, 3, 1, 0)
checks["+/- on the floor"] = (pl[1]["pm"], pl[5]["pm"], pl[6]["pm"], pl[14]["pm"]) == (1, -3, 4, -1)
checks["whole game on the floor"] = g["on"][("HOM", 5)] == 26300 and g["on"][("HOM", 6)] == 2500 and g["on"][("AWY", 11)] == 28800

# the fixture league: clutch splits from its shot charts, written and checked against the rest of its site
teams, players, games, lines = site_fixture.make(random.Random(7))
direct = tempfile.mkdtemp()
site_fixture.stints(games, lines)
write_site(direct, "2026-27", "2026-27", "2026-10-26T06:00:00Z", teams, players, games, lines)
shots = site_fixture.spots(random.Random(13), games, lines)
write_shots(direct, teams, shots)
write_clutch(direct, teams, site_fixture.clutch_games(games, lines, shots))
check_clutch(direct)
cl = json.load(open(os.path.join(direct, "clutch.json")))
checks["fixture has clutch games"] = len(cl["games"]) > 10 and cl["stats"] == STATS and sum(c[0] for c in cl["teams"].values()) == 2 * len(cl["games"])


def tampered(change):
    bad = json.loads(json.dumps(cl))
    change(bad)
    json.dump(bad, open(os.path.join(direct, "clutch.json"), "w"))
    try:
        check_clutch(direct)
        return False
    except ValueError:
        return True
    finally:
        json.dump(cl, open(os.path.join(direct, "clutch.json"), "w"))


gid, code = next((k, t) for k, v in cl["games"].items() for t in v if t != "ds" and v[t][2])
pid = next(iter(cl["players"]))
checks["a club's record must be its results"] = tampered(lambda c: c["teams"][code].__setitem__(1, c["teams"][code][1] + 1))
checks["a game's shots must be its shot chart's"] = tampered(lambda c: c["games"][gid][code].__setitem__(2, c["games"][gid][code][2] + 1))
checks["players must add up to the games"] = tampered(lambda c: c["players"][pid].__setitem__(3, c["players"][pid][3] + 1))

# the warehouse: the game above, and the same game with a three that moves the score by two, which is left out
wh, read = tempfile.mkdtemp(), tempfile.mkdtemp()
box = [{"game": gid_, "team": t, "player": p, "starter": p <= 5 or p >= 11, "seconds": 2880.0,
        **{k: 9 for k in ("pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "ast", "tov")}}
       for gid_ in ("0022600001", "0022600002") for t, ps in (("HOM", HOME + [6]), ("AWY", AWAY)) for p in ps]
tables = {"games": [{"game": k, "game_type": "regular", "home": "HOM", "away": "AWY", "home_score": 87, "away_score": 83, "final": True}
                    for k in ("0022600001", "0022600002")],
          "box": box, "events": game() + game("0022600002", broken=True)}
con = duckdb.connect()
for name, rs in tables.items():
    path = os.path.join(wh, name)
    with open(path + ".jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rs)
    con.execute(f"copy (select * from read_json_auto('{path}.jsonl')) to '{path}.parquet' (format parquet)")
results, bad = from_warehouse(wh)
checks["broken game left out"] = [r[0] for r in results] == ["0022600001"] and list(bad) == ["0022600002"] and "from the score" in bad["0022600002"]
checks["warehouse game is the walk"] = results[0][5]["players"] == g["players"] and results[0][5]["ds"] == 2500

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
