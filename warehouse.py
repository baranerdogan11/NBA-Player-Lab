"""Silver layer: normalised tables built from the cached feeds (bronze) and persisted as Parquet.

Tables under warehouse/<season>/: teams, games, players, box (one line per player per game), team_box (one line per
team per game: the official totals, team rebounds and team turnovers included), periods (points per team per period),
events (every play-by-play action) and shots (every field-goal attempt). Player ids are the league's personId, team
codes its tricodes. See warehouse/SCHEMA.md.

usage: python warehouse.py [2026-27]
"""
import glob
import json
import os
import re
import duckdb
from season import ROOT, season

SEASON = season()
CACHE = os.path.join(ROOT, "cache", SEASON)
OUT = os.path.join(ROOT, "warehouse", SEASON)
os.makedirs(OUT, exist_ok=True)
GAME_TYPE = {"1": "preseason", "2": "regular", "3": "allstar", "4": "playoffs", "5": "playin", "6": "cup_final"}


def secs(iso):
    """ISO 8601 duration as the feeds write clocks and minutes (PT11M47.00S) to seconds."""
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", iso or "")
    return round(int(m.group(1) or 0) * 60 + float(m.group(2) or 0), 2) if m and iso != "PT" else None


def num(v):
    return None if v in (None, "") else int(v)


# ---- games and teams, from the schedule
# A game whose teams are not decided yet (the NBA Cup knockout rounds, the play-in, the playoffs) carries a placeholder
# team with teamId 0 and no tricode; it is kept with home or away NULL until the schedule names the teams.
tricode = lambda t: t.get("teamTricode") if t.get("teamId") else None
games, teams = [], {}
for g in json.load(open(os.path.join(CACHE, "schedule.json"))):
    h, a = g["homeTeam"], g["awayTeam"]
    gtype = GAME_TYPE.get(g["gameId"][2])
    if gtype == "regular":
        for t in (h, a):
            if tricode(t):
                teams[t["teamTricode"]] = {"team": t["teamTricode"], "team_id": t["teamId"], "city": t["teamCity"], "name": t["teamName"]}
    games.append({"game": g["gameId"], "game_type": gtype, "date": (g.get("gameDateEst") or "")[:10] or None, "tipoff_utc": g.get("gameDateTimeUTC"),
                  "home": tricode(h), "away": tricode(a), "home_score": h.get("score"), "away_score": a.get("score"),
                  "status": g["gameStatus"], "final": g["gameStatus"] == 3})

# ---- box scores: player lines, team totals and period scores, both teams of every cached game
STAT = {"pts": "points", "fgm": "fieldGoalsMade", "fga": "fieldGoalsAttempted", "fg3m": "threePointersMade", "fg3a": "threePointersAttempted",
        "ftm": "freeThrowsMade", "fta": "freeThrowsAttempted", "oreb": "reboundsOffensive", "dreb": "reboundsDefensive", "reb": "reboundsTotal",
        "ast": "assists", "stl": "steals", "blk": "blocks", "blka": "blocksReceived", "tov": "turnovers", "pf": "foulsPersonal",
        "pf_off": "foulsOffensive", "tech": "foulsTechnical", "fd": "foulsDrawn", "plus_minus": "plusMinusPoints"}
TEAM_ONLY = {"team_reb": "reboundsTeam", "team_oreb": "reboundsTeamOffensive", "team_dreb": "reboundsTeamDefensive", "team_tov": "turnoversTeam"}
players, box, team_box, periods = {}, [], [], []
for path in sorted(glob.glob(os.path.join(CACHE, "box_*.json"))):
    b = json.load(open(path))["game"]
    gid = b["gameId"]
    for side in ("homeTeam", "awayTeam"):
        t = b[side]
        team = t["teamTricode"]
        for p in t["players"]:
            s = p.get("statistics") or {}
            players[p["personId"]] = {"player": p["personId"], "name": p["name"], "first_name": p.get("firstName"), "family_name": p.get("familyName")}
            box.append({"game": gid, "player": p["personId"], "team": team, "jersey": p.get("jerseyNum"), "position": p.get("position") or None,
                        "starter": p.get("starter") == "1", "played": p.get("played") == "1", "status": p.get("status"),
                        "not_playing_reason": p.get("notPlayingReason"), "seconds": secs(s.get("minutes")) or 0.0,
                        **{k: num(s.get(v)) for k, v in STAT.items()}})
        s = t["statistics"]
        # the team's reboundsTotal includes team rebounds; reb here is the players' sum, like every other column, and team_reb the rest
        team_box.append({"game": gid, "team": team, "opponent": b["awayTeam" if side == "homeTeam" else "homeTeam"]["teamTricode"], "home": side == "homeTeam",
                         "score": t["score"], "seconds": secs(s.get("minutes")), **{k: num(s.get(v)) for k, v in STAT.items() if k != "plus_minus"},
                         "reb": num(s.get("reboundsPersonal")), **{k: num(s.get(v)) for k, v in TEAM_ONLY.items()}})
        for q in t.get("periods", []):
            periods.append({"game": gid, "team": team, "period": q["period"], "period_type": q.get("periodType"), "pts": q["score"]})

# ---- play-by-play: every action, and every field-goal attempt as a shot
events, shots = [], []
for path in sorted(glob.glob(os.path.join(CACHE, "pbp_*.json"))):
    j = json.load(open(path))["game"]
    gid = j["gameId"]
    for a in j["actions"]:
        e = {"game": gid, "action": a["actionNumber"], "order_no": a.get("orderNumber"), "period": a["period"], "clock": secs(a.get("clock")),
             "team": a.get("teamTricode") or None, "player": a.get("personId") or None, "action_type": a["actionType"], "sub_type": a.get("subType") or None,
             "descriptor": a.get("descriptor") or None, "qualifiers": a.get("qualifiers") or [], "result": a.get("shotResult"),
             "assist_player": a.get("assistPersonId"), "block_player": a.get("blockPersonId"), "steal_player": a.get("stealPersonId"),
             "foul_drawn_player": a.get("foulDrawnPersonId"), "jump_won_player": a.get("jumpBallWonPersonId"), "jump_lost_player": a.get("jumpBallLostPersonId"),
             "team_id": a.get("teamId") or None, "possession": a.get("possession") or None, "score_home": num(a.get("scoreHome")), "score_away": num(a.get("scoreAway")),
             "description": a.get("description")}
        events.append(e)
        if a.get("isFieldGoal") == 1:
            shots.append({"game": gid, "action": a["actionNumber"], "player": a.get("personId"), "team": a.get("teamTricode"), "period": a["period"],
                          "clock": e["clock"], "made": a.get("shotResult") == "Made", "pts": 3 if a["actionType"] == "3pt" else 2,
                          "x": a.get("xLegacy"), "y": a.get("yLegacy"), "distance": a.get("shotDistance"), "area": a.get("area"),
                          "area_detail": a.get("areaDetail"), "sub_type": a.get("subType"), "descriptor": a.get("descriptor") or None,
                          "qualifiers": e["qualifiers"], "assist_player": a.get("assistPersonId"), "block_player": a.get("blockPersonId"),
                          "score_home": e["score_home"], "score_away": e["score_away"]})

con = duckdb.connect()


def to_parquet(name, rows, schema):
    """schema: list of (column, duckdb type); rows: list of dicts."""
    tmp = os.path.join(OUT, f"{name}.jsonl")
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k, _ in schema}) + "\n")
    cols = ", ".join(f"'{k}': '{t}'" for k, t in schema)
    con.execute(f"copy (select * from read_json('{tmp}', format='newline_delimited', columns={{{cols}}})) to '{os.path.join(OUT, name + '.parquet')}' (format parquet, compression zstd)")
    os.remove(tmp)
    return len(rows)


I, V, B, D = "INTEGER", "VARCHAR", "BOOLEAN", "DOUBLE"
counts = {
    "teams": to_parquet("teams", sorted(teams.values(), key=lambda t: t["team"]), [("team", V), ("team_id", I), ("city", V), ("name", V)]),
    "games": to_parquet("games", games, [("game", V), ("game_type", V), ("date", "DATE"), ("tipoff_utc", "TIMESTAMP"), ("home", V), ("away", V),
                                         ("home_score", I), ("away_score", I), ("status", I), ("final", B)]),
    "players": to_parquet("players", list(players.values()), [("player", I), ("name", V), ("first_name", V), ("family_name", V)]),
    "box": to_parquet("box", box, [("game", V), ("player", I), ("team", V), ("jersey", V), ("position", V), ("starter", B), ("played", B), ("status", V),
                                   ("not_playing_reason", V), ("seconds", D)] + [(k, I) for k in STAT]),
    "team_box": to_parquet("team_box", team_box, [("game", V), ("team", V), ("opponent", V), ("home", B), ("score", I), ("seconds", D)]
                           + [(k, I) for k in STAT if k != "plus_minus"] + [(k, I) for k in TEAM_ONLY]),
    "periods": to_parquet("periods", periods, [("game", V), ("team", V), ("period", I), ("period_type", V), ("pts", I)]),
    "events": to_parquet("events", events, [("game", V), ("action", I), ("order_no", "BIGINT"), ("period", I), ("clock", D), ("team", V), ("player", I),
                                            ("action_type", V), ("sub_type", V), ("descriptor", V), ("qualifiers", "VARCHAR[]"), ("result", V),
                                            ("assist_player", I), ("block_player", I), ("steal_player", I), ("foul_drawn_player", I),
                                            ("jump_won_player", I), ("jump_lost_player", I), ("team_id", I), ("possession", I), ("score_home", I), ("score_away", I), ("description", V)]),
    "shots": to_parquet("shots", shots, [("game", V), ("action", I), ("player", I), ("team", V), ("period", I), ("clock", D), ("made", B), ("pts", I),
                                         ("x", I), ("y", I), ("distance", D), ("area", V), ("area_detail", V), ("sub_type", V), ("descriptor", V),
                                         ("qualifiers", "VARCHAR[]"), ("assist_player", I), ("block_player", I), ("score_home", I), ("score_away", I)]),
}
json.dump({"season": SEASON, "tables": counts}, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
print(f"{SEASON} warehouse: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
