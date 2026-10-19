"""Profile checks: the rate formulas on a hand-computed game, position groups from starts and from role, and
percentiles within a group.

usage: python tests/test_profiles.py
"""
import os
import sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import profiles  # noqa: E402

Z = {k: 0 for k in profiles.STATS}


def line(game, team, pid, sec, starter=False, position="", **stats):
    return {"game": game, "teamId": team, "personId": pid, "seconds": sec, "starter": starter, "position": position, **{**Z, **stats}}


# one game, five players a side playing 48 minutes; player A1 has the numbers worked by hand below
box = [line(1, "A", "A1", 2880, True, "PG", points=30, fieldGoalsMade=11, fieldGoalsAttempted=20, threePointersMade=4, threePointersAttempted=8,
            freeThrowsMade=4, freeThrowsAttempted=5, reboundsOffensive=1, reboundsDefensive=5, assists=10, turnovers=3, steals=2, blocks=1)]
box += [line(1, "A", f"A{i}", 2880, True, "C" if i == 5 else "SF", fieldGoalsMade=5, fieldGoalsAttempted=10, threePointersAttempted=2, freeThrowsAttempted=2,
             reboundsOffensive=2, reboundsDefensive=5, turnovers=2, points=10) for i in range(2, 6)]
box += [line(1, "B", f"B{i}", 2880, True, "G", fieldGoalsMade=4, fieldGoalsAttempted=10, threePointersAttempted=4, freeThrowsAttempted=2,
             reboundsOffensive=1, reboundsDefensive=6, turnovers=3, points=9) for i in range(1, 6)]
box = pd.DataFrame(box)
r = profiles.rates(profiles.season_lines(box)).set_index("personId")
a = r.loc["A1"]
# team A: FGA 60, FTA 13, TOV 11, FGM 31, OREB 9, DREB 25; team B: FGA 50, FTA 10, TOV 15, OREB 5, DREB 30, 3PA 20
checks = {
    "usage": np.isclose(a.usg, 100 * (20 + 0.44 * 5 + 3) / (60 + 0.44 * 13 + 11)),
    "assist %": np.isclose(a.ast_pct, 100 * 10 / (31 - 11)),
    "turnover %": np.isclose(a.tov_pct, 100 * 3 / (20 + 0.44 * 5 + 3)),
    "offensive rebound %": np.isclose(a.oreb_pct, 100 * 1 / (9 + 30)),
    "defensive rebound %": np.isclose(a.dreb_pct, 100 * 5 / (25 + 5)),
    "steal %": np.isclose(a.stl_pct, 100 * 2 / (50 - 5 + 15 + 0.44 * 10)),
    "block %": np.isclose(a.blk_pct, 100 * 1 / (50 - 20)),
    "true shooting": np.isclose(a.ts, 30 / (2 * (20 + 0.44 * 5))),
    "rates": np.isclose(a.fg3a_rate, 0.4) and np.isclose(a.fta_rate, 0.25) and np.isclose(a.pps, 26 / 20),
    "team usage adds up to 100": np.isclose(r.loc[[f"A{i}" for i in range(1, 6)]].usg.sum(), 100),
}

# groups and percentiles: 30 guards, 30 forwards, 30 centres over 3 games, starters with positions plus one bench player
rng = np.random.default_rng(1)
rows = []
for g in range(3):
    for k, (pos, reb, ast, blk, three) in enumerate([("PG", 3, 8, 0, 6), ("SF", 6, 3, 1, 4), ("C", 11, 2, 3, 0)]):
        for i in range(30):
            pid = f"{pos}{i}"
            fga = 10 + i % 7
            rows.append(line(g, f"T{i % 10}", pid, 1800, True, pos, fieldGoalsAttempted=fga, fieldGoalsMade=fga // 2, threePointersAttempted=min(three, fga),
                             freeThrowsAttempted=2, points=fga + i % 5, reboundsOffensive=reb // 3, reboundsDefensive=reb - reb // 3,
                             assists=ast, turnovers=1 + i % 3, blocks=blk))
    rows.append(line(g, "T0", "bench_big", 1500, False, "", fieldGoalsAttempted=8, fieldGoalsMade=5, reboundsOffensive=4, reboundsDefensive=8, blocks=3, points=11, turnovers=1))
big = pd.DataFrame(rows)
p = profiles.profiles(big).set_index("personId")
checks["starters take the group they started at"] = p.loc["PG0", "group"] == "G" and p.loc["SF3", "group"] == "F" and p.loc["C7", "group_source"] == "started"
checks["a bench player is placed by role"] = p.loc["bench_big", "group"] == "C" and p.loc["bench_big", "group_source"] == "role"
cs = p[(p.group == "C") & p.eligible]
checks["percentiles within the group, 0 to 100"] = cs.pctl_ts.between(0, 100).all() and p[p.group == "G"].pctl_ts.notna().all()
best, worst = cs.ts.idxmax(), cs.ts.idxmin()
checks["best true shooting ranks top, worst bottom"] = cs.loc[best, "pctl_ts"] > 90 and cs.loc[worst, "pctl_ts"] == 0
checks["fewer turnovers rank higher"] = cs.loc[cs.tov_pct.idxmin(), "pctl_tov_pct"] > cs.loc[cs.tov_pct.idxmax(), "pctl_tov_pct"]
small = profiles.profiles(big[big.personId.str.startswith(("PG", "SF")) | (big.personId == "C0")]).set_index("personId")
checks["no ranking for a group under the minimum pool"] = np.isnan(small.loc["C0", "pctl_ts"]) and not np.isnan(small.loc["PG0", "pctl_ts"])

for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
sys.exit(0 if all(checks.values()) else 1)
