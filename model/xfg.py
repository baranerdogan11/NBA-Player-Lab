"""Expected field-goal model (xFG): the probability a shot goes in given where, how and when it was taken.

Trained on past seasons' play-by-play from the archive (model/training.json lists them, oldest first; model/archive.py
builds their shots). The base model uses shot context only: location, distance, angle, shot value, shot type and move
(driving, pullup, step back...), clock, game state, how the possession began and how long it has run. Shooter quality
enters as a separate, leak-free feature: each shooter's shrunk residual (made minus xFG) over his earlier shots only,
decayed at each new season. Validation is by time: the last 25% of the latest season's games (by date, so the
playoffs fall in it) are held out and everything before them trains. Outputs the fitted model, a model card with
metrics and calibration, and per-shooter effects as of the end of the latest season, used as priors next season.

usage: python model/xfg.py                  # seasons from model/training.json
       python model/xfg.py 2024-25 2025-26  # explicit list, oldest first
"""
import datetime
import json
import os
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import CATEG, FEATURES, featurize  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "model")
CACHE = os.path.join(ROOT, "cache", "archive")
SEASONS = [a for a in sys.argv[1:] if a[:4].isdigit()] or json.load(open(os.path.join(OUT, "training.json")))["seasons"]
SEASON = SEASONS[-1]   # the latest training season: validation, shooter effects and the model card's trained_on
K_SHRINK = 300.0       # attempts at which a shooter's own record gets half the weight of the league prior
PRIOR_DECAY = 0.6      # a shooter's record carried into a new season keeps this share of its weight
SEED = 7


def load_seasons(seasons):
    """Shots of several seasons in game order; game ids are unique across seasons (the season is in the id)."""
    parts = []
    for s in seasons:
        path = os.path.join(CACHE, f"shots_{s}.parquet")
        if not os.path.exists(path):
            raise SystemExit(f"{path} missing: run python model/archive.py {s}")
        parts.append(pd.read_parquet(path))
    return pd.concat(parts, ignore_index=True).sort_values(["date", "game", "order"], kind="stable").reset_index(drop=True)


def make_model(feats, seed=SEED):
    return HistGradientBoostingClassifier(learning_rate=0.05, max_iter=800, max_leaf_nodes=31, min_samples_leaf=80, l2_regularization=1.0,
                                          early_stopping=True, validation_fraction=0.1, n_iter_no_change=40,
                                          categorical_features=[feats.index(c) for c in CATEG if c in feats], random_state=seed)


def shooter_effects(df, resid, k=K_SHRINK, decay=PRIOR_DECAY):
    """Sequential shrunk residual per shooter, from shots before each shot only (leak-free); decayed at each new season."""
    prior = np.zeros(len(df))
    acc, n = {}, {}
    seasons = df.season.values
    for i, (p, r) in enumerate(zip(df.player.values, resid)):
        if i and seasons[i] != seasons[i - 1]:
            acc = {q: v * decay for q, v in acc.items()}
            n = {q: v * decay for q, v in n.items()}
        prior[i] = acc.get(p, 0.0) / (n.get(p, 0) + k)
        acc[p] = acc.get(p, 0.0) + r
        n[p] = n.get(p, 0) + 1
    final = pd.DataFrame({"player": list(acc), "n": [round(float(n[p]), 1) for p in acc], "effect": [acc[p] / (n[p] + k) for p in acc]})
    return prior, final


def metrics(y, p):
    return {"logloss": round(log_loss(y, p), 4), "brier": round(brier_score_loss(y, p), 4), "auc": round(roc_auc_score(y, p), 4)}


def calibration(y, p, bins=10):
    q = pd.qcut(p, bins, labels=False, duplicates="drop")
    t = pd.DataFrame({"y": y, "p": p, "q": q}).groupby("q").agg(n=("y", "size"), pred=("p", "mean"), actual=("y", "mean"))
    return [{"n": int(r.n), "pred": round(r.pred, 3), "actual": round(r.actual, 3)} for r in t.itertuples()]


def fit(feats, data):
    return make_model(feats).fit(data[feats], data.made)


if __name__ == "__main__":
    df = featurize(load_seasons(SEASONS))
    dates = pd.to_datetime(df.date)
    cut = dates[df.season == SEASON].quantile(0.75)
    held = ((df.season == SEASON) & (dates > cut)).values
    train, test = df[~held], df[held]
    by_season = {s: int(n) for s, n in df.groupby("season").size().items()}
    print(f"{'+'.join(SEASONS)}: {len(df)} shots {by_season}, {df.player.nunique()} shooters; train {len(train)} (to {cut.date()}), test {len(test)}")

    # baselines: one rate, the rate per court area, the rate per distance band
    base_rate = train.made.mean()
    area_rate = train.groupby("area", observed=True).made.mean().rename(index=str)
    bands = [-1, 3, 6, 10, 16, 22, 23.75, 28, 100]
    band_rate = train.groupby(pd.cut(train.dist, bands), observed=True).made.mean()
    p_area = test.area.astype(str).map(area_rate).astype(float).fillna(base_rate).values
    p_band = pd.cut(test.dist, bands).map(band_rate).astype(float).fillna(base_rate).values

    # context model, and the same without the move: the scorer leaves the move out more often on misses (a mild label leak)
    no_move = [f for f in FEATURES if f != "move"]
    p_nomove = fit(no_move, train).predict_proba(test[no_move])[:, 1]
    base = fit(FEATURES, train)
    p_base = base.predict_proba(test[FEATURES])[:, 1]

    # shooter feature: out-of-fold residuals on train, residuals against the base model on test (earlier shots only)
    oof = np.zeros(len(train))
    for tr, va in GroupKFold(5).split(train, groups=train.game):
        oof[va] = fit(FEATURES, train.iloc[tr]).predict_proba(train.iloc[va][FEATURES])[:, 1]
    resid = np.concatenate([train.made.values - oof, test.made.values - p_base])
    prior_all, effects = shooter_effects(pd.concat([train, test]), resid)
    train = train.assign(shooter=prior_all[:len(train)])
    test = test.assign(shooter=prior_all[len(train):])
    FEAT2 = FEATURES + ["shooter"]
    aug = fit(FEAT2, train)
    p_aug = aug.predict_proba(test[FEAT2])[:, 1]

    res = {"constant": metrics(test.made, np.full(len(test), base_rate)), "area_fg": metrics(test.made, p_area), "distance_bands": metrics(test.made, p_band),
           "xfg_context_without_move": metrics(test.made, p_nomove), "xfg_context": metrics(test.made, p_base), "xfg_context_plus_shooter": metrics(test.made, p_aug)}
    print(pd.DataFrame(res).T.to_string())
    use_shooter = res["xfg_context_plus_shooter"]["logloss"] < res["xfg_context"]["logloss"]
    chosen, feats, model_test, p_final = ("xfg_context_plus_shooter", FEAT2, aug, p_aug) if use_shooter else ("xfg_context", FEATURES, base, p_base)
    cal = calibration(test.made.values, p_final)
    print("calibration (test deciles):")
    print(pd.DataFrame(cal).to_string(index=False))
    pi = permutation_importance(model_test, test[feats], test.made, scoring="neg_log_loss", n_repeats=3, random_state=SEED)
    importance = sorted(zip(feats, [round(float(v), 4) for v in pi.importances_mean]), key=lambda t: -t[1])

    # refit on everything for deployment; the context-only model is kept too, for shot quality (what the shot was worth)
    full = pd.concat([train, test])
    final = fit(feats, full)
    context = fit(FEATURES, full) if use_shooter else final
    cats = {c: list(df[c].cat.categories) for c in CATEG}
    joblib.dump({"model": final, "context_model": context, "features": feats, "context_features": FEATURES, "categories": cats, "k_shrink": K_SHRINK,
                 "prior_decay": PRIOR_DECAY, "trained_on": SEASON, "training_seasons": SEASONS}, os.path.join(OUT, "xfg_model.joblib"), compress=3)
    effects.to_parquet(os.path.join(OUT, f"shooter_effects_{SEASON}.parquet"), index=False)
    card = {"model": "xFG (expected field goal)", "version": datetime.date.today().isoformat(), "trained_on": SEASON, "training_seasons": SEASONS,
            "source": "NBA CDN play-by-play actions via the shufinskiy/nba_data archive (model/training.json pins the commit and checksums)",
            "n_shots": int(len(df)), "n_shots_by_season": by_season, "n_shooters": int(df.player.nunique()),
            "split": f"time-based: test = {SEASON} games after {cut.date()} ({len(test)} shots), train = every earlier game ({len(train)} shots)",
            "features": feats, "chosen": chosen, "metrics_test": res, "calibration_test": cal, "permutation_importance": importance,
            "shooter_shrinkage_k": K_SHRINK, "shooter_prior_decay": PRIOR_DECAY, "algorithm": "sklearn HistGradientBoostingClassifier, early stopping",
            "notes": "Shooter effect is a sequential shrunk residual from earlier shots only; no leakage. The move (descriptor) is "
                     "recorded more often on makes than misses; xfg_context_without_move shows what the model scores without it.",
            "context_coverage": round(float(df.poss_sec.notna().mean()), 3)}
    json.dump(card, open(os.path.join(OUT, "model_card.json"), "w"), indent=1)
    print(f"\nchosen: {chosen}; saved model, card and {len(effects)} shooter effects")
    print("top features:", importance[:8])
