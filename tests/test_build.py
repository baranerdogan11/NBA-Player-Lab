"""Builds index.html into a scratch copy of the repository and checks that every placeholder was filled and every
Turkish string the page asks for exists.

usage: python tests/test_build.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
for f in ("build.py", "season.py", "config.json", "template.html"):
    shutil.copy(os.path.join(ROOT, f), tmp)
shutil.copytree(os.path.join(ROOT, "lang"), os.path.join(tmp, "lang"))
r = subprocess.run([sys.executable, os.path.join(tmp, "build.py")], capture_output=True, text=True)
print(r.stdout.strip(), r.stderr.strip())
ok = r.returncode == 0
page = open(os.path.join(tmp, "index.html"), encoding="utf-8").read() if ok else ""
meta = json.loads(re.search(r"const META = (\{.*?\});", page).group(1)) if ok else {}
season = json.load(open(os.path.join(ROOT, "config.json")))["season"]
checks = {
    "build exits cleanly": ok,
    "placeholders filled": ok and "/*META*/" not in page and "/*TR*/" not in page,
    "season in META": meta.get("season") == season,
    "build time in META": bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", meta.get("built", ""))),
}
# every string passed to t('...') in the template has a Turkish entry
tpl = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
tr = json.load(open(os.path.join(ROOT, "lang", "tr.json"), encoding="utf-8"))
wanted = set(re.findall(r"\bt\('([^']+)'\)", tpl)) | {label for _, label in re.findall(r"\['(\w+)', '([^']+)'\]", tpl)}
missing = sorted(w for w in wanted if w not in tr)
checks["every page string has a Turkish entry" + (f" (missing: {missing})" if missing else "")] = not missing
shutil.rmtree(tmp)
for name, passed in checks.items():
    print(("PASS " if passed else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
