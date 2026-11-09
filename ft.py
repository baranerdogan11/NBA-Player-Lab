"""Free throws attempt by attempt: every free throw of the play-by-play by kind of trip, with the and-ones and the free
throws under pressure, by player, by club (its own and its opponents') and for the league.

<out>/ft.json  {"kinds": KINDS, "out": [gid, ...], "league": [[ftm, fta] x 7], "players": {pid: [[ftm, fta] x 7]},
                "teams": {code: {"for": [[ftm, fta] x 7], "against": [[ftm, fta] x 7]}}}
  The seven pairs follow KINDS. The first five split every free throw once: first of two, second of two, the one shot of
  a trip of one, any of a trip of three, and other (technical and flagrant free throws, whatever the trip). The last two
  are counted again inside those: and-ones (the one shot after a foul on the shooter's own made basket, at the same
  clock) and pressure free throws (the fourth quarter or overtime, two minutes or less left, the score within five
  points before the attempt: the NBA's clutch margin over its last two minutes). A player's first five pairs add up to
  his FTM-FTA over the same games, a traded player's clubs summed; a club's "against" is what its opponents shot.
  out lists the finals left out: those an earlier gate holds out of the play-by-play and those whose free throws differ
  from the box score.

from_warehouse() reads the free throws of warehouse/<season>/events.parquet, regular-season finals only, and checks each
player's FTM and FTA per game against his box score. The box score takes the league's post-game stat corrections and the
play-by-play does not, so a game whose free throws differ is left out; up to one differing player-game per thousand box
lines (at least two) is such a correction and only reported. More than that is a feed problem: those games are
quarantined (quarantine.py, scope ft) and the run fails when the quarantine is systemic. check_ft() then holds the
written file to the game box scores (games/<gid>.json) of every final not left out.
usage: python ft.py [2026-27]   (reads warehouse/<season>/, after site_data.py has written teams/<season>/; writes teams/<season>/ft.json)
"""
import json
import os
import quarantine

KINDS = ["first", "second", "one", "three", "other", "andone", "press"]
SPLIT = 5   # KINDS[:SPLIT] split every free throw once
PRESS_CLOCK, PRESS_MARGIN = 120, 5


def kind(sub_type, descriptor):
    """The index in KINDS[:SPLIT] of a free throw from its play-by-play subType ('1 of 2', ...) and descriptor."""
    if descriptor in ("technical", "flagrant") or sub_type not in ("1 of 2", "2 of 2", "1 of 1", "1 of 3", "2 of 3", "3 of 3"):
        return 4
    return {"1 of 2": 0, "2 of 2": 1, "1 of 1": 2}.get(sub_type, 3)


def attempts(events, home):
    """events: one game's play-by-play in order, dicts with action_type, sub_type, descriptor, result, player, team,
    period, clock (seconds left), score_home and score_away (after the action), and a made field goal's shot flag fg.
    home: the home club's code. One row per free throw: pid, team, kind (KINDS index), andone, press, made."""
    out, last, made_fg = [], (0, 0), set()
    for e in events:
        if e.get("fg") and e["result"] == "Made":
            made_fg.add((e["player"], e["period"], e["clock"]))
        if e["action_type"] == "freethrow" and e["player"]:
            made = e["result"] == "Made"
            h, a = last
            us, them = (h, a) if e["team"] == home else (a, h)
            k = kind(e["sub_type"], e["descriptor"])
            out.append({"pid": str(e["player"]), "team": e["team"], "kind": k, "made": made,
                        "andone": k == 2 and (e["player"], e["period"], e["clock"]) in made_fg,
                        "press": e["period"] >= 4 and e["clock"] is not None and e["clock"] <= PRESS_CLOCK and abs(us - them) <= PRESS_MARGIN})
        if e["score_home"] is not None and e["score_away"] is not None:
            last = (e["score_home"], e["score_away"])
    return out


def _add(c, r):
    for i in (r["kind"], *([5] if r["andone"] else []), *([6] if r["press"] else [])):
        c[i][0] += r["made"]
        c[i][1] += 1


def write_ft(out, teams, rows, left_out=()):
    """teams: site_data.load_teams() rows. rows: attempts() rows, each with gid and opp too."""
    zero = lambda: [[0, 0] for _ in KINDS]
    league, players, clubs = zero(), {}, {t["code"]: {"for": zero(), "against": zero()} for t in teams}
    for r in rows:
        for c in (league, players.setdefault(r["pid"], zero()), clubs[r["team"]]["for"], clubs[r["opp"]]["against"]):
            _add(c, r)
    with open(os.path.join(out, "ft.json"), "w") as f:
        json.dump({"kinds": KINDS, "out": sorted(left_out), "league": league, "players": dict(sorted(players.items())), "teams": clubs},
                  f, separators=(",", ":"))


def check_ft(out):
    """Raises unless ft.json agrees with the game box scores of every final it does not leave out: each player's and each
    club's split adds up to their FTM-FTA, a club's against is its opponents' for, the league is the players' sum, and
    and-ones and pressure free throws are made no more often than tried and never outnumber what holds them."""
    ft = json.load(open(os.path.join(out, "ft.json")))
    skip, want, clubs = set(ft["out"]), {}, {}
    for g in json.load(open(os.path.join(out, "games.json")))["games"]:
        if g["hs"] is None or g["gid"] in skip:
            continue
        for code, side in json.load(open(os.path.join(out, "games", f"{g['gid']}.json")))["box"].items():
            opp = g["away"] if code == g["home"] else g["home"]
            for x in side:
                for k, v in ((x["pid"], want), (code, clubs), ("-" + opp, clubs)):
                    w = v.setdefault(k, [0, 0])
                    w[0] += x["ftm"]
                    w[1] += x["fta"]
    total = lambda c: [sum(m for m, _ in c[:SPLIT]), sum(a for _, a in c[:SPLIT])]
    sane = lambda c: all(0 <= m <= a for m, a in c) and c[5][1] <= c[2][1] and c[6][1] <= total(c)[1]
    got = {p: total(c) for p, c in ft["players"].items()}
    if {p: v for p, v in got.items() if v[1]} != {p: v for p, v in want.items() if v[1]}:
        bad = sorted(p for p in set(got) | set(want) if got.get(p, [0, 0]) != want.get(p, [0, 0]))
        raise ValueError(f"ft.json: players {[(p, got.get(p), want.get(p)) for p in bad[:5]]} (ft.json, box) differ")
    for code, c in ft["teams"].items():
        if total(c["for"]) != clubs.get(code, [0, 0]) or total(c["against"]) != clubs.get("-" + code, [0, 0]):
            raise ValueError(f"ft.json: {code} for {total(c['for'])} against {total(c['against'])}, box {clubs.get(code)} {clubs.get('-' + code)}")
    lg = [[sum(c[i][j] for c in ft["players"].values()) for j in (0, 1)] for i in range(len(KINDS))]
    for name, c in (("league", ft["league"]), ("league from the clubs", [[sum(t["for"][i][j] for t in ft["teams"].values()) for j in (0, 1)]
                                                                         for i in range(len(KINDS))])):
        if c != lg:
            raise ValueError(f"ft.json: {name} {c}, players add up to {lg}")
    if sum(t["against"][i][j] for t in ft["teams"].values() for i in range(len(KINDS)) for j in (0, 1)) != sum(x for c in lg for x in c):
        raise ValueError("ft.json: the clubs' against does not add up to the league")
    for who, c in [*ft["players"].items(), *((k + " " + s, t[s]) for k, t in ft["teams"].items() for s in ("for", "against")), ("league", ft["league"])]:
        if not sane(c):
            raise ValueError(f"ft.json: {who} {c}: and-ones or pressure free throws out of range")


def allowed(lines):
    """The post-game corrections tolerated in a season of so many box lines, as in warehouse_tests.py."""
    return max(2, lines // 1000)


def from_warehouse(wh, skip=()):
    """(rows for write_ft(), {game: what differs}, player-games that differ, box lines checked) from the Parquet tables
    in the directory wh; the games in skip and the games whose free throws differ from the box score are left out."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"create view games as select * from {quarantine.games_sql(wh)}")
    for t in ("box", "events"):
        con.execute(f"create view {t} as select * from read_parquet('{os.path.join(wh, t + '.parquet')}')")
    final = "join games g using (game) where g.game_type = 'regular' and g.final" + \
        (f" and g.game not in ({', '.join(repr(x) for x in sorted(skip))})" if skip else "")
    bad = con.execute(f"""
        with e as (select e.game, e.player, count(*) filter (where e.result = 'Made') as ftm, count(*) as fta
                   from events e {final} and e.action_type = 'freethrow' and e.player is not null group by all),
             b as (select b.game, b.player, b.ftm, b.fta from box b {final} and b.status = 'ACTIVE' and b.fta > 0)
        select coalesce(e.game, b.game), coalesce(e.player, b.player), e.ftm, e.fta, b.ftm, b.fta
        from e full join b using (game, player) where e.ftm is distinct from b.ftm or e.fta is distinct from b.fta order by 1, 2""").fetchall()
    games = {}
    for g, p, em, ea, bm, ba in bad:
        games.setdefault(g, []).append(f"player {p}: play-by-play {em or 0}-{ea or 0}, box {bm or 0}-{ba or 0}")
    games = {g: "; ".join(rs) for g, rs in games.items()}
    lines = con.execute(f"select count(*) from box b {final} and b.status = 'ACTIVE'").fetchone()[0]
    keep = f"{final} and e.game not in ({', '.join(repr(x) for x in sorted(games))})" if games else final
    cur = con.execute(f"""select e.game, g.home, g.away, e.action_type, e.sub_type, e.descriptor, e.result, e.player, e.team, e.period, e.clock,
                                 e.score_home, e.score_away, e.action_type in ('2pt', '3pt') as fg
                          from events e {keep} and (e.action_type in ('freethrow', '2pt', '3pt') or e.score_home is not null)
                          order by e.game, e.order_no, e.action""")
    cols = [c[0] for c in cur.description]
    by = {}
    for r in cur.fetchall():
        by.setdefault(r[0], []).append(dict(zip(cols, r)))
    rows = []
    for gid, es in by.items():
        home, away = es[0]["home"], es[0]["away"]
        rows += [{**r, "gid": gid, "opp": away if r["team"] == home else home} for r in attempts(es, home)]
    return rows, games, len(bad), lines


if __name__ == "__main__":
    from season import ROOT, season
    from site_data import load_teams
    SEASON = season()
    out, wh = os.path.join(ROOT, "teams", SEASON), os.path.join(ROOT, "warehouse", SEASON)
    if not os.path.exists(os.path.join(wh, "events.parquet")):
        raise SystemExit(f"{SEASON}: no warehouse tables in {wh}; run warehouse.py first")
    skip = quarantine.held(wh, "ft", gate="ft")
    rows, bad, n, lines = from_warehouse(wh, skip)
    for g, r in sorted(bad.items()):
        print(f"WARN game {g}: free throws differ from the box score, left out: {r}")
    held = bad if n > allowed(lines) else {}
    quarantine.record(wh, "ft", {g: ("ft", f"free throws differ from the box score: {r}") for g, r in held.items()})
    write_ft(out, load_teams(), rows, set(skip) | set(bad))
    check_ft(out)
    print(f"{SEASON}: free throws written to {os.path.join(out, 'ft.json')}; {len(bad)} games left out ({n} player-games differ, "
          f"{allowed(lines)} allowed), {len(held)} quarantined, {len(skip)} held by an earlier gate")
    raise SystemExit(quarantine.exit_code(wh))
