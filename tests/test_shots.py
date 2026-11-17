"""shots.py: the shot files read from the warehouse are the shot files written from the same shots directly, a
player-game whose shots differ from his box-score line (FG or 3P) stops the build, and the zones split the FG column
along the 3P column and the shot types and distance bands split it again.
usage: python tests/test_shots.py
"""
import filecmp
import json
import math
import os
import random
import sys
import tempfile

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures"))
import site_fixture  # noqa: E402
from shots import BANDS, TYPES, ZONES, band, check_bands, check_context, check_types, feet, from_warehouse, kind, write_shots, zone  # noqa: E402

teams, players, games, lines = site_fixture.make(random.Random(7))
shots = site_fixture.spots(random.Random(13), games, lines)
first = next(i for i, s in enumerate(shots) if s["pts"] == 2 and zone(2, None, s["x"], s["y"]) != 2)
shots[first]["area"] = "Mid-Range"   # the feed's area names the zone over the spot
direct, wh, read = (tempfile.mkdtemp() for _ in range(3))
write_shots(direct, teams, shots)

home = {g["gid"]: g["home"] for g in games}
side = lambda s: (s["own"], s["opp"]) if s["team"] == home[s["gid"]] else (s["opp"], s["own"])   # score_home, score_away
tables = {
    "games": [{"game": g["gid"], "game_type": "regular", "tipoff_utc": g["time"].rstrip("Z"), "final": g["final"], "home": g["home"], "away": g["away"]} for g in games]
    + [{"game": "0012600001", "game_type": "preseason", "tipoff_utc": "2026-10-10T23:00:00", "final": True, "home": "BOS", "away": "NYK"}],
    "box": [{"game": x["gid"], "player": int(x["pid"]), "status": "ACTIVE", "fga": x["fga"], "fgm": x["fgm"],
             "fg3a": x["fg3a"], "fg3m": x["fg3m"]} for x in lines]
    + [{"game": "0012600001", "player": int(lines[0]["pid"]), "status": "ACTIVE", "fga": 1, "fgm": 1, "fg3a": 0, "fg3m": 0}],
    "shots": [{"game": s["gid"], "action": i, "player": int(s["pid"]), "team": s["team"], "x": s["x"], "y": s["y"], "made": s["made"],
               "pts": s["pts"], "area": s.get("area"), "sub_type": s["sub_type"], "descriptor": s["descriptor"],
               "distance": None if i == 1 else math.hypot(s["x"], s["y"]) / 10, "period": s["period"], "clock": s["clock"],
               "score_home": side(s)[0], "score_away": side(s)[1]} for i, s in enumerate(shots)]   # one from its spot
    + [{"game": "0012600001", "action": 1, "player": int(lines[0]["pid"]), "team": "BOS", "x": 0, "y": 10, "made": True, "pts": 2, "area": None,
        "sub_type": "DUNK", "descriptor": None, "distance": 1.0, "period": 1, "clock": 700.0, "score_home": 2, "score_away": 0}],
}
# the play-by-play: every shot, in clock order, and a period start before each game's first (no score)
tables["events"] = [{"game": s["game"], "action": s["action"], "order_no": round(10 * (1000 * s["period"] - s["clock"])), "score_home": s["score_home"],
                     "score_away": s["score_away"]} for s in tables["shots"]] + [{"game": g, "action": -1, "order_no": -10, "score_home": None, "score_away": None} for g in home]
con = duckdb.connect()


def store(name, rows):
    path = os.path.join(wh, name)
    with open(path + ".jsonl", "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    con.execute(f"copy (select * from read_json_auto('{path}.jsonl')) to '{path}.parquet' (format parquet)")


for name, rows in tables.items():
    store(name, rows)
con.execute(f"copy (select * replace (tipoff_utc::timestamp as tipoff_utc) from '{wh}/games.parquet') to '{wh}/g.parquet' (format parquet)")
os.replace(f"{wh}/g.parquet", f"{wh}/games.parquet")
write_shots(read, teams, from_warehouse(wh))

diff = filecmp.dircmp(os.path.join(direct, "shots"), os.path.join(read, "shots")).diff_files
one = json.load(open(os.path.join(read, "shots", f"{lines[0]['team']}.json")))
mine = [s for s in shots if s["pid"] == lines[0]["pid"] and s["gid"] == lines[0]["gid"]]
files = [json.load(open(os.path.join(read, "shots", f"{t['code']}.json"))) for t in teams]
full = json.load(open(os.path.join(read, "shots", "league.json")))
league, sides = full["zones"], full["teams"]
rows = [r for f in files for p in f["players"].values() for r in p]
zoned = {}
for f in files:
    for pid, rs in f["players"].items():
        for r in rs:
            z = zoned.setdefault((f["games"][r[0]], pid), [0, 0, 0, 0])
            z[0] += r[3]
            z[1] += 1
            z[2] += r[3] if r[4] >= 3 else 0
            z[3] += r[4] >= 3
box = {(x["gid"], x["pid"]): [x["fgm"], x["fga"], x["fg3m"], x["fg3a"]] for x in lines if x["fga"]}
fg = {(x["gid"], x["pid"]): (x["fgm"], x["fga"]) for x in lines}
fg4 = {(x["gid"], x["pid"]): (x["fgm"], x["fga"], x["fg3m"], x["fg3a"]) for x in lines}
fin = {}
for x in lines:
    fin.setdefault(x["gid"], {}).setdefault(x["team"], 0)
    fin[x["gid"]][x["team"]] += x["pts"]


def gate(change, check=check_types, want=fg):
    """check (check_types() or check_bands()) on a copy of the read files with change(files, league) applied: the error, or None."""
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "shots"))
    fs, lg = json.loads(json.dumps(files)), json.loads(json.dumps(full))
    change(fs, lg)
    for f in fs:
        json.dump(f, open(os.path.join(tmp, "shots", f"{f['code']}.json"), "w"))
    json.dump(lg, open(os.path.join(tmp, "shots", "league.json"), "w"))
    try:
        check(tmp, want)
    except ValueError as e:
        return str(e)


def bands(change):
    return gate(change, check_bands, fg4)


def context(change):
    return gate(change, check_context, fin)


def scored(fs, lg):   # a score above the final
    next(p for p in fs[0]["players"].values() if p)[0][9] += 500


def overtime(fs, lg):   # an overtime clock past five minutes
    r = next(p for p in fs[0]["players"].values() if p)[0]
    r[7], r[8] = 5, 3001


def swapped(fs, lg):   # a player's later shot with a lower score than his earlier one
    rows = next(p for p in fs[0]["players"].values() if len(p) > 1 and len({r[0] for r in p}) < len(p))
    a, b = next((a, b) for a, b in zip(rows, rows[1:]) if a[0] == b[0] and (a[9], a[10]) != (b[9], b[10]))
    a[9:11], b[9:11] = b[9:11], a[9:11]


def unscored(fs, lg):   # one game without scores is fine
    p = next(p for p in fs[0]["players"].values() if p)
    for r in p:
        if r[0] == p[0][0]:
            r[9:11] = [None, None]


def drop(fs, lg):
    p = next(p for p in fs[0]["players"].values() if p)
    p.pop()


def untyped(fs, lg):
    next(p for p in fs[0]["players"].values() if p)[0][5] = len(TYPES)


def moved(fs, lg):
    lg["types"][0][1] += 1


def undistanced(fs, lg):
    next(p for p in fs[0]["players"].values() if p)[0][6] = None


def farther(fs, lg):   # a two-point attempt moved to a three-point band: FG still adds up, 3P does not
    r = next(r for p in fs[0]["players"].values() for r in p if r[4] < 3)
    r[4] = 3


def deeper(fs, lg):
    lg["players"][next(iter(lg["players"]))][3] += 1
checks = {
    "zones: a three by its shot value, then the feed's area, then the spot":
        [zone(3, "Left Corner 3", 0, 300), zone(3, "Above the Break 3", 230, 0), zone(3, "Backcourt", 0, 600), zone(3, None, -230, 40),
         zone(3, None, 0, 250), zone(2, "Restricted Area", 100, 100), zone(2, "In The Paint (Non-RA)", 0, 0), zone(2, "Mid-Range", 0, 10),
         zone(2, "Left Corner 3", 230, 0), zone(2, None, 10, 30), zone(2, None, 60, 120), zone(2, None, 150, 50), zone(2, None, None, None)]
        == [3, 4, 4, 3, 4, 0, 1, 2, 2, 0, 1, 2, 2],
    "every player-game's zones add up to his FG and his two three-point zones to his 3P": zoned == box,
    "every zone has shots in the fixture": all(n for _, n in league),
    "the league file is every club's shots by zone": len(league) == len(ZONES)
        and league == [[sum(r[3] for r in rows if r[4] == z), sum(1 for r in rows if r[4] == z)] for z in range(len(ZONES))],
    "a club's own zones are its file's shots": all(sides[f["code"]]["for"] == [[sum(r[3] for p in f["players"].values() for r in p if r[4] == z),
        sum(1 for p in f["players"].values() for r in p if r[4] == z)] for z in range(len(ZONES))] for f in files),
    "a club's zones against are its opponents' shots in its games": all(sides[t["code"]]["against"] == [[sum(s["made"] for s in shots if s["team"] != t["code"]
        and s["gid"] in {x["gid"] for x in games if t["code"] in (x["home"], x["away"])} and zone(s["pts"], s.get("area"), s["x"], s["y"]) == z),
        sum(1 for s in shots if s["team"] != t["code"] and s["gid"] in {x["gid"] for x in games if t["code"] in (x["home"], x["away"])}
            and zone(s["pts"], s.get("area"), s["x"], s["y"]) == z)] for z in range(len(ZONES))] for t in teams),
    "the feed's area wins over the spot": sum(r[4] == 2 for r in files[[t["code"] for t in teams].index(shots[first]["team"])]["players"][shots[first]["pid"]])
        == 1 + sum(zone(s["pts"], None, s["x"], s["y"]) == 2 for s in shots if s["pid"] == shots[first]["pid"]),
    "types: dunks first, then putbacks and tips, cuts and alley-oops, floaters, pull-ups and step-backs, other jumpers, hooks, layups":
        [kind("DUNK", "putback"), kind("Layup", "tip"), kind("Layup", "putback"), kind("Layup", "cutting finger roll"), kind("DUNK", "alley-oop"),
         kind("Layup", "running alley-oop"), kind("Jump Shot", "driving floating bank"), kind("Jump Shot", "running pullup"),
         kind("Jump Shot", "step back bank"), kind("Jump Shot", None), kind("Jump Shot", "fadeaway"), kind("shot", None), kind(None, None),
         kind("Hook", "turnaround"), kind("Hook", "driving"), kind("Layup", "driving"), kind("Layup", "running reverse"), kind("Layup", None)]
        == [7, 6, 6, 5, 7, 5, 2, 0, 0, 1, 1, 1, 1, 4, 4, 3, 3, 3],
    "every shot has a type and every type has shots in the fixture": all(len(r) == 11 and 0 <= r[5] < len(TYPES) for r in rows) and all(n for _, n in full["types"]),
    "the league file is every club's shots by type": full["types"] == [[sum(r[3] for r in rows if r[5] == k), sum(1 for r in rows if r[5] == k)]
                                                                        for k in range(len(TYPES))],
    "a shot's type is its feed subType and descriptor": sorted(r[5] for r in rows) == sorted(kind(s["sub_type"], s["descriptor"]) for s in shots),
    "the type gate passes on the files as written": gate(lambda fs, lg: None) is None,
    "a missing shot stops the type gate": "differ from the box score" in (gate(drop) or ""),
    "a shot of no type stops the type gate": "of no type" in (gate(untyped) or ""),
    "league types that do not add up to its zones stop the type gate": "do not add up" in (gate(moved) or ""),
    "distance: the feed's feet in tenths, rounded half up, else the spot's distance from the rim":
        [feet(9.544, 0, 0), feet(2.25, None, None), feet(0.0, None, None), feet(None, 30, 40), feet(None, -189, 172), feet(None, None, 5)]
        == [95, 23, 0, 50, 256, None],
    "bands: twos by distance up to the arc, threes from the arc, 27 and 30 feet": [band(29, 0), band(30, 1), band(99, 2), band(100, 2),
        band(159, 2), band(160, 2), band(236, 2), band(220, 3), band(269, 4), band(270, 4), band(299, 3), band(300, 4), band(612, 4)]
        == [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6] and len(BANDS) == 7,
    "every shot has a distance, and the league's bands, distances and players are the files'":
        all(len(r) == 11 and isinstance(r[6], int) for r in rows) and full["bands"] == [[sum(r[3] for r in rows if band(r[6], r[4]) == b),
            sum(1 for r in rows if band(r[6], r[4]) == b)] for b in range(len(BANDS))] and full["dist"] == sum(r[6] for r in rows)
        and sum(v[0] for v in full["players"].values()) == len(rows) and sum(v[3] for v in full["players"].values()) == full["bands"][5][1] + full["bands"][6][1],
    "a shot's distance is its spot's in the fixture": sorted(r[6] for r in rows) == sorted(feet(None, s["x"], s["y"]) for s in shots),
    "the fixture has deep threes": full["bands"][5][1] > 0,
    "the band gate passes on the files as written": bands(lambda fs, lg: None) is None,
    "a missing shot stops the band gate": "differ from the box score" in (bands(drop) or ""),
    "a shot of no distance stops the band gate": "of no distance" in (bands(undistanced) or ""),
    "a two in a three-point band stops the band gate": "differ from the box score" in (bands(farther) or ""),
    "league players that are not the files' stop the band gate": "not those of the club files" in (bands(deeper) or ""),
    "every shot has its period, clock in tenths and the score after it, its club first": all(r[7] in (1, 2, 3, 4) and 0 <= r[8] <= 7200 for r in rows)
        and sorted(tuple(r[7:]) for r in rows) == sorted((s["period"], round(s["clock"] * 10), s["own"], s["opp"]) for s in shots)
        and any(r[8] % 10 for r in rows),
    "the context gate passes on the files as written": context(lambda fs, lg: None) is None,
    "a score above the final stops the context gate": "final" in (context(scored) or ""),
    "an overtime clock past five minutes stops the context gate": "tenths of a second" in (context(overtime) or ""),
    "a score that goes down between a player's shots stops the context gate": "goes down" in (context(swapped) or ""),
    "a game with no shot scores passes the context gate": context(unscored) is None,
    "warehouse tables give the same shot files" + (f" (differs: {diff[:5]})" if diff else ""): not diff and len(os.listdir(os.path.join(read, "shots"))) == 31,
    "a player's shots in a game are his box-score FGA, his makes his FGM":
        len(mine) == lines[0]["fga"] and sum(s["made"] for s in mine) == lines[0]["fgm"],
    "the file lists each final once, in game order": one["games"] == sorted(set(one["games"]), key=lambda g: (next(x["time"] for x in games if x["gid"] == g), g)),
}



def stops(name, rows):
    store("shots", rows)
    try:
        from_warehouse(wh)
        checks[name] = False
    except ValueError as e:
        checks[name] = "differ from the box score" in str(e)


i = next(i for i, s in enumerate(tables["shots"]) if s["pts"] == 3)
stops("a three counted as a two stops the build", [{**s, "pts": 2} if j == i else s for j, s in enumerate(tables["shots"])])
stops("a missing shot stops the build", tables["shots"][1:])   # one attempt fewer than the box score
store("shots", [{**s, "x": None, "y": None, "distance": None} if j == 2 else s for j, s in enumerate(tables["shots"])])
try:
    from_warehouse(wh)
    checks["a shot of no distance and no spot stops the build"] = False
except ValueError as e:
    checks["a shot of no distance and no spot stops the build"] = "no distance and no spot" in str(e)

store("shots", tables["shots"])
i = next(i for i, s in enumerate(tables["shots"]) if s["made"] and s["pts"] == 2)
moved = tables["shots"][i]
store("events", [{**e, "score_home": e["score_home"] + 1} if e["game"] == moved["game"] and e["action"] == moved["action"] else e for e in tables["events"]])
got = from_warehouse(wh)
checks["a game whose score does not follow the play-by-play keeps its shots but none of their scores"] = \
    len(got) == len(shots) and {s["gid"] for s in got if s["own"] is None} == {moved["game"]} and all(s["opp"] is None for s in got if s["gid"] == moved["game"])
store("events", tables["events"])
store("shots", [{**s, "clock": 721.0} if j == 3 else s for j, s in enumerate(tables["shots"])])
try:
    from_warehouse(wh)
    checks["a shot with a clock past the quarter stops the build"] = False
except ValueError as e:
    checks["a shot with a clock past the quarter stops the build"] = "no period or clock" in str(e)

for name, ok in checks.items():
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
sys.exit(0 if all(checks.values()) else 1)
