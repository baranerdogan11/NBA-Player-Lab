"""Similar role: each regular's three nearest players by what he does on the floor, not how well he does it.

Every player with at least MIN_GAMES games and MIN_MPG minutes a game (and a position group) is placed by the nine
role rates of profiles.py (usage, assist, turnover, offensive and defensive rebound, steal and block percentages,
three-point attempt rate, free-throw rate), each standardised over those players. Efficiency (true shooting, points
per shot, on/off) is left out, so a comp shares a style, not a level. His comps are the K nearest by that distance
among the players of his own position group (G, F, C); a group with fewer than K others is filled from the rest of
the league. A player below the floors has no comps and is not anyone's; the floors are higher than profiles.py's, so
the comps don't jump from night to night on a handful of games.

<out>/similar.json  {"keys": [the role rates], "games": MIN_GAMES, "mpg": MIN_MPG, "players": {pid: [pid, pid, pid]}},
  nearest first. Ties go to the lower pid.

Gate (check): the file is exactly what profiles.parquet gives again; every listed player and comp clears the floors
and is on leaders.json with the same games and seconds as the profile, so a comp row names only players the site
shows, over the same box-score lines.
usage: python similar.py [2026-27]   (reads warehouse/<season>/profiles.parquet, writes teams/<season>/similar.json)
"""
import json
import os
import numpy as np
from profiles import ROLE

MIN_GAMES, MIN_MPG, K = 5, 15.0, 3


def pool(prof):
    """The players who get comps: the floors, a group, and every role rate known."""
    p = prof[(prof.gp >= MIN_GAMES) & (prof["min"] >= MIN_MPG * prof.gp) & prof.group.notna()].dropna(subset=ROLE)
    return p.assign(pid=p.player.astype(str)).sort_values("pid").reset_index(drop=True)


def comps(prof):
    """{pid: [K nearest pids]} from profiles.profiles() rows."""
    p = pool(prof)
    if len(p) <= K:
        return {}
    x = p[ROLE].to_numpy(dtype=float)
    sd = x.std(axis=0)
    z = (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1)
    d = ((z[:, None, :] - z[None, :, :]) ** 2).sum(axis=2)
    pids, groups, out = p.pid.tolist(), p.group.tolist(), {}
    for i, pid in enumerate(pids):
        order = sorted((j for j in range(len(pids)) if j != i), key=lambda j: (groups[j] != groups[i], round(d[i, j], 9), pids[j]))
        out[pid] = [pids[j] for j in order[:K]]
    return out


def document(prof):
    return {"keys": ROLE, "games": MIN_GAMES, "mpg": MIN_MPG, "players": comps(prof)}


def check(doc, prof, leaders):
    """Raises unless doc is what prof gives again and every player in it clears the floors and matches leaders.json."""
    if doc != document(prof):
        raise SystemExit("similar.json: not what profiles.parquet gives")
    ok = set(pool(prof).pid)
    rows = {str(r.player): r for r in prof.itertuples()}
    lead = {p["pid"]: p for p in leaders["players"]}
    for pid, cs in doc["players"].items():
        if len(cs) != K or len(set(cs)) != K or pid in cs:
            raise SystemExit(f"similar.json: {pid}: comps {cs} are not {K} other players")
        for q in [pid] + cs:
            if q not in ok:
                raise SystemExit(f"similar.json: {q} is below the floors")
            r, ld = rows[q], lead.get(q)
            if ld is None or ld["gp"] != r.gp or ld["sec"] != round(r.min * 60):
                raise SystemExit(f"similar.json: {q}: profile {r.gp} games, {round(r.min * 60)} s; leaders.json "
                                 f"{ld and (ld['gp'], ld['sec'])}")


if __name__ == "__main__":
    import pandas as pd
    from season import ROOT, season
    s = season()
    prof = pd.read_parquet(os.path.join(ROOT, "warehouse", s, "profiles.parquet"))
    out = os.path.join(ROOT, "teams", s)
    doc = document(prof)
    check(doc, prof, json.load(open(os.path.join(out, "leaders.json"))))
    with open(os.path.join(out, "similar.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"{s}: comps for {len(doc['players'])} players (floors {MIN_GAMES} games, {MIN_MPG:g} mpg)")
