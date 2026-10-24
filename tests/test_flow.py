"""A game's flow (site_data.game_flow): the play-by-play score at every change, on a clock of game time, and the gate
that holds it to the box score's periods and final.
usage: python tests/test_flow.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from site_data import check_flow, game_flow, period_start  # noqa: E402

# tip-off, a basket, a rebound, a three at the first buzzer, two free throws in the second quarter, the fourth's end and
# overtime's last basket with 0.6 seconds left
ev = [(1, 720.0, 0, 0), (1, 700.5, 2, 0), (1, 690.0, 2, 0), (1, 0.0, 2, 3), (2, 480.0, 3, 3), (2, 480.0, 4, 3),
      (4, 0.0, 4, 3), (5, 0.6, 4, 6)]
f = game_flow(ev)
g = {"gid": "x", "hs": 4, "as": 6, "periods": [[2, 3], [2, 0], [0, 0], [0, 0], [0, 3]], "flow": f}
checks = {
    "one point per change of score": f == [[195, 2, 0], [7200, 2, 3], [9600, 3, 3], [9600, 4, 3], [31794, 4, 6]],
    "quarters are 12 minutes, overtimes 5": [period_start(p) for p in (1, 2, 5, 6, 7)] == [0, 7200, 28800, 31800, 34800],
}
try:
    check_flow(g)
    checks["a flow through every period's score and the final passes"] = True
except ValueError:
    checks["a flow through every period's score and the final passes"] = False
# HOU@SAS 23 Oct 2026: two free throws at 1:45 of the first quarter logged after its buzzer
late = game_flow([(1, 115.0, 24, 28), (1, 92.0, 24, 30), (1, 53.4, 27, 32), (1, 0.0, 27, 32), (1, 105.0, 24, 29),
                  (1, 105.0, 24, 30), (2, 720.0, 27, 32)])
checks["free throws logged after the buzzer go back to their clock"] = late == [
    [6050, 24, 28], [6150, 24, 29], [6150, 24, 30], [6666, 27, 32]]
for name, bad in (("a flow off the final stops the build", {"hs": 5}),
                  ("a flow off a period's score stops the build", {"periods": [[2, 2], [2, 1], [0, 0], [0, 0], [0, 3]]})):
    try:
        check_flow({**g, **bad})
        checks[name] = False
    except ValueError:
        checks[name] = True

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
