"""The awards ladder: the Lab's own ladder for MVP, Rookie of the Year and Defensive Player of the Year, from numbers
the site already shows, with one published formula. It is the Lab's reading of the season, not a prediction of the vote.

Each player of an award's pool gets three parts, each by his rank in that pool from 100 (first) to 0 (last), ties
sharing the better rank (points = 100 (n - 1 - players ahead) / (n - 1), rounded):
                  impact                       production                    team
  MVP, Rookie     his RAPM                     Game Score per game           his club's win percentage
  Defensive       his D-RAPM                   steals and blocks per game    his club's defensive rating (lower is better)
RAPM and D-RAPM are the values leaders.json shows. The score is 0.5 impact + 0.3 production + 0.2 team, kept in tenths
(5 impact + 3 production + 2 team).

Pools (every player needs a RAPM and a game):
  MVP, Defensive  on pace for the 65-game line: a game counts at 20 minutes, and up to two of 15 to 19 minutes count
                  too; counted games x 82 >= 65 x his club's games played
  Rookie          rookies who played 70% of their club's games at 15 minutes a game (the RAPM boards' floor)
Each ladder lists its TOP best, ties broken by impact, then production, then pid.

<out>/awards.json  {"rule": {...the numbers above}, "pool": {award: players in the pool},
                    "mvp" | "roy" | "dpoy": [{"pid", "c": [impact, production, team], "s": score in tenths, "g": counted games}]}
Games, seconds, steals, blocks and Game Score come from the box scores of the finals' game files (games/<gid>.json),
the club record from games.json, its defensive rating from ratings.json (opponents' points per possession, possessions
= FGA - OREB + TOV + 0.44 FTA), RAPM, D-RAPM and rookies from leaders.json.

Gate (check): the file is exactly what the published JSON gives again; every row's games, seconds, steals, blocks and
Game Score are his leaders.json totals, every score is its parts' blend, every row is in its pool, and each ladder is
in order.
usage: python awards.py [2026-27]   (after site_data.py; writes teams/<season>/awards.json)
"""
import json
import os
from fractions import Fraction
from rounding import avg
from site_data import finals_lines, game_score

W = (5, 3, 2)                      # impact, production, team, out of ten
GAMES, LINE = 82, 65               # the 65-game line over an 82-game season
FULL, PART, PARTS = 1200, 900, 2   # a game counts at 20 minutes; up to two of 15 to 19 minutes count too
SHARE, MPG = 70, 15                # Rookie: 70% of the club's games, 15 minutes a game
TOP = 10
AWARDS = ("mvp", "roy", "dpoy")


def counted(secs):
    """Games that count for the 65-game line, from his seconds in each game played."""
    return sum(s >= FULL for s in secs) + min(PARTS, sum(PART <= s < FULL for s in secs))


def records(out):
    """{club: [games, wins]} over the finals of games.json."""
    rec = {}
    for g in json.load(open(os.path.join(out, "games.json")))["games"]:
        if g["hs"] is None:
            continue
        for c, us, them in ((g["home"], g["hs"], g["as"]), (g["away"], g["as"], g["hs"])):
            r = rec.setdefault(c, [0, 0])
            r[0] += 1
            r[1] += us > them
    return rec


def defences(out):
    """{club: opponents' points per possession, exact} from ratings.json; a club without a possession has none."""
    d = {}
    for c in json.load(open(os.path.join(out, "ratings.json")))["teams"]:
        a = c["against"]
        poss = 100 * (a["fga"] - a["oreb"] + a["tov"]) + 44 * a["fta"]
        if poss > 0:
            d[c["code"]] = Fraction(100 * a["pts"], poss)
    return d


def points(vals):
    """{pid: 0..100} by rank: the best gets 100, the last 0, ties share the better rank."""
    n = len(vals)
    if n == 1:
        return {p: 100 for p in vals}
    return {p: avg(100 * (n - 1 - sum(w > v for w in vals.values())), n - 1, 0) for p, v in vals.items()}


def players(out):
    """One row per player with a RAPM and a game: leaders.json's RAPM, D-RAPM and rookie flag plus his box-score
    games, seconds, steals and blocks, Game Score, counted games and his club's record and defence."""
    lines, rec, dfn = finals_lines(out), records(out), defences(out)
    rows = []
    for p in json.load(open(os.path.join(out, "leaders.json")))["players"]:
        ls = lines.get(p["pid"], [])
        if not ls or p.get("rapm") is None or p.get("drapm") is None:
            continue
        club = rec.get(p["team"], [0, 0])
        rows.append({"pid": p["pid"], "rookie": p["rookie"], "rapm": p["rapm"], "drapm": p["drapm"], "gp": len(ls),
                     "sec": sum(x["sec"] for x in ls), "gs": sum(game_score(x) for x in ls),
                     "stl": sum(x["stl"] for x in ls), "blk": sum(x["blk"] for x in ls),
                     "g": counted([x["sec"] for x in ls]), "cgp": club[0], "cw": club[1], "cd": dfn.get(p["team"])})
    return rows


def on_pace(r):
    return r["cgp"] > 0 and r["g"] * GAMES >= LINE * r["cgp"]


def regular(r):
    return r["cgp"] > 0 and 100 * r["gp"] >= SHARE * r["cgp"] and r["sec"] >= 60 * MPG * r["gp"]


def pools(rows):
    return {"mvp": [r for r in rows if on_pace(r)],
            "roy": [r for r in rows if r["rookie"] and regular(r)],
            "dpoy": [r for r in rows if on_pace(r) and r["cd"] is not None]}


# each award's impact, production and team values, higher the better
PARTS_OF = {
    "mvp": (lambda r: r["rapm"], lambda r: Fraction(r["gs"], r["gp"]), lambda r: Fraction(r["cw"], r["cgp"])),
    "dpoy": (lambda r: r["drapm"], lambda r: Fraction(r["stl"] + r["blk"], r["gp"]), lambda r: -r["cd"]),
}
PARTS_OF["roy"] = PARTS_OF["mvp"]


def ladder(pool, parts):
    pts = [points({r["pid"]: f(r) for r in pool}) for f in parts]
    rows = [{"pid": r["pid"], "c": [x[r["pid"]] for x in pts], "g": r["g"], "k": (parts[0](r), parts[1](r))} for r in pool]
    for x in rows:
        x["s"] = sum(w * c for w, c in zip(W, x["c"]))
    rows.sort(key=lambda x: (-x["s"], -x["k"][0], -x["k"][1], x["pid"]))
    return [{"pid": x["pid"], "c": x["c"], "s": x["s"], "g": x["g"]} for x in rows[:TOP]]


def document(out):
    p = pools(players(out))
    return {"rule": {"w": list(W), "games": GAMES, "line": LINE, "full": FULL, "part": PART, "parts": PARTS, "share": SHARE,
                     "mpg": MPG, "top": TOP},
            "pool": {k: len(v) for k, v in p.items()}, **{k: ladder(p[k], PARTS_OF[k]) for k in AWARDS}}


def check(doc, out):
    """Raises unless doc is what the published JSON gives again and every row matches leaders.json, blends its parts
    and is in its pool, each ladder in order."""
    if doc != document(out):
        raise SystemExit("awards.json: not what the published JSON gives")
    lead = {p["pid"]: p for p in json.load(open(os.path.join(out, "leaders.json")))["players"]}
    rows = {r["pid"]: r for r in players(out)}
    ok = {k: {r["pid"] for r in v} for k, v in pools(list(rows.values())).items()}
    keys = ("gp", "sec", "gs", "stl", "blk")
    for k in AWARDS:
        xs = doc[k]
        if len(xs) > TOP or len({x["pid"] for x in xs}) != len(xs):
            raise SystemExit(f"awards.json: {k} has {len(xs)} rows or a player twice")
        for x in xs:
            pid, r, ld = x["pid"], rows.get(x["pid"]), lead.get(x["pid"])
            if pid not in ok[k] or r is None or ld is None:
                raise SystemExit(f"awards.json: {k}: {pid} is not in the pool")
            if [ld.get(q) for q in keys] != [r[q] for q in keys] or x["g"] != r["g"]:
                raise SystemExit(f"awards.json: {k}: {pid} box scores {[r[q] for q in keys]}, leaders.json {[ld.get(q) for q in keys]} ({keys})")
            if x["s"] != sum(w * c for w, c in zip(W, x["c"])) or not all(0 <= c <= 100 for c in x["c"]):
                raise SystemExit(f"awards.json: {k}: {pid} score {x['s']} is not the blend of {x['c']}")
        if [-x["s"] for x in xs] != sorted(-x["s"] for x in xs):
            raise SystemExit(f"awards.json: {k} is out of order")


if __name__ == "__main__":
    from season import ROOT, season
    s = season()
    out = os.path.join(ROOT, "teams", s)
    doc = document(out)
    check(doc, out)
    with open(os.path.join(out, "awards.json"), "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"{s}: awards ladder written; pools {doc['pool']}")
