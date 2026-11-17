"""Self-tests for due.py: which games count, and when the update workflow runs.
usage: python tests/test_publish.py
"""
import ast
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from due import BUILT_TYPES, decide, final_games, open_games  # noqa: E402


def t(h, m=0):
    return datetime(2026, 10, 20, h, m, tzinfo=timezone.utc)


sched = {"leagueSchedule": {"seasonYear": "2026-27", "gameDates": [{"games": [
    {"gameId": "0022600001", "gameStatus": 3}, {"gameId": "0022600002", "gameStatus": 2},
    {"gameId": "0012600050", "gameStatus": 3}, {"gameId": "0052600001", "gameStatus": 3},
    {"gameId": "0062600001", "gameStatus": 3}]}]}}
assert final_games(sched, "2026-27") == {"0022600001", "0052600001", "0062600001"}, \
    "only final regular, play-in, playoff and Cup final games: the ones fetch_season.py fetches"
try:
    final_games(sched, "2027-28")
    raise AssertionError("a schedule for another season must stop the run")
except SystemExit:
    pass

after_nightly = {"games": 2, "checked_at": "2026-10-20T10:05:00Z"}
before_nightly = {"games": 2, "checked_at": "2026-10-20T09:00:00Z"}
assert decide(3, after_nightly, t(23))[0], "a newly final game runs the update"
assert not decide(2, after_nightly, t(23))[0], "nothing new since the nightly: no run"
assert not decide(2, before_nightly, t(9, 30))[0], "before 10:00 UTC the nightly waits"
assert decide(2, before_nightly, t(10, 5))[0], "after 10:00 UTC the nightly is due"
assert not decide(2, after_nightly, t(14))[0], "the nightly runs once a day"
assert decide(0, {}, t(3))[0], "nothing published yet: run"
night = {"leagueSchedule": {"seasonYear": "2026-27", "gameDates": [{"games": [
    {"gameId": "0022600001", "gameStatus": 3, "gameDateTimeUTC": "2026-10-20T23:00:00Z"},
    {"gameId": "0022600002", "gameStatus": 2, "gameDateTimeUTC": "2026-10-21T01:30:00Z"},
    {"gameId": "0022600003", "gameStatus": 1, "gameDateTimeUTC": "2026-10-21T02:00:00Z"},
    {"gameId": "0022600004", "gameStatus": 1, "gameDateTimeUTC": "2026-10-22T23:00:00Z"},
    {"gameId": "0012600005", "gameStatus": 1, "gameDateTimeUTC": "2026-10-21T00:00:00Z"}]}]}}
assert open_games(night, "2026-27", t(23)) == {"0022600002", "0022600003"}, "tonight's built games not final yet"
assert open_games(night, "2026-27", datetime(2026, 10, 21, 16, tzinfo=timezone.utc)) == set(), \
    "a game 14 hours past its tip-off no longer keeps the watcher up"
# status.json counts every game with a box score in the warehouse (warehouse_tests.py), so due.py must count the game
# types fetch_season.py fetches: a fetched game it did not count (the NBA Cup final) would keep the build one game ahead,
# and the last game of every night would wait for the nightly run. fetch_season.py fetches on import, so it is read as text.
fetch_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fetch_season.py")).read()
fetched = ast.literal_eval(re.search(r"^GAME_TYPES = (.+)$", fetch_src, re.M).group(1))
assert {t[2] for t in BUILT_TYPES} == fetched, f"due.py counts {BUILT_TYPES}, fetch_season.py fetches {fetched}"
print("test_publish: ok")
