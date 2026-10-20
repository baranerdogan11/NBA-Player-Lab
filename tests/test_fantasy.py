"""fantasy.py on a two-team league answered in the Fantasy API's documented JSON shapes: the league file's fields, the
slot runs, Yahoo's week totals, the name matching and its gates, and the encryption round trip.
usage: python tests/test_fantasy.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fantasy  # noqa: E402

KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"   # bytes 0..31: a test key, never a real one
os.environ["FANTASY_LEAGUE"] = "12345"
LK = "466.l.12345"


def coll(key, items):
    out = {str(i): {key: v} for i, v in enumerate(items)}
    out["count"] = len(items)
    return out


def player(yid, first, last, club, num, elig, slot=None, status=None):
    info = [{"player_key": f"466.p.{yid}"}, {"player_id": str(yid)},
            {"name": {"full": f"{first} {last}", "ascii_first": first, "ascii_last": last}},
            [], {"editorial_team_abbr": club}, {"uniform_number": num},
            {"eligible_positions": [{"position": p} for p in elig]}]
    if status:
        info.append({"status": status})
    out = [info]
    if slot:
        out.append({"selected_position": [{"coverage_type": "date"}, {"date": "x"}, {"position": slot}]})
    return out


def team(n, name, extra=None):
    info = [[{"team_key": f"{LK}.t.{n}"}, {"team_id": str(n)}, {"name": name}, [],
             {"team_logos": [{"team_logo": {"size": "large", "url": f"https://example.com/{n}.png"}}]},
             {"managers": [{"manager": {"manager_id": str(n), "nickname": f"mgr{n}", "guid": "SECRETGUID", "email": "a@b.co"}}]}]]
    return info + ([extra] if extra else [])


def stats(fg, ft, *rest):
    ids = ["10", "12", "15", "16", "17", "18", "19"]
    return {"team_stats": {"coverage_type": "week", "stats": [{"stat": {"stat_id": "9004003", "value": fg}}, {"stat": {"stat_id": "5", "value": ".480"}},
                                                               {"stat": {"stat_id": "9007006", "value": ft}}, {"stat": {"stat_id": "8", "value": ".800"}}]
                           + [{"stat": {"stat_id": i, "value": v}} for i, v in zip(ids, rest)]}}


ROSTER = {  # (team, day) -> players
    (1, "2026-10-21"): [player(6014, "Luka", "Doncic", "LAL", "77", ["PG", "SG", "G", "Util"], "PG"),
                        player(5007, "Jalen", "Williams", "OKC", "8", ["SG", "SF", "G", "F", "Util"], "BN", "DTD")],
    (1, "2026-10-22"): [player(6014, "Luka", "Doncic", "LAL", "77", ["PG", "SG", "G", "Util"], "PG"),
                        player(5007, "Jalen", "Williams", "OKC", "8", ["SG", "SF", "G", "F", "Util"], "SF")],
    (2, "2026-10-21"): [player(6400, "Nikola", "Jokic", "DEN", "15", ["C", "Util"], "C")],
    (2, "2026-10-22"): [player(6400, "Nikola", "Jokic", "DEN", "15", ["C", "Util"], "C")],
}


class FakeYahoo:
    calls = 0

    def get(self, path):
        self.calls += 1
        meta = {"league_key": LK, "league_id": "12345", "name": "Friends League", "start_week": "1", "current_week": "1", "end_week": "2"}
        if path == "game/nba":
            return {"game": [{"game_key": "466"}, {"code": "nba"}]}
        if path == "game/466/game_weeks":
            return {"game": [{"game_key": "466"}, {"game_weeks": coll("game_week", [{"week": "1", "start": "2026-10-21", "end": "2026-10-26"},
                                                                                 {"week": "2", "start": "2026-10-27", "end": "2026-11-02"}])}]}
        if path == f"league/{LK}/settings":
            cats = [{"stat": {"stat_id": int(k), "enabled": "1", "display_name": v}} for k, v in fantasy.CATS.items()]
            cats.insert(0, {"stat": {"stat_id": 9004003, "enabled": "1", "is_only_display_stat": "1"}})
            pos = [{"roster_position": {"position": p, "count": c}} for p, c in (("PG", 1), ("C", 2), ("Util", 2), ("BN", 3), ("IL", 1))]
            return {"league": [meta, {"settings": [{"scoring_type": "head", "stat_categories": {"stats": cats}, "roster_positions": pos}]}]}
        if path == f"league/{LK}/teams":
            return {"league": [meta, {"teams": coll("team", [team(1, "Alpha"), team(2, "Beta")])}]}
        if path == f"league/{LK}/standings":
            st = [team(n, nm, {"team_standings": {"rank": r, "outcome_totals": {"wins": w, "losses": 1 - w, "ties": 0}}})
                  for n, nm, r, w in ((1, "Alpha", 1, 1), (2, "Beta", 2, 0))]
            return {"league": [meta, {"standings": [{"teams": coll("team", st)}]}]}
        if path == f"league/{LK}/scoreboard;week=1":
            side = [team(1, "Alpha", stats("145/303", "40/50", "30", "400", "180", "90", "25", "20", "50")),
                    team(2, "Beta", stats("120/250", "-/-", "-", "300", "150", "70", "20", "15", "40"))]
            m = {"week": "1", "0": {"teams": coll("team", side)}}
            return {"league": [meta, {"scoreboard": {"0": {"matchups": coll("matchup", [m])}, "week": "1"}}]}
        if path.startswith("team/"):
            tk, day = path.split("/")[1], path.split("date=")[1]
            players = ROSTER[(int(tk.split(".t.")[1]), day)]
            return {"team": [[{"team_key": tk}], {"roster": {"coverage_type": "date", "0": {"players": coll("player", players)}}}]}
        if path.startswith(f"league/{LK}/transactions"):
            ts = int(datetime.datetime(2026, 10, 22, 1, 30, tzinfo=datetime.timezone.utc).timestamp())   # the 21st in New York
            p = player(5007, "Jalen", "Williams", "OKC", "8", [])
            p.append({"transaction_data": [{"type": "add", "source_type": "freeagents", "destination_team_key": f"{LK}.t.1"}]})
            tr = [{"transaction_key": "466.l.12345.tr.1"}, {"type": "add"}, {"timestamp": str(ts)}]
            return {"league": [meta, {"transactions": coll("transaction", [[flatten(tr), {"players": coll("player", [p])}]])}]}
        raise AssertionError(f"unexpected call {path}")


def flatten(dicts):
    return {k: v for d in dicts for k, v in d.items()}


OURS = {"luka doncic": [("LAL", "1629029", "77")], "jalen williams": [("OKC", "1631114", "8"), ("DEN", "1631116", "33")],
        "nikola jokic": [("DEN", "203999", "15")]}

# names: accents, suffixes and punctuation do not matter
assert fantasy.norm("Luka Dončić") == fantasy.norm("luka doncic") == "luka doncic"
assert fantasy.norm("Jaren Jackson Jr.") == "jaren jackson" and fantasy.norm("Shai Gilgeous-Alexander") == "shai gilgeous alexander"
assert fantasy.flat([{"a": 1}, [], [{"b": 2}, [{"c": 3}]]]) == {"a": 1, "b": 2, "c": 3}

league = fantasy.build(FakeYahoo(), OURS, datetime.date(2026, 10, 22))
lg = league["league"]
assert lg["key"] == LK and lg["format"] == "h2h-cats" and lg["week"] == 1 and lg["points"] is None, lg
assert lg["cats"] == ["fg%", "ft%", "fg3m", "pts", "reb", "ast", "stl", "blk", "-tov"], lg["cats"]
assert lg["slots"] == ["PG", "C", "C", "UTIL", "UTIL", "BN", "BN", "BN", "IL"], lg["slots"]
assert lg["weeks"] == [["2026-10-21", "2026-10-26"], ["2026-10-27", "2026-11-02"]]
a, b = league["teams"]
assert (a["t"], a["name"], a["mgr"], a["w"], a["l"], a["rank"]) == (1, "Alpha", "mgr1", 1, 0, 1), a
assert a["now"] == [["1629029", "PG", ["PG", "SG", "G", "UTIL"], None], ["1631114", "SF", ["SG", "SF", "G", "F", "UTIL"], None]], a["now"]
# Jalen Williams sat on the bench on the 21st and played SF on the 22nd: two runs; Doncic one run over both days
assert a["runs"] == [["1629029", "PG", "2026-10-21", "2026-10-22"], ["1631114", "BN", "2026-10-21", "2026-10-21"],
                     ["1631114", "SF", "2026-10-22", "2026-10-22"]], a["runs"]
assert b["runs"] == [["203999", "C", "2026-10-21", "2026-10-22"]]
assert league["matchups"] == [[1, 1, 2]]
assert league["yahoo"]["1"]["1"] == {"fgm": 145, "fga": 303, "ftm": 40, "fta": 50, "fg3m": 30, "pts": 400, "reb": 180,
                                     "ast": 90, "stl": 25, "blk": 20, "tov": 50}, league["yahoo"]
assert league["yahoo"]["1"]["2"]["fta"] == 0 and league["yahoo"]["1"]["2"]["fg3m"] == 0
assert league["moves"] == [["2026-10-21", "add", 1, "1631114", None]], league["moves"]
assert not list(fantasy.private_fields(league)), "no GUID or email in the file"
assert "SECRETGUID" not in str(league) and "a@b.co" not in str(league)

# encryption: the round trip, the league id bound as associated data, a fresh nonce each time
lid, env = fantasy.seal(league, KEY)
assert lid == "12345" and env["alg"] == "A256GCM" and len(env["iv"]) == 16 and "Friends" not in env["ct"]
assert fantasy.open_sealed(env, "12345", KEY) == league
assert fantasy.seal(league, KEY)[1]["iv"] != env["iv"]
for bad in (lambda: fantasy.open_sealed(env, "99999", KEY), lambda: fantasy.open_sealed(env, "12345", "B" + KEY[1:]),
            lambda: fantasy.key_bytes("short"), lambda: fantasy.seal({**league, "teams": [{"guid": "x"}]}, KEY)):
    try:
        bad()
    except (Exception, SystemExit):
        continue
    raise AssertionError("a wrong key, league id, short key or a GUID must fail")

# an unmatched rostered player stops the build, and fantasy/ids.json would fix it
ROSTER[(2, "2026-10-22")].append(player(9999, "Nobody", "Known", "BOS", "0", ["C"], "BN"))
try:
    fantasy.build(FakeYahoo(), OURS, datetime.date(2026, 10, 22))
    raise AssertionError("an unmatched player must stop the build")
except SystemExit as e:
    assert "1 rostered Yahoo players" in str(e) and "9999" in str(e), e
print("fantasy ok")
