"""Bronze layer: pulls the season's schedule and, for every final game, the official box score and play-by-play from
the NBA's game-data bucket, into cache/<season>/. Each rerun fetches only games that are new, plus the
games of the last 72 hours again so late stat corrections land. Runs in GitHub Actions only.

The CDN's schedule file covers the current season only; for an earlier season the regular-season games are found by
walking the game ids, and the schedule is rebuilt from their box scores.

usage: python fetch_season.py [2026-27]
"""
import json
import os
import time
from datetime import datetime, timezone
import requests
from season import ROOT, season

SEASON = season()
CACHE = os.path.join(ROOT, "cache", SEASON)
os.makedirs(CACHE, exist_ok=True)
# cdn.nba.com refuses scripted clients (GitHub's runners and a home connection alike), so the files are read from the S3
# bucket it serves from: the same JSON, under /NBA instead of /static/json. Chosen by Baran on 19 Oct 2026.
CDN = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA"
SCHEDULE = f"{CDN}/staticData/scheduleLeagueV2.json"
BOX = CDN + "/liveData/boxscore/boxscore_{}.json"
PBP = CDN + "/liveData/playbyplay/playbyplay_{}.json"
ROSTER = f"{CDN}/staticData/playerIndex.json"       # every player on a club's roster now, with jersey, position and height
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}
# the third digit of a game id is its type: 1 preseason, 2 regular season, 3 All-Star, 4 playoffs, 5 play-in, 6 NBA Cup final
GAME_TYPES = {"2", "4", "5", "6"}
FINAL = 3                                           # gameStatus: 1 scheduled, 2 live, 3 final


class Missing(Exception):
    pass


def get(url):
    for attempt in range(6):
        r = requests.get(url, headers=H, timeout=60)
        if r.ok:
            time.sleep(0.2)
            # the bucket serves some files (playerIndex.json, the schedule) as text/plain with no charset, which requests
            # would decode as Latin-1 ("Luka DonÄiÄ"); the bytes are UTF-8, so they are parsed as such
            return json.loads(r.content)
        if r.status_code in (403, 404):            # the bucket answers 403 for a file that does not exist
            raise Missing(url)
        time.sleep(6 * (attempt + 1) if r.status_code == 429 else 2)
    raise RuntimeError(f"{r.status_code} {url}")


# The league corrects box scores and play-by-play after the buzzer, so a game's files are fetched again while the game
# is recent: at most every REFRESH_EVERY seconds, for REFRESH_WINDOW seconds after tip-off. Older games stay cached.
REFRESH_WINDOW = 72 * 3600
REFRESH_EVERY = 6 * 3600
# the first hours after a game are when the league reorders and rewrites its play-by-play, so then it is fetched more often
NEW_WINDOW = 12 * 3600
NEW_EVERY = 30 * 60
FETCHED = os.path.join(CACHE, "fetched_at.json")   # file name -> unix time it was last fetched (mtimes do not survive the CI cache)
fetched_at = json.load(open(FETCHED)) if os.path.exists(FETCHED) else {}


def cached(name, fetch, refresh=False, force=False, every=REFRESH_EVERY):
    """Read name from the cache, or fetch and store it. With refresh, a copy older than every seconds is fetched again;
    with force, it is fetched again now. If that fetch fails the cached copy is kept, so a feed outage never costs a
    game we already have."""
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and not force and not (refresh and time.time() - fetched_at.get(name, 0) >= every):
        return json.load(open(path))
    try:
        data = fetch()
    except Exception as e:
        if not os.path.exists(path):
            raise
        print(f"   refresh of {name} failed, keeping the cached copy: {e}")
        return json.load(open(path))
    if refresh and os.path.exists(path) and json.load(open(path)) != data:
        print(f"   {name} changed in the feed since it was cached (late correction)")
    json.dump(data, open(path, "w"))
    fetched_at[name] = time.time()
    json.dump(fetched_at, open(FETCHED, "w"))
    return data


def recent(tipoff, window=REFRESH_WINDOW):
    """True while a game is inside the correction window (or another window), counted from its scheduled tip-off."""
    try:
        t = datetime.fromisoformat(tipoff.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return 0 <= (datetime.now(timezone.utc) - t).total_seconds() <= window


def fetch_game(gid, tipoff):
    fresh = recent(tipoff)
    every = NEW_EVERY if recent(tipoff, NEW_WINDOW) else REFRESH_EVERY   # the box score and play-by-play on one clock
    box = cached(f"box_{gid}.json", lambda: get(BOX.format(gid)), fresh, every=every)
    if box["game"]["gameStatus"] != FINAL:          # the schedule can mark a game final a moment before its box score does
        os.remove(os.path.join(CACHE, f"box_{gid}.json"))
        fetched_at.pop(f"box_{gid}.json", None)
        print(f"   {gid}: box score not final yet, skipped")
        return None
    pbp = cached(f"pbp_{gid}.json", lambda: get(PBP.format(gid)), fresh, every=every)
    if fresh and not complete(pbp, box):
        # the play-by-play can trail the box score at the buzzer; a copy cached then would fail the warehouse tests
        # and hold every update until its refresh, so it is fetched again on each run until its last score is final
        print(f"   {gid}: play-by-play ends before the final score, fetching it again")
        cached(f"pbp_{gid}.json", lambda: get(PBP.format(gid)), force=True)
    return box


def complete(pbp, box):
    """True when the play-by-play's last scored action has the box score's final score."""
    b = box["game"]
    scored = [a for a in pbp["game"]["actions"] if a.get("scoreHome") not in (None, "")]
    return bool(scored) and (int(scored[-1]["scoreHome"]), int(scored[-1]["scoreAway"])) == (b["homeTeam"]["score"], b["awayTeam"]["score"])


# ---- schedule: the CDN's file for the current season, or one rebuilt from the box scores for an earlier season
sched = get(SCHEDULE)["leagueSchedule"]
if sched["seasonYear"] == SEASON:
    games = [g for d in sched["gameDates"] for g in d["games"]]
    json.dump(games, open(os.path.join(CACHE, "schedule.json"), "w"))
    final = [g for g in games if g["gameId"][2] in GAME_TYPES and g["gameStatus"] == FINAL]
    print(f"{SEASON}: {len(games)} games scheduled, {len(final)} final")
    n = sum(fetch_game(g["gameId"], g["gameDateTimeUTC"]) is not None for g in final)
else:
    print(f"{SEASON}: the CDN schedule is for {sched['seasonYear']}; walking the regular-season game ids")
    games, misses, i = [], 0, 1
    prefix = f"002{SEASON[2:4]}"
    while misses < 3:
        gid = f"{prefix}{i:05d}"
        try:
            box = fetch_game(gid, None)
            misses = 0
        except Missing:
            box, misses = None, misses + 1
        if box:
            b = box["game"]
            side = lambda t: {k: t[k] for k in ("teamId", "teamName", "teamCity", "teamTricode", "score")}
            games.append({"gameId": gid, "gameStatus": b["gameStatus"], "gameDateTimeUTC": b["gameTimeUTC"], "gameDateEst": b["gameEt"][:10] + "T00:00:00Z",
                          "homeTeam": side(b["homeTeam"]), "awayTeam": side(b["awayTeam"])})
        i += 1
    json.dump(games, open(os.path.join(CACHE, "schedule.json"), "w"))
    n = len(games)
print(f"{n} final games cached")

# ---- rosters: the league's player index for the current season, fetched again on every run so signings, waivers and
# trades land; if the fetch fails the cached copy stays. An earlier season has no roster file (players come from box scores).
if sched["seasonYear"] == SEASON:
    try:
        index = get(ROSTER)
        if index["parameters"]["Season"] != SEASON:
            raise ValueError(f"player index is for {index['parameters']['Season']}")
        json.dump(index, open(os.path.join(CACHE, "roster.json"), "w"))
        print(f"roster: {len(index['resultSets'][0]['rowSet'])} players")
    except Exception as e:
        print(f"   roster fetch failed, keeping the cached copy: {e}")
