"""The site's JSON: what the page reads, written from plain rows (games, box-score lines, players).

Every file is derived from the same box-score lines, so a player's game log, his season row, the game page and the
leaders agree by construction. Only integer totals are written; the page turns them into averages and percentages
with one rounding rule, rdiv below, which has an exact twin in template.html.

Files under <out>/ (out is teams/<season>/):
  index.json        season, label, build time, the 30 clubs with colours and games played
  games.json        every game of the schedule: date, tip time, clubs, and the score once final
  <CODE>.json       the club's players, each with a log of his box-score lines (any club, newest last)
  games/<gid>.json  one final: score by period and both box scores
  leaders.json      every player's season totals, under his current club
"""
import json
import os

STATS = ["pts", "oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf",
         "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm"]
HERE = os.path.dirname(os.path.abspath(__file__))


def rdiv(num, den, d=1):
    """num/den to d decimals, half away from zero, in exact integer arithmetic; None when den is 0.

    The page's rdiv() in template.html is the same formula, so Python and the page never disagree on a digit."""
    if not den:
        return None
    p = 10 ** d
    q = (2 * abs(num) * p + den) // (2 * den)
    s = str(q).rjust(d + 1, "0")
    out = s[:-d] + "." + s[-d:] if d else s
    return "-" + out if num < 0 and q else out


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
    """teams: load_teams() rows. players: pid, team (current), name, jersey, pos, height, born.
    games: gid, date, time (UTC ISO), home, away, final, hs, as, periods ([[home, away], ...]) for finals.
    lines: one per player per final: gid, team, pid, name, start, sec and every key in STATS."""
    final = {g["gid"]: g for g in games if g["final"]}
    gp = {t["code"]: 0 for t in teams}
    for g in final.values():
        gp[g["home"]] += 1
        gp[g["away"]] += 1
    _dump(os.path.join(out, "index.json"), {
        "season": season, "label": label, "built": built,
        "teams": [{**{k: t[k] for k in ("code", "city", "name", "conf", "div", "colors")}, "gp": gp[t["code"]]} for t in teams]})
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
    roster = {}
    leaders = []
    for p in players:
        log = logs.get(p["pid"], [])
        played = [x for x in log if x["sec"] > 0]
        info = {k: p[k] for k in ("pid", "name", "jersey", "pos", "height", "born")}
        roster.setdefault(p["team"], []).append({**info, "log": log})
        leaders.append({"pid": p["pid"], "name": p["name"], "team": p["team"], "pos": p["pos"], "gp": len(played),
                        "sec": sum(x["sec"] for x in played), **{k: sum(x[k] for x in played) for k in STATS}})
    for t in teams:
        _dump(os.path.join(out, f"{t['code']}.json"), {"code": t["code"], "players": roster.get(t["code"], [])})
    _dump(os.path.join(out, "leaders.json"), {"players": leaders})
