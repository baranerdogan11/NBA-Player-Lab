"""Feature construction shared by training and nightly scoring. No I/O, no DuckDB.

Every feature is known before the ball leaves the shooter's hand. The feed's made-only annotations (assists,
and-ones, goaltending, the 'pointsinthepaint' qualifier, which is far more often on makes) are left out, and blocks
come as a separate action after the shot, so they never reach a shot row.
"""
import numpy as np
import pandas as pd

NUMERIC = ["dist", "angle", "x", "y", "clock", "period", "margin", "poss_sec"]
BINARY = ["three", "home", "fastbreak", "second_chance", "from_tov"]
CATEG = ["area", "shot_type", "move", "poss_start"]
AREA = ["?", "Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3", "Right Corner 3", "Above the Break 3", "Backcourt"]
SHOT_TYPE = ["?", "Jump Shot", "Layup", "DUNK", "Hook"]
POSS_START = ["?", "period", "make", "dreb", "oreb", "steal", "tov"]
# the descriptor's leading words, in order of precedence (a 'driving floating bank' shot is a floater)
MOVE = ["alley-oop", "putback", "tip", "cutting", "floating", "finger roll", "step back", "fadeaway", "turnaround", "pullup",
        "running", "driving", "reverse", "bank"]
FEATURES = NUMERIC + BINARY + CATEG


def move(descriptor):
    d = descriptor or ""
    return next((m for m in MOVE if m in d), "none")


def featurize(df):
    """Shots from model/actions.py (with the home team's tricode in `home`) -> the model's feature columns, alongside
    the originals."""
    d = df.copy()
    d["x"] = d.x.astype(float)
    d["y"] = d.y.astype(float)
    d["dist"] = d.distance.astype(float).fillna(np.hypot(d.x, d.y) / 10)
    d["angle"] = np.degrees(np.arctan2(d.x.abs(), d.y.clip(lower=1)))
    d["three"] = (d.pts == 3).astype(int)
    d["home"] = (d.team == d["home"]).astype(int)
    sh, sa = pd.to_numeric(d.score_home).astype(float), pd.to_numeric(d.score_away).astype(float)
    own, opp = np.where(d.home == 1, sh, sa), np.where(d.home == 1, sa, sh)
    # the feed reports the score after the play, so a made basket is taken off to get the margin before the shot
    d["margin"] = np.nan_to_num(own) - np.nan_to_num(opp) - d.made.astype(int) * d.pts
    q = d.qualifiers.map(lambda v: set(v) if v is not None and not isinstance(v, float) else set())
    d["fastbreak"] = q.map(lambda v: "fastbreak" in v).astype(int)
    d["second_chance"] = q.map(lambda v: "2ndchance" in v).astype(int)
    d["from_tov"] = q.map(lambda v: "fromturnover" in v).astype(int)
    d["area"] = pd.Categorical(d.area.where(d.area.isin(AREA), "?"), categories=AREA)
    d["shot_type"] = pd.Categorical(d.sub_type.where(d.sub_type.isin(SHOT_TYPE), "?"), categories=SHOT_TYPE)
    d["move"] = pd.Categorical(d.descriptor.map(lambda v: move(v if isinstance(v, str) else "")), categories=["none"] + MOVE)
    d["poss_start"] = pd.Categorical(d.poss_start.fillna("?"), categories=POSS_START)
    d["poss_sec"] = pd.to_numeric(d.poss_sec, errors="coerce")
    d["period"] = d.period.astype(int)
    d["clock"] = pd.to_numeric(d.clock).astype(float)
    d["made"] = d.made.astype(int)
    return d
