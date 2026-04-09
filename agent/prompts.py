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

## SWITCH RULES — MARKET-WIDE RECOMMENDATIONS
When recommending a SWITCH:
- You are NOT limited to funds already in the investor's portfolio
- Recommend the BEST fund available in India for that category, from any AMC
- Well-known high-quality funds by category:
  Large Cap       : Mirae Asset Large Cap, HDFC Top 100, Axis Bluechip
  Mid Cap         : Kotak Emerging Equity (Kotak Midcap), HDFC Mid-Cap Opportunities, Nippon India Growth Fund
  Small Cap       : Nippon India Small Cap, Quant Small Cap, Canara Robeco Small Cap
  Flexi Cap       : Parag Parikh Flexi Cap, HDFC Flexi Cap, Mirae Asset Flexi Cap
  Multi Cap       : Nippon India Multi Cap, ICICI Pru Multicap, Quant Active Fund
  ELSS            : Mirae Asset ELSS, Quant ELSS, Parag Parikh ELSS
  Aggressive Hybrid: ICICI Pru Equity & Debt, Mirae Asset Hybrid Equity
  Index (Large)   : UTI Nifty 50 Index, Nippon India Index Nifty 50, HDFC Index Nifty 50
  Index (Mid)     : Motilal Oswal Nifty Midcap 150 Index, UTI Nifty Midcap 150 Index
- State WHY the recommended fund is better: its alpha track record, consistency, AUM stability
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
- Judge across ALL three horizons (1yr, 3yr, 5yr) not just recent

### Step 4 — Trend Classification
Assign one of:
- stable_outperformer    : beats benchmark across all 3 horizons
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
    "reasoning": "2-4 sentences. Must mention: SIP status, key alpha numbers, market context, and why this verdict."
  }
]

Be direct. Be specific. Use actual numbers from the data. Do not hedge excessively.
""".strip()


# ── Analyst prompt is in analyst.py ──────────────────────────────────────────
# sip_status, last_transaction_date, fmt_pct imported from tools.formatting


def build_advisor_prompt(holdings: list[dict], user_profile: dict, market_condition: str) -> str:
    """
    Build the user message for the Advisor Agent.
    Formats all holdings + profile into a structured prompt.
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
        lines.append(f"- Fund Returns  — 1yr: {fmt_pct(h.get('return_1yr'))} | 3yr: {fmt_pct(h.get('return_3yr'))} | 5yr: {fmt_pct(h.get('return_5yr'))}")
        lines.append(f"- Benchmark ({h.get('benchmark_ticker', 'N/A')}) — 1yr: {fmt_pct(h.get('benchmark_return_1yr'))} | 3yr: {fmt_pct(h.get('benchmark_return_3yr'))} | 5yr: {fmt_pct(h.get('benchmark_return_5yr'))}")
        lines.append(f"- Alpha         — 1yr: {fmt_pct(h.get('alpha_1yr'))} | 3yr: {fmt_pct(h.get('alpha_3yr'))} | 5yr: {fmt_pct(h.get('alpha_5yr'))}")
        if score:
            lines.append(f"- Analyst Score — trend: {score.get('trend')} | alpha: {score.get('alpha_score')} | downside: {score.get('downside_protection')} | consistency: {score.get('consistency')}")
            if score.get("red_flags"):
                lines.append(f"- Red Flags: {', '.join(score['red_flags'])}")
            if score.get("green_flags"):
                lines.append(f"- Green Flags: {', '.join(score['green_flags'])}")
            if score.get("score_notes"):
                lines.append(f"- Analyst Notes: {score['score_notes']}")
        lines.append("")

    return "\n".join(lines)
