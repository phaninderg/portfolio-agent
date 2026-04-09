"""
Research Agent — Tool: fetch_nav.py
Resolves fund names → scheme codes and fetches 1yr / 3yr / 5yr returns
from mfapi.in historical NAV data.
"""

from __future__ import annotations
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

# Project root
_ROOT = Path(__file__).parent.parent
_SCHEME_CODES_FILE = _ROOT / "scheme_codes.json"

MFAPI_BASE   = "https://api.mfapi.in/mf"
MFAPI_SEARCH = "https://api.mfapi.in/mf/search"

# Approx trading days per year (used to step back in NAV array)
DAYS_1YR = 365
DAYS_3YR = 365 * 3
DAYS_5YR = 365 * 5


# ── scheme code cache ─────────────────────────────────────────────────────────

def _load_scheme_cache() -> dict[str, str]:
    if _SCHEME_CODES_FILE.exists():
        with open(_SCHEME_CODES_FILE) as f:
            return json.load(f)
    return {}


def _save_scheme_cache(cache: dict[str, str]) -> None:
    with open(_SCHEME_CODES_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# ── search helpers ────────────────────────────────────────────────────────────

def search_scheme_code(fund_name: str, top_n: int = 5) -> list[dict]:
    """Search mfapi.in for a fund by name. Returns list of {schemeCode, schemeName}."""
    # Simplify name: strip AMC prefixes and common noise for better matching
    query = fund_name.strip()
    for prefix in ("Mirae Asset", "ICICI Prudential", "HDFC", "SBI", "Axis",
                   "Kotak", "Nippon India", "DSP", "Franklin", "Invesco",
                   "Parag Parikh", "Quant", "UTI", "Aditya Birla Sun Life"):
        query = query.replace(prefix, "").strip()

    try:
        resp = requests.get(MFAPI_SEARCH, params={"q": query}, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        return results[:top_n]
    except Exception as exc:
        print(f"  [fetch_nav] Search failed for '{fund_name}': {exc}")
        return []


def resolve_scheme_code(fund_name: str, cache: dict[str, str]) -> str | None:
    """
    Look up scheme code for a fund name.
    Uses cache first; falls back to mfapi.in search and picks top result.
    """
    if fund_name in cache:
        return cache[fund_name]

    results = search_scheme_code(fund_name)
    if not results:
        return None

    # Pick exact or best match
    fund_lower = fund_name.lower()
    for r in results:
        if r.get("schemeName", "").lower() == fund_lower:
            code = str(r["schemeCode"])
            cache[fund_name] = code
            return code

    # Fallback: first result
    code = str(results[0]["schemeCode"])
    cache[fund_name] = code
    print(f"  [fetch_nav] '{fund_name}' → '{results[0]['schemeName']}' (best guess)")
    return code


# ── NAV + returns ─────────────────────────────────────────────────────────────

def _fetch_nav_history(scheme_code: str, retries: int = 3) -> list[dict]:
    """Fetch full NAV history from mfapi.in. Returns list [{date, nav}, ...]."""
    url = f"{MFAPI_BASE}/{scheme_code}"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            return payload.get("data", [])   # newest first
        except Exception as exc:
            if attempt < retries:
                time.sleep(2 * attempt)
            else:
                print(f"  [fetch_nav] History fetch failed for code {scheme_code}: {exc}")
    return []


def _find_nav_n_days_ago(nav_history: list[dict], days: int) -> float | None:
    """
    Find the NAV closest to `days` calendar days ago.
    nav_history is sorted newest-first, each entry: {"date": "DD-MM-YYYY", "nav": "123.45"}
    """
    target = date.today() - timedelta(days=days)
    best_entry = None
    best_delta = None

    for entry in nav_history:
        try:
            d_str = entry["date"]          # DD-MM-YYYY
            d = date(int(d_str[6:]), int(d_str[3:5]), int(d_str[:2]))
        except Exception:
            continue
        delta = abs((d - target).days)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_entry = entry
        if delta > 7 and best_delta is not None and best_delta < 7:
            # Already past the window and found a good match
            break

    if best_entry:
        try:
            return float(best_entry["nav"])
        except (ValueError, TypeError):
            return None
    return None


def _compute_return(nav_old: float | None, nav_new: float | None) -> float | None:
    """CAGR-style return as a percentage."""
    if nav_old is None or nav_new is None or nav_old <= 0:
        return None
    return round(((nav_new / nav_old) - 1) * 100, 2)


def _compute_cagr(nav_old, nav_new, years):
    """Delegate to shared implementation."""
    from tools.xirr import compute_cagr
    return compute_cagr(nav_old, nav_new, years)


def fetch_fund_returns(scheme_code: str) -> dict:
    """
    Fetch NAV history and compute 1yr / 3yr / 5yr returns.
    Also extracts current NAV, fund category, AUM, expense ratio.
    Returns a dict with all fields (None if data unavailable).
    """
    result = {
        "scheme_code":    scheme_code,
        "current_nav":    None,
        "return_1yr":     None,
        "return_3yr":     None,
        "return_5yr":     None,
        "fund_category":  None,
        "aum_cr":         None,
        "expense_ratio":  None,
        "fund_age_years": None,
        "nav_history_len": 0,
    }

    # Fetch metadata (with retries)
    nav_history = []
    for attempt in range(1, 4):
        try:
            meta_resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=20)
            meta_resp.raise_for_status()
            payload = meta_resp.json()
            meta = payload.get("meta", {})
            result["fund_category"] = meta.get("scheme_category") or meta.get("scheme_type")
            nav_history = payload.get("data", [])
            break
        except Exception as exc:
            if attempt < 3:
                time.sleep(2 * attempt)
            else:
                print(f"  [fetch_nav] Metadata fetch failed for {scheme_code}: {exc}")
                return result

    if not nav_history:
        return result

    result["nav_history_len"] = len(nav_history)

    # Current NAV (newest entry)
    try:
        result["current_nav"] = float(nav_history[0]["nav"])
    except (ValueError, KeyError):
        pass

    # Oldest available date → fund age
    try:
        oldest_str = nav_history[-1]["date"]
        oldest = date(int(oldest_str[6:]), int(oldest_str[3:5]), int(oldest_str[:2]))
        result["fund_age_years"] = round((date.today() - oldest).days / 365, 1)
    except Exception:
        pass

    nav_now = result["current_nav"]
    nav_1y  = _find_nav_n_days_ago(nav_history, DAYS_1YR)
    nav_3y  = _find_nav_n_days_ago(nav_history, DAYS_3YR)
    nav_5y  = _find_nav_n_days_ago(nav_history, DAYS_5YR)

    result["return_1yr"] = _compute_return(nav_1y, nav_now)
    result["return_3yr"] = _compute_cagr(nav_3y, nav_now, 3)
    result["return_5yr"] = _compute_cagr(nav_5y, nav_now, 5)

    return result


# ── batch enrichment ──────────────────────────────────────────────────────────

def enrich_holdings_with_returns(holdings: list[dict]) -> list[dict]:
    """
    For each holding, resolve scheme code and fetch return data.
    Mutates each dict in-place and returns the list.
    """
    cache = _load_scheme_cache()
    enriched: list[dict] = []

    for i, h in enumerate(holdings):
        fund_name = h["fund_name"]
        print(f"\n[fetch_nav] [{i+1}/{len(holdings)}] {fund_name}")

        code = resolve_scheme_code(fund_name, cache)
        if not code:
            print(f"  ⚠ Could not resolve scheme code — skipping returns")
            h.update({
                "scheme_code": None, "current_nav": None,
                "return_1yr": None, "return_3yr": None, "return_5yr": None,
                "fund_category": None, "fund_age_years": None,
            })
            enriched.append(h)
            continue

        returns = fetch_fund_returns(code)
        h.update(returns)
        print(
            f"  ✓ code={code} | NAV={returns['current_nav']} | "
            f"1yr={returns['return_1yr']}% | 3yr={returns['return_3yr']}% | "
            f"5yr={returns['return_5yr']}% | cat={returns['fund_category']}"
        )
        enriched.append(h)
        time.sleep(0.3)   # gentle rate limiting

    _save_scheme_cache(cache)
    print(f"\n[fetch_nav] Done. Scheme code cache saved → {_SCHEME_CODES_FILE}")
    return enriched


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.parse_cas import parse_cas
    from config import CAS_PDF_PATH, CAS_PASSWORD

    holdings = parse_cas(CAS_PDF_PATH, CAS_PASSWORD)
    enriched = enrich_holdings_with_returns(holdings)
    # Print without full transaction history to keep it readable
    for h in enriched:
        h.pop("transactions", None)
    print(json.dumps(enriched, indent=2, default=str))
