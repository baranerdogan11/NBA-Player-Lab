"""Gold layer: renders index.html from template.html, with the build's metadata and the Turkish dictionary inlined.

usage: python build.py [2026-27]
"""
import datetime
import json
import os
from season import ROOT, season

SEASON = season()
meta = {"season": SEASON, "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
tr = json.load(open(os.path.join(ROOT, "lang", "tr.json"), encoding="utf-8"))
tpl = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
for marker in ("/*META*/", "/*TR*/{}"):
    if tpl.count(marker) != 1:
        raise SystemExit(f"template.html: expected one {marker}, found {tpl.count(marker)}")
html = tpl.replace("/*META*/", json.dumps(meta, ensure_ascii=False)).replace("/*TR*/{}", json.dumps(tr, ensure_ascii=False))
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
print(f"{SEASON}: index.html built")
