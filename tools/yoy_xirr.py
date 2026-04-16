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
from tools.formatting import is_purchase, is_redemption


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
    """Return the unit balance as of the given date.

    Takes the highest non-zero balance from transactions on or before target.
    Ignores zero-balance entries (e.g. STAMP_DUTY_TAX) that would overwrite
    a valid balance from a purchase on the same date.
    """
    balance = 0.0
    for txn in sorted(transactions, key=lambda t: t.get("date", "")):
        txn_date = _to_date(txn["date"])
        if txn_date > target:
            break
        txn_balance = txn.get("balance")
        if txn_balance is not None and float(txn_balance) > 0:
            balance = float(txn_balance)
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
        if amount == 0:
            continue
        txn_type = str(txn.get("type") or "")

        if is_purchase(txn_type):
            cfs.append((txn_date, -abs(amount)))
        elif is_redemption(txn_type):
            cfs.append((txn_date, abs(amount)))
    return cfs


def _cashflows_in_year(transactions: list[dict], year: int) -> list[tuple[date, float]]:
    """Build signed cashflow list from transactions within a single calendar year."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    cfs: list[tuple[date, float]] = []
    for txn in transactions:
        txn_date = _to_date(txn["date"])
        if txn_date < start or txn_date > end:
            continue
        amount = float(txn.get("amount", 0))
        if amount == 0:
            continue
        txn_type = str(txn.get("type") or "")
        if is_purchase(txn_type):
            cfs.append((txn_date, -abs(amount)))
        elif is_redemption(txn_type):
            cfs.append((txn_date, abs(amount)))
    return cfs


def _units_bought_in_year(transactions: list[dict], year: int) -> float:
    """Sum of units purchased (minus redeemed) within a single calendar year."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    units = 0.0
    for txn in transactions:
        txn_date = _to_date(txn["date"])
        if txn_date < start or txn_date > end:
            continue
        txn_type = str(txn.get("type") or "")
        txn_units = float(txn.get("units", 0))
        if is_purchase(txn_type):
            units += abs(txn_units)
        elif is_redemption(txn_type):
            units -= abs(txn_units)
    return units


def compute_fund_yoy_xirr(
    holding: dict, nav_history: list[dict]
) -> dict[int, dict]:
    """
    Compute year-slice performance for a single fund.

    For each year, considers ONLY the SIP installments made in that year
    and their value at Dec 31 of that year. This answers: "How did the
    money I invested in 2023 perform by end of 2023?"

    Returns {year: {"return_pct": float|None, "invested": float, "actual": float}}
    """
    transactions = holding.get("transactions", [])
    if not transactions:
        return {}

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
    result: dict[int, dict] = {}

    for year in range(first_year, current_year + 1):
        # Only consider investments made in THIS year
        year_cashflows = _cashflows_in_year(transactions, year)
        if not year_cashflows:
            continue

        year_invested = sum(abs(amt) for _, amt in year_cashflows if amt < 0)
        if year_invested <= 0:
            continue

        units_in_year = _units_bought_in_year(transactions, year)
        if units_in_year <= 0:
            continue

        if year == current_year:
            # Current partial year: use current NAV
            current_nav = holding.get("current_nav")
            if not current_nav:
                # Try from nav_history
                if nav_history:
                    try:
                        current_nav = float(nav_history[0]["nav"])
                    except (KeyError, ValueError, IndexError):
                        continue
            if not current_nav:
                continue
            year_end_value = units_in_year * current_nav
        else:
            nav = _find_nav_on_date(nav_history, date(year, 12, 31))
            if nav is None:
                continue
            year_end_value = units_in_year * nav

        # XIRR considering SIP timing within the year
        end = date(year, 12, 31) if year != current_year else date.today()
        cf_with_terminal = year_cashflows + [(end, year_end_value)]
        xirr_val = xirr(cf_with_terminal)
        xirr_pct = round(xirr_val, 2) if xirr_val is not None else None

        # Fallback to simple return if XIRR fails
        if xirr_pct is None:
            xirr_pct = round((year_end_value - year_invested) / year_invested * 100, 2)

        result[year] = {
            "return_pct": xirr_pct,
            "invested": round(year_invested),
            "actual": round(year_end_value),
        }

    return result


def compute_portfolio_yoy_xirr(
    holdings: list[dict],
    nav_histories: dict[str, list[dict]],
) -> dict[int, dict]:
    """
    Compute cumulative XIRR, invested value, and actual value at each year-end.

    nav_histories: {fund_name: nav_history_list} for NAV lookups.

    Returns: {year: {"xirr": float|None, "invested": float, "actual": float}, ...}
    """
    all_dates: list[date] = []
    for h in holdings:
        for txn in h.get("transactions", []):
            try:
                all_dates.append(_to_date(txn["date"]))
            except (KeyError, ValueError):
                continue
    if not all_dates:
        return {}

    first_date = min(all_dates)
    first_year = first_date.year
    current_year = date.today().year
    result: dict[int, dict] = {}

    for year in range(first_year, current_year + 1):
        is_current = (year == current_year)
        end_date = date.today() if is_current else date(year, 12, 31)

        all_cashflows: list[tuple[date, float]] = []
        total_terminal = 0.0
        total_invested = 0.0
        has_any_value = False

        for h in holdings:
            transactions = h.get("transactions", [])
            if not transactions:
                continue

            cfs = _cashflows_up_to_date(transactions, end_date)
            all_cashflows.extend(cfs)

            # Sum invested (purchases) up to this date
            for _, amt in cfs:
                if amt < 0:
                    total_invested += abs(amt)

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
            result[year] = {"xirr": None, "invested": round(total_invested), "actual": round(total_terminal)}
            continue

        return_pct = round((total_terminal - total_invested) / total_invested * 100, 2) if total_invested > 0 else None

        days_held = (end_date - first_date).days
        if days_held < 365:
            xirr_pct = return_pct
        else:
            all_cashflows.append((end_date, total_terminal))
            xirr_val = xirr(all_cashflows)
            xirr_pct = round(xirr_val, 2) if xirr_val is not None else None

        result[year] = {
            "xirr": xirr_pct,
            "return_pct": return_pct,
            "invested": round(total_invested),
            "actual": round(total_terminal),
        }

    return result


def _check_nav_mismatch(holding: dict, nav_history: list[dict]) -> None:
    """Warn if CAS transaction NAV diverges from mfapi NAV — indicates wrong scheme code."""
    transactions = holding.get("transactions", [])
    for txn in reversed(transactions):
        txn_type = str(txn.get("type") or "")
        if not is_purchase(txn_type):
            continue
        units = float(txn.get("units", 0))
        amount = float(txn.get("amount", 0))
        if units <= 0 or amount <= 0:
            continue
        cas_nav = amount / units
        txn_date = _to_date(txn["date"])
        mfapi_nav = _find_nav_on_date(nav_history, txn_date)
        if mfapi_nav is None:
            break
        ratio = mfapi_nav / cas_nav if cas_nav > 0 else 0
        if ratio > 1.5 or ratio < 0.67:
            print(
                f"\n  ⚠ SCHEME CODE MISMATCH for {holding['fund_name'][:45]}"
                f"\n    CAS NAV={cas_nav:.2f} vs mfapi NAV={mfapi_nav:.2f} (ratio={ratio:.1f}x)"
                f"\n    scheme_codes.json likely has a wrong mapping → per-fund numbers will be inaccurate"
                f"\n    Fix: delete scheme_codes.json and re-run to re-resolve scheme codes\n"
            )
        break


def enrich_holdings_with_yoy_xirr(
    holdings: list[dict],
) -> tuple[list[dict], dict[int, dict]]:
    """
    Compute year-on-year XIRR for each fund and the portfolio.

    Fetches NAV history from mfapi.in for each fund (one API call per fund).
    Adds 'yoy_xirr' dict to each holding.

    Returns (holdings, portfolio_yoy_dict).
    Portfolio dict: {year: {"xirr": float|None, "invested": float, "actual": float}}
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

        # Cross-validate: compare CAS transaction NAV with mfapi NAV
        # If they diverge significantly, scheme_codes.json has a wrong mapping
        _check_nav_mismatch(h, nav_hist)

        nav_histories[name] = nav_hist
        yoy = compute_fund_yoy_xirr(h, nav_hist)
        h["yoy_xirr"] = yoy

        years_computed = [y for y, d in yoy.items() if d.get("return_pct") is not None]
        if years_computed:
            print(f"✓ {min(years_computed)}-{max(years_computed)} ({len(years_computed)} years)")
        else:
            print("⚠ no valid years")

        time.sleep(0.3)

    # Portfolio-level
    print("  [portfolio] Computing aggregate YoY XIRR...", end=" ", flush=True)
    portfolio_yoy = compute_portfolio_yoy_xirr(holdings, nav_histories)
    years_with_xirr = [y for y, d in portfolio_yoy.items() if d.get("xirr") is not None]
    if years_with_xirr:
        print(f"✓ {min(years_with_xirr)}-{max(years_with_xirr)}")
    else:
        print("⚠ no valid years")

    print(f"[yoy_xirr] Done.\n")
    return holdings, portfolio_yoy
