"""Role and efficiency profiles: what each player does and how well, ranked within his position group.

Role: usage, assist, turnover, offensive and defensive rebound, steal and block percentages, three-point attempt
rate and free-throw rate. Efficiency: true shooting, points per shot attempt and, when lineups.py has run, net
rating on/off. All are season totals from the box score (team totals are the sums of the players' lines, so every
share adds up across a roster), in the standard Basketball-Reference forms.

Position groups (G, F, C) come from the box score, which names a position only for starters: a player takes the
group he started at most this season. A player who has not started is placed by his role numbers, at the nearest
group centre of this season's starters (standardised usage, assist, rebound and block rates, three-point rate).

Percentiles are against the eligible players of the same group (at least MIN_GAMES games and MIN_MPG minutes a
game, and at least MIN_POOL such players in the group): the share of them below the player, so 90 means better than
nine in ten; for turnovers lower is better. Values are stored unrounded; the page rounds once, with the site's rule.

usage: python profiles.py [season]     # warehouse/<season>/box.parquet -> warehouse/<season>/profiles.parquet
"""
import os
import sys
import numpy as np
import pandas as pd

MIN_GAMES, MIN_MPG, MIN_POOL = 3, 12.0, 20
GROUP = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}
ROLE = ["usg", "ast_pct", "tov_pct", "oreb_pct", "dreb_pct", "stl_pct", "blk_pct", "fg3a_rate", "fta_rate"]
EFFICIENCY = ["ts", "pps", "onoff"]
LOWER_IS_BETTER = {"tov_pct"}
CENTRE_KEYS = ["usg", "ast_pct", "oreb_pct", "dreb_pct", "blk_pct", "fg3a_rate"]
STATS = ["points", "fieldGoalsMade", "fieldGoalsAttempted", "threePointersMade", "threePointersAttempted", "freeThrowsMade", "freeThrowsAttempted",
         "reboundsOffensive", "reboundsDefensive", "assists", "turnovers", "steals", "blocks"]


def season_lines(box):
    """Per-player season totals with his teams' totals over the same games and their opponents' (only games he played)."""
    b = box.copy()
    b["min"] = b.seconds / 60
    team = b.groupby(["game", "teamId"], as_index=False)[STATS + ["min"]].sum()
    opp = team.rename(columns={"teamId": "oppId", **{c: f"opp_{c}" for c in STATS + ["min"]}})
    pair = team.merge(opp, on="game").query("teamId != oppId")
    pair = pair.rename(columns={c: f"tm_{c}" for c in STATS + ["min"]})
    played = b[b.seconds > 0].merge(pair, on=["game", "teamId"])
    cols = STATS + ["min"] + [f"tm_{c}" for c in STATS + ["min"]] + [f"opp_{c}" for c in STATS + ["min"]]
    tot = played.groupby("personId", as_index=False)[cols].sum()
    tot["gp"] = played.groupby("personId").game.nunique().values
    tot["teamId"] = played.sort_values("game").groupby("personId").teamId.last().values   # his current team
    return tot


def rates(t):
    """The role and efficiency rates from season_lines (unrounded; NaN where a denominator is zero)."""
    d = pd.DataFrame({"personId": t.personId, "teamId": t.teamId, "gp": t.gp, "min": t["min"]})
    div = lambda a, b: (a / b).where(b > 0)  # noqa: E731
    share = t.tm_min / 5 / t["min"]                       # team minutes per player slot over his minutes
    poss = lambda p="": t[f"{p}fieldGoalsAttempted"] + 0.44 * t[f"{p}freeThrowsAttempted"] + t[f"{p}turnovers"]  # noqa: E731
    opp_poss = t.opp_fieldGoalsAttempted - t.opp_reboundsOffensive + t.opp_turnovers + 0.44 * t.opp_freeThrowsAttempted
    d["usg"] = 100 * div(poss() * share, poss("tm_"))
    d["ast_pct"] = 100 * div(t.assists, t["min"] / (t.tm_min / 5) * t.tm_fieldGoalsMade - t.fieldGoalsMade)
    d["tov_pct"] = 100 * div(t.turnovers, poss())
    d["oreb_pct"] = 100 * div(t.reboundsOffensive * share, t.tm_reboundsOffensive + t.opp_reboundsDefensive)
    d["dreb_pct"] = 100 * div(t.reboundsDefensive * share, t.tm_reboundsDefensive + t.opp_reboundsOffensive)
    d["stl_pct"] = 100 * div(t.steals * share, opp_poss)
    d["blk_pct"] = 100 * div(t.blocks * share, t.opp_fieldGoalsAttempted - t.opp_threePointersAttempted)
    d["fg3a_rate"] = div(t.threePointersAttempted, t.fieldGoalsAttempted)
    d["fta_rate"] = div(t.freeThrowsAttempted, t.fieldGoalsAttempted)
    d["ts"] = div(t.points, 2 * (t.fieldGoalsAttempted + 0.44 * t.freeThrowsAttempted))
    d["pps"] = div(t.points - t.freeThrowsMade, t.fieldGoalsAttempted)
    return d


def position_groups(box, r):
    """{personId: (group, source)}: the group he started at most, else the nearest starters' centre by role."""
    st = box[box.starter & box.position.fillna("").isin(list(GROUP))].assign(group=lambda x: x.position.map(GROUP))
    started = st.groupby("personId").group.agg(lambda g: g.value_counts().sort_index().idxmax()).to_dict()
    out = {p: (g, "started") for p, g in started.items()}
    known = r[r.personId.isin(started) & (r.gp >= MIN_GAMES)].dropna(subset=CENTRE_KEYS)
    rest = r[~r.personId.isin(started)].dropna(subset=CENTRE_KEYS)
    if len(known) >= 10 and len(rest):
        mu, sd = known[CENTRE_KEYS].mean(), known[CENTRE_KEYS].std().replace(0, 1)
        z = lambda f: ((f[CENTRE_KEYS] - mu) / sd).values  # noqa: E731
        groups = known.personId.map(started)
        centres = {g: z(known)[(groups == g).values].mean(axis=0) for g in sorted(set(groups))}
        for pid, v in zip(rest.personId, z(rest)):
            out[pid] = (min(centres, key=lambda g: float(np.sum((v - centres[g]) ** 2))), "role")
    return out


def percentile(pool, v, lower_better=False):
    vals = pool[~np.isnan(pool)]
    if np.isnan(v) or len(vals) == 0:
        return np.nan
    return 100 * float(np.mean(vals > v if lower_better else vals < v))


def profiles(box, onoff=None):
    r = rates(season_lines(box))
    # on/off with his current team (a traded player has a row per team)
    r["onoff"] = (r.merge(onoff.rename(columns={"club": "teamId", "player": "personId"})[["teamId", "personId", "onoff"]], how="left", on=["teamId", "personId"]).onoff.values
                  if onoff is not None else np.nan)
    pos = position_groups(box, r)
    r["group"] = r.personId.map(lambda p: pos.get(p, (None, None))[0])
    r["group_source"] = r.personId.map(lambda p: pos.get(p, (None, None))[1])
    r["eligible"] = (r.gp >= MIN_GAMES) & (r["min"] / r.gp >= MIN_MPG) & r.group.notna()
    for k in ROLE + EFFICIENCY:
        r[f"pctl_{k}"] = np.nan
    for g, members in r[r.eligible].groupby("group"):
        if len(members) < MIN_POOL:
            continue
        idx = r.index[r.eligible & (r.group == g)]
        for k in ROLE + EFFICIENCY:
            pool = members[k].to_numpy(dtype=float)
            r.loc[idx, f"pctl_{k}"] = [percentile(pool, v, k in LOWER_IS_BETTER) for v in r.loc[idx, k].to_numpy(dtype=float)]
    return r


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from season import season
    s = season()
    w = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warehouse", s)
    box = pd.read_parquet(os.path.join(w, "box.parquet"))
    box[["teamId", "personId"]] = box[["teamId", "personId"]].astype(str)
    oo_path = os.path.join(w, "onoff.parquet")
    out = profiles(box, pd.read_parquet(oo_path) if os.path.exists(oo_path) else None)
    out.to_parquet(os.path.join(w, "profiles.parquet"), index=False)
    print(f"{s}: {len(out)} players, {int(out.eligible.sum())} ranked; groups {out[out.eligible].group.value_counts().to_dict()}")
