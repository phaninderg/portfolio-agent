"""
Year-on-Year XIRR computation.

Computes rolling cumulative XIRR at each year-end (Dec 31) for both
individual funds and the overall portfolio. Uses full transaction history
from the CAS and NAV data from mfapi.in.

"Cumulative XIRR at year-end Y" = XIRR using ALL cash flows from inception
to Dec 31 of Y, with terminal value = units_held × NAV on Dec 31.
"""

from __future__ import annotations

import time
from datetime import date

from tools.xirr import xirr, _to_date
from tools.fetch_nav import fetch_nav_history
from tools.formatting import PURCHASE_TYPES, REDEMPTION_TYPES


def _find_nav_on_date(nav_history: list[dict], target: date) -> float | None:
    """Find NAV closest to target date, within 7-day tolerance."""
    best_entry = None
    best_delta = None

    for entry in nav_history:
        try:
            d_str = entry["date"]  # DD-MM-YYYY
            d = date(int(d_str[6:]), int(d_str[3:5]), int(d_str[:2]))
        except (KeyError, ValueError, IndexError):
            continue

        delta = abs((d - target).days)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_entry = entry

        # Optimisation: if we've passed the target and found a good match, stop
        if d < target and best_delta is not None and best_delta <= 5:
            break

    if best_entry and best_delta is not None and best_delta <= 7:
        try:
            return float(best_entry["nav"])
        except (ValueError, TypeError):
            return None
    return None


def _units_held_on_date(transactions: list[dict], target: date) -> float:
    """Return the unit balance as of the given date (last balance on or before target)."""
    balance = 0.0
    for txn in sorted(transactions, key=lambda t: t.get("date", "")):
        txn_date = _to_date(txn["date"])
        if txn_date > target:
            break
        if txn.get("balance") is not None:
            balance = float(txn["balance"])
    return balance


def _cashflows_up_to_date(
    transactions: list[dict], end_date: date
) -> list[tuple[date, float]]:
    """Build signed cashflow list from transactions on or before end_date."""
    cfs: list[tuple[date, float]] = []
    for txn in transactions:
        txn_date = _to_date(txn["date"])
        if txn_date > end_date:
            continue
        amount = float(txn.get("amount", 0))
        txn_type = (txn.get("type") or "").upper()

        if txn_type in PURCHASE_TYPES:
            cfs.append((txn_date, -abs(amount)))
        elif txn_type in REDEMPTION_TYPES:
            cfs.append((txn_date, abs(amount)))
    return cfs


def compute_fund_yoy_xirr(
    holding: dict, nav_history: list[dict]
) -> dict[int, float | None]:
    """
    Compute cumulative XIRR at each year-end for a single fund.

    Returns {year: xirr_percentage_or_None, ...}.
    Current year uses holding['current_value'] as terminal value.
    """
    transactions = holding.get("transactions", [])
    if not transactions:
        return {}

    # Determine year range
    dates = []
    for txn in transactions:
        try:
            dates.append(_to_date(txn["date"]))
        except (KeyError, ValueError):
            continue
    if not dates:
        return {}

    first_year = min(dates).year
    current_year = date.today().year
    result: dict[int, float | None] = {}

    for year in range(first_year, current_year + 1):
        if year == current_year:
            # Current partial year — use current_value as terminal
            terminal_value = holding.get("current_value") or 0
            end_date = date.today()
        else:
            end_date = date(year, 12, 31)
            units = _units_held_on_date(transactions, end_date)
            if units <= 0:
                result[year] = None
                continue
            nav = _find_nav_on_date(nav_history, end_date)
            if nav is None:
                result[year] = None
                continue
            terminal_value = units * nav

        cashflows = _cashflows_up_to_date(transactions, end_date)
        if not cashflows:
            result[year] = None
            continue

        # Add terminal value
        cashflows.append((end_date, terminal_value))

        xirr_val = xirr(cashflows)
        if xirr_val is not None:
            result[year] = round(xirr_val * 100, 2)
        else:
            result[year] = None

    return result


def compute_portfolio_yoy_xirr(
    holdings: list[dict],
    nav_histories: dict[str, list[dict]],
) -> dict[int, float | None]:
    """
    Compute cumulative XIRR at each year-end for the entire portfolio.

    nav_histories: {fund_name: nav_history_list} for NAV lookups.
    """
    # Determine year range across all holdings
    all_dates: list[date] = []
    for h in holdings:
        for txn in h.get("transactions", []):
            try:
                all_dates.append(_to_date(txn["date"]))
            except (KeyError, ValueError):
                continue
    if not all_dates:
        return {}

    first_year = min(all_dates).year
    current_year = date.today().year
    result: dict[int, float | None] = {}

    for year in range(first_year, current_year + 1):
        is_current = (year == current_year)
        end_date = date.today() if is_current else date(year, 12, 31)

        all_cashflows: list[tuple[date, float]] = []
        total_terminal = 0.0
        has_any_value = False

        for h in holdings:
            transactions = h.get("transactions", [])
            if not transactions:
                continue

            cfs = _cashflows_up_to_date(transactions, end_date)
            all_cashflows.extend(cfs)

            if is_current:
                terminal = h.get("current_value") or 0
            else:
                units = _units_held_on_date(transactions, end_date)
                if units <= 0:
                    continue
                nav_hist = nav_histories.get(h["fund_name"], [])
                nav = _find_nav_on_date(nav_hist, end_date)
                if nav is None:
                    continue
                terminal = units * nav

            total_terminal += terminal
            if terminal > 0:
                has_any_value = True

        if not all_cashflows or not has_any_value:
            result[year] = None
            continue

        all_cashflows.append((end_date, total_terminal))
        xirr_val = xirr(all_cashflows)
        if xirr_val is not None:
            result[year] = round(xirr_val * 100, 2)
        else:
            result[year] = None

    return result


def enrich_holdings_with_yoy_xirr(
    holdings: list[dict],
) -> tuple[list[dict], dict[int, float | None]]:
    """
    Compute year-on-year XIRR for each fund and the portfolio.

    Fetches NAV history from mfapi.in for each fund (one API call per fund).
    Adds 'yoy_xirr' dict to each holding.

    Returns (holdings, portfolio_yoy_xirr_dict).
    """
    print("\n── Year-on-Year XIRR ────────────────────────────────────────────")
    nav_histories: dict[str, list[dict]] = {}

    for i, h in enumerate(holdings):
        name = h["fund_name"]
        code = h.get("scheme_code")

        if not code:
            h["yoy_xirr"] = {}
            continue

        print(f"  [{i+1}/{len(holdings)}] {name[:55]}...", end=" ", flush=True)

        nav_hist = fetch_nav_history(code)
        if not nav_hist:
            print("⚠ no NAV history")
            h["yoy_xirr"] = {}
            continue

        nav_histories[name] = nav_hist
        yoy = compute_fund_yoy_xirr(h, nav_hist)
        h["yoy_xirr"] = yoy

        years_computed = [y for y, v in yoy.items() if v is not None]
        if years_computed:
            print(f"✓ {min(years_computed)}-{max(years_computed)} ({len(years_computed)} years)")
        else:
            print("⚠ no valid years")

        time.sleep(0.3)

    # Portfolio-level
    print("  [portfolio] Computing aggregate YoY XIRR...", end=" ", flush=True)
    portfolio_yoy = compute_portfolio_yoy_xirr(holdings, nav_histories)
    years_computed = [y for y, v in portfolio_yoy.items() if v is not None]
    if years_computed:
        print(f"✓ {min(years_computed)}-{max(years_computed)}")
    else:
        print("⚠ no valid years")

    print(f"[yoy_xirr] Done.\n")
    return holdings, portfolio_yoy
