"""
Chat Agent — Interactive Q&A after report generation.
Maintains full portfolio context in the system prompt.
User can ask follow-up questions; type 'exit' to quit.
"""

from __future__ import annotations
from openai import OpenAI

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from tools.formatting import fmt_pct, sip_status, last_transaction_date


def _build_chat_system_prompt(
    holdings: list[dict],
    verdicts: list[dict],
    market_condition: str,
    user_profile: dict,
) -> str:
    """
    Build a rich system prompt with full portfolio context for the chat session.
    The LLM carries this as memory across the entire conversation.
    """
    verdict_map = {v["fund_name"]: v for v in verdicts}

    total_invested = sum(h.get("invested_amount", 0) or 0 for h in holdings)
    total_current  = sum(h.get("current_value", 0) or 0 for h in holdings)
    total_pnl      = total_current - total_invested

    lines = [
        "You are a knowledgeable Indian mutual fund advisor.",
        "You have already analysed the investor's portfolio and generated verdicts.",
        "The investor is now asking follow-up questions. Answer concisely and specifically.",
        "Always refer to actual numbers from the portfolio data below.",
        "If asked about funds not in the portfolio, use your general knowledge of Indian MF market.",
        "",
        "## Investor Profile",
        f"- Age: {user_profile.get('age')} | Goal: {user_profile.get('goal')}",
        f"- Horizon: {user_profile.get('horizon_years')} years | Risk: {user_profile.get('risk_appetite')}",
        f"- Monthly SIP Budget: ₹{user_profile.get('monthly_sip_budget'):,}",
        "",
        f"## Market Condition: {market_condition.upper()}",
        "",
        f"## Portfolio Summary",
        f"- Total Invested: ₹{total_invested:,.0f}",
        f"- Current Value:  ₹{total_current:,.0f}",
        f"- Overall P&L:    ₹{total_pnl:+,.0f} ({total_pnl/total_invested*100:+.1f}%)",
        "",
        "## Holdings + Verdicts",
    ]

    for h in holdings:
        v       = verdict_map.get(h["fund_name"], {})
        txns    = h.get("transactions", [])
        sip_st  = sip_status(txns)
        last_p  = last_transaction_date(txns)
        score   = h.get("analyst_score") or {}
        invested = h.get("invested_amount", 0) or 0
        current  = h.get("current_value", 0) or 0

        lines += [
            f"### {h['fund_name']}",
            f"- Category: {h.get('fund_category') or 'Unknown'} | SIP: {sip_st.upper()} | Last purchase: {last_p or 'N/A'}",
            f"- Invested: ₹{invested:,.0f} | Current: ₹{current:,.0f} | P&L: ₹{current-invested:+,.0f}",
            f"- XIRR: {fmt_pct(h.get('xirr'))} | 1yr: {fmt_pct(h.get('return_1yr'))} | 3yr: {fmt_pct(h.get('return_3yr'))} | 5yr: {fmt_pct(h.get('return_5yr'))}",
            f"- Alpha: 1yr {fmt_pct(h.get('alpha_1yr'))} | 3yr {fmt_pct(h.get('alpha_3yr'))} | 5yr {fmt_pct(h.get('alpha_5yr'))}",
            f"- Analyst: trend={score.get('trend','?')} | alpha_score={score.get('alpha_score','?')} | downside={score.get('downside_protection','?')}",
            f"- VERDICT: {v.get('verdict','?')} (confidence={v.get('confidence','?')})"
            + (f" → switch to: {v['switch_to']}" if v.get('switch_to') else ""),
            f"- Reasoning: {v.get('reasoning', 'N/A')}",
            "",
        ]

    return "\n".join(lines)


def start_chat(
    holdings: list[dict],
    verdicts: list[dict],
    market_condition: str,
    user_profile: dict,
) -> None:
    """
    Start an interactive chat session with the LLM about the portfolio.
    Maintains conversation history so the LLM remembers prior exchanges.
    Type 'exit' or 'quit' to end the session.
    """
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    system_prompt = _build_chat_system_prompt(
        holdings, verdicts, market_condition, user_profile
    )

    # Conversation history — grows with each exchange
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    print("\n" + "=" * 70)
    print("  💬  PORTFOLIO CHAT  —  Ask anything about your portfolio")
    print("  Type 'exit' to quit")
    print("=" * 70 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[chat] Session ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q", "bye"):
            print("\n[chat] Goodbye! Re-run python main.py for a fresh analysis.")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            print("\nAdvisor: ", end="", flush=True)
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=LLM_TEMPERATURE,
                max_tokens=1024,
                stream=True,       # stream tokens for responsive feel
            )

            reply = ""
            for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                print(delta, end="", flush=True)
                reply += delta

            print("\n")
            # Add assistant reply to history so next question has context
            messages.append({"role": "assistant", "content": reply})

        except Exception as exc:
            print(f"\n[chat] LLM error: {exc}\n")
            # Remove the failed user message so history stays clean
            messages.pop()
