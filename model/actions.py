"""Shots from the play-by-play, with the possession context known before each shot. Works on the warehouse's events
table (warehouse.py: the CDN liveData actions with snake_case names, shot geometry joined from shots) and on the
shufinskiy/nba_data `cdnnba` archive, which stores the same CDN actions verbatim as CSV; from_archive renames the
archive's columns to the warehouse's, so the model is trained on exactly the fields it scores. No I/O here.

Possession context: the feed's `possession` field names the team (by id) with the ball on every action. A possession
starts when that team changes, or on an offensive rebound (the shot clock resets); poss_start says how it began and
poss_sec is the game-clock seconds from that start to the shot.
"""
import re
import pandas as pd

# archive (CDN) column -> warehouse column
ARCHIVE = {"gameId": "game", "actionNumber": "action", "orderNumber": "order_no", "period": "period", "clock": "clock", "teamTricode": "team",
           "personId": "player", "actionType": "action_type", "subType": "sub_type", "descriptor": "descriptor", "qualifiers": "qualifiers",
           "shotResult": "result", "assistPersonId": "assist_player", "blockPersonId": "block_player", "stealPersonId": "steal_player",
           "foulDrawnPersonId": "foul_drawn_player", "jumpBallWonPersonId": "jump_won_player", "jumpBallLostPersonId": "jump_lost_player",
           "teamId": "team_id", "possession": "possession", "scoreHome": "score_home", "scoreAway": "score_away",
           "xLegacy": "x", "yLegacy": "y", "shotDistance": "distance", "area": "area", "timeActual": "time_actual"}
IDS = ["player", "assist_player", "block_player", "steal_player", "foul_drawn_player", "jump_won_player", "jump_lost_player", "team_id", "possession"]
INTS = ["action", "order_no", "period", "score_home", "score_away"]
CLOCK = re.compile(r"PT(\d+)M([\d.]+)S")


def clock_sec(s):
    """'PT07M42.00S' -> 462.0 seconds left in the period."""
    m = CLOCK.match(s or "")
    return round(int(m.group(1)) * 60 + float(m.group(2)), 2) if m else None


def from_archive(raw):
    """The archive's CSV (all strings) as warehouse events: same names and types; ids of 0 (team actions) become null."""
    d = raw[[c for c in ARCHIVE if c in raw]].rename(columns=ARCHIVE)
    d["game"] = d.game.str.zfill(10)
    d["clock"] = d.clock.map(clock_sec)
    for c in INTS + IDS:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce").astype("Int64")
            if c in IDS:
                d[c] = d[c].replace(0, pd.NA)
    for c in ("x", "y", "distance"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["qualifiers"] = d.qualifiers.map(lambda q: [s.strip() for s in q.split(",") if s.strip()])
    for c in ("team", "sub_type", "descriptor", "result", "area"):
        d[c] = d[c].replace("", None)
    return d


def _v(x):
    """A value from a row, with pandas' missing markers as None."""
    return None if x is None or x is pd.NA or (isinstance(x, float) and x != x) else x


def _cause(a, prev):
    """How a possession began and the clock it began at, from the action that handed the ball over: the action where
    the `possession` field flips (a defensive rebound, a steal, a jump ball) or, when the flip only shows on the next
    action (after a made basket or a turnover), the action before it."""
    for x in (a, prev):
        if x is None:
            continue
        t, sub = x["action_type"], x.get("sub_type")
        if t == "rebound":
            return ("oreb" if sub == "offensive" else "dreb"), _v(x.get("clock"))
        if t == "steal":
            return "steal", _v(x.get("clock"))
        if t == "turnover":
            return "tov", _v(x.get("clock"))
        if t in ("period", "jumpball"):
            return "period", _v(x.get("clock"))
        if t in ("2pt", "3pt", "freethrow") and x is prev:
            return "make", _v(x.get("clock"))
    return "?", _v(a.get("clock"))


def shots_from_actions(actions):
    """One row per field-goal attempt of one game, from its events as dicts (any order)."""
    acts = sorted(actions, key=lambda a: int(a["order_no"]))
    out, team, start_clock, kind, period, prev = [], None, 720.0, "period", 0, None
    for a in acts:
        t = a["action_type"]
        if t in ("substitution", "timeout"):
            continue
        per, c = int(a["period"]), _v(a.get("clock"))
        if per != period:
            period, team, kind, prev = per, None, "period", None
            start_clock = 720.0 if per <= 4 else 300.0
        pos = _v(a.get("possession"))
        if pos is not None and pos != team:
            if team is not None:
                kind, sc = _cause(a, prev)
                start_clock = sc if sc is not None else start_clock
            team = pos
        elif t == "rebound" and a.get("sub_type") == "offensive":
            kind, start_clock = "oreb", c if c is not None else start_clock
        if t in ("2pt", "3pt"):
            q = _v(a.get("qualifiers"))
            out.append({"game": a["game"], "action": int(a["action"]), "order_no": int(a["order_no"]), "player": _v(a.get("player")),
                        "team": _v(a.get("team")), "period": per, "clock": c, "x": _v(a.get("x")), "y": _v(a.get("y")),
                        "distance": _v(a.get("distance")), "area": _v(a.get("area")), "sub_type": _v(a.get("sub_type")),
                        "descriptor": _v(a.get("descriptor")), "qualifiers": list(q) if q is not None else [], "pts": 3 if t == "3pt" else 2,
                        "made": a.get("result") == "Made", "score_home": _v(a.get("score_home")), "score_away": _v(a.get("score_away")),
                        "poss_sec": None if c is None or start_clock is None else max(start_clock - c, 0.0), "poss_start": kind})
        prev = a
    return out


def shots_frame(events, home):
    """Shots of many games from an events frame; home maps game -> home team tricode."""
    rows = [r for _, g in events.groupby("game", sort=False) for r in shots_from_actions(g.to_dict("records"))]
    df = pd.DataFrame(rows)
    df["home"] = df.game.map(home)
    return df
