"""xFG checks: possession context from a hand-written stretch of play-by-play, feature construction, and the committed
model (it loads, its features match model/features.py, its probabilities are sane and ordered).

usage: python tests/test_xfg.py
"""
import json
import os
import sys
import joblib
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "model"))
from actions import clock_sec, shots_from_actions  # noqa: E402
from features import FEATURES, featurize  # noqa: E402

H, A = "1610612760", "1610612745"
n = iter(range(1, 1000))


def act(t, team, clock, pos, sub="", made=None, x=None, y=None, dist=None, area="", desc="", q="", sh=0, sa=0, period=1):
    k = next(n)
    return {"actionNumber": k, "orderNumber": k * 10000, "actionType": t, "subType": sub, "teamId": team, "personId": "7" if team else "0",
            "period": period, "clock": f"PT{clock // 60:02d}M{clock % 60:02d}.00S", "possession": pos, "isFieldGoal": 1 if t in ("2pt", "3pt") else 0,
            "shotResult": made, "xLegacy": x, "yLegacy": y, "shotDistance": dist, "area": area, "descriptor": desc, "qualifiers": q,
            "scoreHome": sh, "scoreAway": sa}


game = [
    act("period", "", 720, 0, "start"),
    act("jumpball", H, 718, H, "recovered"),
    act("3pt", H, 700, H, "Jump Shot", "Missed", 0, 250, 25, "Above the Break 3", "pullup"),           # 20 s into the period
    act("rebound", A, 698, A, "defensive"),
    act("2pt", A, 690, A, "Layup", "Made", 0, 5, 1, "Restricted Area", "driving", "pointsinthepaint", 0, 2),   # 8 s after dreb
    act("substitution", H, 690, A, "out"),
    act("2pt", H, 676, H, "Jump Shot", "Missed", 100, 100, 14, "Mid-Range", "", "", 0, 2),             # 14 s after the make
    act("rebound", H, 674, H, "offensive"),
    act("2pt", H, 673, H, "Layup", "Made", 0, 2, 0, "Restricted Area", "putback", "2ndchance", 2, 2),  # 1 s after oreb
    act("turnover", A, 660, A, "bad pass"),
    act("steal", H, 660, H),
    act("2pt", H, 655, H, "DUNK", "Made", 0, 0, 0, "Restricted Area", "running", "fastbreak, fromturnover", 4, 2),  # 5 s after the steal
]
shots = pd.DataFrame(shots_from_actions(game, "0022600001"))
shots["home_team"] = H
f = featurize(shots)
model = joblib.load(os.path.join(ROOT, "model", "xfg_model.joblib"))
card = json.load(open(os.path.join(ROOT, "model", "model_card.json")))
p = model["context_model"].predict_proba(f[model["context_features"]])[:, 1]

checks = {
    "clock parse": clock_sec("PT07M42.50S") == 462.5 and clock_sec(None) is None,
    "one row per field-goal attempt": len(shots) == 5,
    "possession starts": list(shots.poss_start) == ["period", "dreb", "make", "oreb", "steal"],
    "possession seconds": list(shots.poss_sec) == [20.0, 8.0, 14.0, 1.0, 5.0],
    "margin is before the shot": list(f.margin) == [0, 0, -2, -2, 0],
    "home flag": list(f.home) == [1, 0, 1, 1, 1],
    "qualifiers": list(f.second_chance) == [0, 0, 0, 1, 0] and list(f.fastbreak) == [0, 0, 0, 0, 1],
    "moves": list(f.move.astype(str)) == ["pullup", "driving", "none", "putback", "running"],
    "committed model uses these features": model["context_features"] == FEATURES and model["features"][:len(FEATURES)] == FEATURES,
    "probabilities in (0, 1)": bool(np.all((p > 0) & (p < 1))),
    "a transition dunk beats a putback, which beats a pullup three": p[4] > p[3] > 0.5 > p[0],
    "card matches the model": card["training_seasons"] == model["training_seasons"] and card["features"] == model["features"],
    "calibrated on held-out games (every decile within 2 points)": all(abs(c["pred"] - c["actual"]) <= 0.02 for c in card["calibration_test"]),
    "beats the distance baseline": card["metrics_test"][card["chosen"]]["logloss"] < card["metrics_test"]["distance_bands"]["logloss"],
}
for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
if not all(checks.values()):
    print(shots[["poss_start", "poss_sec"]], f[["margin", "home", "move"]], p)
sys.exit(0 if all(checks.values()) else 1)
