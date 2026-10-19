"""SQL assertions over the silver layer. Exits non-zero if any fails, printing a few offending rows.

usage: python warehouse_tests.py [2026-27]
"""
import datetime
import json
import os
import sys
import duckdb
from season import ROOT, season

SEASON = season()
W = os.path.join(ROOT, "warehouse", SEASON)
con = duckdb.connect()
TABLES = ["teams", "games", "players", "box", "team_box", "periods", "events", "shots"]
for t in TABLES:
    con.execute(f"create view {t} as select * from read_parquet('{os.path.join(W, t + '.parquet')}')")
STATS = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk", "blka", "tov", "pf"]
sum_stats = ", ".join(f"sum({s}) {s}" for s in STATS)
differs = lambda a, b: " or ".join(f"{a}.{s} is distinct from {b}.{s}" for s in STATS)

# (name, query returning the offending rows)
TESTS = [
    ("teams: 30 rows, unique codes and ids", "select * from (select count(*) n, count(distinct team) t, count(distinct team_id) i from teams) where n != 30 or t != 30 or i != 30"),
    ("games: unique ids", "select game from games group by game having count(*) > 1"),
    # preseason games against non-NBA clubs are kept as scheduled, with the visitor's code as the feed gives it
    ("games: named teams are known outside the preseason", "select * from games where game_type != 'preseason' and ((home is not null and home not in (select team from teams)) or (away is not null and away not in (select team from teams)))"),
    ("games: final games have both teams", "select * from games where final and (home is null or away is null)"),
    ("games: final games have a winner", "select * from games where final and home_score = away_score"),
    ("games: final games are not in the future", "select * from games where final and tipoff_utc > now()::timestamp"),
    ("box: every cached game is a final game on the schedule", "select distinct b.game from box b left join games g using (game) where g.game is null or not g.final"),
    ("box: both teams of the game", "select b.* from box b join games g using (game) where b.team not in (g.home, g.away)"),
    ("box: one line per player per game", "select game, player from box group by 1, 2 having count(*) > 1"),
    ("box: makes never exceed attempts", "select * from box where fgm > fga or fg3m > fg3a or ftm > fta or fg3a > fga"),
    ("box: points reconcile with makes", "select * from box where pts != 2 * fgm + fg3m + ftm"),
    ("box: rebounds add up", "select * from box where reb != oreb + dreb"),
    ("team_box: two teams per game", "select game from team_box group by game having count(*) != 2"),
    ("team_box: score is the schedule's final score", """
        select t.* from team_box t join games g using (game) where t.score != case when t.home then g.home_score else g.away_score end"""),
    ("team_box: player lines add up to the team totals", f"""
        select t.game, t.team from team_box t join (select game, team, {sum_stats} from box group by 1, 2) p using (game, team) where {differs('t', 'p')}"""),
    ("periods: points by period add up to the final score", "select t.game, t.team from team_box t join (select game, team, sum(pts) p from periods group by 1, 2) q using (game, team) where q.p != t.score"),
    ("events: every final game has its play-by-play", "select game from team_box where game not in (select game from events) group by game"),
    ("shots: both teams of the game", "select s.* from shots s join games g using (game) where s.team not in (g.home, g.away)"),
]
# every player total rebuilt from the play-by-play must equal the official box score, stat by stat
con.execute("""
create view pbp_box as
with fg as (select game, player, count(*) fga, count(*) filter (made) fgm, count(*) filter (pts = 3) fg3a, count(*) filter (made and pts = 3) fg3m,
                   count(*) filter (block_player is not null) blka from shots where player is not null group by 1, 2),
     ft as (select game, player, count(*) fta, count(*) filter (result = 'Made') ftm from events where action_type = 'freethrow' and player is not null group by 1, 2),
     ast as (select game, assist_player player, count(*) ast from shots where made and assist_player is not null group by 1, 2),
     ev as (select game, player,
                   count(*) filter (action_type = 'rebound' and sub_type = 'offensive') oreb,
                   count(*) filter (action_type = 'rebound' and sub_type = 'defensive') dreb,
                   count(*) filter (action_type = 'steal') stl,
                   count(*) filter (action_type = 'block') blk,
                   count(*) filter (action_type = 'turnover') tov,
                   count(*) filter (action_type = 'foul' and sub_type not in ('technical', 'double technical')) pf
            from events where player is not null group by 1, 2)
select b.game, b.player, b.team,
       coalesce(fg.fgm, 0) * 2 + coalesce(fg.fg3m, 0) + coalesce(ft.ftm, 0) pts, coalesce(fg.fgm, 0) fgm, coalesce(fg.fga, 0) fga,
       coalesce(fg.fg3m, 0) fg3m, coalesce(fg.fg3a, 0) fg3a, coalesce(ft.ftm, 0) ftm, coalesce(ft.fta, 0) fta,
       coalesce(ev.oreb, 0) oreb, coalesce(ev.dreb, 0) dreb, coalesce(ev.oreb, 0) + coalesce(ev.dreb, 0) reb, coalesce(ast.ast, 0) ast,
       coalesce(ev.stl, 0) stl, coalesce(ev.blk, 0) blk, coalesce(fg.blka, 0) blka, coalesce(ev.tov, 0) tov, coalesce(ev.pf, 0) pf
from box b left join fg using (game, player) left join ft using (game, player) left join ast using (game, player) left join ev using (game, player)
where b.game in (select game from events)""")
for s in STATS:
    TESTS.append((f"play-by-play {s} per player per game equals the box score",
                  f"select p.game, p.player, p.team, p.{s} pbp, b.{s} box from pbp_box p join box b using (game, player) where p.{s} != b.{s}"))
TESTS += [
    ("play-by-play: every player with a stat in the play-by-play has a box line", """
        select distinct e.game, e.player from events e join team_box t on t.game = e.game and t.team = e.team left join box b on b.game = e.game and b.player = e.player
        where e.player is not null and b.player is null and e.action_type in ('2pt', '3pt', 'freethrow', 'rebound', 'steal', 'block', 'turnover')"""),
    ("play-by-play: the last score equals the final score", """
        select t.game, t.team, t.score, case when t.home then e.h else e.a end pbp
        from team_box t join (select game, max(score_home) h, max(score_away) a from events group by 1) e using (game)
        where t.score != case when t.home then e.h else e.a end"""),
]
# warnings: reported and counted, never fail the run
WARNINGS = [
    # the NBA Cup knockout games are added to the schedule in December, so a team shows 80 games until then
    ("games: each team plays 80 to 82 regular-season games", "select team, count(*) n from teams join games on team in (home, away) and game_type = 'regular' group by team having n not between 80 and 82"),
    ("games: final games have a box score cached", "select * from games where final and game_type in ('regular', 'playin', 'playoffs', 'cup_final') and game not in (select game from box)"),
]


def run(name, q, word):
    rows = con.execute(f"select * from ({q}) limit 6").fetchall()
    n = con.execute(f"select count(*) from ({q})").fetchone()[0] if rows else 0
    print(("PASS " if not n else word + " ") + name + ("" if not n else f"  ({n} rows)"))
    for r in rows[:5]:
        print("       ", r)
    return n


warn = sum(run(n, q, "WARN") != 0 for n, q in WARNINGS)
bad = sum(run(n, q, "FAIL") != 0 for n, q in TESTS)
stats = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}
json.dump({"season": SEASON, "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": stats,
           "games": con.execute("select count(distinct game) from box").fetchone()[0], "tests": len(TESTS), "failures": bad, "warnings": warn, "ok": bad == 0},
          open(os.path.join(W, "status.json"), "w"), indent=1)
print("rows:", stats)
print("RESULT:", "OK" if not bad else f"{bad} test(s) failed")
sys.exit(0 if not bad else 1)
