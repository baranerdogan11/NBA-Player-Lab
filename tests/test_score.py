"""Scoring checks on a scratch warehouse holding one real 2024-25 game (a season the model never saw): one row per
shot, probabilities in (0, 1), and no shot's xFG depends on its own result.

usage: python tests/test_score.py
"""
import gzip
import json
import os
import sys
import tempfile
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "model"))
import score  # noqa: E402

fx = json.load(gzip.open(os.path.join(ROOT, "tests", "fixtures", "warehouse_0022400101.json.gz"), "rt"))
events, shots, games = (pd.DataFrame(fx[k]) for k in ("events", "shots", "games"))


def run(ev):
    w = tempfile.mkdtemp()
    ev.to_parquet(os.path.join(w, "events.parquet"))
    shots.to_parquet(os.path.join(w, "shots.parquet"))
    games.to_parquet(os.path.join(w, "games.parquet"))
    score.main("test", w)
    return pd.read_parquet(os.path.join(w, "shots_xfg.parquet")).set_index("action")


out = run(events)
# the same game with its last made field goal turned into a miss (and the score after it corrected)
fg = events[events.action_type.isin(["2pt", "3pt"]) & (events.result == "Made")].sort_values("order_no").iloc[-1]
flipped = events.copy()
side = "score_home" if fg.team == games.home.iloc[0] else "score_away"
later = flipped.order_no >= fg.order_no
flipped.loc[later, side] -= 3 if fg.action_type == "3pt" else 2
flipped.loc[flipped.action == fg.action, "result"] = "Missed"
out2 = run(flipped)

checks = {
    "one row per field-goal attempt": len(out) == len(shots) and out.index.is_unique,
    "probabilities in (0, 1)": bool(((out.xfg > 0) & (out.xfg < 1) & (out.xfg_ctx > 0) & (out.xfg_ctx < 1)).all()),
    "game-level xFG near the actual rate": abs(out.xfg.mean() - out.made.mean()) < 0.06,
    "a shot's xFG does not see its own result": np.isclose(out.loc[fg.action, "xfg"], out2.loc[fg.action, "xfg"])
    and np.isclose(out.loc[fg.action, "xfg_ctx"], out2.loc[fg.action, "xfg_ctx"]),
    "earlier shots are untouched by a later result": np.allclose(out.xfg[out.index < fg.action], out2.xfg[out2.index < fg.action]),
}
for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
sys.exit(0 if all(checks.values()) else 1)
