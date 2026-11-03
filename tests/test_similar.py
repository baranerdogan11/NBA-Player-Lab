"""similar.py: comps are the nearest players of the same position group by the role rates alone, the floors keep
part-timers out on both sides, and the gate refuses a file that profiles.parquet does not give again or that names a
player leaders.json does not show with the same games and seconds.
usage: python tests/test_similar.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import similar  # noqa: E402
from profiles import ROLE  # noqa: E402

rng = np.random.default_rng(5)
rows = []
for g, centre in (("G", 0.0), ("F", 5.0), ("C", 10.0)):
    for i in range(8):
        r = {k: centre + i + rng.normal(0, 0.01) for k in ROLE}
        rows.append({"player": int(f"{ord(g)}{i:02d}"), "group": g, "gp": 10, "min": 300.0, **r,
                     "ts": rng.random(), "pps": rng.random(), "onoff": rng.normal()})
rows.append({**rows[0], "player": 99901, "gp": 4})                  # below the games floor
rows.append({**rows[0], "player": 99902, "min": 10 * 14.9})         # below the minutes floor
rows.append({**rows[0], "player": 99903, "group": None})            # no group
prof = pd.DataFrame(rows)
doc = similar.document(prof)
P = doc["players"]

assert set(P) == {str(r["player"]) for r in rows[:24]}, sorted(P)
assert not any(q.startswith("999") for cs in P.values() for q in cs)
# nearest first, within the group: a guard's comps are the guards next to him on the role scale
assert P["7100"] == ["7101", "7102", "7103"], P["7100"]
assert P["7104"][:2] in (["7103", "7105"], ["7105", "7103"]), P["7104"]
assert all(q[:2] == p[:2] for p, cs in P.items() for q in cs)
# efficiency plays no part
assert similar.document(prof.assign(ts=1 - prof.ts, pps=0.0, onoff=-prof.onoff)) == doc
# a group with too few others is filled from the rest of the league
small = prof[~((prof.group == "C") & (prof.player % 100 > 1))]
sp = similar.document(small)["players"]
assert sp["6700"][0] == "6701" and len(sp["6700"]) == 3 and sp["6700"][1][:2] != "67", sp["6700"]

leaders = {"players": [{"pid": str(r["player"]), "gp": r["gp"], "sec": round(r["min"] * 60)} for r in rows]}
similar.check(doc, prof, leaders)


def refused(d, p=prof, ld=leaders):
    try:
        similar.check(d, p, ld)
    except SystemExit:
        return True
    return False


assert refused({**doc, "players": {**P, "7100": ["7101", "7102", "7104"]}})          # not what the profiles give
assert refused({**doc, "players": {**P, "7100": ["7101", "7102", "99901"]}})         # below the floor
off = {"players": [dict(p, sec=p["sec"] + 1) if p["pid"] == "7103" else p for p in leaders["players"]]}
assert refused(doc, ld=off)                                                           # seconds differ from the site
assert refused(doc, ld={"players": [p for p in leaders["players"] if p["pid"] != "7101"]})  # not on the site
print("similar: ok")
