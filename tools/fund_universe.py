"""
Curated fund universe for new investor recommendations.

Each segment contains top-rated Direct Growth funds across AMCs.
Static data (fund names, segment tags, reasons) is used as a SEED.
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


# ── Curated fund list ────────────────────────────────────────────────────────
# Each fund: name, segment, approx_3yr_cagr, approx_5yr_cagr, why

FUND_UNIVERSE: list[dict] = [
    # ── Large Cap ────────────────────────────────────────────────
    {
        "fund_name": "Mirae Asset Large Cap Fund - Direct Growth",
        "scheme_code": "118825",
        "segment": "large_cap",
        "amc": "Mirae Asset",
        "approx_3yr_cagr": 16.5,
        "approx_5yr_cagr": 15.2,
        "expense_ratio": 0.53,
        "min_sip": 500,
        "why": "Consistently beats Nifty 50. Clean portfolio, low churn. Top AUM in category.",
    },
    {
        "fund_name": "HDFC Large Cap Fund - Direct Growth",
        "scheme_code": "119018",
        "segment": "large_cap",
        "amc": "HDFC",
        "approx_3yr_cagr": 18.1,
        "approx_5yr_cagr": 14.8,
        "why": "Value-oriented large cap. Strong in bull runs. One of India's oldest large cap funds.",
    },
    {
        "fund_name": "Canara Robeco Large Cap Fund - Direct Growth",
        "scheme_code": "118269",
        "segment": "large_cap",
        "amc": "Canara Robeco",
        "approx_3yr_cagr": 15.8,
        "approx_5yr_cagr": 16.1,
        "why": "Under-the-radar outperformer. Consistent alpha, low drawdowns.",
    },

    # ── Mid Cap ──────────────────────────────────────────────────
    {
        "fund_name": "HDFC Mid Cap Fund - Direct Growth",
        "scheme_code": "118989",
        "segment": "mid_cap",
        "amc": "HDFC",
        "approx_3yr_cagr": 22.5,
        "approx_5yr_cagr": 19.8,
        "why": "Largest mid-cap fund by AUM. Proven 10+ year track record across cycles.",
    },
    {
        "fund_name": "Kotak Midcap Fund - Direct Growth",
        "scheme_code": "119775",
        "segment": "mid_cap",
        "amc": "Kotak",
        "approx_3yr_cagr": 21.0,
        "approx_5yr_cagr": 20.5,
        "why": "Consistent compounder. Less volatile than peers. Quality-focused portfolio.",
    },
    {
        "fund_name": "Motilal Oswal Midcap Fund - Direct Growth",
        "scheme_code": "127042",
        "segment": "mid_cap",
        "amc": "Motilal Oswal",
        "approx_3yr_cagr": 28.0,
        "approx_5yr_cagr": 23.5,
        "why": "Concentrated high-conviction bets. Aggressive but delivers strong alpha.",
    },

    # ── Small Cap ────────────────────────────────────────────────
    {
        "fund_name": "Nippon India Small Cap Fund - Direct Growth",
        "scheme_code": "118778",
        "segment": "small_cap",
        "amc": "Nippon India",
        "approx_3yr_cagr": 25.0,
        "approx_5yr_cagr": 28.5,
        "why": "Largest small cap fund. Diversified across 150+ stocks. Strong long-term alpha.",
    },
    {
        "fund_name": "Quant Small Cap Fund - Direct Growth",
        "scheme_code": "120828",
        "segment": "small_cap",
        "amc": "Quant",
        "approx_3yr_cagr": 22.0,
        "approx_5yr_cagr": 35.0,
        "why": "Quant-driven, momentum-based. Highest returns in category over 5 years.",
    },
    {
        "fund_name": "Canara Robeco Small Cap Fund - Direct Growth",
        "scheme_code": "146130",
        "segment": "small_cap",
        "amc": "Canara Robeco",
        "approx_3yr_cagr": 20.5,
        "approx_5yr_cagr": 24.0,
        "why": "Quality-focused small cap. Lower volatility than peers. Newer but consistent.",
    },

    # ── Flexi Cap ────────────────────────────────────────────────
    {
        "fund_name": "Parag Parikh Flexi Cap Fund - Direct Growth",
        "scheme_code": "122639",
        "segment": "flexi_cap",
        "amc": "PPFAS",
        "approx_3yr_cagr": 18.5,
        "approx_5yr_cagr": 19.0,
        "why": "Unique blend of Indian + international stocks. Built-in geographic diversification.",
    },
    {
        "fund_name": "HDFC Flexi Cap Fund - Direct Growth",
        "scheme_code": "118955",
        "segment": "flexi_cap",
        "amc": "HDFC",
        "approx_3yr_cagr": 20.5,
        "approx_5yr_cagr": 17.5,
        "why": "Value-oriented flex. Strong recovery from 2020 dip. Large AUM, stable fund house.",
    },

    # ── Index Funds ──────────────────────────────────────────────
    {
        "fund_name": "UTI Nifty 50 Index Fund - Direct Growth",
        "scheme_code": "120716",
        "segment": "index",
        "amc": "UTI",
        "approx_3yr_cagr": 14.5,
        "approx_5yr_cagr": 13.8,
        "expense_ratio": 0.18,
        "min_sip": 500,
        "why": "Lowest tracking error among Nifty 50 index funds. Rock-bottom expense ratio.",
    },
    {
        "fund_name": "Motilal Oswal Nifty Midcap 150 Index Fund - Direct Growth",
        "scheme_code": "147622",
        "segment": "index",
        "amc": "Motilal Oswal",
        "approx_3yr_cagr": 20.0,
        "approx_5yr_cagr": 18.5,
        "expense_ratio": 0.30,
        "min_sip": 500,
        "why": "Low-cost midcap exposure. Good alternative to active mid-cap funds.",
    },
    {
        "fund_name": "Motilal Oswal Nifty Next 50 Index Fund - Direct Growth",
        "scheme_code": "147796",
        "segment": "index",
        "amc": "Motilal Oswal",
        "approx_3yr_cagr": 18.0,
        "approx_5yr_cagr": 14.0,
        "expense_ratio": 0.25,
        "min_sip": 500,
        "why": "Next 50 blue-chips (51-100). Bridge between large and mid cap. Low cost.",
    },

    # ── ELSS ─────────────────────────────────────────────────────
    {
        "fund_name": "Mirae Asset ELSS Tax Saver Fund - Direct Growth",
        "scheme_code": "135781",
        "segment": "elss",
        "amc": "Mirae Asset",
        "approx_3yr_cagr": 17.0,
        "approx_5yr_cagr": 16.5,
        "why": "Best ELSS by consistency. Tax saving + wealth creation in one fund.",
    },
    {
        "fund_name": "Quant ELSS Tax Saver Fund - Direct Growth",
        "scheme_code": "120847",
        "segment": "elss",
        "amc": "Quant",
        "approx_3yr_cagr": 20.0,
        "approx_5yr_cagr": 28.0,
        "why": "Highest returns in ELSS category. Momentum-driven strategy.",
    },

    # ── Gold ─────────────────────────────────────────────────────
    {
        "fund_name": "SBI Gold Fund - Direct Growth",
        "scheme_code": "119788",
        "segment": "gold",
        "amc": "SBI",
        "approx_3yr_cagr": 15.0,
        "approx_5yr_cagr": 13.5,
        "why": "Largest gold fund by AUM. Tracks domestic gold prices. No demat needed.",
    },
    {
        "fund_name": "HDFC Gold ETF Fund of Fund - Direct Growth",
        "scheme_code": "119132",
        "segment": "gold",
        "amc": "HDFC",
        "approx_3yr_cagr": 14.8,
        "approx_5yr_cagr": 13.2,
        "why": "Reliable gold exposure. Invests in gold ETFs. Low tracking error.",
    },
    {
        "fund_name": "Nippon India Gold Savings Fund - Direct Growth",
        "scheme_code": "118663",
        "segment": "gold",
        "amc": "Nippon India",
        "approx_3yr_cagr": 14.5,
        "approx_5yr_cagr": 13.0,
        "why": "Fund of fund investing in Nippon India Gold ETF. Easy SIP in gold.",
    },

    # ── Silver ───────────────────────────────────────────────────
    {
        "fund_name": "ICICI Prudential Silver ETF Fund of Fund - Direct Growth",
        "scheme_code": "149775",
        "segment": "silver",
        "amc": "ICICI Prudential",
        "approx_3yr_cagr": 12.0,
        "approx_5yr_cagr": None,  # newer fund
        "why": "First silver FoF in India. SIP into silver without demat. Newer but from top AMC.",
    },
    {
        "fund_name": "Nippon India Silver ETF Fund of Fund - Direct Growth",
        "scheme_code": "149760",
        "segment": "silver",
        "amc": "Nippon India",
        "approx_3yr_cagr": 11.5,
        "approx_5yr_cagr": None,
        "why": "Silver exposure via ETF route. Growing AUM. Alternative to physical silver.",
    },

    # ── International ────────────────────────────────────────────
    {
        "fund_name": "Motilal Oswal Nasdaq 100 Fund of Fund - Direct Growth",
        "scheme_code": "145552",
        "segment": "international",
        "amc": "Motilal Oswal",
        "approx_3yr_cagr": 12.0,
        "approx_5yr_cagr": 18.0,
        "why": "Access to top 100 US tech/growth stocks. Best way to own Apple, Google, etc.",
    },
    {
        "fund_name": "Motilal Oswal S&P 500 Index Fund - Direct Growth",
        "scheme_code": "148381",
        "segment": "international",
        "amc": "Motilal Oswal",
        "approx_3yr_cagr": 13.5,
        "approx_5yr_cagr": 15.0,
        "why": "Broad US market exposure. 500 largest US companies. Lower risk than Nasdaq 100.",
    },

    # ── Debt / Fixed Income ──────────────────────────────────────
    {
        "fund_name": "HDFC Short Term Debt Fund - Direct Growth",
        "scheme_code": "119016",
        "segment": "debt",
        "amc": "HDFC",
        "approx_3yr_cagr": 7.0,
        "approx_5yr_cagr": 7.5,
        "why": "Stable returns, low volatility. Good parking spot for conservative allocation.",
    },
    {
        "fund_name": "ICICI Prudential Corporate Bond Fund - Direct Growth",
        "scheme_code": "120692",
        "segment": "debt",
        "amc": "ICICI Prudential",
        "approx_3yr_cagr": 6.8,
        "approx_5yr_cagr": 7.2,
        "why": "High-quality corporate bonds. Better than FD for 2+ year horizon. Stable.",
    },
    {
        "fund_name": "Parag Parikh Conservative Hybrid Fund - Direct Growth",
        "scheme_code": "148958",
        "segment": "debt",
        "amc": "PPFAS",
        "approx_3yr_cagr": 9.0,
        "approx_5yr_cagr": None,
        "why": "75% debt + 25% equity. Slightly higher returns than pure debt. Tax efficient.",
    },

    # ── Aggressive Hybrid ────────────────────────────────────────
    {
        "fund_name": "ICICI Prudential Equity & Debt Fund - Direct Growth",
        "scheme_code": "120251",
        "segment": "hybrid",
        "amc": "ICICI Prudential",
        "approx_3yr_cagr": 18.0,
        "approx_5yr_cagr": 16.5,
        "why": "Best aggressive hybrid. Auto-rebalances equity/debt. Lower drawdown than pure equity.",
    },
    {
        "fund_name": "Mirae Asset Aggressive Hybrid Fund - Direct Growth",
        "scheme_code": "134813",
        "segment": "hybrid",
        "amc": "Mirae Asset",
        "approx_3yr_cagr": 15.5,
        "approx_5yr_cagr": 14.0,
        "why": "Quality stock picking + debt cushion. Good for moderate risk investors.",
    },

    # ── Real Estate (REITs) ──────────────────────────────────────
    {
        "fund_name": "Kotak International REIT Fund of Fund - Direct Growth",
        "scheme_code": "148646",
        "segment": "reit",
        "amc": "Kotak",
        "approx_3yr_cagr": 5.0,
        "approx_5yr_cagr": None,
        "why": "Global REIT exposure via fund of fund. Diversified real estate without buying property.",
    },
    {
        "fund_name": "Mahindra Manulife Asia Pacific REITs Fund of Fund - Direct Growth",
        "scheme_code": "149230",
        "segment": "reit",
        "amc": "Mahindra Manulife",
        "approx_3yr_cagr": 4.5,
        "approx_5yr_cagr": None,
        "why": "Asia Pacific REIT exposure. Income-generating real estate assets.",
    },
]


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


def pick_funds(allocation: dict[str, float], budget: int) -> list[dict]:
    """
    STATIC fallback: select one fund per segment using hardcoded order.
    Used when live data fetch is skipped or fails entirely.
    Prefer `pick_funds_live()` for real-time ranked picks.
    """
    recommendations = []

    for segment, pct in sorted(allocation.items(), key=lambda x: -x[1]):
        if pct <= 0:
            continue

        candidates = [f for f in FUND_UNIVERSE if f["segment"] == segment]
        if not candidates:
            continue

        fund = candidates[0]
        sip_amount = round(budget * pct / 100)
        min_sip = fund.get("min_sip", 500)
        if sip_amount < min_sip:
            sip_amount = min_sip

        recommendations.append({
            "fund_name":        fund["fund_name"],
            "segment":          segment,
            "segment_label":    SEGMENTS[segment]["label"],
            "amc":              fund.get("amc", ""),
            "allocation_pct":   pct,
            "sip_amount":       sip_amount,
            "approx_3yr_cagr":  fund.get("approx_3yr_cagr"),
            "approx_5yr_cagr":  fund.get("approx_5yr_cagr"),
            "expense_ratio":    fund.get("expense_ratio"),
            "benchmark":        SEGMENTS[segment]["benchmark"],
            "segment_description": SEGMENTS[segment]["description"],
            "why":              fund["why"],
        })

    return recommendations


# ══════════════════════════════════════════════════════════════════════════════
# LIVE DATA: fetch real returns from mfapi.in and rank funds dynamically
# ══════════════════════════════════════════════════════════════════════════════

def enrich_fund_universe(segments_needed: set[str] | None = None) -> list[dict]:
    """
    Fetch LIVE NAV + returns from mfapi.in for every fund in FUND_UNIVERSE
    (or only for the segments listed in `segments_needed`).

    Uses pre-configured `scheme_code` from each fund entry for exact lookup —
    no fuzzy name search needed.

    Each fund dict is updated IN A COPY with:
      - live_return_1yr, live_return_3yr, live_return_5yr  (actual % from mfapi)
      - live_nav                                           (current NAV)
      - live_fund_category                                 (scheme category from API)
      - live_fund_age_years                                (years since inception)
      - data_source: "live" | "static"

    Returns the enriched list (does NOT mutate FUND_UNIVERSE).
    """
    from tools.fetch_nav import fetch_fund_returns

    enriched: list[dict] = []

    candidates = FUND_UNIVERSE
    if segments_needed:
        candidates = [f for f in FUND_UNIVERSE if f["segment"] in segments_needed]

    total = len(candidates)
    print(f"\n[fund_universe] Fetching live data for {total} funds from mfapi.in...")

    for i, fund in enumerate(candidates):
        fund_copy = dict(fund)  # don't mutate the global
        name = fund["fund_name"]
        code = fund.get("scheme_code")

        print(f"  [{i+1}/{total}] {name[:55]}...", end=" ", flush=True)

        if not code:
            print("⚠ no scheme_code configured — using static data")
            fund_copy["data_source"] = "static"
            enriched.append(fund_copy)
            continue

        returns = fetch_fund_returns(code)

        fund_copy["live_nav"]            = returns.get("current_nav")
        fund_copy["live_return_1yr"]     = returns.get("return_1yr")
        fund_copy["live_return_3yr"]     = returns.get("return_3yr")
        fund_copy["live_return_5yr"]     = returns.get("return_5yr")
        fund_copy["live_fund_category"]  = returns.get("fund_category")
        fund_copy["live_fund_age_years"] = returns.get("fund_age_years")
        fund_copy["data_source"]         = "live"

        r1 = fund_copy["live_return_1yr"]
        r3 = fund_copy["live_return_3yr"]
        r5 = fund_copy["live_return_5yr"]
        print(f"✓ 1yr={r1}% | 3yr={r3}% | 5yr={r5}%")

        enriched.append(fund_copy)
        time.sleep(0.3)  # gentle rate limit

    live_count = sum(1 for f in enriched if f.get("data_source") == "live")
    print(f"[fund_universe] Done. {live_count}/{total} funds enriched with live data.\n")
    return enriched


def _rank_score(fund: dict) -> float:
    """
    Compute a composite score for ranking funds within a segment.
    Weights: 3yr CAGR (50%), 5yr CAGR (30%), 1yr return (20%).
    Uses live data if available, falls back to static approx figures.
    """
    def _get(key_live: str, key_static: str) -> float:
        val = fund.get(key_live)
        if val is None:
            val = fund.get(key_static)
        return float(val) if val is not None else 0.0

    r1 = _get("live_return_1yr", "approx_3yr_cagr")  # 1yr not in static → use 3yr as proxy
    r3 = _get("live_return_3yr", "approx_3yr_cagr")
    r5 = _get("live_return_5yr", "approx_5yr_cagr")

    # For live data, use actual 1yr
    if fund.get("live_return_1yr") is not None:
        r1 = float(fund["live_return_1yr"])

    return r3 * 0.50 + r5 * 0.30 + r1 * 0.20


def pick_funds_live(
    allocation: dict[str, float],
    budget: int,
    enriched_universe: list[dict],
) -> list[dict]:
    """
    Select the BEST fund per segment using live return data.
    Ranks candidates by composite score (3yr/5yr/1yr weighted)
    and picks the top performer.

    Returns a list of recommendation dicts with live data attached.
    """
    recommendations = []

    for segment, pct in sorted(allocation.items(), key=lambda x: -x[1]):
        if pct <= 0:
            continue

        candidates = [f for f in enriched_universe if f["segment"] == segment]
        if not candidates:
            # Fallback to static universe
            candidates = [f for f in FUND_UNIVERSE if f["segment"] == segment]
            if not candidates:
                continue

        # Rank by composite score (highest first)
        ranked = sorted(candidates, key=_rank_score, reverse=True)
        best = ranked[0]

        sip_amount = round(budget * pct / 100)
        min_sip = best.get("min_sip", 500)
        if sip_amount < min_sip:
            sip_amount = min_sip

        # Use live returns if available, else fallback to static
        return_1yr = best.get("live_return_1yr")
        return_3yr = best.get("live_return_3yr", best.get("approx_3yr_cagr"))
        return_5yr = best.get("live_return_5yr", best.get("approx_5yr_cagr"))

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
            "live_nav":           best.get("live_nav"),
            "live_fund_category": best.get("live_fund_category"),
            "data_source":        best.get("data_source", "static"),
            "expense_ratio":      best.get("expense_ratio"),
            "benchmark":          SEGMENTS[segment]["benchmark"],
            "segment_description": SEGMENTS[segment]["description"],
            "why":                best["why"],
            "rank_score":         round(_rank_score(best), 2),
            "runner_up":          runner_up_note,
            "alternatives":       [f["fund_name"] for f in ranked[1:]],
        })

    return recommendations
