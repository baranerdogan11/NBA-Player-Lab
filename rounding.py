"""The site's one rounding rule. Every average, percentage and rating the site shows goes through it, whether the page
derives it from integer totals or Python writes it into the JSON, so the same number reads the same on every page to
the last decimal.

The rule: round half up on the exact value, in integer arithmetic: floor((2 * num * 10^d + den) / (2 * den)) / 10^d,
the same formula the page uses. 2675 / 1000 rounds to 2.68 (binary floating point would give 2.67); a half always goes
up, so 2.5 rounds to 3 and -2.5 to -2. A value with no denominator is None and shows as a dash.
"""
from fractions import Fraction


def _half_up(q, digits):
    """Exact fraction q rounded half up to `digits` decimals."""
    q = q * 10 ** digits
    n = (2 * q.numerator + q.denominator) // (2 * q.denominator)
    return n if digits == 0 else n / 10 ** digits


def avg(num, den, digits=1, scale=1):
    """num / den * scale, rounded; exact for integer totals. None when den is 0 or missing."""
    if den is None or num is None or den == 0:
        return None
    return _half_up(Fraction(num) * Fraction(scale) / Fraction(den), digits)


def rnd(x, digits=1):
    """An already-computed value (a model output, a difference of ratings), rounded the same way. The float is read
    at its shortest decimal form (0.35 is 0.35, not 0.34999...), so the rule applies to the number as written."""
    if x is None or x != x:
        return None
    return _half_up(Fraction(repr(float(x))), digits)
