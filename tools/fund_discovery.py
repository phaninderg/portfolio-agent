"""
Dynamic fund discovery from mfapi.in.

Fetches the master scheme list, filters for Direct Growth plans,
categorises into segments via regex, applies quality filters (AMC tier,
cap per segment), and caches the result for fast subsequent runs.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import MFAPI_BASE

# ── Paths ────────────────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent.parent / "data"
_CACHE_FILE = _CACHE_DIR / "fund_universe_cache.json"


# ── AMC priority tiers (used to cap candidates per segment) ──────────────────

TIER1_AMCS = (
    "hdfc", "icici prudential", "sbi", "kotak", "axis",
    "nippon india", "mirae asset", "dsp", "franklin",
    "parag parikh", "ppfas", "uti", "aditya birla",
)

TIER2_AMCS = (
    "quant", "canara robeco", "motilal oswal", "invesco",
    "tata", "sundaram", "pgim", "edelweiss", "mahindra",
    "bandhan", "baroda bnp", "hsbc", "union", "lic",
    "groww", "navi", "360 one", "samco", "helios",
    "itl", "jm financial", "quantum", "whiteoak",
)


def _amc_tier(scheme_name: str) -> int:
    """Return 0 for tier-1, 1 for tier-2, 2 for others."""
    name_lower = scheme_name.lower()
    for amc in TIER1_AMCS:
        if amc in name_lower:
            return 0
    for amc in TIER2_AMCS:
        if amc in name_lower:
            return 1
    return 2


# ── Segment categorisation via regex ─────────────────────────────────────────
# Order matters: more specific patterns first to avoid mis-categorisation.
# E.g. "ELSS" before "large_cap" since ELSS funds can mention cap sizes.

_SEGMENT_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("elss", [
        re.compile(r"\belss\b", re.I),
        re.compile(r"tax\s*sav", re.I),
        re.compile(r"tax\s*gain", re.I),
    ]),
    ("gold", [
        re.compile(r"\bgold\b", re.I),
    ]),
    ("silver", [
        re.compile(r"\bsilver\b", re.I),
    ]),
    ("reit", [
        re.compile(r"\breit\b", re.I),
        re.compile(r"\binvit\b", re.I),
        re.compile(r"real\s*estate", re.I),
        re.compile(r"infrastructure\s*trust", re.I),
    ]),
    # Index BEFORE cap-based segments (many index fund names contain "midcap"/"smallcap")
    ("index", [
        re.compile(r"index\s*fund", re.I),
        re.compile(r"nifty\s*\d+\s*index", re.I),
        re.compile(r"sensex\s*index", re.I),
        re.compile(r"index\s*-?\s*direct", re.I),
        re.compile(r"\bindex\b.*\bgrowth\b", re.I),
    ]),
    ("small_cap", [
        re.compile(r"small\s*cap", re.I),
        re.compile(r"smallcap", re.I),
    ]),
    ("mid_cap", [
        re.compile(r"mid\s*cap", re.I),
        re.compile(r"midcap", re.I),
    ]),
    ("large_cap", [
        re.compile(r"large\s*cap", re.I),
        re.compile(r"largecap", re.I),
        re.compile(r"bluechip", re.I),
        re.compile(r"blue\s*chip", re.I),
    ]),
    ("flexi_cap", [
        re.compile(r"flexi\s*cap", re.I),
        re.compile(r"flexicap", re.I),
        re.compile(r"multi\s*cap", re.I),
        re.compile(r"multicap", re.I),
    ]),
    ("international", [
        re.compile(r"\bnasdaq\b", re.I),
        re.compile(r"s\s*&?\s*p\s*500", re.I),
        re.compile(r"\binternational\b", re.I),
        re.compile(r"\bglobal\b", re.I),
        re.compile(r"\bus\s*equity\b", re.I),
        re.compile(r"\bus\s*total\b", re.I),
        re.compile(r"hang\s*seng", re.I),
        re.compile(r"greater\s*china", re.I),
    ]),
    ("hybrid", [
        re.compile(r"aggressive\s*hybrid", re.I),
        re.compile(r"balanced\s*advantage", re.I),
        re.compile(r"equity\s*(&|and)\s*debt", re.I),
        re.compile(r"equity\s*hybrid", re.I),
        re.compile(r"dynamic\s*asset\s*alloc", re.I),
        re.compile(r"multi\s*asset\s*alloc", re.I),
    ]),
    ("debt", [
        re.compile(r"short\s*term\s*(debt|bond)", re.I),
        re.compile(r"corporate\s*bond", re.I),
        re.compile(r"banking\s*(&|and)\s*psu", re.I),
        re.compile(r"\bliquid\b", re.I),
        re.compile(r"ultra\s*short", re.I),
        re.compile(r"money\s*market", re.I),
        re.compile(r"\bovernight\b", re.I),
        re.compile(r"\bgilt\b", re.I),
        re.compile(r"dynamic\s*bond", re.I),
        re.compile(r"medium\s*(duration|term)", re.I),
        re.compile(r"long\s*duration", re.I),
        re.compile(r"credit\s*risk", re.I),
        re.compile(r"\bfloater\b", re.I),
        re.compile(r"conservative\s*hybrid", re.I),
        re.compile(r"low\s*duration", re.I),
    ]),
]


def categorize_fund(scheme_name: str) -> str | None:
    """Return segment key for a fund name, or None if uncategorised."""
    for segment, patterns in _SEGMENT_PATTERNS:
        for pat in patterns:
            if pat.search(scheme_name):
                return segment
    return None


# ── Direct Growth filter ─────────────────────────────────────────────────────

_EXCLUDE_PATTERNS = [
    re.compile(r"\bdividend\b", re.I),
    re.compile(r"\bidcw\b", re.I),
    re.compile(r"\bbonus\b", re.I),
    re.compile(r"\bregular\b", re.I),        # exclude Regular plans
    re.compile(r"\binstitutional\b", re.I),
]

_DIRECT_PATTERN = re.compile(r"\bdirect\b", re.I)
_GROWTH_PATTERN = re.compile(r"\bgrowth\b", re.I)


def _is_direct_growth(scheme_name: str) -> bool:
    """Check if scheme is a Direct Growth plan."""
    if not _DIRECT_PATTERN.search(scheme_name):
        return False
    if not _GROWTH_PATTERN.search(scheme_name):
        return False
    for pat in _EXCLUDE_PATTERNS:
        if pat.search(scheme_name):
            return False
    return True


# ── Master list fetch ────────────────────────────────────────────────────────

def fetch_master_list() -> list[dict]:
    """
    Fetch all scheme codes and names from mfapi.in/mf.
    Returns list of {"schemeCode": int, "schemeName": str}.
    Single HTTP GET, ~1MB response.
    """
    url = MFAPI_BASE
    print("[discovery] Fetching master scheme list from mfapi.in...", end=" ", flush=True)
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            print(f"done ({len(data):,} schemes)")
            return data
        except Exception as exc:
            if attempt < 3:
                print(f"retry {attempt}...", end=" ", flush=True)
                time.sleep(2 * attempt)
            else:
                print(f"FAILED: {exc}")
                raise RuntimeError(f"Could not fetch master list from mfapi.in: {exc}") from exc


# ── Discovery pipeline ───────────────────────────────────────────────────────

def _build_universe(
    max_per_segment: int = 15,
    cache_ttl_days: int = 7,
) -> dict:
    """
    Fetch → filter → categorise → quality-cap.
    Returns cache-ready dict with 'segments', 'stats', 'cached_at'.
    """
    master = fetch_master_list()

    # Filter for Direct Growth
    direct_growth = [s for s in master if _is_direct_growth(s.get("schemeName", ""))]
    print(f"[discovery] Direct Growth filter: {len(master):,} → {len(direct_growth):,} schemes")

    # Categorise into segments
    segments: dict[str, list[dict]] = {}
    uncategorised = 0
    for scheme in direct_growth:
        name = scheme.get("schemeName", "")
        seg = categorize_fund(name)
        if seg is None:
            uncategorised += 1
            continue
        entry = {
            "schemeCode": str(scheme["schemeCode"]),
            "schemeName": name,
            "segment": seg,
        }
        segments.setdefault(seg, []).append(entry)

    print(f"[discovery] Categorised into segments ({uncategorised} uncategorised):")
    for seg, funds in sorted(segments.items()):
        print(f"  {seg:<16} {len(funds):>4} funds")

    # Quality filter: AMC tiering + cap per segment
    filtered: dict[str, list[dict]] = {}
    for seg, funds in segments.items():
        # Sort by AMC tier (tier-1 first)
        ranked = sorted(funds, key=lambda f: _amc_tier(f["schemeName"]))
        filtered[seg] = ranked[:max_per_segment]

    total_filtered = sum(len(v) for v in filtered.values())
    print(f"[discovery] After quality filter (max {max_per_segment}/segment): {total_filtered} candidates")

    return {
        "cached_at": datetime.now().isoformat(),
        "ttl_days": cache_ttl_days,
        "version": 1,
        "segments": {seg: funds for seg, funds in filtered.items()},
        "stats": {
            "total_master": len(master),
            "total_direct_growth": len(direct_growth),
            "total_categorised": total_filtered,
            "per_segment": {seg: len(funds) for seg, funds in filtered.items()},
        },
    }


# ── Cache layer ──────────────────────────────────────────────────────────────

def _load_cache(ttl_days: int) -> dict | None:
    """Load cached universe if valid. Returns None if stale or missing."""
    if not _CACHE_FILE.exists():
        return None
    try:
        with open(_CACHE_FILE) as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache["cached_at"])
        if datetime.now() - cached_at > timedelta(days=ttl_days):
            print(f"[discovery] Cache expired (>{ttl_days} days old)")
            return None
        age_hours = (datetime.now() - cached_at).total_seconds() / 3600
        print(f"[discovery] Using cached universe ({age_hours:.0f}h old, "
              f"{cache['stats']['total_categorised']} funds)")
        return cache
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
        print(f"[discovery] Cache load failed: {exc}")
        return None


def _save_cache(cache_data: dict) -> None:
    """Save universe to disk."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump(cache_data, f, indent=2)
    print(f"[discovery] Cache saved → {_CACHE_FILE}")


# ── Public API ───────────────────────────────────────────────────────────────

def discover_fund_universe(
    segments_needed: set[str] | None = None,
    force_refresh: bool = False,
    max_per_segment: int = 15,
    cache_ttl_days: int = 7,
) -> dict[str, list[dict]]:
    """
    Main entry point. Returns categorised fund candidates per segment.
    Uses cache if valid; fetches fresh from mfapi.in otherwise.

    Returns: {segment_key: [{"schemeCode": str, "schemeName": str, "segment": str}, ...]}
    """
    cache = None
    if not force_refresh:
        cache = _load_cache(cache_ttl_days)

    if cache is None:
        print("[discovery] ── Building dynamic fund universe from mfapi.in ──")
        cache = _build_universe(max_per_segment=max_per_segment, cache_ttl_days=cache_ttl_days)
        _save_cache(cache)

    all_segments = cache.get("segments", {})

    # Filter to needed segments
    if segments_needed:
        return {seg: funds for seg, funds in all_segments.items() if seg in segments_needed}
    return all_segments
