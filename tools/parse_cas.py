"""
Data Agent — Tool: parse_cas.py
Parses MF Central / CAMS / KFintech CAS PDF using casparser and returns
a clean list of active holdings.
"""

from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.xirr import compute_xirr_for_holding

try:
    import casparser
except ImportError:
    import sys
    sys.exit("casparser not installed. Run: pip install casparser")


# ── helpers ──────────────────────────────────────────────────────────────────

def _f(val: Any, default: float = 0.0) -> float:
    """Safely convert Decimal / str / None to float."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _detect_sip_type(transactions) -> str:
    if not transactions:
        return "unknown"
    types = set()
    for txn in transactions:
        desc = (getattr(txn, "description", "") or "").lower()
        t    = str(getattr(txn, "type", "") or "").lower()
        if "systematic" in desc or "sip" in desc or "systematic" in t:
            types.add("sip")
        elif "purchase" in desc or "purchase" in t:
            types.add("lumpsum")
    if "sip" in types and "lumpsum" in types:
        return "both"
    return "sip" if "sip" in types else ("lumpsum" if "lumpsum" in types else "unknown")


def _avg_cost(transactions, units: float) -> float:
    """Compute average cost per unit from purchase transactions."""
    total_amount = 0.0
    total_units  = 0.0
    for txn in transactions:
        amt   = _f(getattr(txn, "amount", 0))
        u     = _f(getattr(txn, "units", 0))
        ttype = str(getattr(txn, "type", "")).upper()
        if amt > 0 and u > 0 and "REDEMPT" not in ttype and "SWITCH_OUT" not in ttype:
            total_amount += amt
            total_units  += u
    if total_units > 0:
        return round(total_amount / total_units, 4)
    if units > 0:
        return 0.0
    return 0.0


def _sip_amount(transactions) -> float:
    """Estimate monthly SIP amount from systematic purchase transactions."""
    sip_amounts = []
    for txn in transactions:
        desc = (getattr(txn, "description", "") or "").lower()
        amt  = _f(getattr(txn, "amount", 0))
        if ("systematic" in desc or "sip" in desc) and amt > 0:
            sip_amounts.append(amt)
    if not sip_amounts:
        return 0.0
    return round(sum(sip_amounts) / len(sip_amounts), 2)


def _txn_to_dict(txn) -> dict:
    return {
        "date":        str(getattr(txn, "date", "")),
        "description": getattr(txn, "description", ""),
        "amount":      _f(getattr(txn, "amount", 0)),
        "units":       _f(getattr(txn, "units", 0)),
        "nav":         _f(getattr(txn, "nav", 0)),
        "balance":     _f(getattr(txn, "balance", 0)),
        "type":        str(getattr(txn, "type", "")),
    }


# ── main parser ──────────────────────────────────────────────────────────────

def parse_cas(pdf_path: str, password: str) -> list[dict]:
    """
    Parse a CAS PDF and return a list of active (units > 0) holdings.
    Works with casparser's CASData Pydantic model (v0.7+).
    """
    pdf_path = str(Path(pdf_path).expanduser().resolve())
    print(f"[parse_cas] Parsing: {pdf_path}")

    data = None
    for pwd in [password, ""]:
        try:
            data = casparser.read_cas_pdf(pdf_path, password=pwd, output="dict")
            break
        except Exception as exc:
            last_exc = exc

    if data is None:
        raise RuntimeError(f"casparser failed: {last_exc}")

    folios = data.folios or []
    print(f"[parse_cas] Found {len(folios)} folios | "
          f"Period: {data.statement_period}")

    holdings: list[dict] = []

    for folio in folios:
        folio_number = getattr(folio, "folio", "") or ""
        amc          = getattr(folio, "amc", "") or ""

        for scheme in (folio.schemes or []):
            units = _f(getattr(scheme, "close", 0))
            if units <= 0:
                continue   # fully redeemed

            fund_name  = getattr(scheme, "scheme", "") or ""
            isin       = getattr(scheme, "isin", "") or ""
            valuation  = getattr(scheme, "valuation", None)
            txns       = scheme.transactions or []

            # Extract from valuation object
            current_nav  = _f(getattr(valuation, "nav", None))  if valuation else 0.0
            invested     = _f(getattr(valuation, "cost", None)) if valuation else 0.0
            current_val  = _f(getattr(valuation, "value", None))if valuation else 0.0

            # Fallback: compute from transactions
            if current_val == 0 and current_nav > 0:
                current_val = round(current_nav * units, 2)
            if invested == 0:
                invested = round(sum(
                    _f(getattr(t, "amount", 0)) for t in txns
                    if _f(getattr(t, "amount", 0)) > 0
                       and "REDEMPT" not in str(getattr(t, "type", "")).upper()
                       and "SWITCH_OUT" not in str(getattr(t, "type", "")).upper()
                ), 2)

            avg_nav    = _avg_cost(txns, units)
            sip_amt    = _sip_amount(txns)
            inv_type   = _detect_sip_type(txns)
            txns_clean = [_txn_to_dict(t) for t in txns]

            # Absolute return %
            abs_return = round((current_val - invested) / invested * 100, 2) if invested > 0 else None

            # XIRR from transaction cash flows
            xirr_val = compute_xirr_for_holding(txns_clean, current_val)

            holdings.append({
                "folio":             folio_number,
                "amc":               amc,
                "fund_name":         fund_name.strip(),
                "isin":              isin,
                "units":             round(units, 4),
                "current_nav":       round(current_nav, 4),
                "avg_nav":           avg_nav,
                "invested_amount":   round(invested, 2),
                "current_value":     round(current_val, 2),
                "abs_return_pct":    abs_return,
                "xirr":              xirr_val,
                "sip_amount":        sip_amt,
                "investment_type":   inv_type,
                "transactions":      txns_clean,
            })

    print(f"[parse_cas] Active holdings: {len(holdings)}")
    return holdings
