"""percentiles.py: each ranked player's counts are the group-mates he is ahead of (fewer turnovers counts as ahead), they
turn back into profiles.py's percentiles, and the gate refuses a file profiles.parquet does not give again or a player
leaders.json does not show with the same games and seconds.
usage: python tests/test_percentiles.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import percentiles  # noqa: E402
import profiles  # noqa: E402

rng = np.random.default_rng(3)
rows = []
for g, n in (("G", 25), ("F", 22), ("C", 8)):                  # the centres' pool is below MIN_POOL: no percentiles
    for i in range(n):
        r = {k: float(i) for k in profiles.ROLE + profiles.EFFICIENCY}
        rows.append({"player": int(f"{ord(g)}{i:02d}"), "team": "BOS", "gp": 10, "min": 300.0, "group": g, **r})
rows[3]["onoff"] = np.nan                                        # no on/off: unknown, and out of the pool
rows.append({**rows[0], "player": 99901, "gp": 2})              # below the games floor
rows.append({**rows[0], "player": 99902, "min": 10 * 11.9})     # below the minutes floor
prof = pd.DataFrame(rows)
prof["eligible"] = (prof.gp >= profiles.MIN_GAMES) & (prof["min"] / prof.gp >= profiles.MIN_MPG)
for k in profiles.ROLE + profiles.EFFICIENCY:                    # the percentiles as profiles.profiles() stores them
    prof[f"pctl_{k}"] = np.nan
    for g, m in prof[prof.eligible].groupby("group"):
        if len(m) >= profiles.MIN_POOL:
            pool = m[k].to_numpy(dtype=float)
            prof.loc[m.index, f"pctl_{k}"] = [profiles.percentile(pool, v, k in profiles.LOWER_IS_BETTER) for v in pool]

doc = percentiles.document(prof)
P, K = doc["players"], doc["keys"]
assert set(P) == {str(r["player"]) for r in rows[:47]}, sorted(P)        # guards and forwards only
assert doc["groups"]["G"][K.index("usg")] == 25 and doc["groups"]["G"][K.index("onoff")] == 24
g5 = P["7105"][1]
assert g5[K.index("usg")] == 5 and g5[K.index("tov_pct")] == 19, g5       # ahead of 5 by usage; 19 turn it over more
assert P["7103"][1][K.index("onoff")] is None and P["7104"][1][K.index("onoff")] == 3
assert P["7124"][1][K.index("ts")] == 24 and P["7000"][1][K.index("ts")] == 0

leaders = {"players": [{"pid": str(r["player"]), "gp": r["gp"], "sec": round(r["min"] * 60)} for r in rows]}
percentiles.check(doc, prof, leaders)


def refused(d, p=prof, ld=leaders):
    try:
        percentiles.check(d, p, ld)
    except SystemExit:
        return True
    return False


bad = {**P, "7105": ["G", [6] + g5[1:]]}
assert refused({**doc, "players": bad})                                     # not what the profiles give
assert refused(doc, p=prof.assign(pctl_ts=prof.pctl_ts + 0.5))             # counts and stored percentiles disagree
off = {"players": [dict(p, sec=p["sec"] + 1) if p["pid"] == "7103" else p for p in leaders["players"]]}
assert refused(doc, ld=off)                                                 # seconds differ from the site
assert refused(doc, ld={"players": [p for p in leaders["players"] if p["pid"] != "7101"]})  # not on the site
print("percentiles: ok")
