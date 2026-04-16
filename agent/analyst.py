"""
Analyst Agent — Phase 3
One focused LLM call per fund.
Input:  raw fund data (returns, benchmark, XIRR)
Output: structured score JSON per fund
        {trend, alpha_score, downside_protection, bear_behaviour, score_notes}

Keeping each call small and focused gives better reasoning quality
than dumping all 14 funds into one prompt.
"""

from __future__ import annotations
import time

from openai import OpenAI

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from tools.formatting import fmt_pct, extract_json_from_llm


# ── System prompt ─────────────────────────────────────────────────────────────

ANALYST_SYSTEM_PROMPT = """
You are a quantitative mutual fund analyst. Your job is to score a single mutual fund
based on its performance data. You do NOT give buy/sell advice — that is another agent's job.
Your job is purely to classify and score the fund objectively.

## YOUR OUTPUT
Return a single valid JSON object (no extra text):

{
  "trend": "stable_outperformer | recent_underperformer | momentum_chaser | consistent_laggard | recovery_candidate | insufficient_data",
  "alpha_score": "strong | moderate | weak | negative",
  "downside_protection": "strong | average | weak",
  "bear_behaviour": "outperforms | inline | underperforms | unknown",
  "consistency": "consistent | mixed | inconsistent",
  "red_flags": ["list of specific concerns, empty if none"],
  "green_flags": ["list of specific strengths, empty if none"],
  "score_notes": "2-3 sentences of objective analysis. Use actual numbers."
}

## DEFINITIONS

trend:
  stable_outperformer   → beats benchmark on 1yr AND 3yr AND 5yr alpha (bonus if 10yr/15yr also positive)
  recent_underperformer → positive 3yr/5yr alpha but negative 1yr alpha
  momentum_chaser       → strong 1yr alpha but weak/negative 3yr or 5yr alpha
  consistent_laggard    → negative alpha across all available horizons
  recovery_candidate    → negative 3yr alpha but improving (positive 1yr alpha)
  insufficient_data     → less than 2 alpha data points available

alpha_score:
  strong   → average alpha across horizons > +3%
  moderate → average alpha 0% to +3%
  weak     → average alpha -3% to 0%
  negative → average alpha < -3%

downside_protection:
  Estimate based on: does the fund lose less than benchmark in weak periods?
  Use 1yr return vs benchmark 1yr return as the primary signal.
  strong  → fund 1yr return >= benchmark 1yr return in a flat/down market
  average → fund 1yr return within 3% of benchmark
  weak    → fund 1yr return more than 3% below benchmark

consistency:
  consistent   → trend direction same across all available horizons (1yr through 15yr)
  mixed        → outperforms on some horizons, underperforms on others
  inconsistent → no clear pattern

red_flags (examples):
  - "Negative XIRR despite X years of investment"
  - "Consistent laggard across all horizons"
  - "Sectoral fund with high concentration risk"
  - "1yr return X% below benchmark"
  - "AUM declining" (if data available)

green_flags (examples):
  - "Beats benchmark across all available horizons"
  - "Strong XIRR of X% over Y years"
  - "Outperforming in sideways/bear market"
  - "10yr/15yr CAGR shows long-term consistency"

When 10yr or 15yr data is available, it is a strong signal of long-term quality.
A fund with positive alpha across 10+ years is far more reliable than one with
only 3yr track record. Highlight long-term performance in your score_notes.

Be objective. Use numbers. Do not recommend actions.
""".strip()


def _build_analyst_prompt(holding: dict, market_condition: str) -> str:
    """Build the per-fund analyst prompt."""
    h = holding
    lines = [
        f"## Fund: {h['fund_name']}",
        f"- Category: {h.get('fund_category') or 'Unknown'}",
        f"- Market Condition: {market_condition.upper()}",
        f"- XIRR: {fmt_pct(h.get('xirr'))}",
        f"- Investment Type: {h.get('investment_type', 'unknown')}",
        f"- Invested: ₹{h.get('invested_amount', 0):,.0f} | "
        f"Current: ₹{h.get('current_value', 0):,.0f} | "
        f"P&L: ₹{(h.get('current_value', 0) or 0) - (h.get('invested_amount', 0) or 0):+,.0f}",
        "",
        "### Returns vs Benchmark",
        f"| Horizon | Fund   | Benchmark ({h.get('benchmark_ticker', 'N/A')}) | Alpha  |",
        f"|---------|--------|--------------|--------|",
        f"| 1yr     | {fmt_pct(h.get('return_1yr'))} | {fmt_pct(h.get('benchmark_return_1yr'))} | {fmt_pct(h.get('alpha_1yr'))} |",
        f"| 3yr     | {fmt_pct(h.get('return_3yr'))} | {fmt_pct(h.get('benchmark_return_3yr'))} | {fmt_pct(h.get('alpha_3yr'))} |",
        f"| 5yr     | {fmt_pct(h.get('return_5yr'))} | {fmt_pct(h.get('benchmark_return_5yr'))} | {fmt_pct(h.get('alpha_5yr'))} |",
    ]

    # Add 10yr/15yr rows if data is available
    if h.get("return_10yr") is not None or h.get("benchmark_return_10yr") is not None:
        lines.append(f"| 10yr    | {fmt_pct(h.get('return_10yr'))} | {fmt_pct(h.get('benchmark_return_10yr'))} | {fmt_pct(h.get('alpha_10yr'))} |")
    if h.get("return_15yr") is not None or h.get("benchmark_return_15yr") is not None:
        lines.append(f"| 15yr    | {fmt_pct(h.get('return_15yr'))} | {fmt_pct(h.get('benchmark_return_15yr'))} | {fmt_pct(h.get('alpha_15yr'))} |")
    return "\n".join(lines)


# ── Core agent call ───────────────────────────────────────────────────────────

def analyse_fund(
    holding: dict,
    market_condition: str,
    client: OpenAI,
) -> dict:
    """
    Run the Analyst Agent for a single fund.
    Returns a score dict merged with the original holding data.
    """
    prompt = _build_analyst_prompt(holding, market_condition)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,   # low temp for consistent scoring
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()
        score = _parse_score(raw)
    except Exception as exc:
        print(f"  [analyst] ⚠ LLM call failed: {exc}")
        score = _fallback_score()

    # Merge score into holding dict
    result = {**holding, "analyst_score": score}
    return result


def _parse_score(raw: str) -> dict:
    """Extract JSON from LLM response."""
    score = extract_json_from_llm(raw, expect_array=False)
    if not isinstance(score, dict):
        return _fallback_score()

    score.setdefault("trend", "insufficient_data")
    score.setdefault("alpha_score", "weak")
    score.setdefault("downside_protection", "average")
    score.setdefault("bear_behaviour", "unknown")
    score.setdefault("consistency", "mixed")
    score.setdefault("red_flags", [])
    score.setdefault("green_flags", [])
    score.setdefault("score_notes", "")
    return score


def _fallback_score() -> dict:
    return {
        "trend": "insufficient_data",
        "alpha_score": "weak",
        "downside_protection": "average",
        "bear_behaviour": "unknown",
        "consistency": "mixed",
        "red_flags": ["Analyst LLM call failed"],
        "green_flags": [],
        "score_notes": "Score unavailable due to LLM error.",
    }


# ── Batch analysis ────────────────────────────────────────────────────────────

def analyse_all_funds(
    holdings: list[dict],
    market_condition: str,
    delay: float = 0.5,
) -> list[dict]:
    """
    Run Analyst Agent for every fund sequentially.
    Returns list of holdings enriched with analyst_score.
    """
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    scored = []

    print(f"[analyst] Analysing {len(holdings)} funds individually...")
    print(f"[analyst] Model: {LLM_MODEL} | This will make {len(holdings)} LLM calls\n")

    for i, holding in enumerate(holdings, 1):
        name = holding["fund_name"][:55]
        print(f"  [{i:02d}/{len(holdings)}] {name}")

        result = analyse_fund(holding, market_condition, client)
        score  = result["analyst_score"]

        print(f"         trend={score['trend']} | alpha={score['alpha_score']} | "
              f"downside={score['downside_protection']}")
        if score["red_flags"]:
            print(f"         🚩 {' | '.join(score['red_flags'][:2])}")
        if score["green_flags"]:
            print(f"         ✅ {' | '.join(score['green_flags'][:2])}")

        scored.append(result)
        if i < len(holdings):
            time.sleep(delay)   # brief pause between calls

    print(f"\n[analyst] ✓ All {len(holdings)} funds scored")
    return scored
