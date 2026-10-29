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
from site_data import HIGHS, RT, STATS, check_highs, check_ratings, game_score, write_lineups, write_ratings, write_site  # noqa: E402

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
checks["every log row carries its Game Score"] = all(r["gs"] == game_score(r) for log in logs.values() for r in log)
checks["form totals are his season's and his last five games played"] = all(
    p["gs"] == sum(r["gs"] for r in played) and p["gs5"] == sum(r["gs"] for r in played[-5:]) and p["sec5"] == sum(r["sec"] for r in played[-5:])
    for p in lead for played in [[r for r in logs[p["pid"]] if r["sec"] > 0]])
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


def gate(*held):
    try:
        check_ratings(out, *held)
        return True
    except ValueError:
        return False


checks["the ratings gate passes when the lineups add up to the box scores"] = gate()
gone = units[0]["gid"]
write_lineups(out, teams, [u for u in units if u["gid"] != gone])
checks["a game quarantined out of the lineups is taken off the box totals it is checked against"] = (
    gate(site_fixture.team_lines(games, lines), {gone}) and not gate())
units[0]["tov"] += 1   # a turnover the box score does not have
write_lineups(out, teams, units)
checks["the ratings gate fails when a club's lineups do not"] = not gate()
night, last = load("night.json"), finals[-1]["date"]
best = sorted(((game_score(x), x["name"], x["pid"], b["gid"]) for b in boxes.values() if b["date"] == last
               for side in b["box"].values() for x in side if x["sec"] > 0), key=lambda r: (-r[0], r[1], r[2]))[:5]
checks["the night's best are the latest night's top five Game Scores, from its box scores"] = (
    night["date"] == last and [(r["gs"], r["name"], r["pid"], r["gid"]) for r in night["rows"]] == best)
highs, order = load("highs.json")["stats"], {g["gid"]: i for i, g in enumerate(finals)}
club = {p["pid"]: p["team"] for p in players}
every = [{**x, "gid": b["gid"], "team": c, "gs": game_score(x)} for b in boxes.values() for c, side in b["box"].items() for x in side if x["sec"] > 0]
checks["the season highs are each stat's ten best box-score lines, best first, then the earlier game"] = all(
    [(r["v"], r["gid"], r["pid"], r["team"], r["club"]) for r in highs[k]]
    == [(x[k], x["gid"], x["pid"], x["team"], club[x["pid"]]) for x in sorted((x for x in every if x[k] > 0),
                                                                         key=lambda x: (-x[k], order[x["gid"]], x["gid"], x["name"], x["pid"]))[:10]]
    for k in HIGHS)


def highs_gate():
    try:
        check_highs(out, list(boxes))
        return True
    except ValueError:
        return False


checks["the season highs gate passes on the box scores"] = highs_gate()
hs = load("highs.json")
hs["stats"]["pts"][0]["v"] += 1   # a line the box score does not have
json.dump(hs, open(os.path.join(out, "highs.json"), "w"))
checks["the season highs gate fails on a line the box score does not have"] = not highs_gate()
hs["stats"]["pts"][0]["v"] -= 1
hs["stats"]["reb"].pop(0)        # a better line left off the board
json.dump(hs, open(os.path.join(out, "highs.json"), "w"))
checks["the season highs gate fails when a better line is left off"] = not highs_gate()
checks["Game Score is Hollinger's, in tenths"] = game_score(
    {"pts": 30, "fgm": 11, "fga": 20, "fta": 8, "ftm": 6, "oreb": 2, "dreb": 8, "stl": 2, "ast": 7, "blk": 1, "pf": 3, "tov": 4}) == 258


def calendar(code):
    """cal/<CODE>.ics unfolded into its events, each a dict of its properties; None unless every line ends in CRLF and
    is at most 75 octets."""
    raw = open(os.path.join(out, "cal", f"{code}.ics"), "rb").read()
    if not raw.endswith(b"\r\n") or any(len(x) > 75 or x.endswith(b"\r") or b"\n" in x for x in raw.split(b"\r\n")):
        return None
    lines = raw.decode().replace("\r\n ", "").split("\r\n")[:-1]
    if lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        return None
    evs = []
    for x in lines:
        k, _, v = x.partition(":")
        if x == "BEGIN:VEVENT":
            evs.append({})
        elif evs and x != "END:VEVENT":
            evs[-1][k] = v
    return evs


cals = {t["code"]: calendar(t["code"]) for t in idx["teams"]}
checks["every club's calendar is well-formed iCalendar (CRLF, folded at 75 octets)"] = all(c is not None for c in cals.values())
checks["each calendar has one event per game of that club, in the schedule's order, UID by gid"] = all(
    [e["UID"] for e in cals[c]] == [f"{g['gid']}@nba-player-lab" for g in sched if c in (g["home"], g["away"])] for c in cals)
team_name = {t["code"]: t["name"] for t in idx["teams"]}
by_uid = {f"{g['gid']}@nba-player-lab": g for g in sched}
checks["each event starts at the game's tip-off in UTC and is titled away @ home"] = all(
    e["DTSTART"] == by_uid[e["UID"]]["time"].replace("-", "").replace(":", "") and e["DTSTART"].endswith("Z")
    and e["SUMMARY"] == f"{team_name[by_uid[e['UID']]['away']]} @ {team_name[by_uid[e['UID']]['home']]}" for c in cals for e in cals[c])
checks["a final's event carries its score and every event links its game page"] = all(
    e["URL"].endswith(f"?l#game/{by_uid[e['UID']]['gid']}")
    and (by_uid[e["UID"]]["hs"] is None or f"{by_uid[e['UID']]['as']}\\, " in e["DESCRIPTION"] and e["DESCRIPTION"].startswith("Final: "))
    for c in cals for e in cals[c])

for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
