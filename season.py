"""The season every script works on: the command-line argument if one is given, otherwise config.json."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def season():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    return args[0] if args else json.load(open(os.path.join(ROOT, "config.json")))["season"]
