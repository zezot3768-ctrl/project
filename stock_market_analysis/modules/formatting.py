"""Small helpers that turn numbers into readable text. Missing values become 'N/A'."""
import math


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def money(x, decimals=2):
    return "N/A" if _missing(x) else f"${x:,.{decimals}f}"


def signed_money(x, decimals=2):
    if _missing(x):
        return "N/A"
    return f"{'+' if x >= 0 else '-'}${abs(x):,.{decimals}f}"


def percent(x, decimals=2, signed=True):
    if _missing(x):
        return "N/A"
    return f"{x:+.{decimals}f}%" if signed else f"{x:.{decimals}f}%"


def compact(x, prefix=""):
    """1_234_000_000 -> '1.23B' (optionally with a prefix such as '$')."""
    if _missing(x):
        return "N/A"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(x) >= limit:
            return f"{prefix}{x / limit:.2f}{suffix}"
    return f"{prefix}{x:,.0f}"


def utc_time(dt):
    return "never" if dt is None else dt.strftime("%Y-%m-%d %H:%M:%S UTC")
