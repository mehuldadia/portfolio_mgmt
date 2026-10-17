"""Currency formatting helpers for portfolio displays and reports."""

import math


def format_inr(value, decimals=2):
    """Format a numeric value as Indian rupees with Indian digit grouping."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if not math.isfinite(amount):
        amount = 0.0

    formatted = f"{abs(amount):.{decimals}f}"
    integer, fraction = formatted.split(".")
    if len(integer) > 3:
        last_group = integer[-3:]
        remaining = integer[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        integer = ",".join(reversed(groups)) + "," + last_group

    sign = "-" if amount < 0 else ""
    return f"{sign}₹{integer}.{fraction}"
