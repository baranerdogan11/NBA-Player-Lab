"""Quarantine: a game that fails a gate is held out of what that gate protects, so the rest of the night still publishes.

warehouse/<season>/quarantine.json: {"games": [{"game", "gate", "scope", "reason", "first_seen"}, ...]}, one entry per
game per gate. The scope says what the game is held out of:
  box      its box score failed (warehouse_tests.py): the whole game, which the site shows as not final yet
  pbp      its play-by-play failed (warehouse_tests.py): lineups, on/off, RAPM, the shot chart and the game flow; the box
           score, which passed its own gates, still publishes
  lineups  lineups.py: lineups, on/off and RAPM
  shots    shots.py: the shot chart
  flow     site_data.py: the game flow
Each gate replaces its own entries on every run, and fetch_season.py fetches every quarantined game's box score and
play-by-play again on every run, so a corrected feed clears the game by itself. A game keeps its first_seen while any
gate holds it.

The run fails only when the failure is systemic, not one game's: more than a quarter of the latest night's finals or of
the season's are held, and at least two (a gate that fails without naming a game fails the run itself).

usage: python quarantine.py --check [2026-27]   exits 1 if a game has been held for more than STALE_HOURS
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

FILE = "quarantine.json"
STALE_HOURS = 12
SHARE = 0.25
HOLDS = {"box": {"box", "pbp", "lineups", "shots", "flow"}, "pbp": {"pbp", "lineups", "shots", "flow"},
         "lineups": {"lineups"}, "shots": {"shots"}, "flow": {"flow"}}   # scope -> the outputs it holds the game out of


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(w):
    path = os.path.join(w, FILE)
    return json.load(open(path))["games"] if os.path.exists(path) else []


def held(w, output, gate=None):
    """The ids of the games held out of one output (a key of HOLDS: box, pbp, lineups, shots or flow), by any gate but
    gate: a gate checks the games it holds itself again, so it can clear them."""
    return {e["game"] for e in load(w) if output in HOLDS[e["scope"]] and e["gate"] != gate}


def games_sql(w):
    """warehouse/<season>/games.parquet as a SQL relation, with a game whose box score is held marked not final."""
    src = f"read_parquet('{os.path.join(w, 'games.parquet')}')"
    ids = held(w, "box")
    return f"(select * replace (final and game not in ({', '.join(repr(g) for g in sorted(ids))}) as final) from {src})" if ids else src


def record(w, gate, failures, at=None):
    """Replaces gate's entries with failures, {game: (scope, reason)}, and returns all entries."""
    at = at or now_iso()
    old = load(w)
    first = {}
    for e in old:
        first[e["game"]] = min(first.get(e["game"], e["first_seen"]), e["first_seen"])
    entries = [e for e in old if e["gate"] != gate] + [
        {"game": g, "gate": gate, "scope": s, "reason": r[:500], "first_seen": first.get(g, at)} for g, (s, r) in sorted(failures.items())]
    entries.sort(key=lambda e: (e["game"], e["gate"]))
    json.dump({"games": entries}, open(os.path.join(w, FILE), "w"), indent=1)
    for g, (s, r) in sorted(failures.items()):
        print(f"QUARANTINE {g} ({gate}, {s}): {r[:300]}")
    return entries


def add(failures, game, scope, reason):
    """Adds one failure to a {game: (scope, reason)} dict; box outranks the narrower scopes, and reasons are joined."""
    s, r = failures.get(game, (scope, ""))
    failures[game] = ("box" if "box" in (s, scope) else s, f"{r}; {reason}" if r else reason)


def systemic(w):
    """The reason the run should fail, or None: too many of the latest night's or the season's finals held."""
    import duckdb
    ids = {e["game"] for e in load(w)}
    if not ids:
        return None
    finals = duckdb.connect().execute(f"select game, date from read_parquet('{os.path.join(w, 'games.parquet')}') "
                                      "where final and game_type in ('regular', 'playin', 'playoffs')").fetchall()
    night = max((d for _, d in finals), default=None)
    for label, games in (("the latest night's", {g for g, d in finals if d == night}), ("the season's", {g for g, _ in finals})):
        bad = len(ids & games)
        if bad > max(1, SHARE * len(games)):
            return f"{bad} of {label} {len(games)} finals are quarantined: more than {SHARE:.0%}, so the failure is systemic"
    return None


def exit_code(w):
    """0 unless the quarantine is systemic; prints what is held either way."""
    held_now = sorted({e["game"] for e in load(w)})
    if held_now:
        print(f"quarantined: {len(held_now)} game(s): {', '.join(held_now)}")
    why = systemic(w)
    if why:
        print(f"::error::{why}")
    return 1 if why else 0


def stale(entries, now=None, hours=STALE_HOURS):
    """The entries first seen more than hours ago."""
    now = now or datetime.now(timezone.utc)
    return [e for e in entries if now - datetime.fromisoformat(e["first_seen"].replace("Z", "+00:00")) > timedelta(hours=hours)]


if __name__ == "__main__":
    from season import ROOT, season
    w = os.path.join(ROOT, "warehouse", season())
    if "--check" not in sys.argv:
        raise SystemExit(__doc__)
    old = stale(load(w))
    for e in old:
        print(f"::error::{e['game']} quarantined since {e['first_seen']} by {e['gate']} ({e['scope']}): {e['reason']}")
    print(f"{len(load(w))} game entries quarantined, {len(old)} for more than {STALE_HOURS} h")
    sys.exit(1 if old else 0)
