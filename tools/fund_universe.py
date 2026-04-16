"""
Fund universe for investor recommendations.

Discovers Direct Growth funds dynamically from mfapi.in master list,
categorises into segments, fetches live returns including 10yr/15yr CAGR.

At runtime, `enrich_fund_universe()` fetches LIVE returns from mfapi.in
and `pick_funds_live()` ranks candidates by actual current performance.
"""

from __future__ import annotations
import time


# ── Segment definitions ──────────────────────────────────────────────────────

SEGMENTS = {
    "large_cap": {
        "label": "Large Cap Equity",
        "description": "Top 100 companies by market cap. Stable, lower volatility.",
        "benchmark": "Nifty 50",
    },
    "mid_cap": {
        "label": "Mid Cap Equity",
        "description": "101st–250th companies. Higher growth potential, moderate risk.",
        "benchmark": "Nifty Midcap 150",
    },
    "small_cap": {
        "label": "Small Cap Equity",
        "description": "Below 250th. High growth, high volatility. 7+ year horizon.",
        "benchmark": "Nifty Smallcap 250",
    },
    "flexi_cap": {
        "label": "Flexi Cap Equity",
        "description": "Fund manager picks across market caps. Diversified by design.",
        "benchmark": "Nifty 500",
    },
    "index": {
        "label": "Index Fund",
        "description": "Passive, low cost. Tracks a benchmark index exactly.",
        "benchmark": "Nifty 50 / Nifty Next 50",
    },
    "elss": {
        "label": "ELSS (Tax Saver)",
        "description": "Equity fund with 3-year lock-in. Section 80C tax benefit.",
        "benchmark": "Nifty 500",
    },
    "gold": {
        "label": "Gold",
        "description": "Hedge against inflation and equity downturns. No storage hassle.",
        "benchmark": "Domestic Gold Price",
    },
    "silver": {
        "label": "Silver",
        "description": "Industrial + precious metal. More volatile than gold.",
        "benchmark": "Domestic Silver Price",
    },
    "international": {
        "label": "International Equity",
        "description": "US/global market exposure. Geographic diversification.",
        "benchmark": "S&P 500 / MSCI World",
    },
    "debt": {
        "label": "Debt / Fixed Income",
        "description": "Low-risk, stable returns. Capital preservation.",
        "benchmark": "CRISIL Short Term Bond Index",
    },
    "hybrid": {
        "label": "Aggressive Hybrid",
        "description": "65-80% equity + 20-35% debt. Built-in rebalancing.",
        "benchmark": "CRISIL Hybrid 35+65 Aggressive",
    },
    "reit": {
        "label": "Real Estate (REITs / InvITs)",
        "description": "Listed real estate / infrastructure trusts. Regular income.",
        "benchmark": "Nifty REITs & InvITs",
    },
}


# ── Allocation templates ─────────────────────────────────────────────────────
# Percentages by segment for each risk profile.
# These are starting points — the LLM personalises based on age/goal/horizon.

ALLOCATION_TEMPLATES: dict[str, dict[str, float]] = {
    "Conservative": {
        "large_cap":      15.0,
        "index":          20.0,
        "flexi_cap":      10.0,
        "mid_cap":         5.0,
        "small_cap":       0.0,
        "gold":           15.0,
        "silver":          0.0,
        "debt":           20.0,
        "hybrid":         10.0,
        "international":   5.0,
        "reit":            0.0,
        "elss":            0.0,
    },
    "Moderate": {
        "large_cap":      10.0,
        "index":          15.0,
        "flexi_cap":      15.0,
        "mid_cap":        15.0,
        "small_cap":       5.0,
        "gold":           10.0,
        "silver":          0.0,
        "debt":           10.0,
        "hybrid":          5.0,
        "international":  10.0,
        "reit":            5.0,
        "elss":            0.0,
    },
    "Aggressive": {
        "large_cap":       5.0,
        "index":          10.0,
        "flexi_cap":      15.0,
        "mid_cap":        20.0,
        "small_cap":      15.0,
        "gold":            5.0,
        "silver":          5.0,
        "debt":            5.0,
        "hybrid":          0.0,
        "international":  10.0,
        "reit":            5.0,
        "elss":            0.0,
    },
}


# ── Age-based adjustments ────────────────────────────────────────────────────

def adjust_allocation_for_age(
    base: dict[str, float], age: int, horizon: int
) -> dict[str, float]:
    """
    Fine-tune allocation based on age and investment horizon.
    Rule of thumb: (100 - age)% in equity, rest in safer assets.
    Horizon < 5 years → shift more to debt/gold.
    """
    alloc = dict(base)

    # Equity segments
    equity_segs = {"large_cap", "mid_cap", "small_cap", "flexi_cap", "index", "elss"}
    safe_segs   = {"debt", "gold", "hybrid"}

    # Short horizon: move 10% from equity to debt
    if horizon <= 3:
        for seg in ("small_cap", "mid_cap"):
            shift = min(alloc.get(seg, 0), 5.0)
            alloc[seg] = alloc.get(seg, 0) - shift
            alloc["debt"] = alloc.get("debt", 0) + shift

    # Very young (< 25): can take more risk — boost small/mid cap
    if age < 25 and horizon >= 10:
        shift = 5.0
        alloc["small_cap"] = alloc.get("small_cap", 0) + shift
        alloc["debt"] = max(0, alloc.get("debt", 0) - shift)

    # Nearing retirement (55+): shift equity to debt/gold
    if age >= 55:
        for seg in ("small_cap", "mid_cap", "reit", "silver"):
            shift = alloc.get(seg, 0)
            alloc[seg] = 0
            alloc["debt"] = alloc.get("debt", 0) + shift * 0.6
            alloc["gold"] = alloc.get("gold", 0) + shift * 0.4

    # Normalise to 100%
    total = sum(alloc.values())
    if total > 0 and abs(total - 100) > 0.1:
        factor = 100.0 / total
        alloc = {k: round(v * factor, 1) for k, v in alloc.items()}

    # Remove zero allocations
    alloc = {k: v for k, v in alloc.items() if v > 0}

    return alloc


def get_allocation(risk: str, age: int, horizon: int) -> dict[str, float]:
    """Get the adjusted allocation for a given risk profile, age, and horizon."""
    base = ALLOCATION_TEMPLATES.get(risk, ALLOCATION_TEMPLATES["Moderate"])
    return adjust_allocation_for_age(base, age, horizon)


# ══════════════════════════════════════════════════════════════════════════════
# LIVE DATA: fetch real returns from mfapi.in and rank funds dynamically
# ══════════════════════════════════════════════════════════════════════════════

from config import FUND_DISCOVERY_MIN_TRACK_RECORD as _MIN_TRACK_RECORD_YRS


def _generate_why(fund: dict) -> str:
    """Generate a brief 'why' note for a dynamically discovered fund."""
    parts = []
    r5 = fund.get("live_return_5yr")
    r10 = fund.get("live_return_10yr")
    r15 = fund.get("live_return_15yr")
    age = fund.get("live_fund_age_years")

    if r15 is not None:
        parts.append(f"15yr CAGR of {r15}% — proven long-term compounder")
    elif r10 is not None:
        parts.append(f"10yr CAGR of {r10}% — decade-long track record")
    elif r5 is not None:
        parts.append(f"5yr CAGR of {r5}%")

    if age and age >= 10:
        parts.append(f"{age:.0f}+ years in market")

    cat = fund.get("live_fund_category")
    if cat:
        parts.append(cat)

    return ". ".join(parts) if parts else "Dynamically discovered from mfapi.in"


def enrich_fund_universe(segments_needed: set[str] | None = None) -> list[dict]:
    """
    Fetch LIVE NAV + returns from mfapi.in for fund candidates.

    Uses dynamic discovery (mfapi.in master list) to find Direct Growth funds
    across all segments. Funds without a scheme_code are skipped.

    Each fund dict includes:
      - live_return_1yr, live_return_3yr, live_return_5yr  (actual % from mfapi)
      - live_return_10yr, live_return_15yr                 (if fund is old enough)
      - live_nav, live_fund_category, live_fund_age_years
      - data_source: "live"

    Returns the enriched list.
    """
    from tools.fetch_nav import fetch_fund_returns
    from tools.fund_discovery import discover_fund_universe
    from config import (
        FUND_DISCOVERY_CACHE_TTL_DAYS,
        FUND_DISCOVERY_MAX_PER_SEGMENT,
    )

    # Step 1: Discover candidates dynamically (uses cache if available)
    candidates_by_segment = discover_fund_universe(
        segments_needed=segments_needed,
        max_per_segment=FUND_DISCOVERY_MAX_PER_SEGMENT,
        cache_ttl_days=FUND_DISCOVERY_CACHE_TTL_DAYS,
    )

    # Build flat candidate list
    candidates = []
    for seg, funds in candidates_by_segment.items():
        for f in funds:
            candidates.append({
                "fund_name": f["schemeName"],
                "scheme_code": str(f["schemeCode"]),
                "segment": f["segment"],
            })

    total = len(candidates)
    print(f"\n[fund_universe] Fetching live data for {total} funds from mfapi.in...")

    enriched: list[dict] = []
    for i, fund in enumerate(candidates):
        fund_copy = dict(fund)
        name = fund["fund_name"]
        code = fund.get("scheme_code")

        print(f"  [{i+1}/{total}] {name[:60]}...", end=" ", flush=True)

        if not code:
            print("⚠ no scheme_code — skipping")
            fund_copy["data_source"] = "static"
            enriched.append(fund_copy)
            continue

        returns = fetch_fund_returns(code)

        fund_copy["live_nav"]            = returns.get("current_nav")
        fund_copy["live_return_1yr"]     = returns.get("return_1yr")
        fund_copy["live_return_3yr"]     = returns.get("return_3yr")
        fund_copy["live_return_5yr"]     = returns.get("return_5yr")
        fund_copy["live_return_10yr"]    = returns.get("return_10yr")
        fund_copy["live_return_15yr"]    = returns.get("return_15yr")
        fund_copy["live_fund_category"]  = returns.get("fund_category")
        fund_copy["live_fund_age_years"] = returns.get("fund_age_years")
        fund_copy["data_source"]         = "live"

        # Generate 'why' for dynamically discovered funds
        if "why" not in fund_copy:
            fund_copy["why"] = _generate_why(fund_copy)

        r1  = fund_copy["live_return_1yr"]
        r3  = fund_copy["live_return_3yr"]
        r5  = fund_copy["live_return_5yr"]
        r10 = fund_copy["live_return_10yr"]
        r15 = fund_copy["live_return_15yr"]

        parts = [f"✓ 1yr={r1}%", f"3yr={r3}%", f"5yr={r5}%"]
        if r10 is not None:
            parts.append(f"10yr={r10}%")
        if r15 is not None:
            parts.append(f"15yr={r15}%")
        print(" | ".join(parts))

        enriched.append(fund_copy)
        time.sleep(0.3)  # gentle rate limit

    # Filter out funds below minimum track record
    before = len(enriched)
    enriched = [
        f for f in enriched
        if (f.get("live_fund_age_years") or 0) >= _MIN_TRACK_RECORD_YRS
    ]
    dropped = before - len(enriched)
    if dropped:
        print(f"[fund_universe] Dropped {dropped} funds with <{_MIN_TRACK_RECORD_YRS}yr track record")

    live_count = sum(1 for f in enriched if f.get("data_source") == "live")
    print(f"[fund_universe] Done. {live_count}/{len(enriched)} funds enriched with live data.\n")
    return enriched


def _rank_score(fund: dict) -> float:
    """
    Composite score for ranking funds within a segment.

    Weights when all periods are available:
      1yr: 15%,  3yr: 30%,  5yr: 25%,  10yr: 18%,  15yr: 12%

    Gracefully degrades when longer periods are missing by
    redistributing their weights proportionally among available periods.
    """
    def _val(key: str) -> float | None:
        v = fund.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    # Gather available periods with their base weights
    periods = [
        (_val("live_return_1yr"),  0.15),
        (_val("live_return_3yr"),  0.30),
        (_val("live_return_5yr"),  0.25),
        (_val("live_return_10yr"), 0.18),
        (_val("live_return_15yr"), 0.12),
    ]

    available = [(val, wt) for val, wt in periods if val is not None]
    if not available:
        return 0.0

    # Redistribute weights proportionally among available periods
    total_wt = sum(wt for _, wt in available)
    score = sum(val * (wt / total_wt) for val, wt in available)
    return score


def pick_funds_live(
    allocation: dict[str, float],
    budget: int,
    enriched_universe: list[dict],
) -> list[dict]:
    """
    Select the BEST fund per segment using live return data.
    Ranks candidates by composite score (1yr/3yr/5yr/10yr/15yr weighted)
    and picks the top performer.

    Returns a list of recommendation dicts with live data attached.
    """
    recommendations = []

    for segment, pct in sorted(allocation.items(), key=lambda x: -x[1]):
        if pct <= 0:
            continue

        candidates = [f for f in enriched_universe if f["segment"] == segment]
        if not candidates:
            continue

        # Rank by composite score (highest first)
        ranked = sorted(candidates, key=_rank_score, reverse=True)
        best = ranked[0]

        sip_amount = round(budget * pct / 100)
        min_sip = best.get("min_sip", 500)
        if sip_amount < min_sip:
            sip_amount = min_sip

        return_1yr  = best.get("live_return_1yr")
        return_3yr  = best.get("live_return_3yr")
        return_5yr  = best.get("live_return_5yr")
        return_10yr = best.get("live_return_10yr")
        return_15yr = best.get("live_return_15yr")

        # Build comparison note showing why this fund was picked
        runner_up_note = ""
        if len(ranked) > 1:
            ru = ranked[1]
            ru_score = _rank_score(ru)
            best_score = _rank_score(best)
            if ru_score > 0:
                runner_up_note = (
                    f"Picked over {ru['fund_name']} "
                    f"(score {best_score:.1f} vs {ru_score:.1f})"
                )

        recommendations.append({
            "fund_name":          best["fund_name"],
            "segment":            segment,
            "segment_label":      SEGMENTS[segment]["label"],
            "amc":                best.get("amc", ""),
            "allocation_pct":     pct,
            "sip_amount":         sip_amount,
            "live_return_1yr":    return_1yr,
            "live_return_3yr":    return_3yr,
            "live_return_5yr":    return_5yr,
            "live_return_10yr":   return_10yr,
            "live_return_15yr":   return_15yr,
            "live_nav":           best.get("live_nav"),
            "live_fund_category": best.get("live_fund_category"),
            "live_fund_age_years": best.get("live_fund_age_years"),
            "data_source":        best.get("data_source", "static"),
            "expense_ratio":      best.get("expense_ratio"),
            "benchmark":          SEGMENTS[segment]["benchmark"],
            "segment_description": SEGMENTS[segment]["description"],
            "why":                best.get("why", _generate_why(best)),
            "rank_score":         round(_rank_score(best), 2),
            "runner_up":          runner_up_note,
            "alternatives":       [f["fund_name"] for f in ranked[1:4]],
        })

    return recommendations
