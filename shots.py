"""The shot charts' JSON: every field-goal attempt of the season's regular-season finals, by club and shooter.

Files under <out>/shots/ (out is teams/<season>/):
  <CODE>.json  {"code", "games": [gid, ...], "players": {pid: [[g, x, y, made, zone], ...]}}, the club's shots in game order:
               g indexes games, x and y are the spot in tenths of a foot from the rim (the CDN's xLegacy and yLegacy:
               x > 0 is the shooter's right as he faces the basket, y grows away from the baseline; null when the feed has
               no spot, so the chart leaves it out but the zones still count it), made is 1 or 0, zone indexes ZONES.
  league.json  {"zones": [[fgm, fga], ...]}, every club's attempts by zone, in ZONES order.
A player traded mid-season has shots in each club's file, under the club he shot for.

from_warehouse() reads warehouse/<season>/shots.parquet (warehouse.py) and checks every player's attempts and makes per
game against his box-score line, threes against his 3P line, so a chart always holds the shots of the FG column beside it
and its two three-point zones add up to the 3P column. A game that fails is quarantined (quarantine.py) and left out of
the charts, as is a game an earlier gate holds; the run fails only when the quarantine is systemic.
usage: python shots.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/shots/)
"""
import json
import os
import quarantine

ZONES = ("Restricted area", "Paint", "Mid-range", "Corner 3", "Above the break 3")


def zone(pts, area, x, y):
    """The shot's index in ZONES: a three by the play's shot value, so the threes are the box score's 3PA, then the feed's
    area name; the spot (court lines in tenths of a foot) only where the feed names no area."""
    if pts == 3:
        if area:
            return 3 if "Corner" in area else 4
        return 3 if x is not None and abs(x) >= 220 and y <= 89 else 4
    if area:
        return 0 if area == "Restricted Area" else 1 if area.startswith("In The Paint") else 2
    if x is None or y is None:
        return 2
    return 0 if x * x + y * y <= 1600 else 1 if abs(x) <= 80 and y <= 137 else 2


def write_shots(out, teams, shots):
    """teams: site_data.load_teams() rows. shots: gid, time (tip-off, for game order), team, pid, x, y, made, pts (2 or 3)
    and the feed's area (or none)."""
    by_team = {t["code"]: [] for t in teams}
    for s in shots:
        by_team[s["team"]].append(s)
    os.makedirs(os.path.join(out, "shots"), exist_ok=True)
    league = [[0, 0] for _ in ZONES]
    for code, rows in by_team.items():
        rows.sort(key=lambda s: (s["time"], s["gid"]))
        games = list(dict.fromkeys(s["gid"] for s in rows))
        g = {gid: i for i, gid in enumerate(games)}
        players = {}
        for s in rows:
            x, y = (None, None) if s["x"] is None or s["y"] is None else (int(s["x"]), int(s["y"]))
            z, made = zone(s["pts"], s.get("area"), x, y), 1 if s["made"] else 0
            league[z][0] += made
            league[z][1] += 1
            players.setdefault(str(s["pid"]), []).append([g[s["gid"]], x, y, made, z])
        with open(os.path.join(out, "shots", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "players": players}, f, separators=(",", ":"))
    with open(os.path.join(out, "shots", "league.json"), "w") as f:
        json.dump({"zones": league}, f, separators=(",", ":"))


class Mismatch(ValueError):
    """Shots that differ from the box score; games: {game id: what differs}."""
    def __init__(self, msg, games):
        super().__init__(msg)
        self.games = games


def from_warehouse(wh, skip=()):
    """shots for write_shots() from the Parquet tables in the directory wh, leaving out the games in skip; raises
    Mismatch if a player's shots in a game do not add up to his box-score FGM-FGA, or his threes to his 3PM-3PA."""
    import duckdb
    con = duckdb.connect()
    for t in ("games", "box", "shots"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    final = "join games g using (game) where g.game_type = 'regular' and g.final" + \
        (f" and g.game not in ({', '.join(repr(x) for x in sorted(skip))})" if skip else "")
    bad = con.execute(f"""
        with s as (select s.game, s.player, count(*) as fga, count(*) filter (where s.made) as fgm, count(*) filter (where s.pts = 3) as fg3a,
                          count(*) filter (where s.made and s.pts = 3) as fg3m from shots s {final} group by all),
             b as (select b.game, b.player, b.fga, b.fgm, b.fg3a, b.fg3m from box b {final} and b.status = 'ACTIVE' and b.fga > 0)
        select coalesce(s.game, b.game), coalesce(s.player, b.player), s.fgm, s.fga, b.fgm, b.fga, s.fg3m, s.fg3a, b.fg3m, b.fg3a
        from s full join b using (game, player) where s.fga is distinct from b.fga or s.fgm is distinct from b.fgm
                                                   or s.fg3a is distinct from b.fg3a or s.fg3m is distinct from b.fg3m""").fetchall()
    if bad:
        games = {}
        for r in bad:
            games.setdefault(r[0], f"player {r[1]}: shots {r[2]}-{r[3]} (3P {r[6]}-{r[7]}), box {r[4]}-{r[5]} (3P {r[8]}-{r[9]})")
        raise Mismatch(f"{len(bad)} player-games whose shots differ from the box score, e.g. game {bad[0][0]} player {bad[0][1]}: "
                         f"shots {bad[0][2]}-{bad[0][3]} (3P {bad[0][6]}-{bad[0][7]}), box {bad[0][4]}-{bad[0][5]} (3P {bad[0][8]}-{bad[0][9]})", games)
    cur = con.execute(f"""select s.game as gid, strftime(g.tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time, s.team, s.player::varchar as pid,
                                 s.x, s.y, s.made, s.pts, s.area from shots s {final} order by g.tipoff_utc, s.game, s.action""")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "shots.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    skip, bad = quarantine.held(wh, "shots", gate="shots"), {}
    try:
        shots = from_warehouse(wh, skip)
    except Mismatch as e:
        bad = e.games
        shots = from_warehouse(wh, skip | set(bad))
    quarantine.record(wh, "shots", {g: ("shots", f"shots differ from the box score, e.g. {r}") for g, r in bad.items()})
    write_shots(out, load_teams(), shots)
    print(f"{SEASON}: shot charts written to {os.path.join(out, 'shots')}; {len(bad)} games quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
