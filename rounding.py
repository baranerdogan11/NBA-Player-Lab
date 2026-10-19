"""The site's one rounding rule. Every average, percentage and rating the page shows is rounded here, once, when the
JSON is written, and the page prints it as given (it never rounds again), so the same number reads the same on every
page to the last decimal.

The rule: half away from zero on the exact value. An average is computed from its integer totals as an exact fraction,
so 2675 / 1000 rounds to 2.68 (binary floating point would give 2.67), and -2.5 rounds to -3 like 2.5 rounds to 3.
A value with no denominator is None and shows as a dash.
"""
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

DIGITS = {"per_game": 1, "pct": 1, "rating": 1, "rate": 3}   # per-game averages, percentages, ratings per 100, shooting rates


def _quantize(q, digits):
    d = Decimal(q.numerator) / Decimal(q.denominator) if isinstance(q, Fraction) else Decimal(str(q))
    v = float(d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))   # ROUND_HALF_UP is away from zero in Decimal
    return int(v) if digits == 0 else v


def avg(num, den, digits=1, scale=1):
    """num / den * scale, rounded; exact when num and den are integers. None when den is 0 or missing."""
    if den is None or num is None or den == 0:
        return None
    if all(isinstance(x, int) for x in (num, den, scale)):
        return _quantize(Fraction(num * scale, den), digits)
    return _quantize(num * scale / den, digits)


def rnd(x, digits=1):
    """An already-computed value (a float from a model or a difference of ratings), rounded the same way."""
    if x is None or x != x:
        return None
    return _quantize(x, digits)
