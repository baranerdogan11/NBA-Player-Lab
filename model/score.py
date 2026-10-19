"""Score every shot of a season with the xFG model: warehouse/<season>/shots_xfg.parquet, one row per field-goal
attempt with xfg (this shot by this shooter) and xfg_ctx (the same shot by a league-average shooter: the quality of
the shot alone).

The shooter term starts from last season's effects (model/shooter_effects_<season>.parquet, decayed as in training)
and is updated through this season in game order from earlier shots only, exactly as model/xfg.py builds it, so a
player's xFG follows his own record as it accumulates and never sees the shot it scores. Values are unrounded.

usage: python model/score.py [season]
"""
import os
import sys
import duckdb
import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from actions import shots_frame  # noqa: E402
from features import featurize  # noqa: E402

OUT_COLS = ["game", "action", "player", "team", "made", "pts", "xfg", "xfg_ctx"]


def load_events(w):
    """The season's events with each shot's geometry joined, the home teams and the game dates."""
    con = duckdb.connect()
    ev = con.execute(f"""select e.*, s.x, s.y, s.distance, s.area from read_parquet('{w}/events.parquet') e
                         left join read_parquet('{w}/shots.parquet') s using (game, action)""").df()
    games = con.execute(f"select game, home, cast(date as varchar) as date from read_parquet('{w}/games.parquet')").df()
    for c in ("player", "team_id", "possession", "score_home", "score_away"):
        ev[c] = ev[c].astype("Int64")     # DuckDB hands nullable INTEGER columns over as float
    return ev, games


def score(shots, bundle, prior):
    """xfg and xfg_ctx for a frame of shots in game order; prior is last season's effects (player, n, effect)."""
    df = featurize(shots)
    for c, cats in bundle["categories"].items():
        df[c] = pd.Categorical(df[c].astype(str), categories=cats)
    ctx = bundle["context_model"].predict_proba(df[bundle["context_features"]])[:, 1]
    if "shooter" not in bundle["features"]:
        return ctx, ctx
    k, decay = bundle["k_shrink"], bundle["prior_decay"]
    p = prior.set_index("player")
    acc = {q: float(r.effect) * (float(r.n) + k) * decay for q, r in p.iterrows()}
    n = {q: float(r.n) * decay for q, r in p.iterrows()}
    shooter = np.zeros(len(df))
    for i, (q, r) in enumerate(zip(df.player.values, df.made.values - ctx)):
        shooter[i] = acc.get(q, 0.0) / (n.get(q, 0.0) + k)
        acc[q] = acc.get(q, 0.0) + r
        n[q] = n.get(q, 0.0) + 1
    xfg = bundle["model"].predict_proba(df.assign(shooter=shooter)[bundle["features"]])[:, 1]
    return xfg, ctx


def main(season, w=None):
    w = w or os.path.join(ROOT, "warehouse", season)
    out_path = os.path.join(w, "shots_xfg.parquet")
    bundle = joblib.load(os.path.join(HERE, "xfg_model.joblib"))
    ev, games = load_events(w)
    shots = shots_frame(ev, dict(zip(games.game, games.home))) if len(ev) else pd.DataFrame()
    if shots.empty:
        pd.DataFrame({c: [] for c in OUT_COLS}).to_parquet(out_path, index=False)
        print(f"{season}: no shots yet; wrote an empty shots_xfg.parquet")
        return
    shots["date"] = shots.game.map(dict(zip(games.game, games.date)))
    shots = shots.sort_values(["date", "game", "order_no"], kind="stable").reset_index(drop=True)
    prior_path = os.path.join(HERE, f"shooter_effects_{bundle['trained_on']}.parquet")
    prior = pd.read_parquet(prior_path) if os.path.exists(prior_path) else pd.DataFrame({"player": [], "n": [], "effect": []})
    shots["xfg"], shots["xfg_ctx"] = score(shots, bundle, prior)
    shots[OUT_COLS].to_parquet(out_path, index=False)
    print(f"{season}: scored {len(shots)} shots; mean xFG {shots.xfg.mean():.3f}, context {shots.xfg_ctx.mean():.3f}, actual {shots.made.mean():.3f}")


if __name__ == "__main__":
    from season import season
    main(season())
