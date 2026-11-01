"""Who played when (site_data.rotation): each player's stretches on the floor from the lineup stints, on the game flow's
clock of game time, and the gate that holds them to the box score.
usage: python tests/test_rotation.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from site_data import check_rotation, played, rotation  # noqa: E402

A, B, C, D, E, F = 1, 2, 3, 4, 5, 6
# one club's game: the starters play the first 346 s, F comes in for A until the first quarter's end and stays on
# across it (the five carry over the break, as lineups.py reads the feed), A comes back at a stoppage for no time while
# the other side makes a free throw, F returns at once and plays 100 s more, then A plays the rest of the game
st = [((A, B, C, D, E), 346.0, 8, 6), ((B, C, D, E, F), 374.0, 9, 9), ((B, C, D, E, F), 100.0, 2, 0),
      ((A, B, C, D, E), 0.0, 0, 1), ((B, C, D, E, F), 100.0, 0, 0), ((A, B, C, D, E), 1960.0, 50, 40)]
r = rotation(st)
checks = {
    "back-to-back stints join, across a quarter's end and out and back in at one moment": r["6"] == [[3460, 9200, 2]],
    "a stretch of no time stays when the score moved in it": r["1"] == [[0, 3460, 2], [8200, 8200, -1], [9200, 28800, 10]],
    "a starter who never sat has one stretch": r["2"] == [[0, 28800, 13]],
    "an overtime with no score is the feed's game-end marker": played([[1, 1]] * 4 + [[0, 0]]) == 4
    and played([[1, 1]] * 4 + [[3, 2]]) == 5,
}
# the other club: one five all game
r.update({str(p): [[0, 28800, -13]] for p in (11, 12, 13, 14, 15)})
line = lambda pid, sec, pm: {"pid": str(pid), "sec": sec, "pm": pm}  # noqa: E731
box = {"H": [line(A, 2306, 11), *(line(p, 2880, 13) for p in (B, C, D, E)), line(F, 574, 2), line(7, 0, 0)],
       "V": [line(p, 2880, -13) for p in (11, 12, 13, 14, 15)]}
g = {"gid": "x", "home": "H", "away": "V", "periods": [[1, 1]] * 4, "box": box, "rotation": r}
try:
    check_rotation(g)
    checks["a rotation that adds up to the box score passes"] = True
except ValueError:
    checks["a rotation that adds up to the box score passes"] = False
off = lambda c, i, **k: {**g, "box": {**box, c: [x if j != i else {**x, **k} for j, x in enumerate(box[c])]}}  # noqa: E731
for name, bad in (("seconds a second and more off the box score stop the build", off("H", 5, sec=572)),
                  ("a plus-minus off the box score stops the build", off("H", 0, pm=12)),
                  ("a club with four on the floor stops the build", {**g, "rotation": {**r, "15": [[0, 20000, -13]]}}),
                  ("a player on the floor twice at once stops the build", {**g, "rotation": {**r, "6": [[3460, 9200, 2], [9000, 9100, 0]]}}),
                  ("a rotation naming a player without a box line stops the build", {**g, "rotation": {**r, "99": []}})):
    try:
        check_rotation(bad)
        checks[name] = False
    except ValueError:
        checks[name] = True
checks["box seconds that drop the tenths still pass"] = True
try:
    check_rotation(off("H", 5, sec=573))
except ValueError:
    checks["box seconds that drop the tenths still pass"] = False

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
