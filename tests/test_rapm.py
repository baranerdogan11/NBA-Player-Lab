"""RAPM on a made-up league whose players' effects are known: the fit recovers them with the right signs (a defender
who holds opponents down has a positive D-RAPM), a prior pulls a thin sample towards it, and main() fits regular
season stints only.

usage: python tests/test_rapm.py
"""
import os
import random
import sys
import tempfile
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import rapm  # noqa: E402

rng = random.Random(3)
TRUE = {p: (rng.gauss(0, 3), rng.gauss(0, 3)) for p in range(1, 41)}   # player: (offence, defence), positive is good


def league(n, base=112.0, per_stint=10):
    """n stints between two random fives of the 40, scored exactly at the players' rates (each gives two rows)."""
    rows = []
    for i in range(n):
        ten = rng.sample(range(1, 41), 10)
        a, b = ten[:5], ten[5:]
        for off, dfn, team in ((a, b, "AAA"), (b, a, "BBB")):
            rate = base + sum(TRUE[p][0] for p in off) - sum(TRUE[p][1] for p in dfn)
            rows.append({"game": f"g{i // 20:03d}", "team": team, "players": off, "opp_players": dfn, "sec": 120.0,
                         "pts": rate * per_stint / 100, "fga": per_stint, "oreb": 0, "tov": 0, "fta": 0})
    return pd.DataFrame(rows)


checks = {}
st = league(3000)
fit = rapm.fit(st, lam=1)
got = fit.set_index("player")
o = np.array([TRUE[p][0] for p in got.index])
d = np.array([TRUE[p][1] for p in got.index])
checks["recovers offence"] = np.corrcoef(o, got.o)[0, 1] > 0.99
checks["recovers defence, positive is good"] = np.corrcoef(d, got.d)[0, 1] > 0.99
checks["RAPM is O + D"] = np.allclose(got.rapm, got.o + got.d)
checks["possessions on the floor add up"] = abs(got.poss.sum() - 5 * 10 * len(st)) < 1e-6

thin = league(30)
prior = pd.DataFrame({"player": list(TRUE), "o": [v[0] for v in TRUE.values()], "d": [v[1] for v in TRUE.values()]})
with_prior = rapm.fit(thin, prior).set_index("player")
no_prior = rapm.fit(thin).set_index("player")
err = lambda f: np.mean([(f.o[p] - TRUE[p][0]) ** 2 + (f.d[p] - TRUE[p][1]) ** 2 for p in f.index])  # noqa: E731
checks["a prior pulls a thin sample towards it"] = err(with_prior) < 0.1 * err(no_prior)
checks["with no prior a thin sample shrinks to zero"] = no_prior.rapm.abs().mean() < 0.5 * np.mean([abs(sum(v)) for v in TRUE.values()])

w = tempfile.mkdtemp()
season = league(200)
season.loc[season.game == "g000", "pts"] += 50          # a preseason game, ignored
season.to_parquet(os.path.join(w, "stints.parquet"), index=False)
pd.DataFrame({"game": sorted(season.game.unique())}).assign(game_type=lambda g: np.where(g.game == "g000", "preseason", "regular")).to_parquet(
    os.path.join(w, "games.parquet"), index=False)
rapm.main("2099-00", w)
out = pd.read_parquet(os.path.join(w, "rapm.parquet")).set_index("player")
ref = rapm.fit(season[season.game != "g000"]).set_index("player")
checks["main fits regular season stints only"] = np.allclose(out.loc[ref.index, ["o", "d"]], ref[["o", "d"]])
checks["the committed 2025-26 prior covers the league"] = len(pd.read_parquet(rapm.PRIOR.format(season="2025-26"))) > 450

for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
