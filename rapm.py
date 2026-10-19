"""Regularized adjusted plus-minus (RAPM): each player's effect on his club's points per 100 possessions at each end,
holding fixed the nine others on the floor, from the lineup stints of lineups.py.

Every stint gives one observation per club: its five on offence against the other five on defence, with the points
scored per 100 possessions (possessions = FGA - OREB + TOV + 0.44 FTA, as everywhere on the site), weighted by those
possessions. The fit is a ridge regression of that rate, less the league's rate, on +1 for each offensive and +1 for
each defensive player. O-RAPM is the offensive coefficient; D-RAPM is minus the defensive one, so positive is good at
both ends; RAPM is their sum.

The ridge pulls each player towards a prior instead of towards zero: his RAPM of the previous season
(model/rapm_prior_<season>.parquet, fitted the same way with a zero prior), or zero for a player with no prior season.
LAMBDA was picked on 2025-26: fitted on the first three quarters of the season's games, it predicts the last quarter
best (see tune()). Values are stored unrounded; the site rounds them once, with rounding.rnd.

usage: python rapm.py [season]          # warehouse/<season>/stints.parquet -> warehouse/<season>/rapm.parquet
       python rapm.py --prior 2025-26   # the archive's season, with a zero prior -> model/rapm_prior_2025-26.parquet
"""
import os
import sys
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = os.path.dirname(os.path.abspath(__file__))
LAMBDA = 2000
PRIOR = os.path.join(ROOT, "model", "rapm_prior_{season}.parquet")


def observations(st):
    """One row per club per distinct matchup of fives: offence, defence, points and possessions summed."""
    key = lambda p: tuple(sorted(int(x) for x in p))  # noqa: E731
    d = pd.DataFrame({"off": st.players.map(key), "dfn": st.opp_players.map(key), "pts": st.pts,
                      "poss": st.fga - st.oreb + st.tov + 0.44 * st.fta})
    d = d.groupby(["off", "dfn"], as_index=False)[["pts", "poss"]].sum()
    return d[d.poss > 0].reset_index(drop=True)


def fit(st, prior=None, lam=LAMBDA):
    """player, poss (offensive possessions on the floor), o, d, rapm from a frame of stints. prior: player, o, d."""
    obs = observations(st)
    players = sorted({p for f in obs.off for p in f} | {p for f in obs.dfn for p in f})
    col = {p: i for i, p in enumerate(players)}
    n, m = len(players), len(obs)
    rows = np.repeat(np.arange(m), 10)
    cols = np.array([[col[p] for p in o] + [n + col[p] for p in d] for o, d in zip(obs.off, obs.dfn)]).ravel()
    X = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(m, 2 * n))
    w = obs.poss.to_numpy()
    y = 100 * obs.pts.to_numpy() / w - 100 * obs.pts.sum() / w.sum()
    b0 = np.zeros(2 * n)
    if prior is not None:
        for r in prior.itertuples():
            if r.player in col:
                b0[col[r.player]], b0[n + col[r.player]] = r.o, -r.d
    Xw = X.multiply(w[:, None]).tocsr()
    b = np.linalg.solve((X.T @ Xw).toarray() + lam * np.eye(2 * n), X.T @ (w * y) + lam * b0)
    poss = np.asarray(Xw[:, :n].sum(axis=0)).ravel()
    out = pd.DataFrame({"player": players, "poss": poss, "o": b[:n], "d": -b[n:]})
    out["rapm"] = out.o + out.d
    return out


def predict(model, st):
    """Points per 100 possessions above the league's for each observation of a stints frame, and the observations."""
    obs = observations(st)
    o, d = model.set_index("player").o.to_dict(), model.set_index("player").d.to_dict()
    return obs.apply(lambda r: sum(o.get(p, 0) for p in r.off) - sum(d.get(p, 0) for p in r.dfn), axis=1), obs


def tune(st, lams=(250, 500, 1000, 2000, 3000, 5000, 8000)):
    """Weighted squared error on the last quarter of the games (by date) of a fit on the first three quarters."""
    games = st.groupby("game").date.min().sort_values().index
    late = set(games[int(0.75 * len(games)):])
    train, test = st[~st.game.isin(late)], st[st.game.isin(late)]
    out = {}
    for lam in lams:
        pred, obs = predict(fit(train, lam=lam), test)
        y = 100 * obs.pts / obs.poss - 100 * train.pts.sum() / (train.fga - train.oreb + train.tov + 0.44 * train.fta).sum()
        out[lam] = float(np.average((y - pred) ** 2, weights=obs.poss))
    return out


def previous(season):
    """'2026-27' -> '2025-26'."""
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def main(season, w=None):
    import duckdb
    w = w or os.path.join(ROOT, "warehouse", season)
    con = duckdb.connect()
    st = con.execute(f"select s.* from read_parquet('{w}/stints.parquet') s join read_parquet('{w}/games.parquet') g using (game) "
                     "where g.game_type = 'regular'").df()
    path = PRIOR.format(season=previous(season))
    prior = pd.read_parquet(path) if os.path.exists(path) else None
    out = fit(st, prior) if len(st) else pd.DataFrame(columns=["player", "poss", "o", "d", "rapm"])
    out.to_parquet(os.path.join(w, "rapm.parquet"), index=False)
    print(f"{season}: RAPM for {len(out)} players from {st.game.nunique() if len(st) else 0} games, prior {'from ' + previous(season) if prior is not None else 'zero'}")


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    if sys.argv[1:2] == ["--prior"]:
        st = pd.read_parquet(sys.argv[3]) if len(sys.argv) > 3 else None   # stints built from the archive
        out = fit(st)
        out.to_parquet(PRIOR.format(season=sys.argv[2]), index=False)
        print(f"{sys.argv[2]}: prior for {len(out)} players")
    else:
        from season import season
        main(season())
