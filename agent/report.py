"""
Report Agent — Phase 4
Generates a self-contained HTML dashboard from scored holdings + verdicts.
No extra dependencies — uses Chart.js via CDN.
"""

from __future__ import annotations
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from tools.formatting import (
    fmt_pct, fmt_inr, color_pct_style,
    sip_status, last_transaction_date,
    compute_portfolio_xirr,
)


# ── Verdict styling ───────────────────────────────────────────────────────────

VERDICT_STYLE = {
    "CONTINUE":         {"color": "#22c55e", "bg": "#f0fdf4", "icon": "✅"},
    "INCREASE_SIP":     {"color": "#16a34a", "bg": "#dcfce7", "icon": "📈"},
    "RESTART_SIP":      {"color": "#0ea5e9", "bg": "#f0f9ff", "icon": "▶️"},
    "DECREASE_SIP":     {"color": "#f59e0b", "bg": "#fffbeb", "icon": "📉"},
    "PAUSE_SIP":        {"color": "#f59e0b", "bg": "#fffbeb", "icon": "⏸"},
    "STOP_SIP":         {"color": "#ef4444", "bg": "#fef2f2", "icon": "🛑"},
    "WITHDRAW_PARTIAL": {"color": "#dc2626", "bg": "#fef2f2", "icon": "⚠️"},
    "WITHDRAW_FULL":    {"color": "#991b1b", "bg": "#fee2e2", "icon": "❌"},
    "SWITCH":           {"color": "#7c3aed", "bg": "#f5f3ff", "icon": "🔄"},
}

TREND_BADGE = {
    "stable_outperformer":   {"color": "#16a34a", "label": "Stable Outperformer"},
    "recent_underperformer": {"color": "#f59e0b", "label": "Recent Underperformer"},
    "momentum_chaser":       {"color": "#ef4444", "label": "Momentum Chaser"},
    "consistent_laggard":    {"color": "#dc2626", "label": "Consistent Laggard"},
    "recovery_candidate":    {"color": "#7c3aed", "label": "Recovery Candidate"},
    "insufficient_data":     {"color": "#6b7280", "label": "Insufficient Data"},
    "unknown":               {"color": "#6b7280", "label": "Unknown"},
}

MARKET_STYLE = {
    "bull":     {"color": "#16a34a", "bg": "#dcfce7", "label": "🐂 Bull Market"},
    "bear":     {"color": "#dc2626", "bg": "#fee2e2", "label": "🐻 Bear Market"},
    "sideways": {"color": "#f59e0b", "bg": "#fffbeb", "label": "↔ Sideways Market"},
    "unknown":  {"color": "#6b7280", "bg": "#f3f4f6", "label": "Market: Unknown"},
}


# Aliases for backward compat within this module's f-strings
_pct = fmt_pct
_inr = fmt_inr
_color_pct = color_pct_style


# ── HTML generation ───────────────────────────────────────────────────────────

def _monthly_investments(transactions: list[dict]) -> dict[str, dict]:
    """
    Group purchase transactions by YYYY-MM.
    Returns: {"2024-01": {"total": 10000.0, "count": 2, "amounts": [5000, 5000]}, ...}
    """
    monthly: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0, "amounts": []})
    for txn in transactions:
        amt   = float(txn.get("amount", 0) or 0)
        ttype = str(txn.get("type", "")).upper()
        d     = str(txn.get("date", ""))
        if amt <= 0 or not d:
            continue
        if any(k in ttype for k in ("PURCHASE", "SWITCH_IN", "DIVIDEND_REINVEST")):
            month_key = d[:7]   # "YYYY-MM"
            monthly[month_key]["total"]  += amt
            monthly[month_key]["count"]  += 1
            monthly[month_key]["amounts"].append(amt)
    return dict(sorted(monthly.items()))


def _monthly_sip_html(transactions: list[dict]) -> str:
    """
    Build a compact monthly investment table for a fund card.
    Shows last 12 months. Clubs multiple investments in the same month.
    For months with 2 instalments shows: ₹5,000 × 2 = ₹10,000
    """
    monthly = _monthly_investments(transactions)
    if not monthly:
        return ""

    recent = dict(list(monthly.items())[-12:])
    if not recent:
        return ""

    # Typical SIP = mode of monthly totals (most frequently occurring monthly amount).
    # This handles both "₹5k in one chunk" and "₹5k split into two ₹2.5k chunks" correctly.
    # On a tie (e.g. 50% single/double months), take the lower value — the base SIP.
    from collections import Counter
    monthly_totals = [round(v["total"] / 500) * 500 for v in recent.values()]  # round to ₹500
    freq = Counter(monthly_totals)
    max_freq = max(freq.values())
    typical_sip = min(amt for amt, cnt in freq.items() if cnt == max_freq)

    rows = ""
    for ym, data in recent.items():
        try:
            y, m = ym.split("-")
            label = date(int(y), int(m), 1).strftime("%b %y")
        except Exception:
            label = ym

        total  = data["total"]
        count  = data["count"]
        amounts = data["amounts"]

        if count > 1:
            # Check if all instalments are roughly equal
            min_a, max_a = min(amounts), max(amounts)
            if max_a - min_a < 50:   # within ₹50 — treat as equal instalments
                display = f"₹{min_a:,.0f} × {count} = ₹{total:,.0f}"
            else:
                # Different amounts — show each
                parts = " + ".join(f"₹{a:,.0f}" for a in amounts)
                display = f"{parts} = ₹{total:,.0f}"
            style = "color:#7c3aed;font-weight:700"
        else:
            display = f"₹{total:,.0f}"
            style = "color:#1e293b"

        rows += (f"<tr>"
                 f"<td style='padding:1px 8px 1px 0;color:#64748b;font-size:10px'>{label}</td>"
                 f"<td style='{style};font-size:10px'>{display}</td>"
                 f"</tr>")

    return f"""
    <details style="margin-top:10px">
      <summary style="font-size:11px;font-weight:600;color:#475569;cursor:pointer;
                      list-style:none;display:flex;align-items:center;gap:4px">
        ▸ Monthly Investments &nbsp;
        <span style="color:#94a3b8;font-weight:400">(typical SIP ₹{typical_sip:,.0f}/mo · last 12 months)</span>
      </summary>
      <div style="margin-top:8px;overflow-x:auto">
        <table style="border-collapse:collapse;width:100%">
          <tbody>{rows}</tbody>
        </table>
      </div>
    </details>"""


def generate_report(
    holdings: list[dict],
    verdicts: list[dict],
    user_profile: dict,
    market_condition: str,
    output_path: str,
    yoy_data: dict | None = None,
) -> str:
    verdict_map = {v["fund_name"]: v for v in verdicts}

    total_invested = sum(h.get("invested_amount", 0) or 0 for h in holdings)
    total_current  = sum(h.get("current_value", 0) or 0 for h in holdings)
    total_pnl      = total_current - total_invested
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested else 0

    # Portfolio XIRR (recompute from output)
    portfolio_xirr = _portfolio_xirr(holdings)

    from collections import Counter
    verdict_counts = Counter(v.get("verdict", "CONTINUE") for v in verdicts)

    mkt = MARKET_STYLE.get(market_condition, MARKET_STYLE["unknown"])

    # Benchmark returns for market context banner
    benchmarks_seen: dict[str, dict] = {}
    for h in holdings:
        t = h.get("benchmark_ticker")
        if t and t not in benchmarks_seen:
            benchmarks_seen[t] = {
                "ticker":    t,
                "return_1yr": h.get("benchmark_return_1yr"),
                "return_3yr": h.get("benchmark_return_3yr"),
                "return_5yr": h.get("benchmark_return_5yr"),
            }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Advisor Report — {date.today().strftime('%d %b %Y')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f8fafc; color: #1e293b; font-size: 14px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}

  /* Header */
  .header {{ background: #1e293b; color: white; padding: 24px 32px;
             border-radius: 12px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .header .subtitle {{ color: #94a3b8; font-size: 13px; }}

  /* Dashboard grid */
  .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 16px; margin-bottom: 24px; }}
  .metric {{ background: white; border-radius: 10px; padding: 20px;
             box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .metric .label {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
                    letter-spacing: 0.5px; color: #64748b; margin-bottom: 8px; }}
  .metric .value {{ font-size: 22px; font-weight: 700; }}
  .metric .sub {{ font-size: 12px; color: #64748b; margin-top: 4px; }}

  /* Market banner */
  .market-banner {{ border-radius: 10px; padding: 16px 24px; margin-bottom: 24px;
                    background: {mkt['bg']}; border: 1px solid {mkt['color']}33; }}
  .market-banner h3 {{ font-size: 15px; font-weight: 700; color: {mkt['color']};
                       margin-bottom: 12px; }}
  .benchmark-grid {{ display: flex; flex-wrap: wrap; gap: 20px; }}
  .bm-item {{ font-size: 12px; }}
  .bm-item .bm-name {{ color: #64748b; margin-bottom: 2px; }}
  .bm-item .bm-vals {{ font-weight: 600; }}

  /* Action summary */
  .action-summary {{ background: white; border-radius: 10px; padding: 20px 24px;
                     box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 24px; }}
  .action-summary h2 {{ font-size: 15px; font-weight: 700; margin-bottom: 14px; }}
  .verdict-chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .verdict-chip {{ padding: 6px 14px; border-radius: 20px; font-size: 12px;
                   font-weight: 600; }}

  /* Fund cards */
  .section-title {{ font-size: 16px; font-weight: 700; margin-bottom: 16px;
                    color: #1e293b; }}
  .fund-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr));
                gap: 16px; margin-bottom: 32px; }}
  .fund-card {{ background: white; border-radius: 12px; padding: 20px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.08);
                border-left: 4px solid #e2e8f0; }}
  .card-header {{ display: flex; justify-content: space-between;
                  align-items: flex-start; margin-bottom: 14px; }}
  .fund-name {{ font-size: 13px; font-weight: 700; color: #1e293b;
                max-width: 65%; line-height: 1.4; }}
  .fund-meta {{ font-size: 11px; color: #64748b; margin-top: 3px; }}
  .verdict-badge {{ padding: 5px 12px; border-radius: 20px; font-size: 11px;
                    font-weight: 700; white-space: nowrap; }}
  .trend-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                  font-size: 10px; font-weight: 600; margin-top: 4px; color: white; }}

  /* Financials row */
  .financials {{ display: grid; grid-template-columns: repeat(4, 1fr);
                 gap: 8px; margin-bottom: 14px; }}
  .fin-item .fin-label {{ font-size: 10px; color: #94a3b8;
                          text-transform: uppercase; letter-spacing: 0.3px; }}
  .fin-item .fin-val {{ font-size: 14px; font-weight: 700; }}

  /* Returns table */
  .returns-row {{ display: grid; gap: 4px; font-size: 11px; margin-bottom: 2px; }}
  .returns-row .rh {{ color: #64748b; font-weight: 600; text-align: center; }}
  .returns-row .rh:first-child {{ text-align: left; }}
  .returns-row .rv {{ font-weight: 600; text-align: center; }}

  /* Chart */
  .chart-wrap {{ height: 90px; margin: 14px 0 10px; }}

  /* Reasoning */
  .reasoning {{ font-size: 12px; color: #475569; line-height: 1.6;
                background: #f8fafc; border-radius: 6px; padding: 10px 12px;
                margin-top: 8px; }}
  .switch-to {{ font-size: 11px; color: #7c3aed; font-weight: 600;
                margin-top: 6px; }}

  /* Flags */
  .flags {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }}
  .flag {{ font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
  .flag.red {{ background: #fee2e2; color: #dc2626; }}
  .flag.green {{ background: #dcfce7; color: #16a34a; }}

  /* Action items */
  .action-items {{ background: white; border-radius: 12px; padding: 24px;
                   box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .action-items h2 {{ font-size: 16px; font-weight: 700; margin-bottom: 16px; }}
  .action-item {{ display: flex; align-items: flex-start; gap: 12px;
                  padding: 12px 0; border-bottom: 1px solid #f1f5f9; }}
  .action-item:last-child {{ border-bottom: none; }}
  .action-num {{ font-size: 11px; font-weight: 700; color: #94a3b8; min-width: 20px; }}
  .action-content .action-verdict {{ font-size: 12px; font-weight: 700; }}
  .action-content .action-fund {{ font-size: 13px; font-weight: 600; color: #1e293b; }}
  .action-content .action-reason {{ font-size: 11px; color: #64748b; margin-top: 2px; }}

  /* Footer */
  .footer {{ text-align: center; color: #94a3b8; font-size: 11px;
             margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>Portfolio Advisor Report</h1>
    <div class="subtitle">
      Generated {date.today().strftime('%d %B %Y')} &nbsp;·&nbsp;
      {user_profile.get('goal')} &nbsp;·&nbsp;
      {user_profile.get('horizon_years')}yr horizon &nbsp;·&nbsp;
      Risk: {user_profile.get('risk_appetite')} &nbsp;·&nbsp;
      All data is local — no portfolio data sent externally
    </div>
  </div>

  <!-- Dashboard -->
  <div class="dashboard">
    <div class="metric">
      <div class="label">Total Invested</div>
      <div class="value">{_inr(total_invested)}</div>
    </div>
    <div class="metric">
      <div class="label">Current Value</div>
      <div class="value">{_inr(total_current)}</div>
    </div>
    <div class="metric">
      <div class="label">Overall P&L</div>
      <div class="value" style="{_color_pct(total_pnl)}">{_inr(total_pnl)}</div>
      <div class="sub" style="{_color_pct(total_pnl_pct)}">{_pct(total_pnl_pct)}</div>
    </div>
    <div class="metric">
      <div class="label">Portfolio XIRR</div>
      <div class="value" style="{_color_pct(portfolio_xirr)}">{_pct(portfolio_xirr)}</div>
      <div class="sub">annualised</div>
    </div>
    <div class="metric">
      <div class="label">Active Funds</div>
      <div class="value">{len(holdings)}</div>
    </div>
  </div>

  <!-- Market Banner -->
  <div class="market-banner">
    <h3>{mkt['label']}</h3>
    <div class="benchmark-grid">
      {"".join(_bm_html(bm) for bm in benchmarks_seen.values())}
    </div>
  </div>

  <!-- Action Summary -->
  <div class="action-summary">
    <h2>Action Summary</h2>
    <div class="verdict-chips">
      {"".join(_verdict_chip_html(v, cnt) for v, cnt in sorted(verdict_counts.items(), key=lambda x: list(VERDICT_STYLE.keys()).index(x[0]) if x[0] in VERDICT_STYLE else 99))}
    </div>
  </div>

  <!-- Year-on-Year XIRR -->
  {_yoy_section_html(holdings, yoy_data)}

  <!-- Fund Cards -->
  <div class="section-title">Fund Analysis</div>
  <div class="fund-grid">
    {"".join(_fund_card_html(h, verdict_map.get(h['fund_name'], {})) for h in holdings)}
  </div>

  <!-- Action Items -->
  {_action_items_html(verdicts)}

  <div class="footer">
    Portfolio Advisor &nbsp;·&nbsp; Powered by local LLM (LM Studio) &nbsp;·&nbsp;
    Data: mfapi.in + yfinance &nbsp;·&nbsp; {date.today().strftime('%d %b %Y')}
  </div>

</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[report] ✓ Report saved → {output_path}")
    return output_path


# ── Component builders ────────────────────────────────────────────────────────

def _bm_html(bm: dict) -> str:
    name = {
        "^NSEI":       "Nifty 50",
        "^NSMIDCP":    "Nifty Midcap 150",
        "NIFTYBEES.NS":"Nifty BeES (Flexi proxy)",
        "SETFNN50.NS": "Nippon ETF (SmallCap proxy)",
        "^GSPC":       "S&P 500",
    }.get(bm["ticker"], bm["ticker"])
    return f"""
    <div class="bm-item">
      <div class="bm-name">{name}</div>
      <div class="bm-vals">
        1yr: <span style="{_color_pct(bm.get('return_1yr'))}">{_pct(bm.get('return_1yr'))}</span> &nbsp;
        3yr: <span style="{_color_pct(bm.get('return_3yr'))}">{_pct(bm.get('return_3yr'))}</span> &nbsp;
        5yr: <span style="{_color_pct(bm.get('return_5yr'))}">{_pct(bm.get('return_5yr'))}</span>
      </div>
    </div>"""


def _verdict_chip_html(verdict: str, count: int) -> str:
    s = VERDICT_STYLE.get(verdict, {"color": "#6b7280", "bg": "#f3f4f6", "icon": "•"})
    return f"""<span class="verdict-chip"
      style="background:{s['bg']};color:{s['color']};border:1px solid {s['color']}44">
      {s['icon']} {verdict}: {count}
    </span>"""


def _returns_table(h: dict) -> str:
    """Build a dynamic returns grid that adapts to available horizons."""
    # Determine which periods have data
    periods = [("1yr", "return_1yr", "benchmark_return_1yr", "alpha_1yr"),
               ("3yr", "return_3yr", "benchmark_return_3yr", "alpha_3yr"),
               ("5yr", "return_5yr", "benchmark_return_5yr", "alpha_5yr")]

    if h.get("return_10yr") is not None or h.get("benchmark_return_10yr") is not None:
        periods.append(("10yr", "return_10yr", "benchmark_return_10yr", "alpha_10yr"))
    if h.get("return_15yr") is not None or h.get("benchmark_return_15yr") is not None:
        periods.append(("15yr", "return_15yr", "benchmark_return_15yr", "alpha_15yr"))

    n_cols = len(periods)
    grid_css = f"grid-template-columns: 50px repeat({n_cols}, 1fr)"

    # Header row
    hdr = f'<div class="returns-row" style="{grid_css}"><span class="rh"></span>'
    for label, *_ in periods:
        hdr += f'<span class="rh">{label}</span>'
    hdr += '</div>'

    # Fund row
    fund_row = f'<div class="returns-row" style="{grid_css}"><span class="rh">Fund</span>'
    for _, fkey, *_ in periods:
        fund_row += f'<span class="rv" style="{_color_pct(h.get(fkey))}">{_pct(h.get(fkey))}</span>'
    fund_row += '</div>'

    # Benchmark row
    bm_row = f'<div class="returns-row" style="{grid_css}"><span class="rh">Bench</span>'
    for _, _, bkey, _ in periods:
        bm_row += f'<span class="rv" style="color:#64748b">{_pct(h.get(bkey))}</span>'
    bm_row += '</div>'

    # Alpha row
    alpha_row = f'<div class="returns-row" style="{grid_css}"><span class="rh">Alpha</span>'
    for _, _, _, akey in periods:
        alpha_row += f'<span class="rv" style="{_color_pct(h.get(akey))}">{_pct(h.get(akey))}</span>'
    alpha_row += '</div>'

    return hdr + fund_row + bm_row + alpha_row


# ── Year-on-Year XIRR Section ────────────────────────────────────────────────

def _yoy_invested_actual_chart(chart_id: str, yoy_data: dict[int, dict], height: int = 320, title: str = "") -> str:
    """Render YoY chart with invested vs actual bars + return % labels."""
    current_year = date.today().year
    sorted_years = sorted(yoy_data.keys())
    if not sorted_years:
        return '<div style="color:#94a3b8;font-size:12px;padding:16px">No year-on-year data available.</div>'

    labels = []
    invested_data = []
    actual_data = []
    return_values = []
    for y in sorted_years:
        d = yoy_data[y]
        labels.append(f"{y}*" if y == current_year else str(y))
        invested_data.append(round(d.get("invested", 0)))
        actual_data.append(round(d.get("actual", 0)))
        return_values.append(d.get("return_pct"))

    title_html = f'<div style="font-size:13px;font-weight:700;color:#334155;margin-bottom:8px">{title}</div>' if title else ""

    return f"""
    {title_html}
    <div style="height:{height}px;margin-bottom:12px">
      <canvas id="{chart_id}"></canvas>
    </div>
    <script>
    new Chart(document.getElementById('{chart_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels},
        datasets: [
          {{
            label: 'Invested',
            data: {invested_data},
            backgroundColor: '#94a3b8',
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.7,
          }},
          {{
            label: 'Actual Value',
            data: {actual_data},
            backgroundColor: {['"#22c55e"' if (return_values[i] or 0) >= 0 else '"#ef4444"' for i in range(len(sorted_years))]},
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.7,
          }}
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ labels: {{ font: {{ size: 11 }}, boxWidth: 12 }} }},
          tooltip: {{
            callbacks: {{
              label: function(item) {{
                const v = item.raw;
                const lbl = item.dataset.label;
                return lbl + ': \\u20B9' + (v >= 100000 ? (v/100000).toFixed(1) + 'L' : v.toLocaleString('en-IN'));
              }}
            }}
          }}
        }},
        scales: {{
          y: {{
            ticks: {{
              font: {{ size: 10 }},
              callback: function(v) {{
                return v >= 100000 ? (v/100000).toFixed(0) + 'L' : v >= 1000 ? (v/1000).toFixed(0) + 'K' : v;
              }}
            }},
            grid: {{ color: '#f1f5f9' }}
          }},
          x: {{ ticks: {{ font: {{ size: 11 }} }}, grid: {{ display: false }} }}
        }}
      }},
      plugins: [{{
        afterDraw(chart) {{
          const ctx = chart.ctx;
          const retVals = {[v if v is not None else 'null' for v in return_values]};
          const meta = chart.getDatasetMeta(1);
          meta.data.forEach((bar, i) => {{
            if (retVals[i] === null) return;
            ctx.save();
            const val = retVals[i];
            ctx.fillStyle = val >= 0 ? '#16a34a' : '#dc2626';
            ctx.font = 'bold 11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText((val >= 0 ? '+' : '') + val + '%', bar.x, bar.y - 6);
            ctx.restore();
          }});
        }}
      }}]
    }});
    </script>"""


def _yoy_section_html(holdings: list[dict], yoy_data: dict | None) -> str:
    """Build the Year-on-Year XIRR section with portfolio chart and fund drill-down."""
    if not yoy_data:
        return ""

    portfolio_yoy = yoy_data.get("portfolio", {})
    if not portfolio_yoy:
        return ""

    # Portfolio-level chart (invested vs actual + return % labels)
    portfolio_chart = _yoy_invested_actual_chart("yoy_portfolio", portfolio_yoy, height=320)

    # Per-fund drill-down charts (same invested vs actual format)
    fund_charts = ""
    for h in holdings:
        fund_yoy = h.get("yoy_xirr", {})
        if not fund_yoy:
            continue
        chart_id = f"yoy_fund_{abs(hash(h['fund_name'])) % 99999}"
        fund_charts += _yoy_invested_actual_chart(chart_id, fund_yoy, height=200, title=h["fund_name"])

    current_year = date.today().year
    return f"""
    <div style="margin:30px 0">
      <div class="section-title">Year-on-Year Portfolio XIRR</div>
      <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">
          Invested vs actual value at each year-end with cumulative XIRR shown above bars.
          {current_year}* = year-to-date.
        </div>
        {portfolio_chart}

        <details style="margin-top:16px">
          <summary style="font-size:12px;font-weight:600;color:#475569;cursor:pointer;
                          list-style:none;display:flex;align-items:center;gap:4px">
            ▸ Per-Fund Year-on-Year XIRR
          </summary>
          <div style="margin-top:12px">
            {fund_charts if fund_charts else '<div style="color:#94a3b8;font-size:12px">No per-fund data available.</div>'}
          </div>
        </details>
      </div>
    </div>"""


def _fund_card_html(h: dict, verdict: dict) -> str:
    v_key    = verdict.get("verdict", "CONTINUE")
    v_style  = VERDICT_STYLE.get(v_key, VERDICT_STYLE["CONTINUE"])
    trend    = (verdict.get("trend") or
                (h.get("analyst_score") or {}).get("trend") or "unknown")
    t_style  = TREND_BADGE.get(trend, TREND_BADGE["unknown"])
    score    = h.get("analyst_score") or {}

    invested    = h.get("invested_amount", 0) or 0
    current_val = h.get("current_value", 0) or 0
    pnl         = current_val - invested
    xirr        = h.get("xirr")

    # Relative performance label
    alpha_1yr = h.get("alpha_1yr")
    if alpha_1yr is not None:
        if alpha_1yr >= 0:
            rel_label = f'<span style="color:#16a34a">▲ {alpha_1yr:+.2f}% vs benchmark</span>'
        else:
            rel_label = f'<span style="color:#dc2626">▼ {alpha_1yr:+.2f}% vs benchmark</span>'
    else:
        rel_label = '<span style="color:#94a3b8">Benchmark N/A</span>'

    # Chart.js data — build dynamic labels/data for available horizons
    chart_id = f"chart_{abs(hash(h['fund_name'])) % 99999}"

    chart_labels = ["1yr", "3yr", "5yr"]
    fund_data = [h.get("return_1yr") or 0, h.get("return_3yr") or 0, h.get("return_5yr") or 0]
    bm_data   = [h.get("benchmark_return_1yr") or 0, h.get("benchmark_return_3yr") or 0, h.get("benchmark_return_5yr") or 0]

    if h.get("return_10yr") is not None or h.get("benchmark_return_10yr") is not None:
        chart_labels.append("10yr")
        fund_data.append(h.get("return_10yr") or 0)
        bm_data.append(h.get("benchmark_return_10yr") or 0)
    if h.get("return_15yr") is not None or h.get("benchmark_return_15yr") is not None:
        chart_labels.append("15yr")
        fund_data.append(h.get("return_15yr") or 0)
        bm_data.append(h.get("benchmark_return_15yr") or 0)

    def bar_color(f, b):
        return "#22c55e" if f >= b else "#f87171"

    fund_colors = [bar_color(f, b) for f, b in zip(fund_data, bm_data)]

    # Red/green flags from analyst
    flags_html = ""
    if score.get("red_flags"):
        flags_html += "".join(f'<span class="flag red">🚩 {f}</span>'
                               for f in score["red_flags"][:3])
    if score.get("green_flags"):
        flags_html += "".join(f'<span class="flag green">✅ {f}</span>'
                               for f in score["green_flags"][:3])
    if flags_html:
        flags_html = f'<div class="flags">{flags_html}</div>'

    switch_html = ""
    if verdict.get("switch_to"):
        switch_html = f'<div class="switch-to">🔄 Switch to: {verdict["switch_to"]}</div>'
    if verdict.get("consolidate_into"):
        switch_html += f'<div class="switch-to">📦 Consolidate into: {verdict["consolidate_into"]}</div>'

    category_short = (h.get("fund_category") or "").replace("Equity Scheme - ", "").replace("Hybrid Scheme - ", "").replace(" Fund", "")

    # SIP status badge
    from tools.formatting import sip_status as _sip_status, last_transaction_date as _last_transaction_date
    txns = h.get("transactions", [])
    sip_st = _sip_status(txns)
    last_txn = _last_transaction_date(txns)
    sip_badge_style = {
        "active":   ("🟢", "#16a34a", "#dcfce7"),
        "inactive": ("🔴", "#dc2626", "#fee2e2"),
        "never":    ("⚪", "#6b7280", "#f3f4f6"),
    }.get(sip_st, ("⚪", "#6b7280", "#f3f4f6"))
    sip_badge = (f'<span style="font-size:10px;padding:2px 8px;border-radius:4px;'
                 f'background:{sip_badge_style[2]};color:{sip_badge_style[1]};font-weight:600">'
                 f'{sip_badge_style[0]} SIP {sip_st.upper()}'
                 f'{(" · Last: " + last_txn) if last_txn and sip_st == "inactive" else ""}'
                 f'</span>')

    return f"""
  <div class="fund-card" style="border-left-color:{v_style['color']}">
    <div class="card-header">
      <div>
        <div class="fund-name">{h['fund_name']}</div>
        <div class="fund-meta">{category_short} &nbsp;·&nbsp; {h.get('investment_type','').upper()}</div>
        <div style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap">
          <span class="trend-badge" style="background:{t_style['color']}">{t_style['label']}</span>
          {sip_badge}
        </div>
      </div>
      <span class="verdict-badge"
        style="background:{v_style['bg']};color:{v_style['color']};border:1px solid {v_style['color']}55">
        {v_style['icon']} {v_key}
      </span>
    </div>

    <div class="financials">
      <div class="fin-item">
        <div class="fin-label">Invested</div>
        <div class="fin-val">{_inr(invested)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">Current</div>
        <div class="fin-val">{_inr(current_val)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">P&L</div>
        <div class="fin-val" style="{_color_pct(pnl)}">{_inr(pnl)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">XIRR</div>
        <div class="fin-val" style="{_color_pct(xirr)}">{_pct(xirr)}</div>
      </div>
    </div>

    <div style="font-size:11px;margin-bottom:8px">{rel_label}</div>

    <!-- Returns chart -->
    <div class="chart-wrap">
      <canvas id="{chart_id}"></canvas>
    </div>
    <script>
    new Chart(document.getElementById('{chart_id}'), {{
      type: 'bar',
      data: {{
        labels: {chart_labels},
        datasets: [
          {{
            label: 'Fund',
            data: {fund_data},
            backgroundColor: {fund_colors},
            borderRadius: 4,
          }},
          {{
            label: 'Benchmark',
            data: {bm_data},
            backgroundColor: 'rgba(148,163,184,0.5)',
            borderRadius: 4,
          }}
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ font: {{ size: 10 }}, boxWidth: 10 }} }} }},
        scales: {{
          x: {{ ticks: {{ font: {{ size: 10 }} }}, grid: {{ display: false }} }},
          y: {{
            ticks: {{ font: {{ size: 10 }}, callback: v => v+'%' }},
            grid: {{ color: '#f1f5f9' }}
          }}
        }}
      }}
    }});
    </script>

    <!-- Returns detail -->
    <div style="margin-bottom:10px">
      {_returns_table(h)}
    </div>

    {flags_html}

    {_monthly_sip_html(h.get('transactions', []))}

    <div class="reasoning" style="margin-top:10px">{verdict.get('reasoning', 'No verdict yet — run LLM analysis.')}</div>
    {switch_html}
  </div>"""


def _action_items_html(verdicts: list[dict]) -> str:
    priority_order = [
        "WITHDRAW_FULL", "WITHDRAW_PARTIAL", "SWITCH",
        "STOP_SIP", "DECREASE_SIP", "RESTART_SIP", "INCREASE_SIP", "PAUSE_SIP"
    ]
    actions = [v for v in verdicts if v.get("verdict") not in ("CONTINUE",)]
    if not actions:
        return ""
    actions.sort(key=lambda v: priority_order.index(v["verdict"])
                 if v["verdict"] in priority_order else 99)

    items_html = ""
    for i, v in enumerate(actions, 1):
        s = VERDICT_STYLE.get(v["verdict"], {"color": "#6b7280", "icon": "•"})
        switch_line = f'<div style="font-size:11px;color:#7c3aed;margin-top:2px">→ Switch to: {v["switch_to"]}</div>' if v.get("switch_to") else ""
        items_html += f"""
    <div class="action-item">
      <div class="action-num">{i}.</div>
      <div class="action-content">
        <div class="action-verdict" style="color:{s['color']}">{s['icon']} {v['verdict']}</div>
        <div class="action-fund">{v['fund_name']}</div>
        <div class="action-reason">{v.get('reasoning','')[:120]}{'...' if len(v.get('reasoning','')) > 120 else ''}</div>
        {switch_line}
      </div>
    </div>"""

    return f"""
  <div class="action-items" style="margin-bottom:24px">
    <h2>⚡ This Week's Action Items</h2>
    {items_html}
  </div>"""


# ── Portfolio XIRR helper ─────────────────────────────────────────────────────
_portfolio_xirr = compute_portfolio_xirr
