"""
Shared formatting and helper functions used across agents and reports.
Centralises duplicated _pct, _inr, sip_status, and LLM JSON extraction logic.
"""

from __future__ import annotations
import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ── Number formatters ────────────────────────────────────────────────────────

def fmt_pct(val, signed: bool = True) -> str:
    """Format a value as a percentage string. Returns 'N/A' for None."""
    if val is None:
        return "N/A"
    return f"{val:+.2f}%" if signed else f"{val:.2f}%"


def fmt_inr(val) -> str:
    """Format a value as Indian Rupees. Returns '—' for None."""
    if val is None:
        return "—"
    return f"₹{val:,.0f}"


def fmt_value(val, suffix: str = "", na: str = "N/A") -> str:
    """General-purpose value formatter."""
    if val is None:
        return na
    if isinstance(val, float):
        return f"{val:+.2f}{suffix}" if suffix else f"{val:.2f}"
    return str(val)


def color_pct_style(val) -> str:
    """Return inline CSS color for a percentage value (green/red)."""
    if val is None:
        return "color:#6b7280"
    return "color:#16a34a" if val >= 0 else "color:#dc2626"


# ── SIP status helpers ───────────────────────────────────────────────────────

def sip_status(transactions: list[dict]) -> str:
    """
    Determine if SIP is active, inactive, or never set up.
    - active   : purchase within last 45 days
    - inactive : purchases exist but last one > 45 days ago
    - never    : only lumpsum purchases (no systematic)
    """
    cutoff = (date.today() - timedelta(days=45)).isoformat()

    sip_txns = [
        t for t in transactions
        if float(t.get("amount", 0) or 0) > 0
        and any(k in str(t.get("type", "")).upper()
                for k in ("SIP", "SYSTEMATIC", "PURCHASE_SIP"))
    ]

    if not sip_txns:
        return "never"

    last_sip = max(t["date"] for t in sip_txns)
    return "active" if last_sip >= cutoff else "inactive"


def last_transaction_date(transactions: list[dict]) -> str | None:
    """Return the date of the most recent purchase transaction."""
    purchases = [
        t["date"] for t in transactions
        if float(t.get("amount", 0) or 0) > 0
        and "REDEMPT" not in str(t.get("type", "")).upper()
    ]
    return max(purchases) if purchases else None


# ── Transaction type constants ───────────────────────────────────────────────

PURCHASE_TYPES   = ("PURCHASE", "SWITCH_IN", "DIVIDEND_REINVEST")
REDEMPTION_TYPES = ("REDEMPTION", "SWITCH_OUT")


def is_purchase(txn_type: str) -> bool:
    return any(k in txn_type.upper() for k in PURCHASE_TYPES)


def is_redemption(txn_type: str) -> bool:
    return any(k in txn_type.upper() for k in REDEMPTION_TYPES)


# ── LLM response parsing ────────────────────────────────────────────────────

def extract_json_from_llm(raw: str, expect_array: bool = False) -> dict | list | None:
    """
    Extract JSON object or array from LLM response text.
    Handles markdown code fences, extra text before/after JSON.
    Returns parsed JSON or None on failure.
    """
    text = raw

    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            opener = "[" if expect_array else "{"
            if stripped.startswith(opener):
                text = stripped
                break

    # Find JSON boundaries
    opener = "[" if expect_array else "{"
    closer = "]" if expect_array else "}"

    start = text.find(opener)
    end   = text.rfind(closer) + 1

    if start == -1 or end == 0:
        logger.warning("Could not find JSON in LLM response")
        return None

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error: %s", exc)
        return None


# ── Portfolio-level calculations ─────────────────────────────────────────────

def compute_portfolio_xirr(holdings: list[dict]) -> float | None:
    """Compute portfolio-level XIRR from all holdings' transactions."""
    from tools.xirr import xirr as _xirr

    total_current = sum(h.get("current_value", 0) or 0 for h in holdings)
    all_txns = []

    for h in holdings:
        for txn in h.get("transactions", []):
            amt   = float(txn.get("amount", 0) or 0)
            ttype = str(txn.get("type", "")).upper()
            d     = txn.get("date", "")
            if not d or amt == 0:
                continue
            if is_purchase(ttype):
                all_txns.append((d, -abs(amt)))
            elif is_redemption(ttype):
                all_txns.append((d, abs(amt)))

    all_txns.append((date.today(), total_current))
    return _xirr(all_txns)


def compute_portfolio_stats(holdings: list[dict]) -> dict:
    """Compute common portfolio-level metrics used across reports and prompts."""
    total_invested = sum(h.get("invested_amount", 0) or 0 for h in holdings)
    total_current  = sum(h.get("current_value", 0) or 0 for h in holdings)
    total_pnl      = total_current - total_invested
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested else 0

    return {
        "total_invested": total_invested,
        "total_current":  total_current,
        "total_pnl":      total_pnl,
        "total_pnl_pct":  total_pnl_pct,
        "fund_count":     len(holdings),
    }
