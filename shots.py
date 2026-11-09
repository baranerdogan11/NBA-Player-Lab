"""The shot charts' JSON: every field-goal attempt of the season's regular-season finals, by club and shooter.

Files under <out>/shots/ (out is teams/<season>/):
  <CODE>.json  {"code", "games": [gid, ...], "players": {pid: [[g, x, y, made, zone, type, dist], ...]}}, the club's shots in game order:
               g indexes games, x and y are the spot in tenths of a foot from the rim (the CDN's xLegacy and yLegacy:
               x > 0 is the shooter's right as he faces the basket, y grows away from the baseline; null when the feed has
               no spot, so the chart leaves it out but the zones still count it), made is 1 or 0, zone indexes ZONES and
               type indexes TYPES (how the shot came, from the feed's subType and descriptor); dist is how far out he shot from, in
               tenths of a foot (the feed's shotDistance, rounded; from the spot where the feed has none), and band(dist, zone)
               puts it in BANDS.
  league.json  {"zones": [[fgm, fga], ...], "types": [[fgm, fga], ...], "bands": [[fgm, fga], ...], "dist": tenths,
               "players": {pid: [fga, dist, fgm 27+, fga 27+]}, "teams": {CODE: {"for": [[fgm, fga], ...], "against": [[fgm, fga], ...]}}}: every
               club's attempts by zone, in ZONES order, by type, in TYPES order, and by distance band, in BANDS order, with the sum of
               their distances; each player's attempts, distances and threes from 27 feet out over all his clubs; then each club's own
               (its file's) attempts by zone and its opponents' in its games.
A player traded mid-season has shots in each club's file, under the club he shot for.

from_warehouse() reads warehouse/<season>/shots.parquet (warehouse.py) and checks every player's attempts and makes per
game against his box-score line, threes against his 3P line, so a chart always holds the shots of the FG column beside it
and its two three-point zones add up to the 3P column. Every shot takes exactly one type, so a player's types in a game
add up to his FGM-FGA too; check_types() checks that on the files as written, and check_bands() that his distance bands
add up to his FGM-FGA and the three-point bands to his 3PM-3PA. A game that fails is quarantined (quarantine.py) and left out of
the charts, as is a game an earlier gate holds; the run fails only when the quarantine is systemic.
usage: python shots.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/shots/)
"""
import json
import math
import os

import quarantine
from rounding import rnd

ZONES = ("Restricted area", "Paint", "Mid-range", "Corner 3", "Above the break 3")
TYPES = ("Pull-ups and step-backs", "Other jumpers", "Floaters", "Drives and layups", "Hooks", "Cuts and alley-oops",
         "Putbacks and tips", "Dunks")

# how far out, in feet: four bands of twos and three of threes, so the twos' bands add up to 2P and the threes' to 3P; a
# two from 16 feet out runs to the arc, a three from inside 27 feet is "arc to 27" (deep threes start at 27 feet, a
# convention, as the NBA's own tracking draws no line there)
BANDS = ("0-3 ft", "3-10 ft", "10-16 ft", "16 ft to the arc", "Arc to 27 ft", "27-30 ft", "30+ ft")
DEEP = 270   # tenths of a foot: a three from here out is a deep three


def band(dist, z):
    """The index in BANDS of a shot dist tenths of a foot out, in zone z (zones 3 and 4 are the threes)."""
    if z >= 3:
        return 4 if dist < DEEP else 5 if dist < 300 else 6
    return 0 if dist < 30 else 1 if dist < 100 else 2 if dist < 160 else 3


def feet(dist, x, y):
    """The shot's distance in tenths of a foot, rounded by the site's rule: the feed's shotDistance (feet), or the spot's
    distance from the rim (x, y in tenths of a foot) where the feed gives none; None with neither."""
    if dist is None:
        if x is None or y is None:
            return None
        dist = math.hypot(x, y) / 10
    return round(rnd(dist, 1) * 10)


def kind(sub, desc):
    """The shot's index in TYPES from the feed's subType (Jump Shot, Layup, DUNK, Hook) and descriptor ("pullup", "driving
    floating bank", ...): every dunk is a dunk, then the putbacks and tips, cuts and alley-oops, floaters, pull-ups and
    step-backs, other jump shots (the feed does not say catch-and-shoot, so untagged ones stay "other"), hooks, and every
    other layup (driving, running, reverse) is a drive or layup. An unknown subType counts as a jump shot."""
    sub, desc = (sub or "").lower(), (desc or "").lower()
    if sub == "dunk":
        return 7
    if "putback" in desc or "tip" in desc:
        return 6
    if "cutting" in desc or "alley-oop" in desc:
        return 5
    if "floating" in desc:
        return 2
    if sub == "layup":
        return 3
    if sub == "hook":
        return 4
    return 0 if "pullup" in desc or "step back" in desc else 1


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
    and the feed's area, sub_type, descriptor and distance in feet (or none)."""
    by_team = {t["code"]: [] for t in teams}
    for s in shots:
        by_team[s["team"]].append(s)
    os.makedirs(os.path.join(out, "shots"), exist_ok=True)
    league, types, bands, dist, who = [[0, 0] for _ in ZONES], [[0, 0] for _ in TYPES], [[0, 0] for _ in BANDS], 0, {}
    side = {code: {"for": [[0, 0] for _ in ZONES], "against": [[0, 0] for _ in ZONES]} for code in by_team}
    clubs = {}
    for s in shots:
        clubs.setdefault(s["gid"], set()).add(s["team"])
    if any(len(c) != 2 for c in clubs.values()):
        raise ValueError(f"games without two clubs' shots: {sorted(g for g, c in clubs.items() if len(c) != 2)[:5]}")
    for code, rows in by_team.items():
        rows.sort(key=lambda s: (s["time"], s["gid"]))
        games = list(dict.fromkeys(s["gid"] for s in rows))
        g = {gid: i for i, gid in enumerate(games)}
        players = {}
        for s in rows:
            x, y = (None, None) if s["x"] is None or s["y"] is None else (int(s["x"]), int(s["y"]))
            z, k, made = zone(s["pts"], s.get("area"), x, y), kind(s.get("sub_type"), s.get("descriptor")), 1 if s["made"] else 0
            d = feet(s.get("distance"), x, y)
            if d is None:
                raise ValueError(f"game {s['gid']} player {s['pid']}: a shot with neither a distance nor a spot")
            b = band(d, z)
            for c in (league[z], types[k], bands[b]):
                c[0] += made
                c[1] += 1
            dist += d
            w = who.setdefault(str(s["pid"]), [0, 0, 0, 0])
            w[0], w[1] = w[0] + 1, w[1] + d
            if b >= 5:
                w[2], w[3] = w[2] + made, w[3] + 1
            side[code]["for"][z][0] += made
            side[code]["for"][z][1] += 1
            for opp in clubs[s["gid"]] - {code}:
                side[opp]["against"][z][0] += made
                side[opp]["against"][z][1] += 1
            players.setdefault(str(s["pid"]), []).append([g[s["gid"]], x, y, made, z, k, d])
        with open(os.path.join(out, "shots", f"{code}.json"), "w") as f:
            json.dump({"code": code, "games": games, "players": players}, f, separators=(",", ":"))
    with open(os.path.join(out, "shots", "league.json"), "w") as f:
        json.dump({"zones": league, "types": types, "bands": bands, "dist": dist, "players": dict(sorted(who.items())), "teams": side}, f,
                  separators=(",", ":"))


class Mismatch(ValueError):
    """Shots that differ from the box score; games: {game id: what differs}."""
    def __init__(self, msg, games):
        super().__init__(msg)
        self.games = games


def from_warehouse(wh, skip=()):
    """shots for write_shots() from the Parquet tables in the directory wh, leaving out the games in skip; raises
    Mismatch if a player's shots in a game do not add up to his box-score FGM-FGA, or his threes to his 3PM-3PA, or a
    shot has neither a distance nor a spot."""
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
    far = con.execute(f"select s.game, any_value(s.player) from shots s {final} and s.distance is null and (s.x is null or s.y is null) group by all order by 1").fetchall()
    if far:
        raise Mismatch(f"{len(far)} games with a shot of no distance and no spot, e.g. game {far[0][0]} player {far[0][1]}",
                       {g: f"player {p}: a shot of no distance and no spot" for g, p in far})
    cur = con.execute(f"""select s.game as gid, strftime(g.tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as time, s.team, s.player::varchar as pid,
                                 s.x, s.y, s.made, s.pts, s.area, s.sub_type, s.descriptor, s.distance from shots s {final} order by g.tipoff_utc, s.game, s.action""")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def check_types(out, box):
    """Raises ValueError unless every player's shots by type in the files under <out>/shots/ add up, game by game, to his
    box-score FGM-FGA, and the league's types to its zones. box: {(gid, pid): (fgm, fga)} of the games the files hold."""
    got = {}
    for name in sorted(os.listdir(os.path.join(out, "shots"))):
        if name == "league.json":
            continue
        f = json.load(open(os.path.join(out, "shots", name)))
        for pid, rows in f["players"].items():
            for r in rows:
                if not 0 <= r[5] < len(TYPES):
                    raise ValueError(f"{name}: player {pid} has a shot of no type: {r}")
                c = got.setdefault((f["games"][r[0]], pid), [[0, 0] for _ in TYPES])[r[5]]
                c[0] += r[3]
                c[1] += 1
    sums = {k: (sum(m for m, _ in v), sum(a for _, a in v)) for k, v in got.items()}
    want = {k: tuple(v[:2]) for k, v in box.items() if v[1]}
    if sums != want:
        k = next(k for k in sorted(set(sums) | set(want)) if sums.get(k) != want.get(k))
        raise ValueError(f"shot types differ from the box score, e.g. game {k[0]} player {k[1]}: types {sums.get(k)}, box {want.get(k)}")
    league = json.load(open(os.path.join(out, "shots", "league.json")))
    if [sum(c) for c in zip(*league["types"])] != [sum(c) for c in zip(*league["zones"])]:
        raise ValueError(f"league shot types {league['types']} do not add up to its zones {league['zones']}")


def check_bands(out, box):
    """Raises ValueError unless every shot in the files under <out>/shots/ has a distance, every player's distance bands add
    up, game by game, to his box-score FGM-FGA and the three-point bands to his 3PM-3PA, and league.json's bands, distances
    and players are those of the files, its two-point bands its two-point zones and its three-point bands its threes.
    box: {(gid, pid): (fgm, fga, fg3m, fg3a)} of the games the files hold."""
    got, bands, dist, who = {}, [[0, 0] for _ in BANDS], 0, {}
    for name in sorted(os.listdir(os.path.join(out, "shots"))):
        if name == "league.json":
            continue
        f = json.load(open(os.path.join(out, "shots", name)))
        for pid, rows in f["players"].items():
            for r in rows:
                if len(r) < 7 or not isinstance(r[6], int) or r[6] < 0:
                    raise ValueError(f"{name}: player {pid} has a shot of no distance: {r}")
                b, c = band(r[6], r[4]), got.setdefault((f["games"][r[0]], pid), [0, 0, 0, 0])
                c[0], c[1] = c[0] + r[3], c[1] + 1
                if b >= 4:
                    c[2], c[3] = c[2] + r[3], c[3] + 1
                bands[b][0] += r[3]
                bands[b][1] += 1
                dist += r[6]
                w = who.setdefault(pid, [0, 0, 0, 0])
                w[0], w[1] = w[0] + 1, w[1] + r[6]
                if b >= 5:
                    w[2], w[3] = w[2] + r[3], w[3] + 1
    got = {k: tuple(v) for k, v in got.items()}
    want = {k: tuple(v) for k, v in box.items() if v[1]}
    if got != want:
        k = next(k for k in sorted(set(got) | set(want)) if got.get(k) != want.get(k))
        raise ValueError(f"shot distance bands differ from the box score, e.g. game {k[0]} player {k[1]}: bands (FG, 3P) {got.get(k)}, box {want.get(k)}")
    league = json.load(open(os.path.join(out, "shots", "league.json")))
    if league["bands"] != bands or league["dist"] != dist or league["players"] != who:
        raise ValueError("league.json distance bands, distances or players are not those of the club files")
    z = league["zones"]
    split = lambda rows, cut: [[sum(c[i] for c in rows[:cut]) for i in (0, 1)], [sum(c[i] for c in rows[cut:]) for i in (0, 1)]]
    if split(bands, 4) != split(z, 3):
        raise ValueError(f"league distance bands {bands} do not split into its twos and threes {z}")


def box_lines(wh, games):
    """{(gid, pid): (fgm, fga, fg3m, fg3a)} of the ACTIVE box lines of the given games, from the warehouse directory wh."""
    import duckdb
    if not games:
        return {}
    rows = duckdb.connect().execute(f"""select game, player::varchar, fgm, fga, fg3m, fg3a from read_parquet('{os.path.join(wh, "box.parquet")}')
                                        where status = 'ACTIVE' and game in ({', '.join(repr(g) for g in sorted(games))})""").fetchall()
    return {(g, p): tuple(r) for g, p, *r in rows}


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
    box = box_lines(wh, {s["gid"] for s in shots})
    check_types(out, box)
    check_bands(out, box)
    print(f"{SEASON}: shot charts written to {os.path.join(out, 'shots')}; {len(bad)} games quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
