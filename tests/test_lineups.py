"""Lineup reconstruction checks on two real 2025-26 games from the play-by-play archive (one went to double overtime)
and on hand-written substitutions: five per club at every action, stint points add up to the final score, stint
seconds to the game length, and on + off adds up to the club's totals.

usage: python tests/test_lineups.py
"""
import glob
import gzip
import json
import os
import sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lineups  # noqa: E402

checks, rows = {}, []
for path in sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "pbp_*.json.gz"))):
    acts = json.load(gzip.open(path, "rt"))
    g = acts[0]["gameId"]
    starters = lineups.infer_starters(acts)
    sts, problems = lineups.stints(acts, starters)
    last = [a for a in lineups.ordered(acts) if a["scoreHome"] != ""][-1]
    periods = max(int(a["period"]) for a in acts)
    checks[f"{g}: five starters each"] = sorted(len(v) for v in starters.values()) == [5, 5]
    checks[f"{g}: no problems"] = problems == []
    checks[f"{g}: five on the floor in every stint"] = all(len(s["players"]) == 5 and len(s["opp_players"]) == 5 for s in sts)
    checks[f"{g}: points add up to the final"] = sorted(sum(s["pts"] for s in sts if s["club"] == c) for c in starters) == sorted([int(last["scoreHome"]), int(last["scoreAway"])])
    checks[f"{g}: seconds add up to the game"] = abs(sum(s["sec"] for s in sts) / 2 - (2880 + 300 * (periods - 4))) < 0.5
    checks[f"{g}: each side's counts mirror the other's"] = all(a["pts"] == b["opp_pts"] and a["fga"] == b["opp_fga"] for a, b in zip(sts[0::2], sts[1::2]))
    sec = lineups.seconds_on(sts)
    checks[f"{g}: 5 x game length of floor time per club"] = all(abs(sum(v for (c, _), v in sec.items() if c == t) - 5 * sum(s["sec"] for s in sts) / 2) < 1 for t in starters)
    rows += [{"game": g, **s} for s in sts]

st = pd.DataFrame(rows)
lu, oo = lineups.season_tables(st)
team = st.groupby("club")[["sec", "pts", "opp_pts"]].sum()
for k in ("sec", "pts", "opp_pts"):
    checks[f"on + off = club total ({k})"] = bool(((oo[k] + oo[f"off_{k}"]) - team.loc[oo.club, k].values).abs().max() < 1e-6)
checks["lineup seconds = club seconds x 1"] = bool((lu.groupby("club").sec.sum() - team.sec).abs().max() < 1e-6)
checks["on/off is net on minus net off"] = bool(((oo.net - oo.off_net) - oo.onoff).abs().max() < 1e-9)

# hand-written: a substitution of a player already on the bench is reported, not absorbed
H, A = "1", "2"
five = lambda t, base: {f"{t}{i}" for i in range(base, base + 5)}  # noqa: E731
acts = [{"actionNumber": 1, "orderNumber": 1, "period": 1, "clock": "PT12M00.00S", "actionType": "period", "subType": "start", "personId": "0", "teamId": "", "scoreHome": "0", "scoreAway": "0"},
        {"actionNumber": 2, "orderNumber": 2, "period": 1, "clock": "PT10M00.00S", "actionType": "substitution", "subType": "out", "personId": "19", "teamId": H, "scoreHome": "0", "scoreAway": "0"},
        {"actionNumber": 3, "orderNumber": 3, "period": 1, "clock": "PT10M00.00S", "actionType": "substitution", "subType": "in", "personId": "18", "teamId": H, "scoreHome": "0", "scoreAway": "0"}]
_, problems = lineups.stints(acts, {H: five("1", 0), A: five("2", 0)})
checks["a bad substitution is reported"] = any("subbed out while on the bench" in p for p in problems)

for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
sys.exit(0 if all(checks.values()) else 1)
