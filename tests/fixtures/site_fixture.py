"""A made-up but self-consistent league for the browser tests: the 30 clubs, ten invented players each, four game days
played and two to come. Every box score adds up to its final, quarters add up to the score, and a game is never tied.
usage: python tests/fixtures/site_fixture.py OUT_DIR   (writes OUT_DIR/teams/<season>/, the layout build.py serves)
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from shots import write_shots  # noqa: E402
from site_data import RT, STATS, load_teams, period_start, write_lineups, write_ratings, write_site  # noqa: E402

SEASON, LABEL, BUILT = "2026-27", "2026-27", "2026-10-26T06:00:00Z"
FIRST = ["Jalen", "Marcus", "Tyrese", "Luka", "Devin", "Andre", "Cole", "Isaiah", "Malik", "Darius", "Evan", "Kobe"]
LAST = ["Carter", "Brooks", "Hayes", "Mitchell", "Coleman", "Reed", "Price", "Ward", "Bishop", "Fields", "Grant", "Holt"]
POS = ["G", "G", "F", "F", "C", "G", "F", "G-F", "F-C", "C"]


def make(rng):
    teams = load_teams()
    players = []
    for i, t in enumerate(teams):
        for j in range(10):
            players.append({"pid": f"{1630000 + i * 10 + j}", "team": t["code"], "name": f"{FIRST[(i + j) % 12]} {LAST[(i * 3 + j) % 12]}",
                            "jersey": str((j * 7 + i) % 45), "pos": POS[j], "height": f"6-{2 + j % 9}",
                            "born": f"{1996 + (i + j) % 9}-0{1 + j % 9}-1{j % 9}"})
    other = random.Random(11)   # RAPM from its own generator, so the box scores stay as they were
    for p in players[:-5]:      # the last club's bench has none
        p["o_rapm"], p["d_rapm"] = other.gauss(0, 2), other.gauss(0, 2)
    games, lines, n = [], [], 0
    codes = [t["code"] for t in teams]
    for day in range(6):
        rng.shuffle(codes)
        date = f"2026-10-{21 + day}"
        for k in range(15):
            n += 1
            home, away = codes[2 * k], codes[2 * k + 1]
            g = {"gid": f"00226{n:05d}", "date": date, "time": f"2026-10-{21 + day + 1}T02:00:00Z" if k % 3 == 2 else f"{date}T23:{k % 2 * 3}0:00Z",
                 "home": home, "away": away, "final": day < 4}
            if g["final"]:
                box = {c: side(rng, [p for p in players if p["team"] == c]) for c in (home, away)}
                score = {c: sum(x["pts"] for x in box[c]) for c in box}
                if score[home] == score[away]:   # never a tie: one more free throw for the home side's first player
                    x = box[home][0]
                    x["ftm"] += 1
                    x["fta"] += 1
                    x["pts"] += 1
                    score[home] += 1
                margin = score[home] - score[away]
                for c, m in ((home, margin), (away, -margin)):
                    for x in box[c]:
                        x["pm"] = m if x["start"] else 0
                        x["gid"] = g["gid"]
                        lines.append(x)
                g.update(hs=score[home], **{"as": score[away]}, periods=[list(q) for q in zip(quarters(rng, score[home]), quarters(rng, score[away]))])
            games.append(g)
    other = random.Random(5)   # the flows from their own generator too
    for g in games:
        if g["final"]:
            g["flow"] = flow(other, g["periods"])
    return teams, players, games, lines


def flow(rng, periods):
    """A flow through the quarters' scores: each side's points in baskets of 1 to 3 at random moments of the quarter."""
    out, h, a = [], 0, 0
    for i, q in enumerate(periods):
        baskets = []
        for side, pts in enumerate(q):
            while pts:
                b = min(pts, rng.choice((1, 2, 2, 2, 3)))
                baskets.append((rng.randint(period_start(i + 1) + 1, period_start(i + 2)), side, b))
                pts -= b
        for ds, side, b in sorted(baskets):
            h, a = (h + b, a) if side == 0 else (h, a + b)
            out.append([ds, h, a])
    return out


def side(rng, roster):
    secs = [2160, 2040, 1980, 1920, 1800, 1500, 1260, 1080, 660, 0]   # 14400 s: five players for 48 minutes
    out = []
    for j, p in enumerate(roster):
        x = {k: 0 for k in STATS}
        if secs[j]:
            s = secs[j] / 2160
            x["fga"] = int(rng.randint(6, 20) * s)
            x["fg3a"] = rng.randint(0, x["fga"] // 2)
            x["fg3m"] = hits(rng, x["fg3a"], .36)
            x["fgm"] = x["fg3m"] + hits(rng, x["fga"] - x["fg3a"], .53)
            x["fta"] = int(rng.randint(0, 9) * s)
            x["ftm"] = hits(rng, x["fta"], .78)
            x["pts"] = 2 * x["fgm"] + x["fg3m"] + x["ftm"]
            x["oreb"], x["dreb"] = int(rng.randint(0, 4) * s), int(rng.randint(0, 9) * s)
            x["reb"] = x["oreb"] + x["dreb"]
            for k, hi in (("ast", 10), ("stl", 3), ("blk", 3), ("tov", 4), ("pf", 5)):
                x[k] = int(rng.randint(0, hi) * s)
        out.append({"pid": p["pid"], "team": p["team"], "name": p["name"], "start": j < 5, "sec": secs[j], **x})
    return out


def spots(rng, games, lines):
    """Every box line's field-goal attempts as shots: its threes beyond the arc, its twos inside it, its makes first."""
    when = {g["gid"]: g["time"] for g in games}
    out = []
    for x in lines:
        for k in range(x["fga"]):
            three = k < x["fg3a"]
            made = k < x["fg3m"] if three else k - x["fg3a"] < x["fgm"] - x["fg3m"]
            if three and rng.random() < .25:
                px, py = rng.choice((-1, 1)) * rng.randint(222, 240), rng.randint(-40, 85)
            else:
                a, r = rng.uniform(.4, math.pi - .4) if three else rng.uniform(0, math.pi), rng.uniform(245, 275) if three else rng.uniform(0, 210)
                px, py = round(r * math.cos(a)), round(r * math.sin(a))
            out.append({"gid": x["gid"], "time": when[x["gid"]], "team": x["team"], "pid": x["pid"], "x": px, "y": py, "made": made,
                        "pts": 3 if three else 2})
    return out


UNITS = [[0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [0, 1, 2, 3, 4], [0, 1, 2, 3, 5]]   # the five of each quarter, by place in the box


def stints(games, lines):
    """One stint a quarter: each side's five of UNITS, the quarter's score, and the side's counts spread over the
    quarters. Sets every box line's plus-minus to the margin while he was on the floor, as the feed's box score does."""
    box = {}
    for x in lines:
        box.setdefault((x["gid"], x["team"]), []).append(x)
    out = []
    for g in games:
        if not g["final"]:
            continue
        for x in box[(g["gid"], g["home"])] + box[(g["gid"], g["away"])]:
            x["pm"] = 0
        for q, score in enumerate(g["periods"]):
            for c, o, i in ((g["home"], g["away"], 0), (g["away"], g["home"], 1)):
                side, opp = box[(g["gid"], c)], box[(g["gid"], o)]
                share = lambda rows, k: sum(x[k] for x in rows) * (q + 1) // 4 - sum(x[k] for x in rows) * q // 4  # noqa: E731
                for j in UNITS[q]:
                    side[j]["pm"] += score[i] - score[1 - i]
                out.append({"gid": g["gid"], "time": g["time"], "team": c, "players": [side[j]["pid"] for j in UNITS[q]], "sec": 720,
                            "pts": score[i], "opp_pts": score[1 - i], **{k: share(side, k) for k in ("fga", "oreb", "tov", "fta")},
                            **{f"opp_{k}": share(opp, k) for k in ("fga", "oreb", "tov", "fta")}})
    return out


def team_lines(games, lines):
    """Each club's box score totals per final, as write_ratings() takes them: four regulation quarters, 14400 s."""
    out = []
    for g in games:
        if g["final"]:
            for c, o in ((g["home"], g["away"]), (g["away"], g["home"])):
                xs = [x for x in lines if x["gid"] == g["gid"] and x["team"] == c]
                out.append({"gid": g["gid"], "team": c, "opp": o, "sec": 14400, **{k: sum(x[k] for x in xs) for k in RT}})
    return out


def hits(rng, n, p):
    return sum(rng.random() < p for _ in range(n))


def quarters(rng, total):
    cuts = sorted(rng.randint(0, total) for _ in range(3))
    return [b - a for a, b in zip([0, *cuts], [*cuts, total])]


if __name__ == "__main__":
    out = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "_site", "teams", SEASON)
    teams, players, games, lines = make(random.Random(7))
    units = stints(games, lines)
    write_site(out, SEASON, LABEL, BUILT, teams, players, games, lines)
    write_shots(out, teams, spots(random.Random(13), games, lines))
    write_lineups(out, teams, units)
    write_ratings(out, teams, team_lines(games, lines))
    print(f"fixture league written to {out}")
