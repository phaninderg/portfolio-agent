"""
Recommend Report — HTML dashboard for new investor recommendations.
Self-contained HTML with Chart.js. No external dependencies beyond CDN.
"""

from __future__ import annotations
import json
from datetime import date
from pathlib import Path

from tools.fund_universe import SEGMENTS


# ── Segment colours ──────────────────────────────────────────────────────────

SEGMENT_COLOR = {
    "large_cap":     "#3b82f6",   # blue
    "mid_cap":       "#8b5cf6",   # violet
    "small_cap":     "#ec4899",   # pink
    "flexi_cap":     "#06b6d4",   # cyan
    "index":         "#6366f1",   # indigo
    "elss":          "#14b8a6",   # teal
    "gold":          "#f59e0b",   # amber
    "silver":        "#94a3b8",   # slate
    "international": "#10b981",   # emerald
    "debt":          "#64748b",   # cool gray
    "hybrid":        "#f97316",   # orange
    "reit":          "#a855f7",   # purple
}

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


def _inr(val) -> str:
    if val is None:
        return "—"
    return f"₹{val:,.0f}"


def _pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


# ── Main generator ───────────────────────────────────────────────────────────

def generate_recommend_report(result: dict, output_path: str) -> str:
    """Generate the HTML recommendation report."""
    recs      = result["recommendations"]
    profile   = result["user_profile"]
    alloc     = result["allocation"]
    llm       = result.get("llm_analysis") or {}

    total_sip = sum(r["sip_amount"] for r in recs)
    num_funds = len(recs)
    num_segs  = len(alloc)

    # Equity / Commodity / Debt / Other split
    equity_segs = {"large_cap", "mid_cap", "small_cap", "flexi_cap", "index", "elss"}
    commodity_segs = {"gold", "silver"}
    safe_segs = {"debt", "hybrid"}
    other_segs = {"international", "reit"}

    equity_pct = sum(alloc.get(s, 0) for s in equity_segs)
    commodity_pct = sum(alloc.get(s, 0) for s in commodity_segs)
    safe_pct = sum(alloc.get(s, 0) for s in safe_segs)
    other_pct = sum(alloc.get(s, 0) for s in other_segs)

    # Chart data for doughnut
    chart_labels = json.dumps([SEGMENTS.get(s, {}).get("label", s) for s in alloc])
    chart_data   = json.dumps([alloc[s] for s in alloc])
    chart_colors = json.dumps([SEGMENT_COLOR.get(s, "#94a3b8") for s in alloc])

    # Fund cards
    fund_cards_html = "\n".join(_fund_card(rec) for rec in recs)

    # Notes
    notes_html = ""
    if llm.get("important_notes"):
        notes_items = "\n".join(
            f'<li style="margin-bottom:8px;line-height:1.6">{note}</li>'
            for note in llm["important_notes"]
        )
        notes_html = f"""
    <div class="notes-section">
      <h2>Important Notes</h2>
      <ul style="padding-left:20px;color:#475569;font-size:13px">{notes_items}</ul>
    </div>"""

    summary_text = llm.get("portfolio_summary", "A diversified mutual fund portfolio tailored to your risk profile.")
    expected_returns = llm.get("expected_return_range", "")
    diversification = (llm.get("diversification_score") or "high").upper()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fund Recommendations — {date.today().strftime('%d %b %Y')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f8fafc; color: #1e293b; font-size: 14px; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}

  .header {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
             color: white; padding: 28px 32px; border-radius: 14px;
             margin-bottom: 24px; }}
  .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
  .header .subtitle {{ color: #94a3b8; font-size: 13px; line-height: 1.5; }}
  .header .strategy {{ color: #e2e8f0; font-size: 14px; margin-top: 12px;
                       line-height: 1.6; font-style: italic; }}

  .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 14px; margin-bottom: 24px; }}
  .metric {{ background: white; border-radius: 10px; padding: 18px;
             box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .metric .label {{ font-size: 10px; font-weight: 700; text-transform: uppercase;
                    letter-spacing: 0.5px; color: #64748b; margin-bottom: 6px; }}
  .metric .value {{ font-size: 20px; font-weight: 700; }}
  .metric .sub {{ font-size: 11px; color: #64748b; margin-top: 3px; }}

  .alloc-section {{ display: grid; grid-template-columns: 280px 1fr;
                    gap: 24px; margin-bottom: 24px; }}
  @media (max-width: 700px) {{ .alloc-section {{ grid-template-columns: 1fr; }} }}

  .chart-card {{ background: white; border-radius: 12px; padding: 24px;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.08);
                 display: flex; align-items: center; justify-content: center; }}
  .chart-wrap {{ width: 240px; height: 240px; }}

  .alloc-bars {{ background: white; border-radius: 12px; padding: 24px;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .alloc-bars h2 {{ font-size: 15px; font-weight: 700; margin-bottom: 16px; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
  .bar-label {{ font-size: 12px; width: 130px; color: #475569; font-weight: 600; }}
  .bar-track {{ flex: 1; height: 18px; background: #f1f5f9; border-radius: 9px;
                overflow: hidden; position: relative; }}
  .bar-fill {{ height: 100%; border-radius: 9px; transition: width 0.5s ease; }}
  .bar-pct {{ font-size: 11px; width: 40px; text-align: right; font-weight: 700;
              color: #475569; }}
  .bar-amt {{ font-size: 11px; width: 70px; text-align: right; color: #64748b; }}

  .asset-split {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
  .split-chip {{ padding: 8px 16px; border-radius: 8px; font-size: 12px;
                 font-weight: 700; }}

  .section-title {{ font-size: 17px; font-weight: 700; margin-bottom: 16px; }}
  .fund-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(480px, 1fr));
                gap: 16px; margin-bottom: 28px; }}
  .fund-card {{ background: white; border-radius: 12px; padding: 20px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.08);
                border-left: 5px solid #e2e8f0; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start;
               margin-bottom: 12px; }}
  .fund-name {{ font-size: 14px; font-weight: 700; color: #1e293b;
                max-width: 72%; line-height: 1.4; }}
  .fund-meta {{ font-size: 11px; color: #64748b; margin-top: 3px; }}
  .sip-badge {{ padding: 6px 14px; border-radius: 8px; font-size: 13px;
                font-weight: 800; white-space: nowrap; }}

  .fund-stats {{ display: grid; grid-template-columns: repeat(3, 1fr);
                 gap: 10px; margin-bottom: 12px; }}
  .stat .stat-label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase;
                       letter-spacing: 0.3px; }}
  .stat .stat-val {{ font-size: 15px; font-weight: 700; }}

  .reasoning {{ font-size: 12px; color: #475569; line-height: 1.7;
                background: #f8fafc; border-radius: 8px; padding: 12px 14px; }}

  .notes-section {{ background: white; border-radius: 12px; padding: 24px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 24px; }}
  .notes-section h2 {{ font-size: 15px; font-weight: 700; margin-bottom: 14px; }}

  .disclaimer {{ background: #fffbeb; border: 1px solid #fcd34d;
                 border-radius: 10px; padding: 16px 20px; margin-bottom: 24px;
                 font-size: 12px; color: #92400e; line-height: 1.6; }}

  .footer {{ text-align: center; color: #94a3b8; font-size: 11px;
             margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>Your Personalised Mutual Fund Portfolio</h1>
    <div class="subtitle">
      Generated {date.today().strftime('%d %B %Y')} &nbsp;·&nbsp;
      Age {profile.get('age')} &nbsp;·&nbsp;
      {profile.get('risk_appetite')} Risk &nbsp;·&nbsp;
      {profile.get('horizon_years')}yr Horizon &nbsp;·&nbsp;
      Goal: {profile.get('goal')}
    </div>
    <div class="strategy">{summary_text}</div>
  </div>

  <!-- Dashboard metrics -->
  <div class="dashboard">
    <div class="metric">
      <div class="label">Monthly SIP</div>
      <div class="value">{_inr(total_sip)}</div>
      <div class="sub">{num_funds} funds</div>
    </div>
    <div class="metric">
      <div class="label">Yearly Investment</div>
      <div class="value">{_inr(total_sip * 12)}</div>
    </div>
    <div class="metric">
      <div class="label">Segments</div>
      <div class="value">{num_segs}</div>
      <div class="sub">asset classes</div>
    </div>
    <div class="metric">
      <div class="label">Diversification</div>
      <div class="value" style="color:#16a34a">{diversification}</div>
    </div>
    {"<div class='metric'><div class='label'>Expected Returns</div><div class='value' style='font-size:14px'>" + expected_returns + "</div></div>" if expected_returns else ""}
  </div>

  <!-- Asset class split -->
  <div class="asset-split">
    <div class="split-chip" style="background:#dbeafe;color:#1e40af">
      📈 Equity: {equity_pct:.0f}%
    </div>
    <div class="split-chip" style="background:#fef3c7;color:#92400e">
      🥇 Commodities: {commodity_pct:.0f}%
    </div>
    <div class="split-chip" style="background:#e2e8f0;color:#475569">
      🏦 Debt/Hybrid: {safe_pct:.0f}%
    </div>
    <div class="split-chip" style="background:#d1fae5;color:#065f46">
      🌍 International/REIT: {other_pct:.0f}%
    </div>
  </div>

  <!-- Allocation chart + bars -->
  <div class="alloc-section">
    <div class="chart-card">
      <div class="chart-wrap">
        <canvas id="allocChart"></canvas>
      </div>
    </div>
    <div class="alloc-bars">
      <h2>Allocation Breakdown</h2>
      {_alloc_bars_html(alloc, profile.get('monthly_sip_budget', 0))}
    </div>
  </div>

  <script>
  new Chart(document.getElementById('allocChart'), {{
    type: 'doughnut',
    data: {{
      labels: {chart_labels},
      datasets: [{{
        data: {chart_data},
        backgroundColor: {chart_colors},
        borderWidth: 2,
        borderColor: '#ffffff',
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ font: {{ size: 10 }}, boxWidth: 10, padding: 8 }} }}
      }}
    }}
  }});
  </script>

  <!-- Fund Cards -->
  <div class="section-title">Recommended Funds</div>
  <div class="fund-grid">
    {fund_cards_html}
  </div>

  {notes_html}

  <!-- Disclaimer -->
  <div class="disclaimer">
    ⚠️ <strong>Disclaimer:</strong> This is AI-generated guidance based on general allocation
    principles. It is NOT SEBI-registered investment advice. Past returns do not guarantee
    future performance. Always verify fund details on the AMC website and consider consulting
    a SEBI-registered investment advisor before investing. Mutual fund investments are subject
    to market risks — read all scheme-related documents carefully.
  </div>

  <!-- Next steps -->
  <div class="notes-section">
    <h2>Next Steps</h2>
    <ul style="padding-left:20px;color:#475569;font-size:13px;line-height:2">
      <li>Open a free account on <strong>Kuvera, Groww, or Coin (Zerodha)</strong> — all offer Direct plans</li>
      <li>Start SIPs on the <strong>1st or 5th of each month</strong> — consistency matters more than timing</li>
      <li>Set up <strong>auto-debit</strong> from your bank so you never miss a SIP date</li>
      <li>Review your portfolio <strong>once every 6 months</strong> — not daily!</li>
      <li>If you get a CAS PDF later, run <code>python main.py full</code> for detailed portfolio analysis</li>
    </ul>
  </div>

  <div class="footer">
    Portfolio Advisor &nbsp;·&nbsp; New Investor Recommendations &nbsp;·&nbsp;
    AI-powered analysis &nbsp;·&nbsp; {date.today().strftime('%d %b %Y')}
  </div>

</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[recommend_report] ✓ Report saved → {output_path}")
    return output_path


# ── Component builders ───────────────────────────────────────────────────────

def _alloc_bars_html(alloc: dict[str, float], budget: int) -> str:
    """Build horizontal bar chart rows for each segment."""
    rows = ""
    max_pct = max(alloc.values()) if alloc else 1
    for seg, pct in sorted(alloc.items(), key=lambda x: -x[1]):
        label = SEGMENTS.get(seg, {}).get("label", seg)
        icon  = SEGMENT_ICON.get(seg, "•")
        color = SEGMENT_COLOR.get(seg, "#94a3b8")
        amt   = round(budget * pct / 100)
        width = pct / max_pct * 100

        rows += f"""
      <div class="bar-row">
        <div class="bar-label">{icon} {label}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:{width:.0f}%;background:{color}"></div>
        </div>
        <div class="bar-pct">{pct:.0f}%</div>
        <div class="bar-amt">{_inr(amt)}</div>
      </div>"""
    return rows


def _fund_card(rec: dict) -> str:
    """Build a single fund recommendation card."""
    seg   = rec["segment"]
    color = SEGMENT_COLOR.get(seg, "#94a3b8")
    icon  = SEGMENT_ICON.get(seg, "•")
    source = rec.get("data_source", "static")

    # Prefer live data, fallback to static approx
    if source == "live":
        r1 = _pct(rec.get("live_return_1yr")) if rec.get("live_return_1yr") is not None else "N/A"
        r3 = _pct(rec.get("live_return_3yr")) if rec.get("live_return_3yr") is not None else "N/A"
        r5 = _pct(rec.get("live_return_5yr")) if rec.get("live_return_5yr") is not None else "N/A"
        source_badge = '<span style="font-size:9px;padding:2px 6px;border-radius:3px;background:#dcfce7;color:#16a34a;font-weight:700">LIVE</span>'
    else:
        r1 = "N/A"
        r3 = _pct(rec.get("approx_3yr_cagr")) if rec.get("approx_3yr_cagr") else "N/A"
        r5 = _pct(rec.get("approx_5yr_cagr")) if rec.get("approx_5yr_cagr") else "N/A"
        source_badge = '<span style="font-size:9px;padding:2px 6px;border-radius:3px;background:#fef3c7;color:#92400e;font-weight:700">STATIC</span>'

    nav_html = f"NAV: ₹{rec['live_nav']:.2f}" if rec.get("live_nav") else ""

    reasoning = rec.get("reasoning", rec.get("why", ""))

    # Runner-up / ranking info
    rank_html = ""
    if rec.get("runner_up"):
        rank_html = f'<div style="font-size:10px;color:#64748b;margin-top:6px;font-style:italic">📊 {rec["runner_up"]}</div>'

    # Alternatives
    alt_html = ""
    if rec.get("alternatives"):
        alts = ", ".join(rec["alternatives"][:2])
        alt_html = f'<div style="font-size:10px;color:#94a3b8;margin-top:4px">Also considered: {alts}</div>'

    return f"""
    <div class="fund-card" style="border-left-color:{color}">
      <div class="card-top">
        <div>
          <div class="fund-name">{rec['fund_name']}</div>
          <div class="fund-meta">
            {icon} {rec['segment_label']} &nbsp;·&nbsp;
            {rec.get('amc', '')} &nbsp;·&nbsp;
            Benchmark: {rec.get('benchmark', 'N/A')} &nbsp;
            {source_badge}
          </div>
        </div>
        <div class="sip-badge" style="background:{color}15;color:{color}">
          {_inr(rec['sip_amount'])}/mo
        </div>
      </div>

      <div class="fund-stats" style="grid-template-columns:repeat(4,1fr)">
        <div class="stat">
          <div class="stat-label">Allocation</div>
          <div class="stat-val" style="color:{color}">{rec['allocation_pct']:.0f}%</div>
        </div>
        <div class="stat">
          <div class="stat-label">1yr Return</div>
          <div class="stat-val" style="color:#16a34a">{r1}</div>
        </div>
        <div class="stat">
          <div class="stat-label">3yr CAGR</div>
          <div class="stat-val" style="color:#16a34a">{r3}</div>
        </div>
        <div class="stat">
          <div class="stat-label">5yr CAGR</div>
          <div class="stat-val" style="color:#16a34a">{r5}</div>
        </div>
      </div>

      {"<div style='font-size:11px;color:#64748b;margin-bottom:8px'>" + nav_html + "</div>" if nav_html else ""}
      <div class="reasoning">{reasoning}</div>
      {rank_html}
      {alt_html}
    </div>"""
