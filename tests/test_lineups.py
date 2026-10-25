"""Lineup reconstruction checks on two real 2025-26 games from the play-by-play archive (one went to double overtime, both stored in the warehouse events layout)
and on hand-written substitutions: five per club at every action, stint points add up to the final score, stint
seconds to the game length, and on + off adds up to the club's totals.

usage: python tests/test_lineups.py
"""
import glob
import gzip
import json
import os
import sys
import tempfile
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lineups  # noqa: E402
from site_data import write_lineups  # noqa: E402

checks, rows = {}, []
for path in sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "events_*.json.gz"))):
    acts = json.load(gzip.open(path, "rt"))
    g = acts[0]["game"]
    starters = lineups.infer_starters(acts)
    sts, problems = lineups.stints(acts, starters)
    last = lineups.ordered(acts)[-1]
    periods = max(int(a["period"]) for a in acts)
    checks[f"{g}: five starters each"] = sorted(len(v) for v in starters.values()) == [5, 5]
    checks[f"{g}: no problems"] = problems == []
    checks[f"{g}: five on the floor in every stint"] = all(len(s["players"]) == 5 and len(s["opp_players"]) == 5 for s in sts)
    checks[f"{g}: points add up to the final"] = sorted(sum(s["pts"] for s in sts if s["team"] == c) for c in starters) == sorted([last["score_home"], last["score_away"]])
    checks[f"{g}: seconds add up to the game"] = abs(sum(s["sec"] for s in sts) / 2 - (2880 + 300 * (periods - 4))) < 0.5
    checks[f"{g}: each side's counts mirror the other's"] = all(a["pts"] == b["opp_pts"] and a["fga"] == b["opp_fga"] for a, b in zip(sts[0::2], sts[1::2]))
    sec = lineups.seconds_on(sts)
    checks[f"{g}: 5 x game length of floor time per club"] = all(abs(sum(v for (c, _), v in sec.items() if c == t) - 5 * sum(s["sec"] for s in sts) / 2) < 1 for t in starters)
    rows += [{"game": g, **s} for s in sts]

st = pd.DataFrame(rows)
lu, oo = lineups.season_tables(st)
team = st.groupby("team")[["sec", "pts", "opp_pts"]].sum()
for k in ("sec", "pts", "opp_pts"):
    checks[f"on + off = club total ({k})"] = bool(((oo[k] + oo[f"off_{k}"]) - team.loc[oo.team, k].values).abs().max() < 1e-6)
checks["lineup seconds = club seconds x 1"] = bool((lu.groupby("team").sec.sum() - team.sec).abs().max() < 1e-6)
checks["on/off is net on minus net off"] = bool(((oo.net - oo.off_net) - oo.onoff).abs().max() < 1e-9)

# the whole run on a scratch warehouse built from the two games: events, box (starters and seconds) and games
w = tempfile.mkdtemp()
ev = pd.concat([pd.DataFrame(json.load(gzip.open(p, "rt"))) for p in sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "events_*.json.gz")))])
box, games = [], []
for g, d in ev.groupby("game"):
    acts = d.to_dict("records")
    starters = lineups.infer_starters(acts)
    sts = lineups.stints(acts, starters)[0]
    for (team, player), sec in lineups.seconds_on(sts).items():
        pm = sum(s["pts"] - s["opp_pts"] for s in sts if s["team"] == team and player in s["players"])
        box.append({"game": g, "team": team, "player": player, "starter": player in starters[team], "seconds": sec + 20,   # a scorer's 20 s
                    "plus_minus": pm})
    last = lineups.ordered(acts)[-1]
    games.append({"game": g, "home_score": last["score_home"], "away_score": last["score_away"], "final": True})
ev.to_parquet(os.path.join(w, "events.parquet"))
pd.DataFrame(box).to_parquet(os.path.join(w, "box.parquet"))
pd.DataFrame(games).to_parquet(os.path.join(w, "games.parquet"))
checks["the warehouse run passes its own checks"] = lineups.main("test", w) == []
checks["it writes stints, lineups and onoff"] = all(os.path.exists(os.path.join(w, f"{t}.parquet")) for t in ("stints", "lineups", "onoff"))
pd.DataFrame(box).assign(seconds=lambda b: b.seconds + 100).to_parquet(os.path.join(w, "box.parquet"))
checks["seconds off the box score by over a minute fail the run"] = any("box" in p for p in lineups.main("test", w))
pd.DataFrame(box).assign(plus_minus=lambda b: b.plus_minus + 1).to_parquet(os.path.join(w, "box.parquet"))
checks["a plus-minus off the box score fails the run"] = any("+/-" in p for p in lineups.main("test", w))

# hand-written: a substitution of a player already on the bench is reported, not absorbed
H, A = "HOM", "AWY"


def ev(k, t, sub, team, player, clock):
    return {"game": "x", "action": k, "order_no": k, "period": 1, "clock": clock, "action_type": t, "sub_type": sub, "team": team, "player": player,
            "score_home": 0, "score_away": 0}


acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "substitution", "out", H, 19, 600.0), ev(3, "substitution", "in", H, 18, 600.0)]
_, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
checks["a bad substitution is reported"] = any("subbed out while on the bench" in p for p in problems)

# hand-written: a substitution between two free throws waits for the second, so both count for the five fouled
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "foul", "personal", A, 20, 600.0), ev(3, "freethrow", "1 of 2", H, 10, 600.0),
        ev(4, "substitution", "out", H, 14, 600.0), ev(5, "substitution", "in", H, 15, 600.0), ev(6, "freethrow", "2 of 2", H, 10, 600.0)]
acts[2]["score_home"] = acts[3]["score_home"] = acts[4]["score_home"] = 1
acts[5]["score_home"] = 2
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
first = next(s for s in sts if s["team"] == H)
checks["free throws after a mid-trip substitution count for the five fouled"] = problems == [] and 14 in first["players"] and first["pts"] == 2 and first["fta"] == 2

# hand-written: a substitution logged before the foul (a technical after a timeout) stays put, so the free throw counts
# for the five coming in, as the box score's plus-minus does
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "substitution", "out", H, 14, 600.0), ev(3, "substitution", "in", H, 15, 600.0),
        ev(4, "foul", "technical", A, 20, 600.0), ev(5, "freethrow", "1 of 1", H, 10, 600.0)]
acts[4]["score_home"] = 1
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
last = [s for s in sts if s["team"] == H][-1]
checks["free throws after a foul that follows the substitution count for the five coming in"] = problems == [] and 15 in last["players"] and last["pts"] == 1

# hand-written: a substitution logged after a technical, its free throw still to come, waits for it (NOP at UTA, 23 Oct)
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "foul", "technical", A, 20, 600.0), ev(3, "substitution", "out", H, 14, 600.0),
        ev(4, "substitution", "in", H, 15, 600.0), ev(5, "freethrow", "1 of 1", H, 10, 600.0)]
acts[4]["score_home"] = 1
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
first = next(s for s in sts if s["team"] == H)
checks["a free throw after a technical counts for the five on the floor for it"] = problems == [] and 14 in first["players"] and first["pts"] == 1

# hand-written: free throws keyed in after the period's end go back to their foul (HOU at SAS, 23 Oct)
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "foul", "personal", A, 20, 300.0), ev(3, "substitution", "out", H, 14, 200.0),
        ev(4, "substitution", "in", H, 15, 200.0), ev(5, "period", "end", None, None, 0.0), ev(6, "freethrow", "1 of 1", H, 10, 300.0)]
acts[5]["score_home"] = 1
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
first = next(s for s in sts if s["team"] == H)
checks["free throws keyed in after the period's end count for the five fouled"] = problems == [] and 14 in first["players"] and first["pts"] == 1 and first["sec"] == 520

# hand-written: a free throw logged after a substitution the clock puts later (sub at 2:04, free throw at 2:06) goes first
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "foul", "personal", A, 20, 126.0), ev(3, "substitution", "out", H, 14, 124.0),
        ev(4, "substitution", "in", H, 15, 124.0), ev(5, "freethrow", "1 of 1", H, 10, 126.0)]
acts[4]["score_home"] = 1
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
first = next(s for s in sts if s["team"] == H)
checks["a free throw the clock puts before the substitution counts for the five fouled"] = problems == [] and 14 in first["players"] and first["pts"] == 1

# hand-written: the game's end logged in a period of its own adds no overtime (PHX-GSW, 24 Oct)
acts = [ev(1, "period", "start", None, None, 720.0), ev(2, "period", "end", None, None, 0.0), {**ev(3, "game", "end", None, None, 0.0), "period": 2}]
sts, problems = lineups.stints(acts, {H: set(range(10, 15)), A: set(range(20, 25))})
checks["a game end logged in the next period adds no time"] = problems == [] and sum(s["sec"] for s in sts) / 2 == 720

# the site's JSON: one row per five per game, integers, adding up to the stints
w2 = tempfile.mkdtemp()
teams = [{"code": c} for c in st.team.unique()]
write_lineups(w2, teams, [{**r, "gid": r["game"], "time": r["game"]} for r in st.to_dict("records")])
for c in st.team.unique():
    f = json.load(open(os.path.join(w2, "lineups", f"{c}.json")))
    mine = st[st.team == c]
    checks[f"{c}: lineup JSON points add up"] = sum(r[3] for r in f["rows"]) == mine.pts.sum() and sum(r[4] for r in f["rows"]) == mine.opp_pts.sum()
    checks[f"{c}: lineup JSON tenths of a second add up"] = abs(sum(r[2] for r in f["rows"]) - 10 * mine.sec.sum()) < len(mine)
    checks[f"{c}: one row per five per game"] = len(f["rows"]) == len({(r[0], r[1]) for r in f["rows"]}) and all(len(x) == 5 for x in f["fives"])

for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
sys.exit(0 if all(checks.values()) else 1)
