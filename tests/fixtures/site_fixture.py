"""A made-up but self-consistent league for the browser tests: the 30 clubs, ten invented players each, four game days
played and two to come. Every box score adds up to its final, quarters add up to the score, and a game is never tied.
usage: python tests/fixtures/site_fixture.py OUT_DIR   (writes OUT_DIR/teams/<season>/, the layout build.py serves)
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from site_data import STATS, load_teams, write_site  # noqa: E402

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
    return teams, players, games, lines


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


def hits(rng, n, p):
    return sum(rng.random() < p for _ in range(n))


def quarters(rng, total):
    cuts = sorted(rng.randint(0, total) for _ in range(3))
    return [b - a for a, b in zip([0, *cuts], [*cuts, total])]


if __name__ == "__main__":
    out = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "_site", "teams", SEASON)
    write_site(out, SEASON, LABEL, BUILT, *make(random.Random(7)))
    print(f"fixture league written to {out}")
