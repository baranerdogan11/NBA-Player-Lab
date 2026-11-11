"""awards.py: the 65-game count, rank points with shared ranks, the pools' floors (pace, rookies, bench, last season),
the blend and its order, Most Improved on shown tenths, the gate refusing a changed file, and the play-by-play counts.
usage: python tests/test_awards.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import awards  # noqa: E402

# the 65-game count: 20 minutes counts, up to two of 15 to 19 minutes
assert awards.counted([1200, 1199, 900, 900, 899, 3000]) == 4
assert awards.counted([]) == 0

# rank points: best 100, last 0, ties share the better rank
assert awards.points({"a": 3, "b": 2, "c": 2, "d": 1}) == {"a": 100, "b": 67, "c": 67, "d": 0}
assert awards.points({"a": 1}) == {"a": 100}

ZERO = dict.fromkeys(["pts", "fgm", "fga", "ftm", "fta", "oreb", "dreb", "stl", "ast", "blk", "pf", "tov"], 0)


def line(pid, sec, pts, start):
    return {**ZERO, "pid": pid, "name": pid, "start": start, "sec": sec, "pts": pts}


def league(tmp, extra=None):
    """Two clubs, ten finals (A wins seven). A1-A3 and B1-B3 play every game; A4 misses four; R1 a rookie, S1 off the
    bench, S2 starts most games."""
    games, box = [], {}
    for i in range(10):
        gid = f"g{i}"
        home_wins = i < 7
        games.append({"gid": gid, "home": "AAA", "away": "BBB", "hs": 100 if home_wins else 90, "as": 90 if home_wins else 100})
        a = [line("A1", 2000, 30, True), line("A2", 1800, 20, True), line("A3", 1500, 10, True), line("R1", 1300, 12, True),
             line("S1", 1250, 15, False)]
        if i >= 4:
            a.append(line("A4", 2200, 25, True))
        b = [line("B1", 2100, 28, True), line("B2", 1700, 18, True), line("B3", 1200, 8, i % 3 == 0), line("S2", 1000, 9, i > 2)]
        box[gid] = {"AAA": a, "BBB": b}
    games.append({"gid": "g10", "home": "AAA", "away": "BBB", "hs": None, "as": None})
    os.makedirs(os.path.join(tmp, "games"))
    json.dump({"games": games}, open(os.path.join(tmp, "games.json"), "w"))
    for gid, b in box.items():
        json.dump({"gid": gid, "box": b}, open(os.path.join(tmp, "games", f"{gid}.json"), "w"))
    rapm = {"A1": 5.0, "A2": 2.0, "A3": 2.0, "A4": 9.0, "R1": 1.0, "S1": 3.0, "B1": 6.0, "B2": 0.5, "B3": -1.0, "S2": 4.0}
    lead = []
    for pid, r in rapm.items():
        ls = [x for b in box.values() for c in b.values() for x in c if x["pid"] == pid]
        lead.append({"pid": pid, "name": pid, "team": "AAA" if pid[0] in "ARS" and pid != "S2" else "BBB", "rookie": pid == "R1",
                     "rapm": r, "gp": len(ls), "sec": sum(x["sec"] for x in ls), "gs": sum(awards.game_score(x) for x in ls)})
    json.dump({"players": lead + (extra or [])}, open(os.path.join(tmp, "leaders.json"), "w"))


with tempfile.TemporaryDirectory() as tmp:
    league(tmp)
    last = {"A1": [70, 70 * 2000, 70 * 250], "A2": [70, 70 * 1800, 70 * 50], "B1": [19, 19 * 2000, 19 * 300], "A3": [40, 40 * 800, 4000]}
    doc = awards.document(tmp, last, "2026-27")
    mvp = [x["pid"] for x in doc["mvp"]]
    # A4 missed four of ten: 6 x 82 < 65 x 10, off the MVP ladder; S2 never plays 15 minutes, counts nothing
    assert "A4" not in mvp and "S2" not in mvp, mvp
    assert set(mvp) == {"A1", "A2", "A3", "R1", "S1", "B1", "B2", "B3"}, mvp
    assert doc["pool"]["mvp"] == 8
    assert mvp[0] == "A1", doc["mvp"]                       # second in impact, first in production, best club
    for x in doc["mvp"]:
        assert x["s"] == 5 * x["c"][0] + 3 * x["c"][1] + 2 * x["c"][2]
    assert [x["s"] for x in doc["mvp"]] == sorted((x["s"] for x in doc["mvp"]), reverse=True)
    # A2 and A3 share a RAPM, so they share its points
    c = {x["pid"]: x["c"] for x in doc["mvp"]}
    assert c["A2"][0] == c["A3"][0]
    assert [x["pid"] for x in doc["roy"]] == ["R1"], doc["roy"]
    # the bench: more games off the bench than starts, 70% of the games, 15 minutes a game (S2 plays 1000 s: out)
    assert [x["pid"] for x in doc["smoy"]] == ["S1", "B3"] or [x["pid"] for x in doc["smoy"]] == ["B3", "S1"], doc["smoy"]
    # Most Improved: B1 had 19 games last season, A3 too few minutes; A2 improved more than A1 declined
    assert [x["pid"] for x in doc["mip"]] == ["A2", "A1"], doc["mip"]
    a2 = doc["mip"][0]
    assert a2["d"] == awards.per36(10 * 200, 18000) - awards.per36(70 * 50, 70 * 1800), a2
    assert a2["last"] == last["A2"]

    awards.check(doc, tmp, last, "2026-27")

    def refused(d, lst=last):
        try:
            awards.check(d, tmp, lst, "2026-27")
        except SystemExit:
            return True
        return False
    assert refused({**doc, "mvp": doc["mvp"][::-1]})                                  # out of order, not what it gives
    assert refused({**doc, "roy": doc["roy"] + [{"pid": "A1", "c": [0, 0, 0], "s": 0, "g": 10}]})
    assert refused(doc, {**last, "A2": [70, 70 * 1800, 70 * 60]})                      # last season changed
    # leaders.json disagreeing with the box scores is refused too
    lead = json.load(open(os.path.join(tmp, "leaders.json")))
    for p in lead["players"]:
        if p["pid"] == "A1":
            p["gs"] += 1
    json.dump(lead, open(os.path.join(tmp, "leaders.json"), "w"))
    assert refused(doc)

# the play-by-play counts behind Game Score
acts = [
    {"game": "g", "action_type": "2pt", "result": "Made", "player": 1, "assist_player": 2, "block_player": None, "sub_type": None},
    {"game": "g", "action_type": "3pt", "result": "Missed", "player": 1, "assist_player": None, "block_player": 3, "sub_type": None},
    {"game": "g", "action_type": "rebound", "result": None, "player": 1, "assist_player": None, "block_player": None, "sub_type": "offensive"},
    {"game": "g", "action_type": "freethrow", "result": "Made", "player": 1, "assist_player": None, "block_player": None, "sub_type": "1 of 1"},
    {"game": "g", "action_type": "foul", "result": None, "player": 3, "assist_player": None, "block_player": None, "sub_type": "technical"},
    {"game": "g", "action_type": "foul", "result": None, "player": 3, "assist_player": None, "block_player": None, "sub_type": "personal"},
    {"game": "g", "action_type": "turnover", "result": None, "player": 2, "assist_player": None, "block_player": None, "sub_type": "bad pass"},
    {"game": "g", "action_type": "steal", "result": None, "player": 3, "assist_player": None, "block_player": None, "sub_type": None},
    {"game": "g", "action_type": "rebound", "result": None, "player": None, "assist_player": None, "block_player": None, "sub_type": "defensive"},
]
t = awards.box_counts(acts)
assert t[("g", 1)] | {} == {**ZERO, "pts": 3, "fgm": 1, "fga": 2, "ftm": 1, "fta": 1, "oreb": 1}, t[("g", 1)]
assert t[("g", 2)] == {**ZERO, "ast": 1, "tov": 1}
assert t[("g", 3)] == {**ZERO, "blk": 1, "pf": 1, "stl": 1}
print("awards ok")
