"""The awards ladder: the Lab's own ladder for MVP, Rookie of the Year, Sixth Man and Most Improved, from numbers the
site already shows, with one published formula. It is the Lab's reading of the season, not a prediction of the vote.

MVP, Rookie and Sixth Man share one score. Each player of the award's pool gets three parts, each by his rank in that
pool from 100 (first) to 0 (last), ties sharing the better rank (points = 100 (n - rank) / (n - 1), rounded):
  impact      his RAPM as leaders.json shows it
  production  his Game Score per game
  team        his club's win percentage
The score is 0.5 impact + 0.3 production + 0.2 team, kept in tenths (5 impact + 3 production + 2 team). Most Improved
is his Game Score per 36 minutes now minus last season's, both shown to one decimal, so the difference is of shown
tenths.

Pools (every player needs a RAPM and a game):
  MVP        on pace for the 65-game line: a game counts at 20 minutes, and up to two of 15 to 19 minutes count too;
             counted games x 82 >= 65 x his club's games played
  Rookie     rookies who played 70% of their club's games at 15 minutes a game (the RAPM boards' floor)
  Sixth Man  the same floor, and more games off the bench than starts
  Most Improved  not a rookie, on pace for the 65-game line, and at least 20 games at 15 minutes a game last season
Each ladder lists its TOP best, ties broken by impact, then production, then pid.

<out>/awards.json  {"rule": {...the numbers above}, "pool": {award: players in the pool},
                    "mvp" | "roy" | "smoy": [{"pid", "c": [impact, production, team], "s": score in tenths, "g": counted games}],
                    "mip": [{"pid", "last": [gp, sec, gs], "d": GS per 36 now minus last season, tenths, "g": counted games}]}
Games, seconds, starts and Game Score come from the box scores of the finals' game files (games/<gid>.json), the club
record from games.json, RAPM and rookies from leaders.json, last season from model/last_<season>.json.

model/last_<season>.json  {pid: [gp, sec, gs]}: each player's regular season a year ago, rebuilt once from the
play-by-play archive (model/archive.py): seconds from lineups.py's stints, the box counts behind Game Score from the
actions (box_counts()). Before writing it, the same counting is held to this season's official box scores and must
agree on all but a few stat corrections (one player-game in 500, at least five).

Gate (check): the file is exactly what the published JSON gives again; every row's games and Game Score are his
leaders.json totals, every score is its parts' blend, every row clears its pool's floors, and each ladder is in order.
usage: python awards.py [2026-27]          (after site_data.py; writes teams/<season>/awards.json)
       python awards.py --last 2025-26     (once a season: writes model/last_2025-26.json from the archive)
"""
import json
import os
from rounding import avg
from site_data import finals_lines, game_score

W = (5, 3, 2)                      # impact, production, team, out of ten
GAMES, LINE = 82, 65               # the 65-game line over an 82-game season
FULL, PART, PARTS = 1200, 900, 2   # a game counts at 20 minutes; up to two of 15 to 19 minutes count too
SHARE, MPG = 70, 15                # Rookie and Sixth Man: 70% of the club's games, 15 minutes a game
LAST_GP = 20                       # Most Improved: last season's games (at MPG minutes a game)
TOP = 10
AWARDS = ("mvp", "roy", "smoy", "mip")
HERE = os.path.dirname(os.path.abspath(__file__))


def previous(season):
    y = int(season[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def last_path(season):
    return os.path.join(HERE, "model", f"last_{previous(season)}.json")


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


def points(vals):
    """{pid: 0..100} by rank: the best gets 100, the last 0, ties share the better rank."""
    n = len(vals)
    if n == 1:
        return {p: 100 for p in vals}
    return {p: avg(100 * (n - 1 - sum(w > v for w in vals.values())), n - 1, 0) for p, v in vals.items()}


def players(out):
    """One row per player with a RAPM and a game: leaders.json's row plus his box-score games, seconds, starts, Game
    Score, counted games and his club's record."""
    lines, rec = finals_lines(out), records(out)
    rows = []
    for p in json.load(open(os.path.join(out, "leaders.json")))["players"]:
        ls = lines.get(p["pid"], [])
        if not ls or p.get("rapm") is None:
            continue
        club = rec.get(p["team"], [0, 0])
        rows.append({"pid": p["pid"], "rookie": p["rookie"], "rapm": p["rapm"], "gp": len(ls), "sec": sum(x["sec"] for x in ls),
                     "starts": sum(x["start"] for x in ls), "gs": sum(game_score(x) for x in ls),
                     "g": counted([x["sec"] for x in ls]), "cgp": club[0], "cw": club[1]})
    return rows


def on_pace(r):
    return r["cgp"] > 0 and r["g"] * GAMES >= LINE * r["cgp"]


def regular(r):
    return 100 * r["gp"] >= SHARE * r["cgp"] and r["sec"] >= 60 * MPG * r["gp"]


def pools(rows, last):
    def had(r):
        x = last.get(r["pid"])
        return x is not None and x[0] >= LAST_GP and x[1] >= 60 * MPG * x[0]
    return {"mvp": [r for r in rows if on_pace(r)],
            "roy": [r for r in rows if r["rookie"] and regular(r)],
            "smoy": [r for r in rows if regular(r) and 2 * r["starts"] < r["gp"]],
            "mip": [r for r in rows if not r["rookie"] and on_pace(r) and had(r)]}


def per36(gs, sec):
    """Game Score per 36 minutes in tenths, as the page shows it to one decimal."""
    return avg(gs * 2160, sec, 0)


def ladder(pool):
    from fractions import Fraction
    parts = [points({r["pid"]: r["rapm"] for r in pool}),
             points({r["pid"]: Fraction(r["gs"], r["gp"]) for r in pool}),
             points({r["pid"]: Fraction(r["cw"], r["cgp"]) for r in pool})]
    rows = [{"pid": r["pid"], "c": [x[r["pid"]] for x in parts], "g": r["g"], "k": (r["rapm"], Fraction(r["gs"], r["gp"]))} for r in pool]
    for x in rows:
        x["s"] = sum(w * c for w, c in zip(W, x["c"]))
    rows.sort(key=lambda x: (-x["s"], -x["k"][0], -x["k"][1], x["pid"]))
    return [{"pid": x["pid"], "c": x["c"], "s": x["s"], "g": x["g"]} for x in rows[:TOP]]


def improved(pool, last):
    rows = [{"pid": r["pid"], "last": last[r["pid"]], "d": per36(r["gs"], r["sec"]) - per36(last[r["pid"]][2], last[r["pid"]][1]),
             "g": r["g"]} for r in pool]
    rows.sort(key=lambda x: (-x["d"], x["pid"]))
    return rows[:TOP]


def document(out, last, season):
    p = pools(players(out), last)
    return {"rule": {"w": list(W), "games": GAMES, "line": LINE, "full": FULL, "part": PART, "parts": PARTS, "share": SHARE,
                     "mpg": MPG, "last_gp": LAST_GP, "top": TOP, "last": previous(season)},
            "pool": {k: len(v) for k, v in p.items()},
            **{k: ladder(p[k]) for k in ("mvp", "roy", "smoy")}, "mip": improved(p["mip"], last)}


def check(doc, out, last, season):
    """Raises unless doc is what the published JSON gives again and every row matches leaders.json, blends its parts
    and clears its pool's floors, each ladder in order."""
    if doc != document(out, last, season):
        raise SystemExit("awards.json: not what the published JSON gives")
    lead = {p["pid"]: p for p in json.load(open(os.path.join(out, "leaders.json")))["players"]}
    rows = {r["pid"]: r for r in players(out)}
    ok = {k: {r["pid"] for r in v} for k, v in pools(list(rows.values()), last).items()}
    for k in AWARDS:
        xs = doc[k]
        if len(xs) > TOP or len({x["pid"] for x in xs}) != len(xs):
            raise SystemExit(f"awards.json: {k} has {len(xs)} rows or a player twice")
        for x in xs:
            pid, r, ld = x["pid"], rows.get(x["pid"]), lead.get(x["pid"])
            if pid not in ok[k] or r is None or ld is None:
                raise SystemExit(f"awards.json: {k}: {pid} is not in the pool")
            if (ld["gp"], ld["sec"], ld["gs"]) != (r["gp"], r["sec"], r["gs"]) or x["g"] != r["g"]:
                raise SystemExit(f"awards.json: {k}: {pid} games/seconds/Game Score {(r['gp'], r['sec'], r['gs'])}, leaders.json "
                                 f"{(ld['gp'], ld['sec'], ld['gs'])}")
            if k != "mip" and (x["s"] != sum(w * c for w, c in zip(W, x["c"])) or not all(0 <= c <= 100 for c in x["c"])):
                raise SystemExit(f"awards.json: {k}: {pid} score {x['s']} is not the blend of {x['c']}")
        key = (lambda x: -x["d"]) if k == "mip" else (lambda x: -x["s"])
        if [key(x) for x in xs] != sorted(key(x) for x in xs):
            raise SystemExit(f"awards.json: {k} is out of order")


# --- last season, once, from the archive ---

COUNTS = ("pts", "fgm", "fga", "ftm", "fta", "oreb", "dreb", "stl", "ast", "blk", "pf", "tov")


def box_counts(actions):
    """{(game, player): {count: n}} for the counts behind Game Score, from play-by-play actions (dicts with game,
    action_type, sub_type, result, player, assist_player, block_player)."""
    t = {}

    def add(g, p, k, n=1):
        x = t.setdefault((g, int(p)), dict.fromkeys(COUNTS, 0))
        x[k] += n
    for a in actions:
        g, p, kind = a["game"], a["player"], a["action_type"]
        if not p:
            continue
        if kind in ("2pt", "3pt"):
            add(g, p, "fga")
            if a["result"] == "Made":
                add(g, p, "fgm")
                add(g, p, "pts", 2 if kind == "2pt" else 3)
                if a["assist_player"]:
                    add(g, a["assist_player"], "ast")
            if a["block_player"]:
                add(g, a["block_player"], "blk")
        elif kind == "freethrow":
            add(g, p, "fta")
            if a["result"] == "Made":
                add(g, p, "ftm")
                add(g, p, "pts")
        elif kind == "rebound":
            add(g, p, "oreb" if a["sub_type"] == "offensive" else "dreb")
        elif kind == "turnover":
            add(g, p, "tov")
        elif kind == "steal":
            add(g, p, "stl")
        elif kind == "foul" and a["sub_type"] in ("personal", "offensive"):
            add(g, p, "pf")
    return t


def _records(df):
    import pandas as pd
    cols = ["game", "action_type", "sub_type", "result", "player", "assist_player", "block_player"]
    return [{k: (None if v is None or v is pd.NA or (isinstance(v, float) and v != v) else v) for k, v in zip(cols, r)}
            for r in df[cols].itertuples(index=False, name=None)]


def check_counting(wh):
    """(player-games that differ, box lines): box_counts() of this season's play-by-play against its official box scores."""
    import duckdb
    con = duckdb.connect()
    ev = con.execute(f"select * from read_parquet('{wh}/events.parquet') order by game, order_no").df()
    box = con.execute(f"select * from read_parquet('{wh}/box.parquet') where played").df()
    got, bad = box_counts(_records(ev)), 0
    for b in box.itertuples():
        x = got.get((b.game, int(b.player)), dict.fromkeys(COUNTS, 0))
        bad += any(x[k] != getattr(b, k) for k in COUNTS)
    return bad, len(box)


def last_season(season):
    """{pid: [gp, sec, gs]} of a past regular season from the archive."""
    import sys
    sys.path.insert(0, os.path.join(HERE, "model"))
    import lineups
    from actions import from_archive
    from archive import fetch
    ev = from_archive(fetch(f"cdnnba_{season[:4]}"))
    ev = ev[ev.game.str.startswith("002")].sort_values(["game", "order_no"])
    secs = {}
    for g, acts in ev.groupby("game"):
        acts = acts.to_dict("records")
        st, problems = lineups.stints(acts, lineups.infer_starters(acts))
        if problems:
            print(f"WARN {season} game {g}: {problems[:2]}; left out")
            continue
        for (_, p), s in lineups.seconds_on(st).items():
            secs[(g, int(p))] = s
    counts = box_counts(_records(ev[ev.game.isin({g for g, _ in secs})]))
    out = {}
    for (g, p), s in secs.items():
        if s <= 0:
            continue
        x = out.setdefault(str(p), [0, 0, 0])
        x[0] += 1
        x[1] += round(s)
        x[2] += game_score(counts.get((g, p), dict.fromkeys(COUNTS, 0)))
    return dict(sorted(out.items()))


if __name__ == "__main__":
    import sys
    from season import ROOT, season
    if sys.argv[1:2] == ["--last"]:
        past, now = sys.argv[2], json.load(open(os.path.join(ROOT, "config.json")))["season"]
        bad, n = check_counting(os.path.join(ROOT, "warehouse", now))
        print(f"{now}: play-by-play counts differ from the box score in {bad} of {n} player-games")
        if bad > max(5, n // 500):   # the box score takes stat corrections the play-by-play keeps (an assist or a rebound moved)
            raise SystemExit("the play-by-play counting does not match the box scores; last season not written")
        doc = last_season(past)
        path = os.path.join(ROOT, "model", f"last_{past}.json")
        with open(path, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        print(f"{past}: {len(doc)} players written to {path}")
    else:
        s = season()
        out = os.path.join(ROOT, "teams", s)
        lp = last_path(s)
        last = json.load(open(lp)) if os.path.exists(lp) else {}
        doc = document(out, last, s)
        check(doc, out, last, s)
        with open(os.path.join(out, "awards.json"), "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        print(f"{s}: awards ladder written; pools {doc['pool']}")
