"""Shots from NBA CDN play-by-play actions (cdn.nba.com/static/json/liveData/playbyplay), with the possession context
known before each shot. The same code reads the live feed and the shufinskiy/nba_data `cdnnba` archive, which stores
those actions verbatim as CSV, so the model is trained on exactly the fields it scores. No I/O here.

Possession context: the feed's `possession` field names the team with the ball on every action. A possession starts
when that team changes, or on an offensive rebound (the shot clock resets); poss_start says how it began and
poss_sec is the game-clock seconds from that start to the shot.
"""
import re
import pandas as pd

CLOCK = re.compile(r"PT(\d+)M([\d.]+)S")


def clock_sec(s):
    """'PT07M42.00S' -> 462.0 seconds left in the period."""
    m = CLOCK.match(s or "")
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def _cause(a, prev):
    """How a possession began and the clock it began at, from the action that handed the ball over: the action where
    the `possession` field flips (a defensive rebound, a steal, a jump ball) or, when the flip only shows on the next
    action (after a made basket or a turnover), the action before it."""
    for x in (a, prev):
        if x is None:
            continue
        t, sub = x["actionType"], x.get("subType")
        if t == "rebound":
            return ("oreb" if sub == "offensive" else "dreb"), clock_sec(x.get("clock"))
        if t == "steal":
            return "steal", clock_sec(x.get("clock"))
        if t == "turnover":
            return "tov", clock_sec(x.get("clock"))
        if t in ("period", "jumpball"):
            return "period", clock_sec(x.get("clock"))
        if t in ("2pt", "3pt", "freethrow") and x is prev:
            return "make", clock_sec(x.get("clock"))
    return "?", clock_sec(a.get("clock"))


def shots_from_actions(actions, game):
    """One row per field-goal attempt of one game. `actions` is the feed's list of action dicts (any order)."""
    acts = sorted(actions, key=lambda a: int(a["orderNumber"]))
    out, team, start_clock, kind, period, prev = [], None, 720.0, "period", 0, None
    for a in acts:
        t = a["actionType"]
        if t in ("substitution", "timeout"):
            continue
        per, c = int(a["period"]), clock_sec(a.get("clock"))
        if per != period:
            period, team, kind, prev = per, None, "period", None
            start_clock = 720.0 if per <= 4 else 300.0
        pos = str(a.get("possession") or "0")
        if pos not in ("0", "") and pos != team:
            if team is not None:
                kind, sc = _cause(a, prev)
                start_clock = sc if sc is not None else start_clock
            team = pos
        elif t == "rebound" and a.get("subType") == "offensive":
            kind, start_clock = "oreb", c if c is not None else start_clock
        if str(a.get("isFieldGoal")) in ("1", "True", "true") and t in ("2pt", "3pt"):
            q = a.get("qualifiers") or ""
            q = q if isinstance(q, str) else ", ".join(q)
            out.append({"game": game, "action": int(a["actionNumber"]), "order": int(a["orderNumber"]), "player": str(a["personId"]),
                        "team": str(a["teamId"]), "period": per, "clock_sec": c, "x": _num(a.get("xLegacy")), "y": _num(a.get("yLegacy")),
                        "dist_ft": _num(a.get("shotDistance")), "area": a.get("area") or "?", "shot_type": a.get("subType") or "?",
                        "descriptor": a.get("descriptor") or "", "qualifiers": q, "pts": 3 if t == "3pt" else 2,
                        "made": a.get("shotResult") == "Made", "score_home": _num(a.get("scoreHome")), "score_away": _num(a.get("scoreAway")),
                        "poss_sec": None if c is None or start_clock is None else max(start_clock - c, 0.0), "poss_start": kind})
        prev = a
    return out


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def shots_frame(actions_by_game, home_team):
    """DataFrame of shots for many games; home_team maps game id -> home teamId (the archive has no game header)."""
    rows = [r for g, acts in actions_by_game.items() for r in shots_from_actions(acts, g)]
    df = pd.DataFrame(rows)
    df["home_team"] = df.game.map(home_team)
    return df
