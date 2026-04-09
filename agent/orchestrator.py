"""
Orchestrator Agent — Phase 3
Coordinates all agents in sequence. Handles failures gracefully.
Does NO financial analysis itself — purely a coordinator.

Flow:
  Data Agent      → parse CAS PDF        → holdings[]
  Research Agent  → fetch NAV + returns  → enriched[]
  Research Agent  → fetch benchmarks     → enriched[] with benchmarks
  Analyst Agent   → score each fund      → scored[]   (1 LLM call per fund)
  Advisor Agent   → give verdicts        → verdicts[] (1 LLM call, uses scores)

Each agent reports its status. If an agent partially fails (e.g. 1 fund
times out), the orchestrator logs it and continues rather than crashing.
"""

from __future__ import annotations
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Agent result wrapper ──────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent: str
    status: str          # "success" | "partial" | "failed"
    output: Any = None
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Manages the full portfolio analysis pipeline.
    Each run() call executes all agents in order and returns final verdicts.
    """

    def __init__(self, cas_path: str, cas_password: str, user_profile: dict):
        self.cas_path    = cas_path
        self.cas_password = cas_password
        self.user_profile = user_profile
        self.results: list[AgentResult] = []
        self._log: list[str] = []

    # ── public entry point ────────────────────────────────────────────────────

    def run(self) -> tuple[list[dict], list[dict]]:
        """
        Execute the full pipeline.
        Returns (scored_holdings, verdicts).
        """
        self._banner("ORCHESTRATOR — Portfolio Analysis Pipeline")

        holdings = self._run_data_agent()
        if not holdings:
            self._fail("Data Agent returned no holdings. Cannot continue.")
            return [], []

        holdings = self._run_research_agent(holdings)
        market_condition = self._detect_market(holdings)
        self._log_line(f"Market condition: {market_condition.upper()}")

        scored = self._run_analyst_agent(holdings, market_condition)
        verdicts = self._run_advisor_agent(scored, market_condition)

        self._print_run_summary()
        return scored, verdicts

    # ── Data Agent ────────────────────────────────────────────────────────────

    def _run_data_agent(self) -> list[dict]:
        self._banner("Agent 1 / 4 — Data Agent  (parse CAS PDF)")
        t0 = datetime.now()
        try:
            from tools.parse_cas import parse_cas
            holdings = parse_cas(self.cas_path, self.cas_password)
            dur = (datetime.now() - t0).total_seconds()
            self.results.append(AgentResult("DataAgent", "success", holdings, duration_s=dur))
            self._log_line(f"✓ {len(holdings)} active holdings parsed in {dur:.1f}s")
            return holdings
        except Exception as exc:
            dur = (datetime.now() - t0).total_seconds()
            self.results.append(AgentResult("DataAgent", "failed", errors=[str(exc)], duration_s=dur))
            self._log_line(f"✗ Data Agent failed: {exc}")
            return []

    # ── Research Agent ────────────────────────────────────────────────────────

    def _run_research_agent(self, holdings: list[dict]) -> list[dict]:
        self._banner("Agent 2 / 4 — Research Agent  (NAV + Returns + Benchmarks)")
        t0 = datetime.now()
        errors: list[str] = []

        # Step A: NAV + returns
        try:
            from tools.fetch_nav import enrich_holdings_with_returns
            holdings = enrich_holdings_with_returns(holdings)
            self._log_line(f"✓ NAV + returns fetched for {len(holdings)} funds")
        except Exception as exc:
            errors.append(f"fetch_nav: {exc}")
            self._log_line(f"⚠ NAV fetch partially failed: {exc}")

        # Step B: Benchmark returns
        try:
            from tools.fetch_benchmark import enrich_holdings_with_benchmarks
            holdings = enrich_holdings_with_benchmarks(holdings)
            self._log_line("✓ Benchmark returns fetched")
        except Exception as exc:
            errors.append(f"fetch_benchmark: {exc}")
            self._log_line(f"⚠ Benchmark fetch failed: {exc}")

        dur = (datetime.now() - t0).total_seconds()
        status = "partial" if errors else "success"
        self.results.append(AgentResult("ResearchAgent", status, holdings, errors, dur))
        self._log_line(f"Research Agent done in {dur:.1f}s  [status={status}]")
        return holdings

    # ── Analyst Agent ─────────────────────────────────────────────────────────

    def _run_analyst_agent(self, holdings: list[dict], market_condition: str) -> list[dict]:
        self._banner("Agent 3 / 4 — Analyst Agent  (score each fund — 1 LLM call per fund)")
        t0 = datetime.now()
        errors: list[str] = []

        try:
            from agent.analyst import analyse_all_funds
            scored = analyse_all_funds(holdings, market_condition)
        except Exception as exc:
            self._log_line(f"✗ Analyst Agent failed: {exc}")
            traceback.print_exc()
            errors.append(str(exc))
            # Fallback: pass holdings through unscored
            scored = [{**h, "analyst_score": None} for h in holdings]

        dur = (datetime.now() - t0).total_seconds()
        scored_count = sum(1 for h in scored if h.get("analyst_score") and
                          h["analyst_score"].get("trend") != "insufficient_data")
        status = "partial" if errors else "success"
        self.results.append(AgentResult("AnalystAgent", status, scored, errors, dur))
        self._log_line(f"✓ {scored_count}/{len(scored)} funds scored in {dur:.1f}s  [status={status}]")
        return scored

    # ── Advisor Agent ─────────────────────────────────────────────────────────

    def _run_advisor_agent(self, scored: list[dict], market_condition: str) -> list[dict]:
        self._banner("Agent 4 / 4 — Advisor Agent  (verdicts from analyst scores)")
        t0 = datetime.now()

        try:
            from agent.advisor import run_advisor, print_verdicts
            verdicts = run_advisor(scored, self.user_profile, market_condition)
            print_verdicts(verdicts, scored)
            dur = (datetime.now() - t0).total_seconds()
            self.results.append(AgentResult("AdvisorAgent", "success", verdicts, duration_s=dur))
            self._log_line(f"✓ {len(verdicts)} verdicts generated in {dur:.1f}s")
            return verdicts
        except Exception as exc:
            dur = (datetime.now() - t0).total_seconds()
            self.results.append(AgentResult("AdvisorAgent", "failed", errors=[str(exc)], duration_s=dur))
            self._log_line(f"✗ Advisor Agent failed: {exc}")
            traceback.print_exc()
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _detect_market(self, holdings: list[dict]) -> str:
        from tools.fetch_benchmark import detect_market_condition
        nifty_1yr = next(
            (h.get("benchmark_return_1yr") for h in holdings
             if h.get("benchmark_ticker") == "^NSEI"),
            None
        )
        return detect_market_condition(nifty_1yr)

    def _banner(self, text: str) -> None:
        line = f"\n── {text} {'─' * max(0, 66 - len(text))}"
        print(line)
        self._log.append(line)

    def _log_line(self, text: str) -> None:
        msg = f"  {text}"
        print(msg)
        self._log.append(msg)

    def _fail(self, msg: str) -> None:
        print(f"\n❌  {msg}")

    def _print_run_summary(self) -> None:
        print("\n" + "=" * 70)
        print("  PIPELINE RUN SUMMARY")
        print("=" * 70)
        total = sum(r.duration_s for r in self.results)
        for r in self.results:
            icon = "✅" if r.status == "success" else ("⚠️ " if r.status == "partial" else "❌")
            print(f"  {icon}  {r.agent:<18} {r.status:<8}  {r.duration_s:.1f}s")
            for e in r.errors:
                print(f"       ⚠ {e}")
        print(f"  {'─' * 46}")
        print(f"  Total pipeline time: {total:.1f}s")
        print("=" * 70)

    def save_outputs(self, scored: list[dict], verdicts: list[dict]) -> None:
        """Persist scored holdings and verdicts to output/."""
        out = Path(__file__).parent.parent / "output"
        out.mkdir(exist_ok=True)

        # Scored holdings (strip transactions for readability)
        clean = [{k: v for k, v in h.items() if k != "transactions"} for h in scored]
        with open(out / "scored_holdings.json", "w") as f:
            json.dump(clean, f, indent=2, default=str)

        with open(out / "verdicts.json", "w") as f:
            json.dump(verdicts, f, indent=2, default=str)

        print(f"\n✅  Outputs saved:")
        print(f"    {out / 'scored_holdings.json'}")
        print(f"    {out / 'verdicts.json'}")

    def generate_report(self, scored: list[dict], verdicts: list[dict]) -> str:
        """Phase 4: Generate HTML report."""
        from agent.report import generate_report
        from config import REPORT_HTML_PATH

        market_condition = self._detect_market(scored)
        output_path = generate_report(
            scored, verdicts, self.user_profile,
            market_condition, REPORT_HTML_PATH
        )
        return output_path
