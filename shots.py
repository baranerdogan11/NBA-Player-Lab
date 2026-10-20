"""The shot charts' JSON: every field-goal attempt of the season's regular-season finals, by club and shooter.

Files under <out>/shots/ (out is teams/<season>/):
  <CODE>.json  {"code", "games": [gid, ...], "players": {pid: [[g, x, y, made], ...]}}, the club's shots in game order:
               g indexes games, x and y are the spot in tenths of a foot from the rim (the CDN's xLegacy and yLegacy:
               x > 0 is the shooter's right as he faces the basket, y grows away from the baseline), made is 1 or 0.
A player traded mid-season has shots in each club's file, under the club he shot for.

from_warehouse() reads warehouse/<season>/shots.parquet (warehouse.py) and checks every player's attempts and makes per
game against his box-score line, so a chart always holds the shots of the FG column beside it.
usage: python shots.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/shots/)
"""
import json
import os


def write_shots(out, teams, shots):
    """teams: site_data.load_teams() rows. shots: gid, time (tip-off, for game order), team, pid, x, y, made."""
    by_team = {t["code"]: [] for t in teams}
    for s in shots:
        by_team[s["team"]].append(s)
    os.makedirs(os.path.join(out, "shots"), exist_ok=True)
    for code, rows in by_team.items():
        rows.sort(key=lambda s: (s["time"], s["gid"]))
        games = list(dict.fromkeys(s["gid"] for s in rows))
        g = {gid: i for i, gid in enumerate(games)}
        players = {}
        for s in rows:
            players.setdefault(str(s["pid"]), []).append([g[s["gid"]], int(s["x"]), int(s["y"]), 1 if s["made"] else 0])
        with open(os.path.join(out, "shots", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "players": players}, f, separators=(",", ":"))


def from_warehouse(wh):
    """shots for write_shots() from the Parquet tables in the directory wh; raises if a player's shots in a game do not
    add up to his box-score FGM-FGA."""
    import duckdb
    con = duckdb.connect()
    for t in ("games", "box", "shots"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    final = "join games g using (game) where g.game_type = 'regular' and g.final"
    bad = con.execute(f"""
        with s as (select s.game, s.player, count(*) as fga, count(*) filter (where s.made) as fgm from shots s {final} group by all),
             b as (select b.game, b.player, b.fga, b.fgm from box b {final} and b.status = 'ACTIVE' and b.fga > 0)
        select coalesce(s.game, b.game), coalesce(s.player, b.player), s.fgm, s.fga, b.fgm, b.fga
        from s full join b using (game, player) where s.fga is distinct from b.fga or s.fgm is distinct from b.fgm""").fetchall()
    if bad:
        raise ValueError(f"{len(bad)} player-games whose shots differ from the box score, e.g. game {bad[0][0]} player {bad[0][1]}: "
                         f"shots {bad[0][2]}-{bad[0][3]}, box {bad[0][4]}-{bad[0][5]}")
    cur = con.execute(f"""select s.game as gid, strftime(g.tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time, s.team, s.player::varchar as pid,
                                 s.x, s.y, s.made from shots s {final} and s.x is not null and s.y is not null order by g.tipoff_utc, s.game, s.action""")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "shots.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    write_shots(out, load_teams(), from_warehouse(wh))
    print(f"{SEASON}: shot charts written to {os.path.join(out, 'shots')}")
