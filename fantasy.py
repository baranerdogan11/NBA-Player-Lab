"""The private fantasy league's file: one Yahoo Fantasy league, read with a league member's read-only token, its players
matched to NBA person ids and encrypted for the members' invite link. Nothing here is committed. Yahoo's terms let us keep
its users' data for 24 hours at most, so every run rebuilds the file and the deploy carries only the newest one.

The file the page reads is <out>/fantasy/<league id>.enc, {"v": 1, "alg": "A256GCM", "iv", "ct", "built"}. ct (base64url,
the GCM tag at its end) decrypts with the 32-byte key from the invite link (#league/<league id>/<key>), with the league id
as associated data, to the league JSON: settings and week dates, teams with today's roster ("now") and the slot runs of the
days fetched, the week pairings, Yahoo's own team totals per finished or current week (for the weekly gate), recent moves.
It holds no stats of ours: the page sums the box-score lines it already loads, so a fantasy number is the site's number.

Gates: every rostered Yahoo player maps to an NBA person id (fantasy/ids.json fixes the names that do not match), and no
Yahoo GUID or email reaches the file. The log prints counts only, never names of teams or managers: the repository's
Actions logs are public.

usage: python fantasy.py [2026-27] [--out=DIR]
         env YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REFRESH_TOKEN, FANTASY_LEAGUE (the league id), FANTASY_KEY;
         YAHOO_REFRESH_OUT, if set, is a file that receives the refresh token when Yahoo issues a new one
       python fantasy.py --league=FILE --key=KEY [--out=DIR]   (seals a league JSON as it is: the browser tests' fixture)
DIR defaults to _league/ (not committed).
"""
import base64
import datetime
import json
import os
import re
import sys
import time
import unicodedata
from zoneinfo import ZoneInfo

from season import ROOT, season

API = "https://fantasysports.yahooapis.com/fantasy/v2/"
TOKEN = "https://api.login.yahoo.com/oauth2/get_token"
REDIRECT = "https://localhost:8080"   # registered on the Yahoo app; fantasy_auth.py signs in with it
PACE = 1.0                            # seconds between calls: Yahoo blocks bursts (HTTP 999) and publishes no limit
# Yahoo's NBA stat ids: the nine categories, and the makes/attempts pairs it shows beside FG% and FT%
CATS = {"5": "fg%", "8": "ft%", "10": "fg3m", "12": "pts", "15": "reb", "16": "ast", "17": "stl", "18": "blk", "19": "-tov"}
TOTALS = {"10": "fg3m", "12": "pts", "15": "reb", "16": "ast", "17": "stl", "18": "blk", "19": "tov"}
PAIRS = {"9004003": ("fgm", "fga"), "9007006": ("ftm", "fta")}
ZONE = ZoneInfo("America/New_York")   # Yahoo's fantasy day
# Yahoo's team abbreviations where they differ from the CDN tricodes in teams.json
ABBR = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "PHO": "PHX", "SA": "SAS", "BRK": "BKN", "CHO": "CHA"}


class Yahoo:
    """The Fantasy API with a refresh token: an access token per run, one call a second, a retry on Yahoo's throttle."""

    def __init__(self, cid, secret, refresh):
        import requests
        self.http, self.cid, self.secret, self.refresh, self.last = requests.Session(), cid, secret, refresh, 0.0
        self.calls = 0
        self.token()

    def token(self):
        r = self.http.post(TOKEN, auth=(self.cid, self.secret), timeout=30,
                           data={"grant_type": "refresh_token", "refresh_token": self.refresh, "redirect_uri": REDIRECT})
        if r.status_code != 200:
            raise SystemExit(f"Yahoo sign-in refused (HTTP {r.status_code}): the refresh token was revoked or the app changed; "
                             "run fantasy_auth.py again")
        j = r.json()
        mask(j["access_token"])
        self.http.headers["Authorization"] = f"Bearer {j['access_token']}"
        new = j.get("refresh_token")
        if new and new != self.refresh:
            # Yahoo revokes the old token once it issues a new one, so the new one is saved before anything else happens
            mask(new)
            out = os.environ.get("YAHOO_REFRESH_OUT")
            if not out:
                raise SystemExit("Yahoo issued a new refresh token and YAHOO_REFRESH_OUT is not set to save it")
            with open(out, "w") as f:
                f.write(new)
            self.refresh = new
            print("Yahoo issued a new refresh token; saved for the workflow to store")

    def get(self, path, retried=False):
        for wait in (0, 60, 300, 600):
            time.sleep(max(0.0, self.last + PACE - time.time()) + wait)
            r = self.http.get(API + path, params={"format": "json"}, timeout=60)
            self.last, self.calls = time.time(), self.calls + 1
            if r.status_code not in (429, 999) and r.status_code < 500:
                break
        what = path.split(";")[0]
        if r.status_code == 401 and not retried:
            self.token()
            return self.get(path, True)
        if r.status_code == 403:
            raise SystemExit(f"Yahoo refused {what} (HTTP 403): the app's Fantasy API access is off or was never enabled")
        if r.status_code != 200:
            raise SystemExit(f"Yahoo answered HTTP {r.status_code} for {what}")
        return r.json()["fantasy_content"]


def mask(secret):
    """Hides a secret in the Actions log, should it ever be printed."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{secret}")


def flat(items):
    """Yahoo lists a resource's fields as one-key dicts, nested in lists, with stray empty lists: merged into one dict."""
    out = {}
    for it in items if isinstance(items, list) else [items]:
        if isinstance(it, dict):
            out.update(it)
        elif isinstance(it, list):
            out.update(flat(it))
    return out


def each(coll, key):
    """Yahoo's collections, {"0": {key: ...}, "1": ..., "count": n}: the items in order."""
    return [v[key] for k, v in sorted((int(k), v) for k, v in coll.items() if k.isdigit())]


def norm(name):
    """A name for matching: no accents, punctuation or Jr./III suffix, lower case."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " "))
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv"))


def our_players(sea):
    """Every player the site lists, by matching name: [(club, pid, jersey)]."""
    teams = json.load(open(os.path.join(ROOT, "teams.json"), encoding="utf-8"))["teams"]
    by = {}
    for t in teams:
        path = os.path.join(ROOT, "teams", sea, f"{t['code']}.json")
        if os.path.exists(path):
            for p in json.load(open(path, encoding="utf-8"))["players"]:
                by.setdefault(norm(p["name"]), []).append((t["code"], str(p["pid"]), p.get("jersey") or ""))
    return by


class Ids:
    """Yahoo player id -> NBA person id: fantasy/ids.json first, then name and club, then name alone, then jersey."""

    def __init__(self, ours):
        path = os.path.join(ROOT, "fantasy", "ids.json")
        self.fixed = {k: str(v) for k, v in json.load(open(path)).items() if k != "_"} if os.path.exists(path) else {}
        self.ours, self.missing = ours, {}

    def pid(self, p, rostered=True):
        yid = str(p["player_id"])
        if yid in self.fixed:
            return self.fixed[yid]
        n = p.get("name", {})
        cands = self.ours.get(norm(f"{n.get('ascii_first', '')} {n.get('ascii_last', '')}")) or self.ours.get(norm(n.get("full", "")), [])
        code = ABBR.get(str(p.get("editorial_team_abbr", "")).upper(), str(p.get("editorial_team_abbr", "")).upper())
        for pick in ([c for c in cands if c[0] == code], cands, [c for c in cands if c[2] == str(p.get("uniform_number", ""))]):
            if len(pick) == 1:
                return pick[0][1]
        if rostered:
            self.missing[yid] = f"{n.get('full', '?')} ({code})"
        return None


def build(y, ours, today):
    """The league JSON from the Yahoo API (y.get), for the local date today (US Eastern, Yahoo's day)."""
    lid = os.environ["FANTASY_LEAGUE"]
    game = y.get("game/nba")["game"]
    game = flat(game[0] if isinstance(game, list) else game)
    key = f"{game['game_key']}.l.{lid}"
    meta, rest = y.get(f"league/{key}/settings")["league"]
    s = flat(rest["settings"])
    stats = [x["stat"] for x in s["stat_categories"]["stats"]]
    scored = [x for x in stats if str(x.get("enabled", "1")) == "1" and str(x.get("is_only_display_stat", "0")) != "1"]
    fmt = {"head": "h2h-cats", "headpoint": "h2h-points", "roto": "roto", "point": "h2h-points"}.get(s["scoring_type"])
    unknown = [x.get("display_name", x["stat_id"]) for x in scored if str(x["stat_id"]) not in CATS] if fmt != "h2h-points" else []
    if not fmt or unknown:
        raise SystemExit(f"league scoring not handled yet: {s['scoring_type']} {unknown}")
    points = None
    if fmt == "h2h-points":
        mods = {str(m["stat"]["stat_id"]): m["stat"]["value"] for m in s["stat_modifiers"]["stats"]}
        points = {CATS[k].lstrip("-"): round(float(v) * 10) for k, v in mods.items() if k in CATS}
    slots = []
    for rp in s["roster_positions"]:
        p = rp["roster_position"]
        slots += [p["position"].upper()] * int(p.get("count", 1))

    weeks = {int(w["week"]): (w["start"], w["end"]) for w in each(y.get(f"game/{game['game_key']}/game_weeks")["game"][1]["game_weeks"], "game_week")}
    first, cur = int(meta["start_week"]), int(meta["current_week"])
    last = int(meta["end_week"])
    day = today.isoformat()
    # the days whose rosters are read: this week's so far, and all of last week on the first day of a new week
    w0, w1 = weeks[cur]
    start = weeks[cur - 1][0] if day == w0 and cur - 1 in weeks and cur > first else w0
    days = list(dates(start, min(day, w1))) or [day]   # before the season: today's rosters

    ids = Ids(ours)
    teams = {}
    for t in each(rest_of(y.get(f"league/{key}/teams"), "teams"), "team"):
        t = flat(t)
        mgr = flat(t["managers"][0]["manager"]) if t.get("managers") else {}
        logo = t.get("team_logos", [{}])[0].get("team_logo", {}).get("url")
        teams[t["team_key"]] = {"t": int(t["team_id"]), "name": t["name"], "mgr": mgr.get("nickname"), "logo": logo,
                                "w": 0, "l": 0, "tie": 0, "rank": None, "now": [], "runs": []}
    for t in each(rest_of(y.get(f"league/{key}/standings"), "standings")[0]["teams"], "team"):
        t = flat(t)
        st = t.get("team_standings", {})
        o = st.get("outcome_totals", {})
        teams[t["team_key"]].update(w=int(o.get("wins") or 0), l=int(o.get("losses") or 0), tie=int(o.get("ties") or 0),
                                    rank=int(st["rank"]) if st.get("rank") not in (None, "") else None)

    matchups, yahoo = [], {}
    for w in range(first, cur + 1):
        board = rest_of(y.get(f"league/{key}/scoreboard;week={w}"), "scoreboard")
        for m in each(board["0"]["matchups"], "matchup"):
            side = [flat(t) for t in each(m["0"]["teams"], "team")]
            matchups.append([w] + [teams[t["team_key"]]["t"] for t in side])
            for t in side:
                yahoo.setdefault(str(w), {})[str(teams[t["team_key"]]["t"])] = week_totals(t.get("team_stats", {}))

    for tk, team in teams.items():
        held = {}
        for d in days:
            for p in each(y.get(f"team/{tk}/roster;date={d}")["team"][1]["roster"]["0"]["players"], "player"):
                p = flat(p)
                pid = ids.pid(p)
                slot = flat(p["selected_position"])["position"].upper()
                held.setdefault(pid, []).append((d, slot))
                if d == days[-1]:
                    team["now"].append([pid, slot, [e["position"].upper() for e in p.get("eligible_positions", [])],
                                        p.get("status") or None])
        for pid, ds in held.items():
            for d, slot in ds:
                r = team["runs"]
                if r and r[-1][0] == pid and r[-1][1] == slot and r[-1][3] == prev(d):
                    r[-1][3] = d
                else:
                    r.append([pid, slot, d, d])

    moves = []
    for tr in each(rest_of(y.get(f"league/{key}/transactions;types=add,drop,trade;count=25"), "transactions"), "transaction"):
        m = flat(tr[0] if isinstance(tr, list) else tr)
        when = datetime.datetime.fromtimestamp(int(m["timestamp"]), ZONE).date().isoformat()
        for p in each(flat(tr[1:] if isinstance(tr, list) else tr).get("players", {}), "player"):
            p = flat(p)
            td = flat(p.get("transaction_data", {}))
            to, frm = teams.get(td.get("destination_team_key"), {}).get("t"), teams.get(td.get("source_team_key"), {}).get("t")
            moves.append([when, td.get("type", m.get("type")), to if to is not None else frm, ids.pid(p, False), frm if to is not None else None])

    if ids.missing:
        raise SystemExit(f"{len(ids.missing)} rostered Yahoo players match no NBA player; add them to fantasy/ids.json: "
                         + "; ".join(f"{k}: {v}" for k, v in sorted(ids.missing.items())))
    league = {"key": key, "name": meta["name"], "built": now(), "week": cur, "format": fmt,
              "cats": [CATS[str(x["stat_id"])] for x in scored] if fmt != "h2h-points" else None, "points": points,
              "slots": slots, "weeks": [list(weeks[w]) for w in range(first, last + 1) if w in weeks]}
    out = {"v": 1, "league": league, "teams": sorted(teams.values(), key=lambda t: t["t"]), "matchups": matchups,
           "yahoo": yahoo, "moves": moves}
    print(f"league read: {len(teams)} teams, {sum(len(t['now']) for t in teams.values())} rostered players, {len(days)} days "
          f"of rosters, weeks {first}-{cur}, {len(moves)} moves, {y.calls} Yahoo calls")
    return out


def rest_of(fc, name):
    """league/<key>/<name>: the resource under the league's meta block."""
    return fc["league"][1][name]


def week_totals(team_stats):
    out = {}
    for st in team_stats.get("stats", []):
        sid, v = str(st["stat"]["stat_id"]), str(st["stat"].get("value") or "")
        if sid in PAIRS and "/" in v:
            for k, n in zip(PAIRS[sid], v.split("/")):
                out[k] = int(n) if n.strip().lstrip("-").isdigit() else 0
        elif sid in TOTALS:
            out[TOTALS[sid]] = int(float(v)) if re.fullmatch(r"-?\d+(\.0+)?", v) else 0
    return out



def dates(a, b):
    d, e = datetime.date.fromisoformat(a), datetime.date.fromisoformat(b)
    while d <= e:
        yield d.isoformat()
        d += datetime.timedelta(days=1)


def prev(d):
    return (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def key_bytes(k):
    """The invite link's key: 32 bytes as base64url without padding (43 characters)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", k or ""):
        raise SystemExit("FANTASY_KEY must be 32 bytes in base64url without padding (43 characters)")
    return base64.urlsafe_b64decode(k + "=")


def private_fields(x, path="league"):
    """Paths to any Yahoo GUID or email in the league JSON: the file must hold neither."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k in ("guid", "email") or (isinstance(v, str) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+", v)):
                yield f"{path}.{k}"
            yield from private_fields(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from private_fields(v, f"{path}[{i}]")


def seal(league, key):
    """The .enc envelope: AES-256-GCM with a fresh 12-byte nonce, the league id as associated data."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    bad = list(private_fields(league))
    if bad:
        raise SystemExit(f"the league file would carry a GUID or an email at {bad[0]}")
    lid = league["league"]["key"].split(".l.")[-1]
    iv = os.urandom(12)
    ct = AESGCM(key_bytes(key)).encrypt(iv, json.dumps(league, separators=(",", ":"), ensure_ascii=False).encode(), lid.encode())
    return lid, {"v": 1, "alg": "A256GCM", "iv": b64(iv), "ct": b64(ct), "built": league["league"]["built"]}


def open_sealed(env, lid, key):
    """The league JSON back from an envelope (the page does the same with WebCrypto)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    return json.loads(AESGCM(key_bytes(key)).decrypt(raw(env["iv"]), raw(env["ct"]), lid.encode()))


def write(out, league, key):
    lid, env = seal(league, key)
    os.makedirs(os.path.join(out, "fantasy"), exist_ok=True)
    path = os.path.join(out, "fantasy", f"{lid}.enc")
    with open(path, "w") as f:
        json.dump(env, f, separators=(",", ":"))
    return path


if __name__ == "__main__":
    opt = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    out = opt.get("out", os.path.join(ROOT, "_league"))
    if "league" in opt:
        league = json.load(open(opt["league"], encoding="utf-8"))
        print(f"sealed {write(out, league, opt.get('key'))}")
    else:
        need = ["YAHOO_CLIENT_ID", "YAHOO_CLIENT_SECRET", "YAHOO_REFRESH_TOKEN", "FANTASY_LEAGUE", "FANTASY_KEY"]
        if [n for n in need if not os.environ.get(n)]:
            raise SystemExit(f"missing settings: {', '.join(n for n in need if not os.environ.get(n))}")
        key_bytes(os.environ["FANTASY_KEY"])
        y = Yahoo(os.environ["YAHOO_CLIENT_ID"], os.environ["YAHOO_CLIENT_SECRET"], os.environ["YAHOO_REFRESH_TOKEN"])
        league = build(y, our_players(season()), datetime.datetime.now(ZONE).date())
        write(out, league, os.environ["FANTASY_KEY"])
        print("league file sealed")
