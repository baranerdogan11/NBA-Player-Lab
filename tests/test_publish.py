"""Self-tests for due.py: which games count, and when the update workflow runs.
usage: python tests/test_publish.py
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from due import decide, final_games  # noqa: E402


def t(h, m=0):
    return datetime(2026, 10, 20, h, m, tzinfo=timezone.utc)


sched = {"leagueSchedule": {"seasonYear": "2026-27", "gameDates": [{"games": [
    {"gameId": "0022600001", "gameStatus": 3}, {"gameId": "0022600002", "gameStatus": 2},
    {"gameId": "0012600050", "gameStatus": 3}, {"gameId": "0052600001", "gameStatus": 3},
    {"gameId": "0062600001", "gameStatus": 3}]}]}}
assert final_games(sched, "2026-27") == {"0022600001", "0052600001"}, "only final regular, play-in and playoff games"
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
print("test_publish: ok")
