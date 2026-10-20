"""One-time sign-in for the private fantasy league, run on your own computer once Yahoo has approved the app: you sign in to
Yahoo in the browser, and the script stores in the repository's Actions settings what fantasy.yml needs (Yahoo's client
id and secret, your read-only refresh token, the league id and the invite key), then prints the members' invite link.

The settings are stored with the GitHub CLI (`gh auth login` first); without it the script prints them for you to paste
into Settings, Secrets and variables, Actions. Nothing is written to disk. Run it again to sign in afresh or, with
--new-key, to change the invite link (the old link stops working at the next league run).

usage: python fantasy_auth.py [--new-key]
"""
import base64
import getpass
import os
import shutil
import subprocess
import sys
import urllib.parse

from fantasy import API, REDIRECT, TOKEN, each, flat

REPO = "baranerdogan11/NBA-Player-Lab"
SITE = "https://baranerdogan11.github.io/NBA-Player-Lab/"


def store(name, value, secret=True):
    """One Actions secret (or variable) through the GitHub CLI; False if the CLI is not there or not signed in."""
    if not shutil.which("gh"):
        return False
    cmd = ["gh", "secret" if secret else "variable", "set", name, "--repo", REPO]
    return subprocess.run(cmd, input=value.encode(), capture_output=True).returncode == 0


def main():
    import requests
    cid = os.environ.get("YAHOO_CLIENT_ID") or input("Yahoo app Client ID: ").strip()
    secret = os.environ.get("YAHOO_CLIENT_SECRET") or getpass.getpass("Yahoo app Client Secret (not shown): ").strip()
    url = "https://api.login.yahoo.com/oauth2/request_auth?" + urllib.parse.urlencode(
        {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": "fspt-r"})
    print(f"\n1. Open this link, sign in to Yahoo and allow read access:\n\n   {url}\n")
    print(f"2. The browser then fails to load {REDIRECT}: that is expected. Copy the whole address from its address bar.\n")
    back = input("Address (or just the code): ").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [back])[0]
    r = requests.post(TOKEN, auth=(cid, secret), timeout=30,
                      data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT})
    if r.status_code != 200:
        sys.exit(f"Yahoo refused the sign-in (HTTP {r.status_code}); the code works once and for a few minutes, try again")
    tok = r.json()

    # your NBA leagues this season, to pick the one to show
    r = requests.get(API + "users;use_login=1/games;game_keys=nba/leagues", params={"format": "json"}, timeout=30,
                     headers={"Authorization": f"Bearer {tok['access_token']}"})
    if r.status_code == 403:
        sys.exit("Yahoo refused the league list (HTTP 403): the app's Fantasy API access is not approved yet")
    r.raise_for_status()
    user = r.json()["fantasy_content"]["users"]["0"]["user"]
    leagues = []
    for g in each(flat(user[1:])["games"], "game"):
        for lg in each(flat(g[1:] if isinstance(g, list) else g).get("leagues", {}), "league"):
            lg = flat(lg)
            leagues.append((str(lg["league_id"]), lg["name"], lg.get("scoring_type")))
    if not leagues:
        sys.exit("This Yahoo account has no NBA fantasy league this season")
    for i, (lid, name, kind) in enumerate(leagues, 1):
        print(f"   {i}. {name} (league {lid}, {kind})")
    lid = leagues[int(input("League number: ") or 1) - 1][0] if len(leagues) > 1 else leagues[0][0]

    key = None if "--new-key" in sys.argv else os.environ.get("FANTASY_KEY")
    key = key or base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    settings = [("YAHOO_CLIENT_ID", cid, True), ("YAHOO_CLIENT_SECRET", secret, True),
                ("YAHOO_REFRESH_TOKEN", tok["refresh_token"], True), ("FANTASY_KEY", key, True), ("FANTASY_LEAGUE", lid, False)]
    missed = [(n, v, s) for n, v, s in settings if not store(n, v, s)]
    if missed:
        print(f"\nThe GitHub CLI could not store these; paste each one at https://github.com/{REPO}/settings/secrets/actions "
              "(FANTASY_LEAGUE under the Variables tab), and keep them out of chats and files:\n")
        for n, v, _ in missed:
            print(f"   {n} = {v}")
    else:
        print("\nStored in the repository's Actions settings.")
    print(f"\nInvite link for the league members (share it privately; it opens after the next league run):\n\n"
          f"   {SITE}#league/{lid}/{key}\n")


if __name__ == "__main__":
    main()
