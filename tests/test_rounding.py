"""The one rounding rule (rounding.py): half away from zero on the exact value, None for an empty denominator.

usage: python tests/test_rounding.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rounding import avg, rnd  # noqa: E402

checks = {
    "half rounds away from zero": avg(5, 2, 0) == 3 and avg(-5, 2, 0) == -3 and avg(25, 10) == 2.5 and avg(1, 8, 2) == 0.13,
    "exact on integer totals (2675/1000 is 2.68, not float's 2.67)": avg(2675, 1000, 2) == 2.68 and round(2.675, 2) == 2.67,
    "per-game average": avg(193, 8) == 24.1 and avg(195, 8) == 24.4,
    "percentage with a scale": avg(7, 16, 1, 100) == 43.8,
    "no denominator is None": avg(3, 0) is None and avg(3, None) is None,
    "floats round the same way": rnd(-0.25, 1) == -0.3 and rnd(0.35, 1) == 0.4 and rnd(112.04999, 1) == 112.0,
    "NaN and None are None": rnd(float("nan")) is None and rnd(None) is None,
    "zero digits gives an int": isinstance(avg(7, 2, 0), int),
}
for k, v in checks.items():
    print("ok  " if v else "FAIL", k)
sys.exit(0 if all(checks.values()) else 1)
