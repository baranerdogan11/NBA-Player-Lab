"""When the update workflow runs: a game has gone final since the last published build, or the nightly is due.
Reads the NBA schedule (from the CDN's S3 origin) and the committed warehouse/<season>/status.json, prints its reasoning and writes run=true|false
and final=<games> to $GITHUB_OUTPUT. warehouse_tests.py writes that file on every passing build;
until it exists, --record=<games> stores the count and the time after a build, so the next check compares against what
was published.
While the gates hold a game (quarantine.json, see quarantine.py) the update also runs every RETRY_EVERY, for RETRY_FOR
after the game was first held, so a corrected feed clears it the same night; after that the nightly retries it.
With --watch it also prints how many of the night's games are still to go final, for watch.yml.
usage: python due.py [--watch] [2026-27]
       python due.py --record=<games> [2026-27]
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from season import ROOT, season

# the S3 origin behind cdn.nba.com: the CDN refuses scripted clients, the bucket serves the same files
SCHEDULE = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/staticData/scheduleLeagueV2.json"
# game ids start with the game type: 002 regular season, 004 playoffs, 005 play-in. Preseason (001), All-Star (003)
# and the NBA Cup final (006) are not built.
BUILT_TYPES = ("002", "004", "005")
NIGHTLY_UTC = (10, 0)   # the last West Coast games end by about 08:30 UTC; the nightly picks up corrections after that
RETRY_EVERY = timedelta(minutes=30)   # fetch_season.py refreshes a new game's feeds every 30 minutes
RETRY_FOR = timedelta(hours=24)


def final_games(schedule, season):
    """Ids of the season's built games that the schedule marks final (gameStatus 3)."""
    ls = schedule["leagueSchedule"]
    if ls.get("seasonYear") != season:
        raise SystemExit(f"the CDN schedule is for {ls.get('seasonYear')}, not {season}: update config.json")
    return {g["gameId"] for d in ls["gameDates"] for g in d["games"]
            if g.get("gameStatus") == 3 and g["gameId"][:3] in BUILT_TYPES}


def open_games(schedule, season, now, hours=12):
    """Ids of the season's built games that tip off within `hours` of now and are not final yet: the night the
    watcher waits for. A postponed game drops out once its tip-off is more than `hours` past."""
    return {g["gameId"] for d in schedule["leagueSchedule"]["gameDates"] for g in d["games"]
            if g.get("gameStatus") != 3 and g["gameId"][:3] in BUILT_TYPES and g.get("gameDateTimeUTC")
            and abs((parse_time(g["gameDateTimeUTC"]) - now).total_seconds()) <= hours * 3600}


def parse_time(s):
    return datetime.fromisoformat(s.replace(" UTC", "+00:00").replace("Z", "+00:00")) if s else None


def decide(final, status, now, held=()):
    """(run, reason). The nightly is due once per UTC day after NIGHTLY_UTC until a build has been published after it,
    so a failed nightly is retried by the next scheduled run. held: when each quarantined game was first held."""
    built = status.get("games", -1)
    slot = now.replace(hour=NIGHTLY_UTC[0], minute=NIGHTLY_UTC[1], second=0, microsecond=0)
    last = parse_time(status.get("checked_at"))
    nightly = now >= slot and (last is None or last < slot)
    retry = any(now - parse_time(t) <= RETRY_FOR for t in held) and (last is None or now - last >= RETRY_EVERY)
    run = final > built or nightly or retry
    return run, f"final games in the feed: {final}; in the last build: {built}; last build: {last}; " \
                f"nightly due: {nightly}; quarantined: {len(held)}, retry due: {retry}; run: {run}"


def main():
    path = os.path.join(ROOT, "warehouse", season(), "status.json")
    status = json.load(open(path)) if os.path.exists(path) else {}
    q = os.path.join(os.path.dirname(path), "quarantine.json")
    held = [e["first_seen"] for e in json.load(open(q))["games"]] if os.path.exists(q) else []
    record = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--record=")]
    if record:
        status.update(games=int(record[0]), checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(status, open(path, "w"), indent=1)
        print(f"recorded {path}: {status}")
        return
    now = datetime.now(timezone.utc)
    req = urllib.request.Request(SCHEDULE)
    pending = -1
    try:
        schedule = json.load(urllib.request.urlopen(req, timeout=60))
        final = len(final_games(schedule, season()))
        pending = len(open_games(schedule, season(), now))
    except OSError as e:
        # an unreachable schedule fails the run once a day (when the nightly is due), not on every 5-minute check
        if decide(-1, status, now)[0]:
            raise SystemExit(f"the NBA schedule could not be read: {e}")
        print(f"::warning::the NBA schedule could not be read ({e}); trying again at the next check")
        final, now = -1, None
    run, reason = decide(final, status, now, held) if now else (False, "schedule unreadable: no run")
    print(reason)
    if "--watch" in sys.argv:
        print(f"watch: run={'true' if run else 'false'} open={pending}")
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"run={'true' if run else 'false'}\nfinal={final}\n")


if __name__ == "__main__":
    main()
