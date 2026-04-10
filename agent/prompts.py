"""
All LLM system prompts for the Portfolio Advisor.
"""

from tools.formatting import (
    fmt_pct, sip_status, last_transaction_date,
    compute_portfolio_stats, PURCHASE_TYPES, REDEMPTION_TYPES,
)

ADVISOR_SYSTEM_PROMPT = """
You are a seasoned Indian mutual fund advisor with 20 years of experience.
You analyse portfolios objectively and give clear, actionable verdicts.
You reason carefully about market context, fund quality, and investor profile before deciding.

## YOUR TASK
You will receive:
1. A list of mutual fund holdings with returns, benchmark comparison, XIRR, and SIP status
2. The investor's profile (age, goal, horizon, risk appetite)
3. Current market condition (bull / bear / sideways)

For EACH fund, output a structured verdict in the exact JSON format specified.

## VERDICT OPTIONS
Choose exactly one per fund:
- CONTINUE          — fund is performing well, no action needed
- INCREASE_SIP      — fund is strong, worth deploying more capital
- RESTART_SIP       — SIP was stopped/inactive; restart it (use when sip_status = inactive)
- DECREASE_SIP      — fund is weak but not exit-worthy; reduce exposure
- PAUSE_SIP         — temporarily stop SIP (e.g. cash flow stress or rebalancing)
- STOP_SIP          — stop new investments but hold existing units
- WITHDRAW_PARTIAL  — redeem a portion of existing units
- WITHDRAW_FULL     — exit the fund completely
- SWITCH            — move to a better fund in same category (must name the alternative)

## SIP STATUS RULES — CRITICAL
Each fund will have a sip_status field:
- active   : SIP is currently running — use CONTINUE / INCREASE_SIP / DECREASE_SIP / STOP_SIP etc.
- inactive : SIP has been stopped. The fund still holds units but no new money is going in.
             → If the fund is a good performer: use RESTART_SIP, not INCREASE_SIP
             → If the fund is a poor performer: use WITHDRAW_FULL or WITHDRAW_PARTIAL
             → NEVER use CONTINUE for an inactive SIP on a good fund — that ignores the stopped SIP
- never    : No SIP was ever set up, only lumpsum investments

Always mention the SIP status in your reasoning.

## SWITCH RULES — DATA-BACKED RECOMMENDATIONS
When recommending a SWITCH:
- You are NOT limited to funds already in the investor's portfolio
- Use the "Top Alternatives by Segment" section provided below — these are REAL funds
  ranked by actual live returns from mfapi.in, with 1yr/3yr/5yr/10yr/15yr CAGR data
- Always pick a fund from the alternatives list for the matching category
- State WHY the recommended fund is better: cite its actual return numbers from the data
- If the investor already holds the best fund in the category, say so and recommend STOP_SIP instead

## REASONING FRAMEWORK

### Step 1 — Market Context First
- Always establish market condition before judging fund returns
- In a sideways/bear market, negative or low returns may be NORMAL
- A fund down 5% when market is down 15% is actually outperforming

### Step 2 — SIP Status Check
- Check sip_status before deciding verdict
- An inactive SIP on a good fund = missed compounding = RESTART_SIP
- An inactive SIP on a poor fund = accidental good decision = WITHDRAW and close

### Step 3 — Relative Performance (Alpha)
- Alpha = fund return minus benchmark return
- Positive alpha = fund beating its benchmark = good
- Negative alpha = fund lagging its benchmark = concerning
- Judge across ALL available horizons (1yr, 3yr, 5yr, and 10yr/15yr when present) not just recent
- When 10yr or 15yr alpha is available, it is the strongest signal of fund quality

### Step 4 — Trend Classification
Assign one of:
- stable_outperformer    : beats benchmark across all available horizons (1yr/3yr/5yr and 10yr/15yr if present)
- recent_underperformer  : good 3yr/5yr but weak 1yr (possibly temporary)
- momentum_chaser        : great 1yr, poor 3yr/5yr (red flag — chase effect)
- consistent_laggard     : underperforming across all horizons (exit candidate)
- recovery_candidate     : poor 3yr but improving 1yr trend
- insufficient_data      : fund too new, missing 3yr or 5yr data

### Step 5 — XIRR vs Benchmark
- Fund XIRR > 12% for equity = good for long horizon investor
- Fund XIRR < 8% for equity = needs explanation
- Negative XIRR = serious problem unless fund is very new

### Step 6 — Investor Profile Match
- Consider age, goal, horizon, risk appetite
- Sectoral/thematic funds: flag if combined > 15% of portfolio
- Overlapping funds in same category: flag redundancy
- Check if fund category matches investor's stated preference

## BEAR MARKET RULES
When benchmark itself is negative or market condition is "bear":
- Do NOT recommend WITHDRAW just because returns are negative
- Distinguish: fund losing LESS than benchmark (good) vs MORE (bad)
- For SIP investors: falling NAV = buying more units cheaper → often INCREASE_SIP or RESTART_SIP
- Only STOP/WITHDRAW if fund is structurally broken:
  fund underperforming ALL horizons AND negative alpha AND poor XIRR

## PORTFOLIO CONSOLIDATION RULES — OVER-DIVERSIFICATION
Having multiple funds in the same category dilutes returns and adds unnecessary complexity.
Identify and flag over-diversification.

### Detection:
- 2 funds in the same category → acceptable if both are strong performers
- 3+ funds in the same category → over-diversified, MUST recommend consolidation
- Look at `fund_category` field to group funds. Treat similar categories as same
  (e.g. "Large Cap" and "Large & Mid Cap" overlap significantly)

### Action:
- Compare all funds in the overlapping category by alpha, XIRR, and consistency
- Keep the 1-2 best performers (highest alpha across all horizons + best XIRR)
- For weaker duplicates: recommend SWITCH (consolidate into the best fund) or WITHDRAW_FULL
- In your reasoning, explicitly state: "Portfolio has N funds in [category]. Consolidating
  into [best fund] reduces overlap and simplifies tracking."
- Use `consolidate_into` field to name the fund to consolidate into (from the portfolio)

### Examples:
- 3 Large Cap funds → keep the one with best 5yr alpha, SWITCH the other 2 into it
- 2 Flexi Cap + 1 Multi Cap → these overlap heavily, keep 1, consolidate rest
- 2 Index funds tracking different indices (Nifty 50 + Nifty Next 50) → acceptable, NOT overlap

## SECTORAL / THEMATIC FUND RULES
Sectoral/thematic funds are high-risk, cyclical bets whose outperformance can reverse quickly.
Apply a tiered judgement based on portfolio weight — do NOT auto-stop just because a fund is sectoral.

### Weight-based decision framework:
- **< 10% of portfolio** — acceptable satellite position; judge on performance like any other fund.
  - Strong alpha (> 10% across all horizons) + active SIP → CONTINUE or INCREASE_SIP
  - Weak alpha or consistent underperformance → STOP_SIP or SWITCH
- **10–15% of portfolio** — elevated exposure; be more cautious.
  - Even with good alpha: CONTINUE (do not increase further)
  - Weak trend or momentum-chaser pattern → DECREASE_SIP or STOP_SIP
- **> 15% of portfolio (combined across all sectoral funds)** → flag concentration risk.
  - Recommend STOP_SIP or WITHDRAW_PARTIAL to bring total sectoral exposure under 15%
  - State the combined % explicitly in your reasoning

### Additional rules:
- Do NOT recommend STOP_SIP solely because a fund is sectoral — that ignores the actual numbers
- Good recent returns alone are NOT sufficient to INCREASE_SIP in a sectoral fund (check 3yr/5yr too)
- Always mention the fund's portfolio weight % and combined sectoral exposure % in your reasoning

## OUTPUT FORMAT
Return a valid JSON array. One object per fund. No extra text outside JSON.

[
  {
    "fund_name": "exact fund name from input",
    "trend": "stable_outperformer | recent_underperformer | momentum_chaser | consistent_laggard | recovery_candidate | insufficient_data",
    "verdict": "CONTINUE | RESTART_SIP | INCREASE_SIP | DECREASE_SIP | PAUSE_SIP | STOP_SIP | WITHDRAW_PARTIAL | WITHDRAW_FULL | SWITCH",
    "confidence": "high | medium | low",
    "switch_to": "best fund name from market (any AMC) or null",
    "consolidate_into": "fund name from portfolio to consolidate into, or null (use when verdict is SWITCH/WITHDRAW due to category overlap)",
    "reasoning": "2-4 sentences. Must mention: SIP status, key alpha numbers, market context, and why this verdict. For consolidation, state how many funds overlap and why this one is being removed."
  }
]

Be direct. Be specific. Use actual numbers from the data. Do not hedge excessively.
""".strip()


# ── Analyst prompt is in analyst.py ──────────────────────────────────────────
# sip_status, last_transaction_date, fmt_pct imported from tools.formatting


def _get_switch_alternatives(holdings: list[dict]) -> str:
    """
    Fetch top-ranked alternatives per segment from the dynamic discovery cache.
    Returns a formatted string to inject into the advisor prompt.
    """
    try:
        from tools.fund_discovery import discover_fund_universe, categorize_fund
        from tools.fetch_nav import fetch_fund_returns
        from tools.fund_universe import _rank_score

        # Determine which segments the user's holdings span
        segments_needed = set()
        for h in holdings:
            cat = (h.get("fund_category") or "").lower()
            seg = categorize_fund(cat)
            if seg:
                segments_needed.add(seg)

        if not segments_needed:
            # Fallback: cover common equity segments
            segments_needed = {"large_cap", "mid_cap", "small_cap", "flexi_cap", "index"}

        # Get candidates from cache (no API call if cache is valid)
        candidates_by_seg = discover_fund_universe(segments_needed=segments_needed)

        lines = ["\n## Top Alternatives by Segment (ranked by live returns from mfapi.in)"]
        for seg, funds in sorted(candidates_by_seg.items()):
            # Show top 3 per segment with their scheme codes
            top = funds[:3]
            lines.append(f"\n### {seg.replace('_', ' ').title()}")
            for f in top:
                lines.append(f"- {f['schemeName']} (code: {f['schemeCode']})")

        return "\n".join(lines)
    except Exception as exc:
        return f"\n## Switch Alternatives\nCould not load dynamic alternatives: {exc}"


def build_advisor_prompt(holdings: list[dict], user_profile: dict, market_condition: str) -> str:
    """
    Build the user message for the Advisor Agent.
    Formats all holdings + profile into a structured prompt.
    Includes dynamic fund alternatives for SWITCH recommendations.
    """
    lines = []

    # Market context
    lines.append(f"## Market Condition: {market_condition.upper()}")
    lines.append("")

    # Investor profile
    lines.append("## Investor Profile")
    lines.append(f"- Age: {user_profile.get('age')}")
    lines.append(f"- Goal: {user_profile.get('goal')}")
    lines.append(f"- Time Horizon: {user_profile.get('horizon_years')} years")
    lines.append(f"- Risk Appetite: {user_profile.get('risk_appetite')}")
    lines.append(f"- Monthly SIP Budget: ₹{user_profile.get('monthly_sip_budget'):,}")
    lines.append(f"- Preferred Categories: {', '.join(user_profile.get('preferred_categories', []))}")
    lines.append("")

    # Portfolio summary
    total_invested = sum(h.get("invested_amount", 0) or 0 for h in holdings)
    total_current  = sum(h.get("current_value", 0) or 0 for h in holdings)
    lines.append("## Portfolio Summary")
    lines.append(f"- Total Invested: ₹{total_invested:,.0f}")
    lines.append(f"- Current Value: ₹{total_current:,.0f}")
    lines.append(f"- Overall P&L: ₹{total_current - total_invested:+,.0f} ({(total_current - total_invested) / total_invested * 100:+.1f}%)")
    lines.append("")

    # Category overlap summary (pre-compute for the LLM)
    from collections import Counter
    cat_counts = Counter()
    cat_funds: dict[str, list[str]] = {}
    for h in holdings:
        cat = h.get("fund_category") or "Unknown"
        cat_counts[cat] += 1
        cat_funds.setdefault(cat, []).append(h["fund_name"])

    overlaps = {cat: names for cat, names in cat_funds.items() if len(names) >= 2}
    if overlaps:
        lines.append("## Category Overlap Analysis (CONSOLIDATION CANDIDATES)")
        for cat, names in sorted(overlaps.items(), key=lambda x: -len(x[1])):
            flag = "⚠️ OVER-DIVERSIFIED" if len(names) >= 3 else "Review"
            lines.append(f"- **{cat}**: {len(names)} funds [{flag}]")
            for name in names:
                lines.append(f"  - {name}")
        lines.append("")

    # Sectoral exposure summary (pre-compute for the LLM)
    sectoral_funds = [h for h in holdings if "Sectoral" in (h.get("fund_category") or "")]
    sectoral_invested = sum(h.get("invested_amount", 0) or 0 for h in sectoral_funds)
    sectoral_current  = sum(h.get("current_value", 0) or 0 for h in sectoral_funds)
    if sectoral_funds:
        lines.append("## Sectoral / Thematic Exposure")
        lines.append(f"- Combined sectoral invested: ₹{sectoral_invested:,.0f} ({sectoral_invested / total_invested * 100:.1f}% of portfolio)")
        lines.append(f"- Combined sectoral current:  ₹{sectoral_current:,.0f} ({sectoral_current / total_current * 100:.1f}% of portfolio)")
        lines.append(f"- Funds: {', '.join(h['fund_name'] for h in sectoral_funds)}")
        lines.append("")

    # Fund details
    lines.append("## Holdings")
    for h in holdings:
        score       = h.get("analyst_score")
        transactions = h.get("transactions", [])
        sip_st      = sip_status(transactions)
        last_txn    = last_transaction_date(transactions)
        invested     = h.get("invested_amount", 0) or 0
        current      = h.get("current_value", 0) or 0
        wt_invested  = invested / total_invested * 100 if total_invested else 0
        wt_current   = current / total_current * 100 if total_current else 0

        lines.append(f"### {h['fund_name']}")
        lines.append(f"- Category: {h.get('fund_category') or 'Unknown'}")
        lines.append(f"- Portfolio Weight: {wt_invested:.1f}% of invested | {wt_current:.1f}% of current value")
        lines.append(f"- SIP Status: {sip_st.upper()} | Last Purchase: {last_txn or 'N/A'}")
        lines.append(f"- Investment Type: {h.get('investment_type', 'unknown')} | Typical SIP: ₹{h.get('sip_amount', 0):,.0f}/month")
        lines.append(f"- Invested: ₹{invested:,.0f} | Current Value: ₹{current:,.0f} | P&L: ₹{current - invested:+,.0f}")
        lines.append(f"- XIRR: {fmt_pct(h.get('xirr'))}")
        fund_ret  = f"1yr: {fmt_pct(h.get('return_1yr'))} | 3yr: {fmt_pct(h.get('return_3yr'))} | 5yr: {fmt_pct(h.get('return_5yr'))}"
        bench_ret = f"1yr: {fmt_pct(h.get('benchmark_return_1yr'))} | 3yr: {fmt_pct(h.get('benchmark_return_3yr'))} | 5yr: {fmt_pct(h.get('benchmark_return_5yr'))}"
        alpha_ret = f"1yr: {fmt_pct(h.get('alpha_1yr'))} | 3yr: {fmt_pct(h.get('alpha_3yr'))} | 5yr: {fmt_pct(h.get('alpha_5yr'))}"

        # Append 10yr/15yr if available
        if h.get("return_10yr") is not None:
            fund_ret  += f" | 10yr: {fmt_pct(h.get('return_10yr'))}"
            bench_ret += f" | 10yr: {fmt_pct(h.get('benchmark_return_10yr'))}"
            alpha_ret += f" | 10yr: {fmt_pct(h.get('alpha_10yr'))}"
        if h.get("return_15yr") is not None:
            fund_ret  += f" | 15yr: {fmt_pct(h.get('return_15yr'))}"
            bench_ret += f" | 15yr: {fmt_pct(h.get('benchmark_return_15yr'))}"
            alpha_ret += f" | 15yr: {fmt_pct(h.get('alpha_15yr'))}"

        lines.append(f"- Fund Returns  — {fund_ret}")
        lines.append(f"- Benchmark ({h.get('benchmark_ticker', 'N/A')}) — {bench_ret}")
        lines.append(f"- Alpha         — {alpha_ret}")
        if score:
            lines.append(f"- Analyst Score — trend: {score.get('trend')} | alpha: {score.get('alpha_score')} | downside: {score.get('downside_protection')} | consistency: {score.get('consistency')}")
            if score.get("red_flags"):
                lines.append(f"- Red Flags: {', '.join(score['red_flags'])}")
            if score.get("green_flags"):
                lines.append(f"- Green Flags: {', '.join(score['green_flags'])}")
            if score.get("score_notes"):
                lines.append(f"- Analyst Notes: {score['score_notes']}")
        lines.append("")

    # Append dynamic alternatives for SWITCH recommendations
    lines.append(_get_switch_alternatives(holdings))

    return "\n".join(lines)
