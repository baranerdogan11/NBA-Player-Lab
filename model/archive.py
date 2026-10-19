"""Past seasons' play-by-play for training, from the shufinskiy/nba_data archive (Apache-2.0). Its `cdnnba` files are
the NBA CDN liveData play-by-play actions stored as CSV, one row per action, so model/actions.py reads them exactly as
it reads the live feed. Downloads are pinned to one archive commit and checked against a SHA-256, cached under
cache/archive/, and the shots are kept as cache/archive/shots_<season>.parquet.

usage: python model/archive.py 2025-26     # download (if needed) and write the season's shots
"""
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.request
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actions import shots_frame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "archive")
SOURCE = json.load(open(os.path.join(ROOT, "model", "training.json")))["archive"]


def fetch(name):
    """The archive file `name` (e.g. cdnnba_2025), downloaded once and verified."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}.tar.xz")
    if not os.path.exists(path):
        url = f"https://github.com/{SOURCE['repo']}/raw/{SOURCE['commit']}/datasets/{name}.tar.xz"
        print("downloading", url)
        data = urllib.request.urlopen(url, timeout=300).read()
        open(path, "wb").write(data)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != SOURCE["sha256"][name]:
        raise SystemExit(f"{name}: sha256 {digest} does not match model/training.json")
    with tarfile.open(path) as t:
        member = next(m for m in t.getmembers() if m.name.endswith(".csv"))
        return pd.read_csv(io.BytesIO(t.extractfile(member).read()), dtype=str, keep_default_na=False)


def home_team(acts):
    """The archive has no game header: the home team is the one whose points move scoreHome."""
    last = 0.0
    for a in sorted(acts, key=lambda a: int(a["orderNumber"])):
        try:
            h = float(a["scoreHome"])
        except ValueError:
            continue
        if h > last and a["teamId"]:
            return a["teamId"]
        last = h
    return None


def season_shots(season):
    """Every field-goal attempt of a season, regular season then playoffs, with game date and phase."""
    year = season[:4]
    parts = []
    for phase, name in (("regular", f"cdnnba_{year}"), ("playoffs", f"cdnnba_po_{year}")):
        if name not in SOURCE["sha256"]:
            continue
        raw = fetch(name)
        games = {g: d.to_dict("records") for g, d in raw.groupby("gameId")}
        shots = shots_frame(games, {g: home_team(a) for g, a in games.items()})
        start = raw[raw.timeActual != ""].groupby("gameId").timeActual.min()
        shots["date"] = pd.to_datetime(shots.game.map(start), format="ISO8601", utc=True).dt.tz_convert("America/New_York").dt.date.astype(str)
        shots["phase"] = phase
        parts.append(shots)
    df = pd.concat(parts, ignore_index=True)
    df["season"] = season
    return df


if __name__ == "__main__":
    for season in sys.argv[1:] or json.load(open(os.path.join(ROOT, "model", "training.json")))["seasons"]:
        df = season_shots(season)
        df.to_parquet(os.path.join(CACHE, f"shots_{season}.parquet"), index=False)
        print(f"{season}: {df.game.nunique()} games, {len(df)} shots, {df.made.mean():.3f} FG, home known for {df.home_team.notna().mean():.3f}")
