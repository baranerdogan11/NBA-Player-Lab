"""Lineup layer: who was on the floor for every second of every game, from the starters and the substitution log of
the NBA CDN play-by-play, and what happened while they were there.

The feed logs every substitution, including the changes made between periods (logged at the start of the period), so
the five on the floor carry over from one period to the next and only the opening five are needed. Those come from the
box score's starter flags; where there is no box score (the training archive) they are read off the first period: the
players who appear in a play before being subbed in.

A stint is a stretch with the same ten players. For each club it records the seconds, both clubs' points (from the
running score, so they always add up to the final) and the box-score counts behind the possession estimate the site
uses everywhere: possessions = FGA - OREB + TOV + 0.44 FTA.

Writes three Parquet tables to warehouse/<season>/:
  stints    one row per club per stint: the five, the opposing five, seconds, both sides' points and counts
  lineups   one row per five-man unit over the season: games, seconds, points, possessions and ratings per 100
  onoff     one row per player: the same totals and ratings with him on the floor and off it, and the difference
Ratings are unrounded here; the page rounds them once, with the site's one rule.

And, from the regular-season finals' stints, the site's teams/<season>/lineups/<CODE>.json (site_data.write_lineups).

Checks, every run: five per club at every action, stint points equal the final score, stint seconds equal the game
length, each player's seconds on the floor agree with the box score within a minute, and his points for and against on the
floor add up to his box-score plus-minus.

usage: python lineups.py [season]
"""
import os
import sys
import duckdb
import pandas as pd

PERIOD_SEC = lambda per: 720 if per <= 4 else 300  # noqa: E731
# who an action puts on the floor: the actor, and the other players it names (technical fouls and ejections can name
# players on the bench, so they never count)


def _v(x):
    """A value from a row, with pandas' missing markers as None."""
    return None if x is None or x is pd.NA or (isinstance(x, float) and x != x) else x


def plays(actions):
    """The actions without the game's end marker, which the feed can log in a period of its own (PHX-GSW, 24 Oct: "Game
    End" in period 5 after a regulation final), where it would open a five-minute overtime nobody played."""
    return [a for a in actions if a["action_type"] != "game"]


def ordered(actions):
    """The actions in feed order, each period's together, with two corrections for plays keyed in late. A play entered
    after its period's end, or during the next period, goes back to its clock: after the last play of its period at that
    time or earlier on the clock. And free throws logged after a substitution that the clock puts later (the change
    made at 2:04, the free throw shot at 2:06) go before it."""
    acts = sorted(actions, key=lambda a: int(a["order_no"]))
    clock = lambda a: _v(a.get("clock"))  # noqa: E731
    out = []
    for per in sorted({int(a["period"]) for a in acts}):
        rows, late, ended = [], [], False
        for a in (a for a in acts if int(a["period"]) == per):
            if ended and a["action_type"] != "period" and clock(a) is not None and clock(a) > 0:
                late.append(a)
                continue
            rows.append(a)
            ended = ended or (a["action_type"] == "period" and a.get("sub_type") == "end")
        for a in late:
            at = [k for k, b in enumerate(rows) if b["action_type"] != "period" and clock(b) is not None and clock(b) >= clock(a)]
            rows.insert(at[-1] + 1 if at else 0, a)
        k = 0
        while k < len(rows):
            n = k
            while n < len(rows) and rows[n]["action_type"] == "substitution":
                n += 1
            f = n
            while f < len(rows) and rows[f]["action_type"] == "freethrow" and clock(rows[k]) is not None and clock(rows[f]) is not None and clock(rows[f]) > clock(rows[k]):
                f += 1
            if n > k and f > n:
                rows[k:f] = rows[n:f] + rows[k:n]
            k = max(f, k + 1)
        out += rows
    return out


def play_order(actions):
    """The actions in feed order, except that a substitution made after a foul while its free throws are still to come
    at the same clock moves to after the last of them: free-throw points belong to the five who were on the floor for the
    foul, the convention of the box score's plus-minus. A substitution logged before the foul (a technical after a
    timeout, an and-one after the change) stays where it is: the incoming five were on the floor for it."""
    acts = ordered(actions)

    def fouled_before(i):
        for b in reversed(acts[:i]):
            if b["period"] != acts[i]["period"] or b["clock"] != acts[i]["clock"]:
                return False
            if b["action_type"] == "foul":
                return True
        return False

    def ft_ahead(i):
        for b in acts[i + 1:]:
            if b["period"] != acts[i]["period"] or b["clock"] != acts[i]["clock"]:
                return False
            if b["action_type"] == "freethrow":
                return True
        return False
    out, held = [], []
    for i, a in enumerate(acts):
        if a["action_type"] == "substitution" and (held or fouled_before(i)) and ft_ahead(i):
            held.append(a)
            continue
        out.append(a)
        if held and not ft_ahead(i):
            out += held
            held = []
    return out + held


def infer_starters(actions):
    """The opening five of each club, from the first period of play: anyone who appears before being subbed in."""
    seen, subbed_in = {}, set()
    for a in ordered(actions):
        if int(a["period"]) != 1:
            break
        t, team, p = a["action_type"], _v(a.get("team")), _v(a.get("player"))
        if t == "substitution":
            if a.get("sub_type") == "in":
                subbed_in.add(p)
            elif p and p not in subbed_in:
                seen.setdefault(team, set()).add(p)
            continue
        if (t == "foul" and a.get("sub_type") == "technical") or t == "ejection":
            continue
        if p and team and p not in subbed_in:
            seen.setdefault(team, set()).add(p)
    return seen


def stints(actions, starters):
    """Stints of one game from its events (dicts, warehouse names) and {team: set of five players}. Returns (stints, problems)."""
    teams = list(starters)
    on = {t: set(starters[t]) for t in teams}
    out, problems = [], []
    if len(teams) != 2 or any(len(v) != 5 for v in on.values()):
        return out, [f"starters {[len(v) for v in on.values()]}"]
    zero = lambda: {t: {"pts": 0, "fga": 0, "oreb": 0, "tov": 0, "fta": 0} for t in teams}  # noqa: E731
    cur, sec, per, clock, idx = zero(), 0.0, 1, 720.0, 0
    home_team = None
    score = (0, 0)

    def flush():
        nonlocal cur, sec, idx
        if sec <= 0 and all(v["fga"] + v["tov"] + v["fta"] + v["pts"] == 0 for v in cur.values()):
            return
        for t in teams:
            o = teams[1] if t == teams[0] else teams[0]
            out.append({"team": t, "stint": idx, "players": sorted(on[t]), "opp_players": sorted(on[o]), "sec": round(sec, 1),
                        "pts": cur[t]["pts"], "opp_pts": cur[o]["pts"], **{k: cur[t][k] for k in ("fga", "oreb", "tov", "fta")},
                        **{f"opp_{k}": cur[o][k] for k in ("fga", "oreb", "tov", "fta")}})
        idx += 1
        sec, cur = 0.0, zero()

    for a in play_order(plays(actions)):
        t, sub, team = a["action_type"], a.get("sub_type"), _v(a.get("team"))
        p, a_per, c = _v(a.get("player")), int(a["period"]), _v(a.get("clock"))
        if a_per != per:                          # whatever the clock said, the old period ran out
            sec += clock
            per, clock = a_per, float(PERIOD_SEC(a_per))
        if c is not None and c < clock:
            sec += clock - c
            clock = c
        if t == "substitution" and team in on and p:
            flush()
            if sub == "in":
                if p in on[team]:
                    problems.append(f"{a['action']}: {p} subbed in while on the floor")
                on[team].add(p)
            else:
                if p not in on[team]:
                    problems.append(f"{a['action']}: {p} subbed out while on the bench")
                on[team].discard(p)
            continue
        # points from the running score: the only source that always adds up to the final
        sh, sa = _v(a.get("score_home")), _v(a.get("score_away"))
        s = (int(sh), int(sa)) if sh is not None and sa is not None else score
        if s != score and team in on:
            if home_team is None:
                home_team = team if s[0] > score[0] else next(x for x in teams if x != team)
            away_team = next(x for x in teams if x != home_team)
            cur[home_team]["pts"] += s[0] - score[0]
            cur[away_team]["pts"] += s[1] - score[1]
            score = s
        if team not in on:
            continue
        if any(len(v) != 5 for v in on.values()) and t in ("2pt", "3pt", "freethrow", "turnover"):
            problems.append(f"{a['action']}: {[len(v) for v in on.values()]} on the floor")
        if t in ("2pt", "3pt"):
            cur[team]["fga"] += 1
        elif t == "freethrow":
            cur[team]["fta"] += 1
        elif t == "turnover":
            cur[team]["tov"] += 1
        elif t == "rebound" and sub == "offensive" and p:
            cur[team]["oreb"] += 1
    sec += clock if per <= 4 or clock > 0 else 0   # a game ends at 0:00; any clock left in the last period still elapsed
    flush()
    return out, problems


def seconds_on(game_stints):
    """{(team, player): seconds on the floor} from one game's stints."""
    secs = {}
    for s in game_stints:
        for p in s["players"]:
            secs[(s["team"], p)] = secs.get((s["team"], p), 0.0) + s["sec"]
    return secs


COUNTS = ("fga", "oreb", "tov", "fta")


def poss(r, side=""):
    return r[side + "fga"] - r[side + "oreb"] + r[side + "tov"] + 0.44 * r[side + "fta"]


def ratings(df):
    """Adds possessions per side and ratings per 100 to a frame of summed stint columns (unrounded)."""
    df = df.copy()
    df["poss"] = poss(df)
    df["opp_poss"] = poss(df, "opp_")
    df["ortg"] = (100 * df.pts / df.poss).where(df.poss >= 1)
    df["drtg"] = (100 * df.opp_pts / df.opp_poss).where(df.opp_poss >= 1)
    df["net"] = df.ortg - df.drtg
    return df


def season_tables(st):
    """lineups and onoff frames from the season's stints frame (needs a game column)."""
    sums = {"g": ("game", "nunique"), "sec": ("sec", "sum"), "pts": ("pts", "sum"), "opp_pts": ("opp_pts", "sum"),
            **{k: (k, "sum") for k in COUNTS}, **{f"opp_{k}": (f"opp_{k}", "sum") for k in COUNTS}}
    st = st.assign(five=st.players.map(lambda p: ",".join(map(str, sorted(p)))))
    lu = ratings(st.groupby(["team", "five"], as_index=False).agg(**sums))
    lu["players"] = lu.five.map(lambda f: [int(p) for p in f.split(",")])
    tot = st.groupby("team").agg(**sums)
    per = st.explode("players").rename(columns={"players": "player"}).groupby(["team", "player"], as_index=False).agg(**sums)
    on = ratings(per)
    off = per.copy()
    for k in [c for c in sums if c != "g"]:
        off[k] = tot.loc[off.team, k].values - off[k].values
    off = ratings(off)
    oo = on[["team", "player", "g", "sec", "pts", "opp_pts", "poss", "opp_poss", "ortg", "drtg", "net"]].copy()
    for k in ("sec", "pts", "opp_pts", "poss", "opp_poss", "ortg", "drtg", "net"):
        oo[f"off_{k}"] = off[k].values
    oo["onoff"] = oo.net - oo.off_net
    return lu.drop(columns="five"), oo


def main(season, w=None, out=None):
    w = w or os.path.join(os.path.dirname(os.path.abspath(__file__)), "warehouse", season)
    con = duckdb.connect()
    ev = con.execute(f"select game, action, order_no, period, clock, team, player, action_type, sub_type, score_home, score_away "
                     f"from read_parquet('{w}/events.parquet')").df()
    ev["player"] = ev.player.astype("Int64")                  # DuckDB hands a nullable INTEGER over as float
    box = con.execute(f"select game, team, player, starter, seconds, plus_minus from read_parquet('{w}/box.parquet')").df()
    box["player"] = box.player.astype(int)
    starters = {g: {t: set(d.player) for t, d in gd[gd.starter].groupby("team")} for g, gd in box.groupby("game")}
    final = {r.game: sorted([r.home_score, r.away_score]) for r in con.execute(f"select * from read_parquet('{w}/games.parquet') where final").df().itertuples()}
    rows, problems = [], []
    for g, acts in ev.groupby("game"):
        acts = acts.to_dict("records")
        sts, pr = stints(acts, starters.get(g, {}))
        problems += [f"game {g}: {p}" for p in pr]
        n_per = max(int(a["period"]) for a in plays(acts))
        if abs(sum(s["sec"] for s in sts) / 2 - (2880 + 300 * max(n_per - 4, 0))) > 1:
            problems.append(f"game {g}: stints cover {sum(s['sec'] for s in sts) / 2:.0f} s")
        pts = sorted(sum(s["pts"] for s in sts if s["team"] == c) for c in {s["team"] for s in sts})
        if g in final and pts != final[g]:
            problems.append(f"game {g}: stint points {pts}, final {final[g]}")
        on, pm = seconds_on(sts), {}
        for s in sts:
            for p in s["players"]:
                pm[(s["team"], p)] = pm.get((s["team"], p), 0) + s["pts"] - s["opp_pts"]
        for b in box[box.game == g].itertuples():
            if abs(on.get((b.team, b.player), 0) - (b.seconds or 0)) > 60:
                problems.append(f"game {g}: {b.player} on the floor {on.get((b.team, b.player), 0):.0f} s, box {b.seconds:.0f} s")
            if g in final and _v(b.plus_minus) is not None and pm.get((b.team, b.player), 0) != b.plus_minus:
                problems.append(f"game {g}: {b.player} +/- on the floor {pm.get((b.team, b.player), 0)}, box {b.plus_minus}")
        rows += [{"game": g, **s} for s in sts]
    cols = ["game", "team", "stint", "players", "opp_players", "sec", "pts", "opp_pts", *COUNTS, *(f"opp_{k}" for k in COUNTS)]
    st = pd.DataFrame(rows, columns=cols)       # before opening night there are no games: the tables are written empty
    lu, oo = season_tables(st) if len(st) else (pd.DataFrame(columns=["team", "players"]), pd.DataFrame(columns=["team", "player"]))
    st.to_parquet(os.path.join(w, "stints.parquet"), index=False)
    lu.to_parquet(os.path.join(w, "lineups.parquet"), index=False)
    oo.to_parquet(os.path.join(w, "onoff.parquet"), index=False)
    if out:
        from site_data import load_teams, write_lineups
        reg = con.execute(f"select game, strftime(tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time from read_parquet('{w}/games.parquet') "
                          "where game_type = 'regular' and final").fetchall()
        when = dict(reg)
        write_lineups(out, load_teams(), [{**r, "gid": r["game"], "time": when[r["game"]]} for r in rows if r["game"] in when])
    for p in problems[:20]:
        print("FAIL", p)
    print(f"{season}: {st.game.nunique()} games, {len(st)} stint rows, {len(lu)} fives, {len(oo)} players; {len(problems)} problems")
    return problems


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from season import ROOT, season
    sys.exit(1 if main(season(), out=os.path.join(ROOT, "teams", season())) else 0)
