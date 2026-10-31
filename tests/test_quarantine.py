"""Quarantine: one game that fails a gate is held out and the rest of the night publishes; the game is released once its
data passes; and only a systemic failure fails the run.

The gates run as scripts on a copy of the committed warehouse (the season's real finals) in a scratch directory: one
game's play-by-play cut short like a copy cached before the buzzer, one game's substitutions broken, one box score off by
a point, then the data put right again.
usage: python tests/test_quarantine.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import quarantine  # noqa: E402
from due import decide  # noqa: E402

SEASON = json.load(open(os.path.join(ROOT, "config.json")))["season"]
checks = {}

# ---- the module on its own
w = tempfile.mkdtemp()
failures = {}
quarantine.add(failures, "g1", "pbp", "last score")
quarantine.add(failures, "g1", "box", "points")
checks["box outranks pbp, and the reasons are joined"] = failures == {"g1": ("box", "last score; points")}
quarantine.record(w, "a", {"g1": ("pbp", "x")}, at="2026-10-26T01:00:00Z")
quarantine.record(w, "b", {"g1": ("lineups", "y"), "g2": ("shots", "z")}, at="2026-10-26T02:00:00Z")
checks["a game keeps its first_seen when another gate holds it too"] = {(e["game"], e["gate"]): e["first_seen"] for e in quarantine.load(w)} == {
    ("g1", "a"): "2026-10-26T01:00:00Z", ("g1", "b"): "2026-10-26T01:00:00Z", ("g2", "b"): "2026-10-26T02:00:00Z"}
checks["held: by scope, and a gate's own games left for it to check again"] = (
    quarantine.held(w, "lineups") == {"g1"} and quarantine.held(w, "shots") == {"g1", "g2"} and quarantine.held(w, "shots", gate="b") == {"g1"}
    and quarantine.held(w, "box") == set())
quarantine.record(w, "b", {}, at="2026-10-26T03:00:00Z")
checks["a gate's run replaces only its own entries"] = [(e["game"], e["gate"]) for e in quarantine.load(w)] == [("g1", "a")]
late = datetime(2026, 10, 26, 13, 30, tzinfo=timezone.utc)
checks["held for more than 12 hours is stale"] = (len(quarantine.stale(quarantine.load(w), late)) == 1
                                                 and not quarantine.stale(quarantine.load(w), datetime(2026, 10, 26, 12, 30, tzinfo=timezone.utc)))

# ---- due.py: a held game runs the update every 30 minutes, for a day
st = {"games": 9, "checked_at": "2026-10-26T03:00:00Z"}
t = lambda h, m=0: datetime(2026, 10, 26, h, m, tzinfo=timezone.utc)  # noqa: E731
checks["due: a held game retries after 30 minutes"] = decide(9, st, t(3, 31), ["2026-10-26T02:00:00Z"])[0]
checks["due: not sooner"] = not decide(9, st, t(3, 20), ["2026-10-26T02:00:00Z"])[0]
checks["due: after a day only the nightly retries it"] = not decide(9, {**st, "checked_at": "2026-10-27T10:05:00Z"},
                                                                    datetime(2026, 10, 27, 11, tzinfo=timezone.utc), ["2026-10-26T02:00:00Z"])[0]

# ---- the gates on the committed warehouse
src = os.path.join(ROOT, "warehouse", SEASON)
root = tempfile.mkdtemp()
for f in ("warehouse_tests.py", "lineups.py", "quarantine.py", "season.py", "site_data.py", "rounding.py", "teams.json", "config.json"):
    shutil.copy(os.path.join(ROOT, f), root)
W = os.path.join(root, "warehouse", SEASON)
shutil.copytree(src, W)
for f in ("quarantine.json", "status.json"):
    if os.path.exists(os.path.join(W, f)):
        os.remove(os.path.join(W, f))
con = duckdb.connect()
night = con.execute(f"select game from read_parquet('{src}/games.parquet') where final and game_type = 'regular' "
                    f"and date = (select max(date) from read_parquet('{src}/games.parquet') where final) order by game").fetchall()
night = [g for (g,) in night]
season = [g for (g,) in con.execute(f"select game from read_parquet('{src}/games.parquet') where final "
                                    "and game_type = 'regular' order by date desc, game").fetchall()]


def gate(script):
    r = subprocess.run([sys.executable, os.path.join(root, script), SEASON], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def rewrite(table, sql):
    """Replaces a table of the scratch warehouse with a query over the committed one."""
    con.execute(f"copy ({sql.format(t=f'read_parquet({chr(39)}{src}/{table}.parquet{chr(39)})')}) to '{W}/{table}.parquet' (format parquet)")


def restore():
    for t in ("events", "box", "team_box"):
        shutil.copy(os.path.join(src, f"{t}.parquet"), os.path.join(W, f"{t}.parquet"))


def stint_games():
    return {g for (g,) in con.execute(f"select distinct game from read_parquet('{W}/stints.parquet')").fetchall()}


# the committed warehouse can hold a game itself (the update job runs these tests before it fetches): what it holds is
# the baseline, and the game broken here is another one, from the busiest night so that one more held game stays
# under the systemic share (a night of 3 finals with one already held would trip it)
code, out = gate("warehouse_tests.py")
gate("lineups.py")
base = {(e["game"], e["gate"], e["scope"]) for e in quarantine.load(W)}
everyone = stint_games()
busiest = [g for (g,) in con.execute(f"select game from read_parquet('{src}/games.parquet') where final and game_type = 'regular' "
                                     "order by count(*) over (partition by date) desc, date desc, game").fetchall()]
bad = next(g for g in busiest if g not in {b[0] for b in base})
checks["the committed warehouse passes"] = code == 0


def held():
    return {(e["game"], e["gate"], e["scope"]) for e in quarantine.load(W)} - base


# a play-by-play cached before the buzzer: its last 40 actions missing
rewrite("events", f"select * from {{t}} where game != '{bad}' or order_no not in "
                  f"(select order_no from {{t}} where game = '{bad}' order by order_no desc limit 40)")
code, out = gate("warehouse_tests.py")
checks["stale play-by-play: the run passes, that game alone is held from its play-by-play"] = code == 0 and held() == {(bad, "warehouse_tests", "pbp")}
first = quarantine.load(W)[0]["first_seen"]
code, out = gate("lineups.py")
checks["stale play-by-play: lineups leave it out and keep every other game"] = code == 0 and stint_games() == everyone - {bad}
lu = json.load(open(os.path.join(root, "teams", SEASON, "lineups", con.execute(
    f"select home from read_parquet('{src}/games.parquet') where game = '{bad}'").fetchone()[0] + ".json")))
checks["stale play-by-play: the club's lineup file has its other games"] = bad not in lu["games"] and len(lu["games"]) > 0
code, out = gate("warehouse_tests.py")
checks["still stale on the next run: still held, since the first time"] = code == 0 and quarantine.load(W)[0]["first_seen"] == first
restore()
code, out = gate("warehouse_tests.py")
code2, out2 = gate("lineups.py")
checks["the corrected feed clears it, and lineups take it back"] = code == 0 and code2 == 0 and held() == set() and stint_games() == everyone

# substitutions broken: the first change of the second period dropped, so one player stays on and one never comes in
rewrite("events", f"select * from {{t}} where game != '{bad}' or order_no not in (select order_no from {{t}} where game = '{bad}' "
                  "and action_type = 'substitution' and period = 2 order by order_no limit 2)")
code, out = gate("warehouse_tests.py")
code2, out2 = gate("lineups.py")
checks["broken substitutions: lineups hold that game alone, and the run passes"] = (code == 0 and code2 == 0 and held() == {(bad, "lineups", "lineups")}
                                                                                    and stint_games() == everyone - {bad})
restore()
gate("warehouse_tests.py")
code2, out2 = gate("lineups.py")
checks["broken substitutions: cleared once the feed is right"] = code2 == 0 and held() == set() and stint_games() == everyone

# a box score off by a point: the whole game held
rewrite("box", f"select * replace (case when game = '{bad}' and player = (select min(player) from {{t}} where game = '{bad}' and pts > 0) "
               "then pts + 1 else pts end as pts) from {t}")
code, out = gate("warehouse_tests.py")
checks["a wrong box score: the whole game held, the run passes"] = code == 0 and held() == {(bad, "warehouse_tests", "box")}
checks["a wrong box score: the game reads as not final"] = con.execute(
    f"select final from {quarantine.games_sql(W)} where game = '{bad}'").fetchone() == (False,)
restore()

# systemic: more than a quarter of the night's finals fail; a night of one final (the first update of an evening) can't
# be systemic on its own, so then more than a quarter of the season's
pool, label = (night, "night's") if len(night) > 1 else (season, "season's")
k = max(int(len(pool) * quarantine.SHARE) + 1, 2)
rewrite("box", f"select * replace (case when game in ({', '.join(repr(g) for g in pool[:k])}) then pts + 1 else pts end as pts) from {{t}}")
code, out = gate("warehouse_tests.py")
checks[f"{k} of the {label} {len(pool)} finals failing fails the run"] = code == 1 and "systemic" in out
restore()
code, out = gate("warehouse_tests.py")
checks["and the run passes again once they are right"] = code == 0 and held() == set()

for name, ok in checks.items():
    print("ok  " if ok else "FAIL", name)
sys.exit(0 if all(checks.values()) else 1)
