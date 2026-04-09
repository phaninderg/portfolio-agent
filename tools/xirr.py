"""
Financial calculations — XIRR and CAGR.
No external dependencies. Used by fetch_nav, fetch_benchmark, and reports.
"""

from __future__ import annotations
import math
from datetime import date, datetime
from typing import Union


DateLike = Union[date, datetime, str]


def _to_date(d: DateLike) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    # Try common string formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(d), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {d!r}")


def _npv(cashflows: list[tuple[date, float]], rate: float) -> float:
    """Net present value at a given annual rate."""
    d0 = cashflows[0][0]
    return sum(
        cf / (1 + rate) ** ((d - d0).days / 365.0)
        for d, cf in cashflows
    )


def xirr(cashflows: list[tuple[DateLike, float]], guess: float = 0.1) -> float | None:
    """
    Compute XIRR given a list of (date, amount) tuples.
    Outflows (investments) should be negative; inflows positive.
    Returns annualised rate as a decimal (e.g. 0.12 = 12%) or None if unsolvable.
    """
    if not cashflows or len(cashflows) < 2:
        return None

    parsed = sorted((_to_date(d), float(cf)) for d, cf in cashflows)

    # Need at least one positive and one negative cash flow
    if not any(cf > 0 for _, cf in parsed) or not any(cf < 0 for _, cf in parsed):
        return None

    # Bisection between -99% and +1000%
    lo, hi = -0.9999, 10.0
    try:
        npv_lo = _npv(parsed, lo)
        npv_hi = _npv(parsed, hi)
        if npv_lo * npv_hi > 0:
            # Same sign — expand hi
            hi = 100.0
            npv_hi = _npv(parsed, hi)
            if npv_lo * npv_hi > 0:
                return None
    except (ZeroDivisionError, OverflowError):
        return None

    for _ in range(300):
        mid = (lo + hi) / 2
        try:
            npv_mid = _npv(parsed, mid)
        except (ZeroDivisionError, OverflowError):
            return None
        if abs(npv_mid) < 1e-6 or (hi - lo) < 1e-8:
            return round(mid * 100, 2)   # return as percentage
        if npv_lo * npv_mid < 0:
            hi = mid
            npv_hi = npv_mid
        else:
            lo = mid
            npv_lo = npv_mid

    return round((lo + hi) / 2 * 100, 2)


def compute_xirr_for_holding(transactions: list[dict], current_value: float) -> float | None:
    """
    Build cash flow list from transaction dicts and compute XIRR.
    transaction dict keys: date (str), amount (float), type (str)
    Purchases → negative CF, Redemptions → positive CF.
    Current value is added as final positive CF on today's date.
    """
    cashflows: list[tuple[DateLike, float]] = []

    for txn in transactions:
        amt  = float(txn.get("amount", 0) or 0)
        ttype = str(txn.get("type", "")).upper()
        d    = txn.get("date", "")
        if not d or amt == 0:
            continue

        # Purchases / SIP instalment = money out (negative)
        if any(k in ttype for k in ("PURCHASE", "SWITCH_IN", "DIVIDEND_REINVEST")):
            cashflows.append((d, -abs(amt)))
        # Redemptions / switch out = money in (positive)
        elif any(k in ttype for k in ("REDEMPTION", "SWITCH_OUT")):
            cashflows.append((d, abs(amt)))

    if not cashflows:
        return None

    # Add current value as terminal positive cash flow (today)
    cashflows.append((date.today(), current_value))

    return xirr(cashflows)


# ── CAGR ─────────────────────────────────────────────────────────────────────

def compute_cagr(
    old_value: float | None,
    new_value: float | None,
    years: float,
) -> float | None:
    """
    Compound Annual Growth Rate as a percentage.
    Returns None if inputs are invalid.
    """
    if old_value is None or new_value is None or old_value <= 0 or years <= 0:
        return None
    try:
        cagr = (math.pow(new_value / old_value, 1 / years) - 1) * 100
        return round(cagr, 2)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
