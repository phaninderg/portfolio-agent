"""
Advisor Agent — Phase 2
Single LLM call: all holdings + user profile → verdicts per fund.
Uses LM Studio's OpenAI-compatible local API.
"""

from __future__ import annotations

from openai import OpenAI

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from agent.prompts import ADVISOR_SYSTEM_PROMPT, build_advisor_prompt
from tools.formatting import extract_json_from_llm


def run_advisor(
    holdings: list[dict],
    user_profile: dict,
    market_condition: str,
) -> list[dict]:
    """
    Call the local LLM with the full portfolio and get verdicts.
    Returns a list of verdict dicts, one per fund.
    """
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    user_message = build_advisor_prompt(holdings, user_profile, market_condition)

    print("[advisor] Sending portfolio to LLM...")
    print(f"[advisor] Model: {LLM_MODEL} | Temperature: {LLM_TEMPERATURE}")
    print(f"[advisor] Funds: {len(holdings)} | Prompt length: ~{len(user_message)} chars")

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ADVISOR_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=4096,
        )
    except Exception as exc:
        raise RuntimeError(
            f"LLM call failed: {exc}\n"
            "Make sure LM Studio is running with a chat model loaded at http://localhost:1234"
        ) from exc

    raw = response.choices[0].message.content.strip()
    print(f"[advisor] Response received ({len(raw)} chars)")

    verdicts = _parse_verdicts(raw, holdings)
    return verdicts


def _parse_verdicts(raw: str, holdings: list[dict]) -> list[dict]:
    """
    Extract JSON array from LLM response.
    Handles cases where the model wraps JSON in markdown code blocks.
    """
    verdicts = extract_json_from_llm(raw, expect_array=True)
    if not isinstance(verdicts, list):
        print("[advisor] ⚠ Could not parse verdicts from LLM response.")
        return _fallback_verdicts(holdings)

    # Validate required fields
    required = {"fund_name", "verdict", "reasoning"}
    clean = []
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        if not required.issubset(v.keys()):
            continue
        # Normalise verdict to uppercase
        v["verdict"] = str(v.get("verdict", "CONTINUE")).upper()
        v.setdefault("trend", "unknown")
        v.setdefault("confidence", "medium")
        v.setdefault("switch_to", None)
        clean.append(v)

    if not clean:
        print("[advisor] ⚠ No valid verdicts parsed. Using fallback.")
        return _fallback_verdicts(holdings)

    print(f"[advisor] ✓ Parsed {len(clean)} verdicts")
    return clean


def _fallback_verdicts(holdings: list[dict]) -> list[dict]:
    """Return CONTINUE for all funds when LLM fails."""
    return [
        {
            "fund_name":  h["fund_name"],
            "trend":      "unknown",
            "verdict":    "CONTINUE",
            "confidence": "low",
            "switch_to":  None,
            "reasoning":  "LLM analysis unavailable. Please check LM Studio is running with a chat model.",
        }
        for h in holdings
    ]


def print_verdicts(verdicts: list[dict], holdings: list[dict]) -> None:
    """Pretty-print verdicts to terminal."""

    # Verdict → display colour/symbol
    VERDICT_ICON = {
        "CONTINUE":         "✅",
        "INCREASE_SIP":     "📈",
        "DECREASE_SIP":     "📉",
        "PAUSE_SIP":        "⏸ ",
        "STOP_SIP":         "🛑",
        "WITHDRAW_PARTIAL": "⚠️ ",
        "WITHDRAW_FULL":    "❌",
        "SWITCH":           "🔄",
    }

    # Build lookup by fund name
    holding_map = {h["fund_name"]: h for h in holdings}

    print("\n" + "=" * 70)
    print("  ADVISOR VERDICTS")
    print("=" * 70)

    # Action summary
    from collections import Counter
    counts = Counter(v["verdict"] for v in verdicts)
    summary_parts = [f"{icon} {v}: {counts[v]}" for v, icon in VERDICT_ICON.items() if counts[v]]
    print("  " + "  |  ".join(summary_parts))
    print("=" * 70)

    for v in verdicts:
        name     = v["fund_name"]
        verdict  = v["verdict"]
        trend    = v.get("trend", "")
        conf     = v.get("confidence", "")
        icon     = VERDICT_ICON.get(verdict, "•")
        h        = holding_map.get(name, {})
        xirr     = h.get("xirr")
        pnl      = (h.get("current_value", 0) or 0) - (h.get("invested_amount", 0) or 0)

        print(f"\n  {icon} {verdict:<18}  [{conf} confidence]")
        print(f"     {name}")
        print(f"     XIRR: {xirr:+.2f}%  |  P&L: ₹{pnl:+,.0f}  |  Trend: {trend}")
        print(f"     → {v['reasoning']}")
        if v.get("switch_to"):
            print(f"     → Switch to: {v['switch_to']}")
        if v.get("consolidate_into"):
            print(f"     → Consolidate into: {v['consolidate_into']}")

    print()

    # This week's action items
    action_verdicts = [v for v in verdicts if v["verdict"] not in ("CONTINUE",)]
    if action_verdicts:
        print("=" * 70)
        print("  THIS WEEK'S ACTION ITEMS")
        print("=" * 70)
        priority_order = [
            "WITHDRAW_FULL", "WITHDRAW_PARTIAL", "SWITCH",
            "STOP_SIP", "DECREASE_SIP", "INCREASE_SIP", "PAUSE_SIP"
        ]
        action_verdicts.sort(key=lambda v: priority_order.index(v["verdict"])
                             if v["verdict"] in priority_order else 99)
        for i, v in enumerate(action_verdicts, 1):
            icon = VERDICT_ICON.get(v["verdict"], "•")
            print(f"  {i}. {icon} {v['verdict']} — {v['fund_name'][:55]}")
            if v.get("switch_to"):
                print(f"       Switch to: {v['switch_to']}")
            if v.get("consolidate_into"):
                print(f"       Consolidate into: {v['consolidate_into']}")
        print()
