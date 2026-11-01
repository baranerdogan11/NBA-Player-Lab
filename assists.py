"""Assist pairs: who set up whose baskets, from the play-by-play's assist credits, by club, game, passer and scorer.

<out>/assists/<CODE>.json  {"code", "games": [gid, ...], "pairs": [[g, passer, scorer, ast, pts], ...]}: g indexes games
(the club's finals in game order), ast counts the passer's assists on the scorer's baskets in that game and pts the points
those baskets made (2 or 3 each). Season pairs are the sums over the games, done by the page.

from_warehouse() reads every made field goal of warehouse/<season>/shots.parquet that names an assist and checks each
player's assists per game against his box-score AST, so a passer's pairs in a game always add up to the AST beside them.
The box score takes the league's post-game stat corrections and the play-by-play does not (an assist moved to a
team-mate), so a game whose credits differ is left out of the pairs; up to one differing player-game per thousand box
lines (at least two) is such a correction and only reported. More than that is a feed problem: those games are
quarantined (quarantine.py) and the run fails when the quarantine is systemic. A game an earlier gate holds is left out.
usage: python assists.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/assists/)
"""
import json
import os
import quarantine


def write_assists(out, teams, rows):
    """teams: site_data.load_teams() rows. rows: one per assisted basket with gid, time (tip-off, for game order), team,
    passer, scorer and pts (2 or 3)."""
    by_team = {t["code"]: [] for t in teams}
    for r in rows:
        by_team[r["team"]].append(r)
    os.makedirs(os.path.join(out, "assists"), exist_ok=True)
    for code, rs in by_team.items():
        rs.sort(key=lambda r: (r["time"], r["gid"]))
        games = list(dict.fromkeys(r["gid"] for r in rs))
        pairs = {}
        for r in rs:
            p = pairs.setdefault((games.index(r["gid"]), str(r["passer"]), str(r["scorer"])), [0, 0])
            p[0] += 1
            p[1] += int(r["pts"])
        with open(os.path.join(out, "assists", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "pairs": [[*k, *v] for k, v in sorted(pairs.items())]}, f, separators=(",", ":"))


def allowed(lines):
    """The post-game corrections tolerated in a season of so many box lines, as in warehouse_tests.py."""
    return max(2, lines // 1000)


def from_warehouse(wh, skip=()):
    """(rows for write_assists(), {game: what differs}, player-games that differ, box lines checked) from the Parquet
    tables in the directory wh; the games in skip and the games whose credits differ from the box score are left out."""
    import duckdb
    con = duckdb.connect()
    for t in ("games", "box", "shots"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    final = "join games g using (game) where g.game_type = 'regular' and g.final" + \
        (f" and g.game not in ({', '.join(repr(x) for x in sorted(skip))})" if skip else "")
    bad = con.execute(f"""
        with a as (select s.game, s.assist_player as player, count(*) as ast from shots s {final} and s.made and s.assist_player is not null group by all),
             b as (select b.game, b.player, b.ast from box b {final} and b.status = 'ACTIVE' and b.ast > 0)
        select coalesce(a.game, b.game), coalesce(a.player, b.player), a.ast, b.ast
        from a full join b using (game, player) where a.ast is distinct from b.ast order by 1, 2""").fetchall()
    games = {}
    for g, p, pbp, box in bad:
        games.setdefault(g, []).append(f"player {p}: play-by-play {pbp or 0}, box {box or 0}")
    games = {g: "; ".join(rs) for g, rs in games.items()}
    lines = con.execute(f"select count(*) from box b {final} and b.status = 'ACTIVE'").fetchone()[0]
    out = f"{final} and s.game not in ({', '.join(repr(x) for x in sorted(games))})" if games else final
    cur = con.execute(f"""select s.game as gid, strftime(g.tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time, s.team, s.assist_player::varchar as passer,
                                 s.player::varchar as scorer, s.pts from shots s {out} and s.made and s.assist_player is not null
                          order by g.tipoff_utc, s.game, s.action""")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()], games, len(bad), lines


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "shots.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    skip = quarantine.held(wh, "assists", gate="assists")
    rows, bad, n, lines = from_warehouse(wh, skip)
    for g, r in sorted(bad.items()):
        print(f"WARN game {g}: assist credits differ from the box score, left out of the pairs: {r}")
    held = bad if n > allowed(lines) else {}
    quarantine.record(wh, "assists", {g: ("assists", f"assist credits differ from the box score: {r}") for g, r in held.items()})
    write_assists(out, load_teams(), rows)
    print(f"{SEASON}: assist pairs written to {os.path.join(out, 'assists')}; {len(bad)} games left out ({n} player-games differ, "
          f"{allowed(lines)} allowed), {len(held)} quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
