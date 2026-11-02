"""Assist pairs and assisted makes: who set up whose baskets, and which baskets nobody set up, from the play-by-play's
assist credits, by club, game, player and shot zone.

<out>/assists/<CODE>.json  {"code", "games": [gid, ...], "pairs": [[g, passer, scorer, ast, pts], ...],
                            "made": [[g, pid, zone, ast, fgm], ...]}
  g indexes games (the club's finals in game order). A pair's ast counts the passer's assists on the scorer's baskets in
  that game and pts the points those baskets made (2 or 3 each). A made row's fgm counts the player's made field goals in
  one zone (shots.ZONES) of that game and ast how many of them a team-mate is credited with setting up; fgm - ast are his
  unassisted makes (putbacks included). Season numbers are the sums over the games, done by the page.
<out>/assists/league.json  {"zones": [[ast, fgm], ...], "players": {pid: [ast, fgm]}}: the same counts over every club,
  by zone in ZONES order and by player (a traded player's clubs summed).
Both come from the same baskets, so a scorer's assisted makes in a game are the pairs naming him as scorer.

from_warehouse() reads every made field goal of warehouse/<season>/shots.parquet that names an assist and checks each
player's assists per game against his box-score AST, so a passer's pairs in a game always add up to the AST beside them.
The box score takes the league's post-game stat corrections and the play-by-play does not (an assist moved to a
team-mate), so a game whose credits differ is left out of the pairs; up to one differing player-game per thousand box
lines (at least two) is such a correction and only reported. More than that is a feed problem: those games are
quarantined (quarantine.py) and the run fails when the quarantine is systemic. Each player's makes in a game are checked
against his box-score FGM, and his three-point zones against his 3PM, so his assisted and unassisted makes always add up
to the FG column. A game an earlier gate holds out of the pairs or the shot charts is left out.
usage: python assists.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/assists/)
"""
import json
import os
import quarantine
from shots import ZONES


def write_assists(out, teams, rows):
    """teams: site_data.load_teams() rows. rows: one per made field goal with gid, time (tip-off, for game order), team,
    scorer, pts (2 or 3), zone (index in shots.ZONES) and passer (none when unassisted)."""
    by_team = {t["code"]: [] for t in teams}
    for r in rows:
        by_team[r["team"]].append(r)
    os.makedirs(os.path.join(out, "assists"), exist_ok=True)
    league, players = [[0, 0] for _ in ZONES], {}
    for code, rs in by_team.items():
        rs.sort(key=lambda r: (r["time"], r["gid"]))
        games = list(dict.fromkeys(r["gid"] for r in rs))
        g = {gid: i for i, gid in enumerate(games)}
        pairs, made = {}, {}
        for r in rs:
            a = r["passer"] is not None
            if a:
                p = pairs.setdefault((g[r["gid"]], str(r["passer"]), str(r["scorer"])), [0, 0])
                p[0] += 1
                p[1] += int(r["pts"])
            for c in (made.setdefault((g[r["gid"]], str(r["scorer"]), int(r["zone"])), [0, 0]), league[int(r["zone"])],
                      players.setdefault(str(r["scorer"]), [0, 0])):
                c[0] += a
                c[1] += 1
        with open(os.path.join(out, "assists", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "pairs": [[*k, *v] for k, v in sorted(pairs.items())],
                       "made": [[*k, *v] for k, v in sorted(made.items())]}, f, separators=(",", ":"))
    with open(os.path.join(out, "assists", "league.json"), "w") as f:
        json.dump({"zones": league, "players": dict(sorted(players.items()))}, f, separators=(",", ":"))


def allowed(lines):
    """The post-game corrections tolerated in a season of so many box lines, as in warehouse_tests.py."""
    return max(2, lines // 1000)


def from_warehouse(wh, skip=()):
    """(rows for write_assists(), {game: what differs}, player-games that differ, box lines checked) from the Parquet
    tables in the directory wh; the games in skip and the games whose credits or makes differ from the box score are
    left out."""
    from shots import zone
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
    bad += con.execute(f"""
        with s as (select s.game, s.player, count(*) as fgm, count(*) filter (where s.pts = 3) as fg3m from shots s {final} and s.made group by all),
             b as (select b.game, b.player, b.fgm, b.fg3m from box b {final} and b.status = 'ACTIVE' and b.fgm > 0)
        select coalesce(s.game, b.game), coalesce(s.player, b.player), s.fgm, s.fg3m, b.fgm, b.fg3m
        from s full join b using (game, player) where s.fgm is distinct from b.fgm or s.fg3m is distinct from b.fg3m order by 1, 2""").fetchall()
    games = {}
    for g, p, *v in bad:
        games.setdefault(g, []).append(f"player {p}: play-by-play {v[0] or 0}, box {v[1] or 0}" if len(v) == 2 else
                                       f"player {p}: makes {v[0] or 0} (3P {v[1] or 0}), box FGM {v[2] or 0} (3P {v[3] or 0})")
    games = {g: "; ".join(rs) for g, rs in games.items()}
    lines = con.execute(f"select count(*) from box b {final} and b.status = 'ACTIVE'").fetchone()[0]
    out = f"{final} and s.game not in ({', '.join(repr(x) for x in sorted(games))})" if games else final
    cur = con.execute(f"""select s.game as gid, strftime(g.tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time, s.team, s.assist_player::varchar as passer,
                                 s.player::varchar as scorer, s.pts, s.area, s.x, s.y from shots s {out} and s.made
                          order by g.tipoff_utc, s.game, s.action""")
    cols = [c[0] for c in cur.description]
    rows = []
    for r in cur.fetchall():
        r = dict(zip(cols, r))
        x, y = r.pop("x"), r.pop("y")
        x, y = (None, None) if x is None or y is None else (int(x), int(y))
        r["zone"] = zone(r["pts"], r.pop("area"), x, y)
        rows.append(r)
    return rows, games, len(bad), lines


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "shots.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    skip = quarantine.held(wh, "assists", gate="assists") | quarantine.held(wh, "shots")
    rows, bad, n, lines = from_warehouse(wh, skip)
    for g, r in sorted(bad.items()):
        print(f"WARN game {g}: assist credits or makes differ from the box score, left out: {r}")
    held = bad if n > allowed(lines) else {}
    quarantine.record(wh, "assists", {g: ("assists", f"assist credits or makes differ from the box score: {r}") for g, r in held.items()})
    write_assists(out, load_teams(), rows)
    print(f"{SEASON}: assist pairs and assisted makes written to {os.path.join(out, 'assists')}; {len(bad)} games left out ({n} player-games differ, "
          f"{allowed(lines)} allowed), {len(held)} quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
