"""The site's JSON: what the page reads, written from plain rows (games, box-score lines, players).

Every file is derived from the same box-score lines, so a player's game log, his season row, the game page and the
leaders agree by construction. Only integer totals are written; the page turns them into averages and percentages
with rdiv in template.html, the same formula as rounding.avg, the site's one rounding rule. The one exception is
RAPM (rapm.py), a model's estimate rather than a ratio of totals, written already rounded by rounding.rnd.

Files under <out>/ (out is teams/<season>/):
  index.json        season, label, build time, the 30 clubs with colours and games played
  games.json        every game of the schedule: date, tip time, clubs, and the score once final
  <CODE>.json       the club's players, each with a log of his box-score lines (any club, newest last)
  games/<gid>.json  one final: score by period and both box scores
  leaders.json      every player's season totals, under his current club, his clubs' totals over the same games
                    (tm_fga, tm_fta, tm_tov, tm_sec, for usage) and his RAPM, O-RAPM and D-RAPM (null without one)

from_warehouse() turns the warehouse tables (warehouse/<season>/*.parquet, see warehouse.py) into those rows: regular
season games only, and box lines of every player who was active (a coach's decision is a line with 0 seconds; inactive
players have none). Every player on a club's roster is listed under that club, with an empty log until his first game;
a player no longer on any roster stays under the club of his last box score.
usage: python site_data.py [2026-27]   (reads warehouse/<season>/, writes teams/<season>/)
"""
import json
import os
from rounding import rnd

STATS = ["pts", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf",
         "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm"]
HERE = os.path.dirname(os.path.abspath(__file__))


def load_teams():
    with open(os.path.join(HERE, "teams.json")) as f:
        return json.load(f)["teams"]


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def _line(r):
    return {"start": bool(r["start"]), "sec": int(r["sec"]), **{k: int(r[k]) for k in STATS}}


def write_site(out, season, label, built, teams, players, games, lines):
    """teams: load_teams() rows. players: pid, team (current), name, jersey, pos, height, born, and optionally
    o_rapm, d_rapm (unrounded, from rapm.py).
    games: gid, date, time (UTC ISO), home, away, final, hs, as, periods ([[home, away], ...]) for finals.
    lines: one per player per final: gid, team, pid, name, start, sec and every key in STATS."""
    final = {g["gid"]: g for g in games if g["final"]}
    gp = {t["code"]: 0 for t in teams}
    for g in final.values():
        gp[g["home"]] += 1
        gp[g["away"]] += 1
    _dump(os.path.join(out, "index.json"), {
        "season": season, "label": label, "built": built,
        "teams": [{**{k: t[k] for k in ("code", "id", "city", "name", "conf", "div", "colors")}, "gp": gp[t["code"]]} for t in teams]})
    _dump(os.path.join(out, "games.json"), {"games": [
        {"gid": g["gid"], "date": g["date"], "time": g["time"], "home": g["home"], "away": g["away"],
         "hs": g["hs"] if g["final"] else None, "as": g["as"] if g["final"] else None} for g in sorted(games, key=lambda g: (g["time"], g["gid"]))]})

    by_game = {}
    for r in lines:
        by_game.setdefault(r["gid"], []).append(r)
    for gid, g in final.items():
        box = {c: [{"pid": r["pid"], "name": r["name"], **_line(r)} for r in by_game.get(gid, []) if r["team"] == c]
               for c in (g["home"], g["away"])}
        for c, side in ((g["home"], "hs"), (g["away"], "as")):
            if sum(x["pts"] for x in box[c]) != g[side]:
                raise ValueError(f"game {gid}: {c} box score adds up to {sum(x['pts'] for x in box[c])}, final says {g[side]}")
        _dump(os.path.join(out, "games", f"{gid}.json"), {
            "gid": gid, "date": g["date"], "home": g["home"], "away": g["away"], "hs": g["hs"], "as": g["as"],
            "periods": g["periods"], "box": box})

    logs = {}
    for r in sorted(lines, key=lambda r: (final[r["gid"]]["time"], r["gid"])):
        g = final[r["gid"]]
        home = r["team"] == g["home"]
        ts, os_ = (g["hs"], g["as"]) if home else (g["as"], g["hs"])
        logs.setdefault(r["pid"], []).append({
            "gid": r["gid"], "date": g["date"], "team": r["team"], "opp": g["away"] if home else g["home"], "home": home,
            "ts": ts, "os": os_, **_line(r)})
    team_tot = {}
    for r in lines:
        t = team_tot.setdefault((r["gid"], r["team"]), {"fga": 0, "fta": 0, "tov": 0, "sec": 0})
        for k in t:
            t[k] += int(r[k])
    roster = {}
    leaders = []
    for p in players:
        log = logs.get(p["pid"], [])
        played = [x for x in log if x["sec"] > 0]
        info = {k: p[k] for k in ("pid", "name", "jersey", "pos", "height", "born")}
        roster.setdefault(p["team"], []).append({**info, "log": log})
        o, d = p.get("o_rapm"), p.get("d_rapm")
        has = o is not None and d is not None
        leaders.append({"pid": p["pid"], "name": p["name"], "team": p["team"], "pos": p["pos"], "gp": len(played),
                        "sec": sum(x["sec"] for x in played), **{k: sum(x[k] for x in played) for k in STATS},
                        **{f"tm_{k}": sum(team_tot[(x["gid"], x["team"])][k] for x in played) for k in ("fga", "fta", "tov", "sec")},
                        "rapm": rnd(o + d) if has else None, "orapm": rnd(o) if has else None, "drapm": rnd(d) if has else None})
    for t in teams:
        _dump(os.path.join(out, f"{t['code']}.json"), {"code": t["code"], "players": roster.get(t["code"], [])})
    _dump(os.path.join(out, "leaders.json"), {"players": leaders})


def from_warehouse(wh):
    """players, games, lines for write_site() from the Parquet tables in the directory wh."""
    import duckdb
    con = duckdb.connect()
    for t in ("games", "box", "players", "periods"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    if os.path.exists(os.path.join(wh, "roster.parquet")):
        con.execute(f"create view roster as select * from read_parquet('{os.path.join(wh, 'roster.parquet')}')")
    else:   # an earlier season, or a warehouse built before rosters were fetched: players come from box scores only
        con.execute("create view roster as select null::int as player, '' as team, '' as name, '' as jersey, '' as position, '' as height where false")

    def rows(sql):
        cur = con.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    played = "from box b join games g using (game) join players p using (player) where g.game_type = 'regular' and g.final and b.status = 'ACTIVE'"
    qtr = {}
    for r in rows("select q.game, q.period, sum(q.pts) filter (where q.team = g.home) as h, sum(q.pts) filter (where q.team = g.away) as a "
                  "from periods q join games g using (game) group by all order by q.game, q.period"):
        qtr.setdefault(r["game"], []).append([int(r["h"] or 0), int(r["a"] or 0)])
    games = [{**g, "final": bool(g["final"]), **({"periods": qtr.get(g["gid"], [])} if g["final"] else {})}
             for g in rows("select game as gid, strftime(date, '%Y-%m-%d') as \"date\", strftime(tipoff_utc, '%Y-%m-%dT%H:%M:%SZ') as \"time\", "
                           "home, away, final, home_score as hs, away_score as \"as\" from games where game_type = 'regular'")]
    stat = ", ".join(f"coalesce(b.{'plus_minus' if k == 'pm' else k}, 0) as {k}" for k in STATS)
    lines = rows(f"select b.game as gid, b.team, b.player::varchar as pid, p.name, b.starter as start, round(b.seconds)::int as sec, {stat} {played}")
    boxed = rows("select b.player::varchar as pid, arg_max(b.team, g.tipoff_utc) as team, any_value(p.name) as \"name\", "
                 "arg_max(b.jersey, g.tipoff_utc) as jersey, arg_max(b.position, g.tipoff_utc) filter (where b.position is not null) as pos, "
                 f"null as height, null as born {played} group by b.player")
    # the roster gives the current club, the jersey and the height (6-8 in the feed, shown as 6'8"); box scores have no height
    players = {p["pid"]: p for p in boxed}
    for r in rows("select player::varchar as pid, team, name, jersey, position as pos, height from roster"):
        b = players.get(r["pid"], {})
        ft, _, inch = (r["height"] or "").partition("-")
        players[r["pid"]] = {**r, "jersey": r["jersey"] or b.get("jersey"), "pos": r["pos"] or b.get("pos"),
                             "height": f"{ft}'{inch}\"" if inch else r["height"], "born": None}
    if os.path.exists(os.path.join(wh, "rapm.parquet")):
        for r in rows(f"select player::varchar as pid, o, d from read_parquet('{os.path.join(wh, 'rapm.parquet')}')"):
            if r["pid"] in players:
                players[r["pid"]].update(o_rapm=r["o"], d_rapm=r["d"])
    return sorted(players.values(), key=lambda p: p["pid"]), games, lines


if __name__ == "__main__":
    import datetime
    from season import ROOT, season
    SEASON = season()
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "box.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    teams = load_teams()
    write_site(out, SEASON, SEASON, built, teams, *from_warehouse(wh))
    print(f"{SEASON}: site JSON written to {out}")
