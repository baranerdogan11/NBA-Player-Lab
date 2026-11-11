"""awards.py: the 65-game count, rank points with shared ranks, the pools' floors (pace, rookies), the blend and its
order, the defensive ladder on D-RAPM, steals and blocks and the club's defence, and the gate refusing a changed file.
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


def line(pid, sec, pts, start, stl=0, blk=0):
    return {**ZERO, "pid": pid, "name": pid, "start": start, "sec": sec, "pts": pts, "stl": stl, "blk": blk}


def league(tmp):
    """Two clubs, ten finals (AAA wins seven and allows fewer points). A1-A3 and B1-B3 play every game; A4 misses four;
    R1 is a rookie, R2 a rookie short of minutes."""
    games, box = [], {}
    for i in range(10):
        gid = f"g{i}"
        home_wins = i < 7
        games.append({"gid": gid, "home": "AAA", "away": "BBB", "hs": 100 if home_wins else 90, "as": 90 if home_wins else 100})
        a = [line("A1", 2000, 30, True, 1, 0), line("A2", 1800, 20, True, 0, 3), line("A3", 1500, 10, True, 2, 0),
             line("R1", 1300, 12, True), line("R2", 600, 15, False)]
        if i >= 4:
            a.append(line("A4", 2200, 25, True, 4, 4))
        b = [line("B1", 2100, 24, True, 2, 2), line("B2", 1700, 18, True), line("B3", 1200, 8, True, 1, 0)]
        box[gid] = {"AAA": a, "BBB": b}
    games.append({"gid": "g10", "home": "AAA", "away": "BBB", "hs": None, "as": None})
    os.makedirs(os.path.join(tmp, "games"))
    json.dump({"games": games}, open(os.path.join(tmp, "games.json"), "w"))
    for gid, b in box.items():
        json.dump({"gid": gid, "box": b}, open(os.path.join(tmp, "games", f"{gid}.json"), "w"))
    side = lambda pts: {"pts": pts, "fga": 800, "oreb": 100, "tov": 120, "fta": 200}   # noqa: E731
    json.dump({"teams": [{"code": "AAA", "for": side(970), "against": side(930)}, {"code": "BBB", "for": side(930), "against": side(970)}]},
              open(os.path.join(tmp, "ratings.json"), "w"))
    rapm = {"A1": (5.0, 1.0), "A2": (2.0, 3.0), "A3": (2.0, 0.5), "A4": (9.0, 6.0), "R1": (1.0, 0.0), "R2": (4.0, 2.0),
            "B1": (6.0, 3.0), "B2": (0.5, -1.0), "B3": (-1.0, 0.2)}
    lead = []
    for pid, (r, d) in rapm.items():
        ls = [x for b in box.values() for c in b.values() for x in c if x["pid"] == pid]
        lead.append({"pid": pid, "name": pid, "team": "BBB" if pid[0] == "B" else "AAA", "rookie": pid[0] == "R", "rapm": r, "drapm": d,
                     "gp": len(ls), "sec": sum(x["sec"] for x in ls), "gs": sum(awards.game_score(x) for x in ls),
                     "stl": sum(x["stl"] for x in ls), "blk": sum(x["blk"] for x in ls)})
    lead.append({"pid": "N1", "name": "N1", "team": "AAA", "rookie": False, "rapm": None, "drapm": None, "gp": 0, "sec": 0, "gs": 0, "stl": 0, "blk": 0})
    json.dump({"players": lead}, open(os.path.join(tmp, "leaders.json"), "w"))


with tempfile.TemporaryDirectory() as tmp:
    league(tmp)
    doc = awards.document(tmp)
    assert set(doc) == {"rule", "pool", "mvp", "roy", "dpoy"}, sorted(doc)
    mvp = [x["pid"] for x in doc["mvp"]]
    # A4 missed four of ten: 6 x 82 < 65 x 10, off the MVP and Defensive ladders; R2 never plays 15 minutes
    assert set(mvp) == {"A1", "A2", "A3", "R1", "B1", "B2", "B3"}, mvp
    assert doc["pool"] == {"mvp": 7, "roy": 1, "dpoy": 7}, doc["pool"]
    assert mvp[0] == "A1", doc["mvp"]                       # second in impact, first in production, best club
    for k in ("mvp", "roy", "dpoy"):
        for x in doc[k]:
            assert x["s"] == 5 * x["c"][0] + 3 * x["c"][1] + 2 * x["c"][2]
        assert [x["s"] for x in doc[k]] == sorted((x["s"] for x in doc[k]), reverse=True)
    # A2 and A3 share a RAPM, so they share its points
    c = {x["pid"]: x["c"] for x in doc["mvp"]}
    assert c["A2"][0] == c["A3"][0]
    assert [x["pid"] for x in doc["roy"]] == ["R1"], doc["roy"]
    # Defensive: A2 and B1 share the best D-RAPM; B1 has more steals and blocks, A2 the better club defence
    d = {x["pid"]: x["c"] for x in doc["dpoy"]}
    assert set(d) == set(mvp)
    assert d["A2"][0] == d["B1"][0] == 100 and d["B1"][1] == 100 and d["A2"][1] < 100, d
    assert d["A2"][2] == 100 and d["B1"][2] == 33, d          # AAA allows fewer points per possession
    assert [x["pid"] for x in doc["dpoy"]][:2] == ["A2", "B1"], doc["dpoy"]   # 500 + 3 x 83 + 200 against 500 + 300 + 66

    awards.check(doc, tmp)

    def refused(d):
        try:
            awards.check(d, tmp)
        except SystemExit:
            return True
        return False
    assert refused({**doc, "mvp": doc["mvp"][::-1]})                                  # out of order, not what it gives
    assert refused({**doc, "roy": doc["roy"] + [{"pid": "A1", "c": [0, 0, 0], "s": 0, "g": 10}]})
    # leaders.json disagreeing with the box scores is refused too
    lead = json.load(open(os.path.join(tmp, "leaders.json")))
    for p in lead["players"]:
        if p["pid"] == "A2":
            p["blk"] += 1
    json.dump(lead, open(os.path.join(tmp, "leaders.json"), "w"))
    assert refused(doc)
print("awards ok")
