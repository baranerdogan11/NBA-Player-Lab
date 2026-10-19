"""Post-deploy check: the public site serves the commit that was just deployed (version.txt, written when the site is
staged) and the committed status.json. GitHub Pages can take a minute or two to switch over, so it retries for five
minutes before failing the run.
usage: SITE=<site url> SHA=<commit> python live.py [2026-27]
"""
import json
import os
import time
import urllib.request
from season import ROOT, season


def get(url):
    req = urllib.request.Request(f"{url}?t={time.time():.0f}", headers={"Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")


def main():
    site, sha, s = os.environ["SITE"].rstrip("/") + "/", os.environ["SHA"], season()
    path = os.path.join(ROOT, "teams", s, "status.json")
    want = json.load(open(path)) if os.path.exists(path) else None
    problem = "not checked"
    for _ in range(20):
        try:
            served = get(site + "version.txt").strip()
            if served != sha:
                problem = f"version.txt is {served}, not {sha}"
            elif want is not None and json.loads(get(f"{site}teams/{s}/status.json")) != want:
                problem = "the served status.json differs from the committed one"
            elif "<html" not in get(site).lower():
                problem = "the home page is not HTML"
            else:
                print(f"live: {site} serves {sha}")
                return
        except Exception as e:   # any fetch error is retried, then reported
            problem = f"{type(e).__name__}: {e}"
        time.sleep(15)
    raise SystemExit(f"live check failed for {site}: {problem}")


if __name__ == "__main__":
    main()
