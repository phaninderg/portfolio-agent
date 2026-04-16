"""
Research Agent — Tool: fetch_nav.py
Resolves fund names → scheme codes and fetches 1yr / 3yr / 5yr / 10yr / 15yr
returns from mfapi.in historical NAV data.
"""

from __future__ import annotations
import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from config import MFAPI_BASE, MFAPI_SEARCH

# Project root
_ROOT = Path(__file__).parent.parent
_SCHEME_CODES_FILE = _ROOT / "scheme_codes.json"

# Approx trading days per year (used to step back in NAV array)
DAYS_1YR  = 365
DAYS_3YR  = 365 * 3
DAYS_5YR  = 365 * 5
DAYS_10YR = 365 * 10
DAYS_15YR = 365 * 15


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

def search_scheme_code(fund_name: str, top_n: int = 10) -> list[dict]:
    """Search mfapi.in for a fund by name. Returns list of {schemeCode, schemeName}."""
    results: list[dict] = []

    # Try full name first (better matches when AMC name is included)
    try:
        resp = requests.get(MFAPI_SEARCH, params={"q": fund_name.strip()}, timeout=10)
        resp.raise_for_status()
        results = resp.json()
    except Exception:
        pass

    # If too few results, retry with stripped AMC prefix
    if len(results) < 3:
        query = fund_name.strip()
        for prefix in ("Mirae Asset", "ICICI Prudential", "HDFC", "SBI", "Axis",
                       "Kotak", "Nippon India", "DSP", "Franklin", "Invesco",
                       "Parag Parikh", "Quant", "UTI", "Aditya Birla Sun Life",
                       "NIPPON INDIA", "TATA"):
            query = query.replace(prefix, "").strip()
        try:
            resp = requests.get(MFAPI_SEARCH, params={"q": query}, timeout=10)
            resp.raise_for_status()
            extra = resp.json()
            # Merge, avoiding duplicates
            seen = {r["schemeCode"] for r in results}
            for r in extra:
                if r["schemeCode"] not in seen:
                    results.append(r)
                    seen.add(r["schemeCode"])
        except Exception as exc:
            print(f"  [fetch_nav] Search failed for '{fund_name}': {exc}")

    return results[:top_n]


def _validate_scheme_nav(scheme_code: str, cas_nav: float) -> bool:
    """Check if mfapi NAV roughly matches the CAS transaction NAV."""
    try:
        resp = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return False
        mfapi_nav = float(data[0]["nav"])
        # Allow 20% tolerance (NAVs change daily, CAS date may differ)
        ratio = mfapi_nav / cas_nav if cas_nav > 0 else 0
        return 0.5 < ratio < 2.0
    except Exception:
        return False


def resolve_scheme_code(
    fund_name: str,
    cache: dict[str, str],
    cas_nav_hint: float | None = None,
) -> str | None:
    """
    Look up scheme code for a fund name.
    Uses cache first; falls back to mfapi.in search.
    When cas_nav_hint is provided, validates the scheme code by comparing
    mfapi NAV against the CAS transaction NAV to catch wrong mappings.
    """
    if fund_name in cache:
        code = cache[fund_name]
        # Validate cached code if we have a NAV hint
        if cas_nav_hint and not _validate_scheme_nav(code, cas_nav_hint):
            print(f"  [fetch_nav] ⚠ Cached code {code} for '{fund_name[:45]}' has NAV mismatch — re-resolving")
            del cache[fund_name]
        else:
            return code

    results = search_scheme_code(fund_name)
    if not results:
        return None

    # Pick exact name match first
    fund_lower = fund_name.lower()
    for r in results:
        if r.get("schemeName", "").lower() == fund_lower:
            code = str(r["schemeCode"])
            if cas_nav_hint and not _validate_scheme_nav(code, cas_nav_hint):
                continue
            cache[fund_name] = code
            return code

    # Try each result, validate NAV if hint available
    for r in results:
        code = str(r["schemeCode"])
        if cas_nav_hint:
            if _validate_scheme_nav(code, cas_nav_hint):
                cache[fund_name] = code
                print(f"  [fetch_nav] '{fund_name[:45]}' → '{r['schemeName'][:45]}' (NAV validated)")
                return code
        else:
            cache[fund_name] = code
            print(f"  [fetch_nav] '{fund_name[:45]}' → '{r['schemeName'][:45]}' (best guess)")
            return code

    print(f"  [fetch_nav] ⚠ No valid scheme code found for '{fund_name[:50]}'")
    return None


# ── NAV + returns ─────────────────────────────────────────────────────────────

def fetch_nav_history(scheme_code: str, retries: int = 3) -> list[dict]:
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
        except (KeyError, ValueError, IndexError):
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


from tools.xirr import compute_cagr as _compute_cagr


def fetch_fund_returns(scheme_code: str) -> dict:
    """
    Fetch NAV history and compute 1yr / 3yr / 5yr / 10yr / 15yr returns.
    Also extracts current NAV, fund category, AUM, expense ratio.
    Returns a dict with all fields (None if data unavailable).
    """
    result = {
        "scheme_code":    scheme_code,
        "current_nav":    None,
        "return_1yr":     None,
        "return_3yr":     None,
        "return_5yr":     None,
        "return_10yr":    None,
        "return_15yr":    None,
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
    except (KeyError, ValueError, IndexError):
        pass

    nav_now  = result["current_nav"]
    nav_1y   = _find_nav_n_days_ago(nav_history, DAYS_1YR)
    nav_3y   = _find_nav_n_days_ago(nav_history, DAYS_3YR)
    nav_5y   = _find_nav_n_days_ago(nav_history, DAYS_5YR)
    nav_10y  = _find_nav_n_days_ago(nav_history, DAYS_10YR)
    nav_15y  = _find_nav_n_days_ago(nav_history, DAYS_15YR)

    result["return_1yr"]  = _compute_return(nav_1y, nav_now)
    result["return_3yr"]  = _compute_cagr(nav_3y, nav_now, 3)
    result["return_5yr"]  = _compute_cagr(nav_5y, nav_now, 5)
    result["return_10yr"] = _compute_cagr(nav_10y, nav_now, 10)
    result["return_15yr"] = _compute_cagr(nav_15y, nav_now, 15)

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

        # Extract a NAV hint from the most recent CAS transaction for validation
        cas_nav_hint = None
        for txn in reversed(h.get("transactions", [])):
            units = float(txn.get("units", 0))
            amount = float(txn.get("amount", 0))
            if units > 0 and amount > 0:
                cas_nav_hint = amount / units
                break

        code = resolve_scheme_code(fund_name, cache, cas_nav_hint=cas_nav_hint)
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
        parts = [
            f"  ✓ code={code} | NAV={returns['current_nav']}",
            f"1yr={returns['return_1yr']}%",
            f"3yr={returns['return_3yr']}%",
            f"5yr={returns['return_5yr']}%",
        ]
        if returns.get("return_10yr") is not None:
            parts.append(f"10yr={returns['return_10yr']}%")
        if returns.get("return_15yr") is not None:
            parts.append(f"15yr={returns['return_15yr']}%")
        parts.append(f"cat={returns['fund_category']}")
        print(" | ".join(parts))
        enriched.append(h)
        time.sleep(0.3)   # gentle rate limiting

    _save_scheme_cache(cache)
    print(f"\n[fetch_nav] Done. Scheme code cache saved → {_SCHEME_CODES_FILE}")
    return enriched
