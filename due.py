"""When the update workflow runs: a game has gone final since the last published build, or the nightly is due.
Reads the NBA schedule (from the CDN's S3 origin) and the committed warehouse/<season>/status.json, prints its reasoning and writes run=true|false
and final=<games> to $GITHUB_OUTPUT. warehouse_tests.py writes that file on every passing build;
until it exists, --record=<games> stores the count and the time after a build, so the next check compares against what
was published.
usage: python due.py [2026-27]
       python due.py --record=<games> [2026-27]
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from season import ROOT, season

# the S3 origin behind cdn.nba.com: the CDN refuses scripted clients, the bucket serves the same files
SCHEDULE = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/staticData/scheduleLeagueV2.json"
# game ids start with the game type: 002 regular season, 004 playoffs, 005 play-in. Preseason (001), All-Star (003)
# and the NBA Cup final (006) are not built.
BUILT_TYPES = ("002", "004", "005")
NIGHTLY_UTC = (10, 0)   # the last West Coast games end by about 08:30 UTC; the nightly picks up corrections after that


def final_games(schedule, season):
    """Ids of the season's built games that the schedule marks final (gameStatus 3)."""
    ls = schedule["leagueSchedule"]
    if ls.get("seasonYear") != season:
        raise SystemExit(f"the CDN schedule is for {ls.get('seasonYear')}, not {season}: update config.json")
    return {g["gameId"] for d in ls["gameDates"] for g in d["games"]
            if g.get("gameStatus") == 3 and g["gameId"][:3] in BUILT_TYPES}


def parse_time(s):
    return datetime.fromisoformat(s.replace(" UTC", "+00:00").replace("Z", "+00:00")) if s else None


def decide(final, status, now):
    """(run, reason). The nightly is due once per UTC day after NIGHTLY_UTC until a build has been published after it,
    so a failed nightly is retried by the next scheduled run."""
    built = status.get("games", -1)
    slot = now.replace(hour=NIGHTLY_UTC[0], minute=NIGHTLY_UTC[1], second=0, microsecond=0)
    last = parse_time(status.get("checked_at"))
    nightly = now >= slot and (last is None or last < slot)
    run = final > built or nightly
    return run, f"final games in the feed: {final}; in the last build: {built}; last build: {last}; " \
                f"nightly due: {nightly}; run: {run}"


def main():
    path = os.path.join(ROOT, "warehouse", season(), "status.json")
    status = json.load(open(path)) if os.path.exists(path) else {}
    record = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--record=")]
    if record:
        status.update(games=int(record[0]), checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(status, open(path, "w"), indent=1)
        print(f"recorded {path}: {status}")
        return
    now = datetime.now(timezone.utc)
    req = urllib.request.Request(SCHEDULE)
    try:
        final = len(final_games(json.load(urllib.request.urlopen(req, timeout=60)), season()))
    except OSError as e:
        # an unreachable schedule fails the run once a day (when the nightly is due), not on every 5-minute check
        if decide(-1, status, now)[0]:
            raise SystemExit(f"the NBA schedule could not be read: {e}")
        print(f"::warning::the NBA schedule could not be read ({e}); trying again at the next check")
        final, now = -1, None
    run, reason = decide(final, status, now) if now else (False, "schedule unreadable: no run")
    print(reason)
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"run={'true' if run else 'false'}\nfinal={final}\n")


if __name__ == "__main__":
    main()
