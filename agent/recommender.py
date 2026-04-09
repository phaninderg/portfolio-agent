"""
Recommender Agent — For new investors without a CAS PDF.

Takes the user's profile (age, risk, horizon, budget) and generates
a diversified mutual fund portfolio recommendation using:
  1. Rule-based asset allocation (fund_universe.py)
  2. LLM-powered personalised reasoning

Hard rules enforced:
  - No single segment > 25% of portfolio
  - Minimum 5 segments covered (diversification)
  - Covers equity (large/mid/small), commodities (gold/silver),
    debt, and optionally international + REIT
"""

from __future__ import annotations
import json

from openai import OpenAI

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from tools.formatting import extract_json_from_llm
from tools.fund_universe import (
    get_allocation, pick_funds, pick_funds_live, enrich_fund_universe,
    SEGMENTS, FUND_UNIVERSE, ALLOCATION_TEMPLATES,
)


# ── System prompt ────────────────────────────────────────────────────────────

RECOMMENDER_SYSTEM_PROMPT = """
You are a seasoned Indian mutual fund advisor helping a NEW investor build their
first SIP portfolio from scratch. You have 20 years of experience across market cycles.

## YOUR TASK
You will receive:
1. The investor's profile (age, goal, horizon, risk appetite, monthly SIP budget)
2. A pre-computed asset allocation across segments
3. A list of recommended funds with suggested SIP amounts

For EACH recommended fund, provide personalised reasoning that explains:
- Why THIS specific fund was chosen over alternatives in the same segment
- How it fits the investor's age, goal, and risk profile
- What role this segment plays in the overall portfolio
- Any caveats or expectations to set (e.g. "small caps can drop 30-40% in bear markets")

## HARD RULES — DIVERSIFICATION
- Never put > 25% in any single segment ("don't put all eggs in one basket")
- The portfolio MUST cover at least 4 different asset types:
  equity, commodity (gold/silver), debt/hybrid, and optionally international/REIT
- For young aggressive investors: still keep 5-10% in gold or debt as cushion
- For conservative investors: still keep 15-25% in equity for inflation-beating growth

## REASONING GUIDELINES
- Be specific: mention actual fund names, return numbers, benchmark comparisons
- Set realistic expectations: equity SIPs need 5-7+ years to show full potential
- Explain the "why" behind each segment, not just the fund
- Flag if the SIP budget is too low (< ₹5000) or too concentrated

## OUTPUT FORMAT
Return a valid JSON object with this structure:
{
  "portfolio_summary": "2-3 sentence overview of the recommended portfolio strategy",
  "diversification_score": "high | medium | low",
  "expected_return_range": "X% - Y% CAGR over Z years (conservative to optimistic)",
  "recommendations": [
    {
      "fund_name": "exact fund name",
      "segment": "segment key",
      "segment_label": "human-readable segment name",
      "allocation_pct": 15.0,
      "sip_amount": 3750,
      "reasoning": "3-4 sentences personalised to investor profile. Must mention: segment role, fund strength, risk expectation."
    }
  ],
  "important_notes": [
    "1-2 sentence actionable note for the investor"
  ]
}

Be direct, specific, and encouraging. This person is starting their investment journey.
""".strip()


# ── Build the user prompt ────────────────────────────────────────────────────

def _build_recommender_prompt(
    user_profile: dict,
    allocation: dict[str, float],
    recommendations: list[dict],
) -> str:
    """Build the user message for the Recommender LLM call."""
    lines = []

    lines.append("## Investor Profile")
    lines.append(f"- Age: {user_profile.get('age')}")
    lines.append(f"- Goal: {user_profile.get('goal')}")
    lines.append(f"- Time Horizon: {user_profile.get('horizon_years')} years")
    lines.append(f"- Risk Appetite: {user_profile.get('risk_appetite')}")
    lines.append(f"- Monthly SIP Budget: ₹{user_profile.get('monthly_sip_budget'):,}")
    lines.append("")

    lines.append("## Asset Allocation")
    for seg, pct in sorted(allocation.items(), key=lambda x: -x[1]):
        label = SEGMENTS.get(seg, {}).get("label", seg)
        lines.append(f"- {label}: {pct:.1f}%")
    lines.append("")

    lines.append("## Recommended Funds (ranked by live returns from mfapi.in)")
    for rec in recommendations:
        source = rec.get("data_source", "static")
        r1 = rec.get("live_return_1yr") if source == "live" else rec.get("approx_3yr_cagr")
        r3 = rec.get("live_return_3yr") if source == "live" else rec.get("approx_3yr_cagr")
        r5 = rec.get("live_return_5yr") if source == "live" else rec.get("approx_5yr_cagr")
        nav = rec.get("live_nav")

        lines.append(f"### {rec['fund_name']}")
        lines.append(f"- Segment: {rec['segment_label']}")
        lines.append(f"- Allocation: {rec['allocation_pct']:.1f}% → ₹{rec['sip_amount']:,}/month")
        lines.append(f"- Data Source: {source.upper()}")
        if nav:
            lines.append(f"- Current NAV: ₹{nav:.2f}")
        lines.append(f"- 1yr Return: {r1}%" if r1 is not None else "- 1yr Return: N/A")
        lines.append(f"- 3yr CAGR: {r3}%" if r3 is not None else "- 3yr CAGR: N/A")
        lines.append(f"- 5yr CAGR: {r5}%" if r5 is not None else "- 5yr CAGR: N/A")
        lines.append(f"- Benchmark: {rec['benchmark']}")
        lines.append(f"- Fund Note: {rec['why']}")
        lines.append(f"- Segment Role: {rec['segment_description']}")
        if rec.get("runner_up"):
            lines.append(f"- Ranking: {rec['runner_up']}")
        if rec.get("alternatives"):
            lines.append(f"- Alternatives considered: {', '.join(rec['alternatives'])}")
        lines.append("")

    lines.append("## Alternative Funds Available (for context)")
    for seg in allocation:
        alts = [f for f in FUND_UNIVERSE if f["segment"] == seg]
        if len(alts) > 1:
            alt_names = [f["fund_name"] for f in alts[1:]]
            label = SEGMENTS.get(seg, {}).get("label", seg)
            lines.append(f"- {label}: {', '.join(alt_names)}")

    return "\n".join(lines)


# ── Run the recommender ──────────────────────────────────────────────────────

def run_recommender(user_profile: dict) -> dict:
    """
    Generate a diversified MF portfolio recommendation for a new investor.

    Returns a dict with:
      - allocation: segment → percentage
      - recommendations: list of fund dicts with SIP amounts
      - llm_analysis: personalised reasoning from the LLM (or None if LLM fails)
    """
    age     = user_profile.get("age", 30)
    risk    = user_profile.get("risk_appetite", "Moderate")
    horizon = user_profile.get("horizon_years", 15)
    budget  = user_profile.get("monthly_sip_budget", 10000)

    print(f"\n[recommender] Profile: age={age}, risk={risk}, horizon={horizon}yr, budget=₹{budget:,}")

    # Step 1: Compute allocation
    allocation = get_allocation(risk, age, horizon)
    print(f"[recommender] Allocation across {len(allocation)} segments:")
    for seg, pct in sorted(allocation.items(), key=lambda x: -x[1]):
        label = SEGMENTS.get(seg, {}).get("label", seg)
        print(f"  {label:<25} {pct:>5.1f}%  →  ₹{round(budget * pct / 100):>,}")

    # Step 2: Fetch LIVE returns from mfapi.in for all candidate funds
    segments_needed = set(allocation.keys())
    print(f"\n[recommender] ── Fetching live fund data from mfapi.in ──")
    try:
        enriched_universe = enrich_fund_universe(segments_needed)
        live_count = sum(1 for f in enriched_universe if f.get("data_source") == "live")
        print(f"[recommender] Live data: {live_count}/{len(enriched_universe)} funds")
    except Exception as exc:
        print(f"[recommender] ⚠ Live fetch failed: {exc}")
        print("[recommender] Falling back to static fund data.")
        enriched_universe = None

    # Step 3: Pick best fund per segment (ranked by live returns)
    if enriched_universe:
        recommendations = pick_funds_live(allocation, budget, enriched_universe)
        print(f"\n[recommender] ✓ Funds ranked by LIVE returns (mfapi.in)")
    else:
        recommendations = pick_funds(allocation, budget)
        print(f"\n[recommender] Using static fund rankings (no live data)")

    total_sip = sum(r["sip_amount"] for r in recommendations)
    print(f"[recommender] {len(recommendations)} funds selected, total SIP: ₹{total_sip:,}/month")

    # Step 4: LLM personalisation (receives live data in prompt)
    llm_analysis = _run_llm_reasoning(user_profile, allocation, recommendations)

    # Merge LLM reasoning into recommendations if available
    if llm_analysis and llm_analysis.get("recommendations"):
        llm_recs = {r["fund_name"]: r for r in llm_analysis["recommendations"]}
        for rec in recommendations:
            llm_rec = llm_recs.get(rec["fund_name"])
            if llm_rec and llm_rec.get("reasoning"):
                rec["reasoning"] = llm_rec["reasoning"]
            # Keep the rule-based 'why' as fallback
            if "reasoning" not in rec:
                rec["reasoning"] = rec["why"]

    return {
        "user_profile":   user_profile,
        "allocation":     allocation,
        "recommendations": recommendations,
        "llm_analysis":   llm_analysis,
    }


def _run_llm_reasoning(
    user_profile: dict,
    allocation: dict[str, float],
    recommendations: list[dict],
) -> dict | None:
    """Call the LLM for personalised reasoning. Returns parsed JSON or None."""
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    user_message = _build_recommender_prompt(user_profile, allocation, recommendations)

    print(f"\n[recommender] Calling LLM for personalised reasoning...")
    print(f"[recommender] Model: {LLM_MODEL} | Prompt: ~{len(user_message)} chars")

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": RECOMMENDER_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=4096,
        )
    except Exception as exc:
        print(f"[recommender] ⚠ LLM call failed: {exc}")
        print("[recommender] Continuing with rule-based recommendations only.")
        return None

    raw = response.choices[0].message.content.strip()
    print(f"[recommender] LLM response received ({len(raw)} chars)")

    return _parse_llm_response(raw)


def _parse_llm_response(raw: str) -> dict | None:
    """Extract JSON from LLM response."""
    result = extract_json_from_llm(raw, expect_array=False)
    if isinstance(result, dict):
        print("[recommender] ✓ LLM analysis parsed successfully")
        return result
    print("[recommender] ⚠ Could not parse JSON from LLM response")
    return None


# ── Pretty print ─────────────────────────────────────────────────────────────

def print_recommendations(result: dict) -> None:
    """Pretty-print recommendations to terminal."""
    recs = result["recommendations"]
    profile = result["user_profile"]
    llm = result.get("llm_analysis") or {}

    SEGMENT_ICON = {
        "large_cap":     "🏢",
        "mid_cap":       "🏗️",
        "small_cap":     "🚀",
        "flexi_cap":     "🎯",
        "index":         "📊",
        "elss":          "🏷️",
        "gold":          "🥇",
        "silver":        "🥈",
        "international": "🌍",
        "debt":          "🏦",
        "hybrid":        "⚖️",
        "reit":          "🏠",
    }

    total_sip = sum(r["sip_amount"] for r in recs)

    print("\n" + "=" * 70)
    print("  YOUR PERSONALISED MUTUAL FUND PORTFOLIO")
    print("=" * 70)
    print(f"  Age: {profile['age']} | Risk: {profile['risk_appetite']} | "
          f"Horizon: {profile['horizon_years']}yr | Goal: {profile['goal']}")
    print(f"  Monthly SIP Budget: ₹{profile['monthly_sip_budget']:,}")
    print(f"  Funds: {len(recs)} | Total SIP: ₹{total_sip:,}/month")

    if llm.get("portfolio_summary"):
        print(f"\n  Strategy: {llm['portfolio_summary']}")
    if llm.get("expected_return_range"):
        print(f"  Expected Returns: {llm['expected_return_range']}")
    if llm.get("diversification_score"):
        print(f"  Diversification: {llm['diversification_score'].upper()}")

    print("=" * 70)

    for rec in recs:
        icon = SEGMENT_ICON.get(rec["segment"], "•")
        source = rec.get("data_source", "static")

        # Prefer live data, fallback to static
        if source == "live":
            r1 = f"{rec['live_return_1yr']}%" if rec.get("live_return_1yr") is not None else "N/A"
            r3 = f"{rec['live_return_3yr']}%" if rec.get("live_return_3yr") is not None else "N/A"
            r5 = f"{rec['live_return_5yr']}%" if rec.get("live_return_5yr") is not None else "N/A"
            data_tag = "[LIVE]"
        else:
            r3 = f"{rec['approx_3yr_cagr']}%" if rec.get("approx_3yr_cagr") else "N/A"
            r5 = f"{rec['approx_5yr_cagr']}%" if rec.get("approx_5yr_cagr") else "N/A"
            r1 = "N/A"
            data_tag = "[static]"

        print(f"\n  {icon} {rec['segment_label']} — {rec['allocation_pct']:.0f}% of portfolio")
        print(f"     {rec['fund_name']}  {data_tag}")
        print(f"     SIP: ₹{rec['sip_amount']:,}/month  |  1yr: {r1}  |  3yr: {r3}  |  5yr: {r5}")
        if rec.get("runner_up"):
            print(f"     Ranking: {rec['runner_up']}")
        print(f"     → {rec.get('reasoning', rec['why'])}")

    if llm.get("important_notes"):
        print("\n" + "─" * 70)
        print("  IMPORTANT NOTES")
        print("─" * 70)
        for note in llm["important_notes"]:
            print(f"  • {note}")

    print("\n" + "=" * 70)
    print("  ⚠  DISCLAIMER: This is AI-generated guidance, not SEBI-registered advice.")
    print("     Always verify fund details on AMC websites before investing.")
    print("=" * 70 + "\n")
