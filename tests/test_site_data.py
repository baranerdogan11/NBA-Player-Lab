"""The site's JSON.

The files written from the fixture league agree with each other: every box score adds up to its final, every player's
log is his box lines, the leaders' totals are the sums of the logs, and each club's ratings totals are its box scores'
and the sums of its lineup rows.
usage: python tests/test_site_data.py
"""
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures"))
import site_fixture  # noqa: E402
from rounding import rnd  # noqa: E402
from site_data import RT, STATS, check_ratings, write_lineups, write_ratings, write_site  # noqa: E402

checks = {}
out = tempfile.mkdtemp()
teams, players, games, lines = site_fixture.make(random.Random(7))
write_site(out, "2026-27", "2026-27", "2026-10-26T06:00:00Z", teams, players, games, lines)


def load(name):
    return json.load(open(os.path.join(out, name)))


idx, sched, lead = load("index.json"), load("games.json")["games"], load("leaders.json")["players"]
finals = [g for g in sched if g["hs"] is not None]
checks["index lists 30 clubs with two colours"] = len(idx["teams"]) == 30 and all(len(t["colors"]) == 2 for t in idx["teams"])
checks["index carries each club's NBA team id for its logo"] = all(isinstance(t["id"], int) and t["id"] > 1610612736 for t in idx["teams"])
checks["club games played match the finals"] = all(t["gp"] == sum(t["code"] in (g["home"], g["away"]) for g in finals) for t in idx["teams"])
boxes = {g["gid"]: load(os.path.join("games", f"{g['gid']}.json")) for g in finals}
checks["every box score adds up to its final"] = all(
    sum(x["pts"] for x in b["box"][b["home"]]) == b["hs"] and sum(x["pts"] for x in b["box"][b["away"]]) == b["as"]
    and sum(p[0] for p in b["periods"]) == b["hs"] and sum(p[1] for p in b["periods"]) == b["as"] for b in boxes.values())
logs = {p["pid"]: p["log"] for t in idx["teams"] for p in load(f"{t['code']}.json")["players"]}
line = {(gid, x["pid"]): x for gid, b in boxes.items() for side in b["box"].values() for x in side}
checks["every log row is the player's box line"] = all(
    all(r[k] == line[(r["gid"], pid)][k] for k in [*STATS, "sec", "start"]) for pid, log in logs.items() for r in log)
checks["leaders' totals are the sums of the logs"] = all(
    p["gp"] == sum(r["sec"] > 0 for r in logs[p["pid"]]) and all(p[k] == sum(r[k] for r in logs[p["pid"]] if r["sec"] > 0) for k in STATS)
    for p in lead)
box_of = {(gid, x["pid"]): side for b in boxes.values() for side in b["box"].values() for x in side for gid in [b["gid"]]}
checks["usage totals are his clubs' totals over his games"] = all(
    p[f"tm_{k}"] == sum(sum(y[k] for y in box_of[(r["gid"], p["pid"])]) for r in logs[p["pid"]] if r["sec"] > 0)
    for p in lead for k in ("fga", "fta", "tov", "sec"))
src = {p["pid"]: p for p in players}
checks["RAPM is written once rounded, null without one"] = all(
    (p["rapm"], p["orapm"], p["drapm"]) == ((rnd(src[p["pid"]]["o_rapm"] + src[p["pid"]]["d_rapm"]), rnd(src[p["pid"]]["o_rapm"]), rnd(src[p["pid"]]["d_rapm"]))
                                            if "o_rapm" in src[p["pid"]] else (None, None, None)) for p in lead) and any(p["rapm"] is None for p in lead)

units = site_fixture.stints(games, lines)
write_lineups(out, teams, units)
write_ratings(out, teams, site_fixture.team_lines(games, lines))
rt = {c["code"]: c for c in load("ratings.json")["teams"]}
side_tot = lambda gid, code: {k: sum(x[k] for x in boxes[gid]["box"][code]) for k in RT}  # noqa: E731
checks["ratings totals are each club's box scores and its opponents'"] = len(rt) == 30 and all(
    c["gp"] == t["gp"] and c["sec"] == 14400 * t["gp"]
    and all(c["for"][k] == sum(side_tot(g, t["code"])[k] for g, b in boxes.items() if t["code"] in (b["home"], b["away"])) for k in RT)
    and all(c["against"][k] == sum(side_tot(g, b["away"] if b["home"] == t["code"] else b["home"])[k] for g, b in boxes.items()
                                   if t["code"] in (b["home"], b["away"])) for k in RT)
    for t in idx["teams"] for c in [rt[t["code"]]])


def gate():
    try:
        check_ratings(out)
        return True
    except ValueError:
        return False


checks["the ratings gate passes when the lineups add up to the box scores"] = gate()
units[0]["tov"] += 1   # a turnover the box score does not have
write_lineups(out, teams, units)
checks["the ratings gate fails when a club's lineups do not"] = not gate()

for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
