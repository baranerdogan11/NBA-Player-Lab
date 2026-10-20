"""Every name in the published site JSON is clean UTF-8: a feed decoded as Latin-1 turns "Luka Dončić" into "Luka DonÄiÄ",
leaving characters from U+0080 to U+00BF that no real name holds.
usage: python tests/test_names.py
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD = re.compile("[\u0080-¿]")


def names(x):
    if isinstance(x, dict):
        for k, v in x.items():
            if k in ("name", "city") and isinstance(v, str):
                yield v
            yield from names(v)
    elif isinstance(x, list):
        for v in x:
            yield from names(v)


assert BAD.search("Luka Dončić".encode().decode("latin-1")) and not BAD.search("Luka Dončić Schröder Mañon"), "the check itself"
bad = sorted({n for f in glob.glob(os.path.join(ROOT, "teams", "**", "*.json"), recursive=True) for n in names(json.load(open(f, encoding="utf-8"))) if BAD.search(n)})
assert not bad, f"double-encoded names in teams/: {bad[:5]}"
print("names ok")
