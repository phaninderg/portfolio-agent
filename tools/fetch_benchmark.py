"""
Research Agent — Tool: fetch_benchmark.py
Fetches the correct benchmark index returns (1yr / 3yr / 5yr) for each
fund using yfinance, based on the fund's category.
"""

from __future__ import annotations
import time
from datetime import date, timedelta
from typing import Any

try:
    import yfinance as yf
except ImportError:
    import sys
    sys.exit("yfinance not installed. Run: pip install yfinance")

# ── Benchmark mapping ─────────────────────────────────────────────────────────
# category keyword (lowercase) → yfinance ticker
CATEGORY_BENCHMARK_MAP: dict[str, str] = {
    # Large Cap — Nifty 50
    "large cap":        "^NSEI",
    "large-cap":        "^NSEI",
    "large and mid cap":"^NSEI",
    # Mid Cap — Nifty Midcap 150
    "mid cap":          "^NSMIDCP",
    "mid-cap":          "^NSMIDCP",
    "midcap":           "^NSMIDCP",
    # Small Cap — SETFNN50 (Nippon ETF, tracks small-cap universe; best available proxy)
    "small cap":        "SETFNN50.NS",
    "small-cap":        "SETFNN50.NS",
    "smallcap":         "SETFNN50.NS",
    # Flexi/Multi/ELSS — Nifty BeES ETF (tracks Nifty 50, close Flexi Cap proxy)
    "flexi cap":        "NIFTYBEES.NS",
    "flexi-cap":        "NIFTYBEES.NS",
    "flexicap":         "NIFTYBEES.NS",
    "multi cap":        "NIFTYBEES.NS",
    "multi-cap":        "NIFTYBEES.NS",
    "multicap":         "NIFTYBEES.NS",
    "elss":             "^NSEI",
    # Index
    "index":            "^NSEI",
    # International
    "international":    "^GSPC",
    "global":           "^GSPC",
    "us equity":        "^GSPC",
    "nasdaq":           "^IXIC",
    # Debt / Liquid — no equity benchmark
    "liquid":           None,
    "debt":             None,
    "money market":     None,
    "overnight":        None,
    "credit risk":      None,
    "banking and psu":  None,
    "gilt":             None,
}


def _ticker_for_category(category: str | None) -> str | None:
    if not category:
        return "^NSEI"   # default to Nifty 50
    cat_lower = category.lower()
    for key, ticker in CATEGORY_BENCHMARK_MAP.items():
        if key in cat_lower:
            return ticker
    return "^NSEI"   # default


def _compute_cagr(old, new, years):
    """Delegate to shared implementation."""
    from tools.xirr import compute_cagr
    return compute_cagr(old, new, years)


def fetch_benchmark_returns(ticker: str) -> dict:
    """
    Fetch 1yr / 3yr / 5yr CAGR returns for a yfinance ticker.
    Returns: {ticker, return_1yr, return_3yr, return_5yr, current_price}
    """
    result: dict[str, Any] = {
        "ticker":       ticker,
        "return_1yr":   None,
        "return_3yr":   None,
        "return_5yr":   None,
        "current_price": None,
    }

    if not ticker:
        return result

    today = date.today()
    start = today - timedelta(days=365 * 5 + 30)   # fetch 5yr+ to cover all windows

    try:
        hist = yf.download(
            ticker,
            start=start.isoformat(),
            end=today.isoformat(),
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        print(f"  [fetch_benchmark] yfinance download failed for {ticker}: {exc}")
        return result

    if hist.empty:
        print(f"  [fetch_benchmark] No data returned for {ticker}")
        return result

    # yfinance ≥ 0.2.x may return multi-level columns; flatten if needed
    if isinstance(hist.columns, __import__("pandas").MultiIndex):
        hist.columns = hist.columns.get_level_values(0)

    # Use 'Close' column
    if "Close" not in hist.columns:
        return result

    close = hist["Close"].dropna()
    if close.empty:
        return result

    current = float(close.iloc[-1])
    result["current_price"] = round(current, 2)

    def price_n_years_ago(years: int) -> float | None:
        target = today - timedelta(days=365 * years)
        # Find closest date at or before target
        subset = close[close.index.date <= target]
        if subset.empty:
            return None
        return float(subset.iloc[-1])

    p1y = price_n_years_ago(1)
    p3y = price_n_years_ago(3)
    p5y = price_n_years_ago(5)

    result["return_1yr"] = _compute_cagr(p1y, current, 1) if p1y else None
    result["return_3yr"] = _compute_cagr(p3y, current, 3) if p3y else None
    result["return_5yr"] = _compute_cagr(p5y, current, 5) if p5y else None

    return result


# ── cache to avoid redundant downloads ───────────────────────────────────────
_benchmark_cache: dict[str, dict] = {}


def get_benchmark_for_fund(fund_category: str | None) -> dict:
    """
    High-level: given a fund category string, resolve the right ticker
    and return its return data.
    """
    ticker = _ticker_for_category(fund_category)
    if ticker is None:
        return {
            "ticker": None,
            "return_1yr": None,
            "return_3yr": None,
            "return_5yr": None,
            "current_price": None,
        }

    if ticker in _benchmark_cache:
        return _benchmark_cache[ticker]

    print(f"  [fetch_benchmark] Fetching {ticker} for category '{fund_category}'")
    data = fetch_benchmark_returns(ticker)
    _benchmark_cache[ticker] = data
    time.sleep(0.5)   # gentle rate limit
    return data


def enrich_holdings_with_benchmarks(holdings: list[dict]) -> list[dict]:
    """
    Add benchmark_* fields to each holding dict.
    Expects each holding to already have a 'fund_category' field (from fetch_nav).
    """
    for h in holdings:
        bm = get_benchmark_for_fund(h.get("fund_category"))
        h["benchmark_ticker"]    = bm["ticker"]
        h["benchmark_return_1yr"] = bm["return_1yr"]
        h["benchmark_return_3yr"] = bm["return_3yr"]
        h["benchmark_return_5yr"] = bm["return_5yr"]

        # Compute alpha
        h["alpha_1yr"] = (
            round(h["return_1yr"] - bm["return_1yr"], 2)
            if h.get("return_1yr") is not None and bm["return_1yr"] is not None
            else None
        )
        h["alpha_3yr"] = (
            round(h["return_3yr"] - bm["return_3yr"], 2)
            if h.get("return_3yr") is not None and bm["return_3yr"] is not None
            else None
        )
        h["alpha_5yr"] = (
            round(h["return_5yr"] - bm["return_5yr"], 2)
            if h.get("return_5yr") is not None and bm["return_5yr"] is not None
            else None
        )

    return holdings


# ── market condition ──────────────────────────────────────────────────────────

def detect_market_condition(nifty_1yr: float | None) -> str:
    """Simple heuristic: bull / bear / sideways based on Nifty 50 1yr return."""
    if nifty_1yr is None:
        return "unknown"
    if nifty_1yr >= 15:
        return "bull"
    if nifty_1yr <= -5:
        return "bear"
    return "sideways"


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Quick smoke test
    tickers = ["^NSEI", "^NSMIDCP", "NIFTYBEES.NS", "SETFNN50.NS"]
    for t in tickers:
        r = fetch_benchmark_returns(t)
        print(f"{t}: 1yr={r['return_1yr']}% | 3yr={r['return_3yr']}% | 5yr={r['return_5yr']}%")
