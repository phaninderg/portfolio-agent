"""
Portfolio Advisor — Entry Point

Commands:
  python main.py              — full pipeline (default, needs CAS PDF)
  python main.py data         — data pipeline only (parse + enrich)
  python main.py advise       — data pipeline + single LLM advisor call
  python main.py recommend    — NEW: build a fresh MF portfolio (no CAS needed)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

# ── imports ───────────────────────────────────────────────────────────────────
from config import CAS_PDF_PATH, CAS_PASSWORD, USER_PROFILE
from tools.parse_cas import parse_cas
from tools.fetch_nav import enrich_holdings_with_returns
from tools.fetch_benchmark import enrich_holdings_with_benchmarks, detect_market_condition
from tools.user_profile import collect_user_profile
from agent.advisor import run_advisor, print_verdicts

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ── pretty print ──────────────────────────────────────────────────────────────

from tools.formatting import fmt_value, compute_portfolio_xirr


def _fmt(val, suffix="", na="N/A") -> str:
    return fmt_value(val, suffix, na)


def print_portfolio_summary(holdings: list[dict]) -> None:
    total_invested  = sum(h.get("invested_amount", 0) or 0 for h in holdings)
    total_current   = sum(h.get("current_value", 0) or 0 for h in holdings)
    total_pnl       = total_current - total_invested
    total_pnl_pct   = (total_pnl / total_invested * 100) if total_invested else 0

    print("\n" + "=" * 70)
    print("  PORTFOLIO HEALTH DASHBOARD")
    print("=" * 70)
    print(f"  Total Invested :  ₹{total_invested:>12,.2f}")
    print(f"  Current Value  :  ₹{total_current:>12,.2f}")
    pnl_sign = "▲" if total_pnl >= 0 else "▼"
    print(f"  Overall P&L    :  ₹{total_pnl:>+12,.2f}  ({total_pnl_pct:+.2f}%)  {pnl_sign}")
    print(f"  Active Funds   :  {len(holdings)}")
    print("=" * 70)

    # Nifty 50 1yr for market condition
    nifty_1yr = None
    for h in holdings:
        if h.get("benchmark_ticker") == "^NSEI" and h.get("benchmark_return_1yr") is not None:
            nifty_1yr = h["benchmark_return_1yr"]
            break
    condition = detect_market_condition(nifty_1yr)
    print(f"\n  Market Condition: {condition.upper()}  (Nifty 50 1yr: {_fmt(nifty_1yr, '%')})")

    # Portfolio-level XIRR (all cash flows combined)
    portfolio_xirr = compute_portfolio_xirr(holdings)
    print(f"  Portfolio XIRR :  {_fmt(portfolio_xirr, '%')}")

    # Per-fund table
    rows = []
    for h in holdings:
        invested = h.get("invested_amount", 0) or 0
        current  = h.get("current_value", 0) or 0
        pnl      = current - invested
        rows.append([
            h["fund_name"][:42],
            h.get("investment_type", "—"),
            f"₹{invested:,.0f}",
            f"₹{current:,.0f}",
            f"{pnl:+,.0f}",
            _fmt(h.get("xirr"), "%"),
            _fmt(h.get("return_1yr"), "%"),
            _fmt(h.get("return_3yr"), "%"),
            _fmt(h.get("return_5yr"), "%"),
            _fmt(h.get("alpha_1yr"), "%"),
        ])

    headers = [
        "Fund", "Type", "Invested", "Current", "P&L",
        "XIRR", "1yr", "3yr", "5yr", "α1yr",
    ]

    print()
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
    else:
        print("  | ".join(f"{h:<12}" for h in headers))
        print("-" * 120)
        for r in rows:
            print("  | ".join(f"{str(c):<12}" for c in r))

    print()


# ── pipeline stages ───────────────────────────────────────────────────────────

def build_data_pipeline(user_profile: dict) -> list[dict]:
    """Parse CAS PDF and enrich holdings with NAV, returns, and benchmarks."""
    print("\n🚀  Portfolio Advisor — Data Pipeline")
    print(f"    CAS file : {CAS_PDF_PATH}")
    print(f"    Profile  : {user_profile['goal']}, {user_profile['horizon_years']}yr horizon\n")

    print("── Step 1: Parse CAS PDF ─────────────────────────────────────────")
    holdings = parse_cas(CAS_PDF_PATH, CAS_PASSWORD)
    if not holdings:
        print("❌  No active holdings found. Check CAS_PDF_PATH and CAS_PASSWORD in config.py")
        sys.exit(1)

    print("\n── Step 2: Fetch NAV + Returns (mfapi.in) ────────────────────────")
    holdings = enrich_holdings_with_returns(holdings)

    print("\n── Step 3: Fetch Benchmark Returns (yfinance) ────────────────────")
    holdings = enrich_holdings_with_benchmarks(holdings)

    print("\n── Step 4: Portfolio Summary ─────────────────────────────────────")
    print_portfolio_summary(holdings)

    out_path = Path(__file__).parent / "output" / "enriched_holdings.json"
    out_path.parent.mkdir(exist_ok=True)
    clean = [{k: v for k, v in h.items() if k != "transactions"} for h in holdings]
    with open(out_path, "w") as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"✅  Enriched holdings saved → {out_path}\n")

    return holdings


def run_single_advisor(holdings: list[dict], user_profile: dict) -> None:
    """Run a single LLM advisor call and print verdicts (no analyst scoring)."""
    print("\n── Single LLM Advisor ────────────────────────────────────────────")

    nifty_1yr = next(
        (h.get("benchmark_return_1yr") for h in holdings
         if h.get("benchmark_ticker") == "^NSEI"),
        None,
    )
    market_condition = detect_market_condition(nifty_1yr)

    verdicts = run_advisor(holdings, user_profile, market_condition)
    print_verdicts(verdicts, holdings)

    verdicts_path = Path(__file__).parent / "output" / "verdicts.json"
    with open(verdicts_path, "w") as f:
        json.dump(verdicts, f, indent=2)
    print(f"✅  Verdicts saved → {verdicts_path}\n")


def run_recommend(user_profile: dict) -> None:
    """
    Recommend pipeline for new investors — no CAS PDF needed.
    Builds a diversified portfolio from scratch based on age, risk, and budget.
    """
    from agent.recommender import run_recommender, print_recommendations
    from agent.recommend_report import generate_recommend_report

    print("\n🚀  Portfolio Advisor — New Investor Recommendations")
    print(f"    Profile  : {user_profile['goal']}, {user_profile['horizon_years']}yr horizon")
    print(f"    Risk     : {user_profile['risk_appetite']}")
    print(f"    Budget   : ₹{user_profile['monthly_sip_budget']:,}/month\n")

    result = run_recommender(user_profile)
    print_recommendations(result)

    # Save outputs
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    with open(out_dir / "recommendations.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"✅  Recommendations saved → {out_dir / 'recommendations.json'}")

    report_path = generate_recommend_report(
        result, str(out_dir / "recommend_report.html")
    )
    print(f"✅  Open in browser: open \"{report_path}\"\n")


def run_full_analysis(user_profile: dict) -> None:
    """
    Full multi-agent pipeline: parse → enrich → score → advise → report → chat.
    Orchestrator coordinates all agents and handles partial failures gracefully.
    """
    print("\n🚀  Portfolio Advisor — Full Analysis")
    print(f"    CAS file : {CAS_PDF_PATH}")
    print(f"    Profile  : {user_profile['goal']}, {user_profile['horizon_years']}yr horizon\n")

    from agent.orchestrator import Orchestrator
    orch = Orchestrator(CAS_PDF_PATH, CAS_PASSWORD, user_profile)
    scored, verdicts = orch.run()

    if scored and verdicts:
        orch.save_outputs(scored, verdicts)

        print("\n── HTML Report ───────────────────────────────────────────────────")
        report_path = orch.generate_report(scored, verdicts)
        print(f"✅  Open in browser: open \"{report_path}\"")

        print("\n── Interactive Chat ──────────────────────────────────────────────")
        nifty_1yr = next(
            (h.get("benchmark_return_1yr") for h in scored
             if h.get("benchmark_ticker") == "^NSEI"),
            None,
        )
        market_condition = detect_market_condition(nifty_1yr)
        from agent.chat import start_chat
        start_chat(scored, verdicts, market_condition, user_profile)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Collect investor profile interactively; config.py values are the defaults
    user_profile = collect_user_profile(USER_PROFILE)

    command = sys.argv[1] if len(sys.argv) > 1 else "full"
    if command == "data":
        build_data_pipeline(user_profile)
    elif command == "advise":
        holdings = build_data_pipeline(user_profile)
        run_single_advisor(holdings, user_profile)
    elif command == "recommend":
        run_recommend(user_profile)
    else:
        run_full_analysis(user_profile)
