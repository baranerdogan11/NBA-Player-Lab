"""Role profile: where each regular ranks within his position group on every rate of profiles.py.

Every player profiles.py ranks (at least MIN_GAMES games and MIN_MPG minutes a game, in a group of at least MIN_POOL
such players) gets, for each of the nine role rates and the three efficiency rates, how many of his group's ranked
players he is ahead of (below him, or above him where lower is better: turnovers). With the pool size per group and
rate, the page shows the percentile as rdiv(100 * ahead, pool), so 90 means ahead of nine in ten, rounded once with
the site's rule; the counts are integers, so nothing is rounded before that.

<out>/profiles.json  {"keys": [12 rates, role first], "role": 9, "lower": [...], "games", "mpg", "pool",
  "groups": {group: [ranked players with that rate known, per key]},
  "players": {pid: [group, [players he is ahead of, per key; null where his rate is unknown]]}}

Gate (check): the file is exactly what profiles.parquet gives again, every count turns back into profiles.py's stored
percentile, every listed player clears the floors and is on leaders.json with the same games and seconds, so a
profile ranks only players the site shows, over the same box-score lines.
usage: python percentiles.py [2026-27]   (reads warehouse/<season>/profiles.parquet, writes teams/<season>/profiles.json)
"""
import json
import os
import numpy as np
from profiles import EFFICIENCY, LOWER_IS_BETTER, MIN_GAMES, MIN_MPG, MIN_POOL, ROLE

KEYS = ROLE + EFFICIENCY


def ranked(prof):
    """profiles.py's ranked players: eligible, in a group big enough to have percentiles."""
    e = prof[prof.eligible.astype(bool)]
    sizes = e.group.value_counts()
    e = e[e.group.map(sizes) >= MIN_POOL]
    return e.assign(pid=e.player.astype(str)).sort_values("pid")


def document(prof):
    r = ranked(prof)
    groups, players = {}, {}
    for g, m in r.groupby("group"):
        vals = {k: m[k].to_numpy(dtype=float) for k in KEYS}
        groups[g] = [int(np.sum(~np.isnan(vals[k]))) for k in KEYS]
        for i, pid in enumerate(m.pid):
            ahead = []
            for k in KEYS:
                v, pool = vals[k][i], vals[k][~np.isnan(vals[k])]
                ahead.append(None if np.isnan(v) else int(np.sum(pool > v if k in LOWER_IS_BETTER else pool < v)))
            players[pid] = [g, ahead]
    return {"keys": KEYS, "role": len(ROLE), "lower": sorted(LOWER_IS_BETTER), "games": MIN_GAMES, "mpg": MIN_MPG,
            "pool": MIN_POOL, "groups": dict(sorted(groups.items())), "players": dict(sorted(players.items()))}


def check(doc, prof, leaders):
    """Raises unless doc is what prof gives again, matches its stored percentiles, and every player matches leaders.json."""
    if doc != document(prof):
        raise SystemExit("profiles.json: not what profiles.parquet gives")
    rows = {str(r.player): r for r in prof.itertuples()}
    lead = {p["pid"]: p for p in leaders["players"]}
    for pid, (g, ahead) in doc["players"].items():
        r, ld = rows[pid], lead.get(pid)
        if not (r.eligible and r.group == g and r.gp >= MIN_GAMES and r.min >= MIN_MPG * r.gp):
            raise SystemExit(f"profiles.json: {pid} is below the floors or not in group {g}")
        if ld is None or ld["gp"] != r.gp or ld["sec"] != round(r.min * 60):
            raise SystemExit(f"profiles.json: {pid}: profile {r.gp} games, {round(r.min * 60)} s; leaders.json "
                             f"{ld and (ld['gp'], ld['sec'])}")
        for k, a, n in zip(KEYS, ahead, doc["groups"][g]):
            p = getattr(r, f"pctl_{k}")
            if (a is None) != bool(np.isnan(p)) or (a is not None and not (0 <= a < n and abs(100 * a / n - p) < 1e-9)):
                raise SystemExit(f"profiles.json: {pid} {k}: {a} of {n} is not the stored percentile {p}")


if __name__ == "__main__":
    import pandas as pd
    from season import ROOT, season
    s = season()
    prof = pd.read_parquet(os.path.join(ROOT, "warehouse", s, "profiles.parquet"))
    out = os.path.join(ROOT, "teams", s)
    doc = document(prof)
    check(doc, prof, json.load(open(os.path.join(out, "leaders.json"))))
    with open(os.path.join(out, "profiles.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"{s}: profiles for {len(doc['players'])} players, groups {doc['groups'] and {g: max(n) for g, n in doc['groups'].items()}}")
