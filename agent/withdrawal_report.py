"""
Withdrawal Report — HTML dashboard for tax-optimized withdrawal plan.
Shows optimal redemption plan with tax breakdown chart.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tools.tax_optimizer import WithdrawalPlan
from config import LTCG_EXEMPTION_LIMIT


def _inr(val) -> str:
    if val is None:
        return "—"
    return f"₹{val:,.0f}"


def generate_withdrawal_report(
    plan: WithdrawalPlan,
    params: dict,
    output_path: str,
) -> str:
    """Generate self-contained HTML withdrawal report."""
    target = params["withdrawal_amount"]
    ltcg_used = params["ltcg_exemption_used"]
    slab_rate = params["debt_slab_rate"]

    # LTCG exemption bar
    ltcg_total_used = ltcg_used + plan.ltcg_exemption_used
    ltcg_pct = min(100, ltcg_total_used / LTCG_EXEMPTION_LIMIT * 100)

    # Tax breakdown for pie chart
    pie_data = {k: round(v) for k, v in plan.tax_by_category.items() if v > 0}
    pie_labels = list(pie_data.keys()) if pie_data else ["No tax"]
    pie_values = list(pie_data.values()) if pie_data else [1]
    pie_colors = ["#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6"][:len(pie_labels)]
    if not pie_data:
        pie_colors = ["#dcfce7"]

    # Fund redemption table rows
    table_rows = ""
    for r in plan.fund_redemptions:
        gain_color = "#16a34a" if r.gain >= 0 else "#dc2626"
        table_rows += f"""
        <tr>
          <td style="font-weight:600">{r.fund_name}</td>
          <td style="text-align:right;font-weight:700">{_inr(r.redeem_amount)}</td>
          <td style="text-align:right;color:{gain_color}">{_inr(r.gain)}</td>
          <td style="text-align:right;color:#dc2626">{_inr(r.tax)}</td>
          <td style="text-align:right;font-weight:700;color:#16a34a">{_inr(r.net_proceeds)}</td>
        </tr>"""

    # Fund bar chart data
    fund_names = [r.fund_name[:30] for r in plan.fund_redemptions]
    fund_amounts = [r.redeem_amount for r in plan.fund_redemptions]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tax-Optimized Withdrawal Plan — {date.today().strftime('%d %b %Y')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f8fafc; color: #1e293b; padding: 24px; }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #64748b; margin-bottom: 24px; }}
  .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 12px; margin-bottom: 24px; }}
  .metric {{ background: #fff; border-radius: 10px; padding: 16px;
             box-shadow: 0 1px 3px rgba(0,0,0,.06); text-align: center; }}
  .metric .label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric .value {{ font-size: 20px; font-weight: 800; margin-top: 4px; }}
  .section {{ background: #fff; border-radius: 12px; padding: 20px;
              box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 20px; }}
  .section-title {{ font-size: 16px; font-weight: 700; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; padding: 10px 8px; border-bottom: 2px solid #e2e8f0;
       color: #64748b; font-size: 10px; text-transform: uppercase; }}
  td {{ padding: 8px; border-bottom: 1px solid #f1f5f9; }}
  tr:last-child td {{ border-bottom: none; }}
  .total-row td {{ border-top: 2px solid #e2e8f0; font-weight: 800; font-size: 13px; }}
  .bar-track {{ background: #e2e8f0; border-radius: 6px; height: 24px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 6px; display: flex; align-items: center;
               padding-left: 8px; font-size: 11px; font-weight: 700; color: #fff; }}
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  @media (max-width: 700px) {{ .charts-row {{ grid-template-columns: 1fr; }} }}
  .footer {{ text-align: center; font-size: 10px; color: #94a3b8; padding: 24px 0 12px; }}
</style>
</head>
<body>
<div class="container">

  <h1>Tax-Optimized Withdrawal Plan</h1>
  <div class="subtitle">
    Generated {date.today().strftime('%d %b %Y')} &nbsp;·&nbsp;
    Debt slab: {int(slab_rate * 100)}%
  </div>

  <div class="dashboard">
    <div class="metric">
      <div class="label">Target Amount</div>
      <div class="value">{_inr(target)}</div>
    </div>
    <div class="metric">
      <div class="label">Gross Redemption</div>
      <div class="value">{_inr(plan.total_gross)}</div>
    </div>
    <div class="metric">
      <div class="label">Capital Gains</div>
      <div class="value" style="color:{'#16a34a' if plan.total_gain >= 0 else '#dc2626'}">{_inr(plan.total_gain)}</div>
    </div>
    <div class="metric">
      <div class="label">Total Tax</div>
      <div class="value" style="color:#dc2626">{_inr(plan.total_tax)}</div>
    </div>
    <div class="metric">
      <div class="label">Net to Hand</div>
      <div class="value" style="color:#16a34a">{_inr(plan.total_net)}</div>
    </div>
  </div>

  <!-- Charts -->
  <div class="charts-row">
    <div class="section">
      <div class="section-title">Redeem from Each Fund</div>
      <div style="height:280px">
        <canvas id="fund_chart"></canvas>
      </div>
      <script>
      new Chart(document.getElementById('fund_chart'), {{
        type: 'bar',
        data: {{
          labels: {fund_names},
          datasets: [{{
            data: {fund_amounts},
            backgroundColor: '#3b82f6',
            borderRadius: 6,
          }}]
        }},
        options: {{
          indexAxis: 'y',
          responsive: true, maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: item => '\\u20B9' + item.raw.toLocaleString('en-IN') }} }}
          }},
          scales: {{
            x: {{
              ticks: {{ font: {{ size: 10 }}, callback: v => v >= 100000 ? (v/100000).toFixed(1) + 'L' : v >= 1000 ? (v/1000).toFixed(0) + 'K' : v }},
              grid: {{ color: '#f1f5f9' }}
            }},
            y: {{ ticks: {{ font: {{ size: 10 }} }}, grid: {{ display: false }} }}
          }}
        }},
        plugins: [{{
          afterDraw(chart) {{
            const ctx = chart.ctx;
            chart.getDatasetMeta(0).data.forEach((bar, i) => {{
              const val = chart.data.datasets[0].data[i];
              const label = val >= 100000 ? (val/100000).toFixed(1) + 'L' : val >= 1000 ? (val/1000).toFixed(0) + 'K' : val;
              ctx.save();
              ctx.fillStyle = '#1e293b';
              ctx.font = 'bold 10px sans-serif';
              ctx.textAlign = 'left';
              ctx.textBaseline = 'middle';
              ctx.fillText('\\u20B9' + label, bar.x + 4, bar.y);
              ctx.restore();
            }});
          }}
        }}]
      }});
      </script>
    </div>

    <div class="section">
      <div class="section-title">Tax Breakdown</div>
      <div style="height:280px">
        <canvas id="tax_pie"></canvas>
      </div>
      <script>
      new Chart(document.getElementById('tax_pie'), {{
        type: 'doughnut',
        data: {{
          labels: {pie_labels},
          datasets: [{{ data: {pie_values}, backgroundColor: {pie_colors}, borderWidth: 0 }}]
        }},
        options: {{
          responsive: true, maintainAspectRatio: false,
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, boxWidth: 10 }} }},
            tooltip: {{ callbacks: {{ label: item => item.label + ': \\u20B9' + item.raw.toLocaleString('en-IN') }} }}
          }}
        }}
      }});
      </script>
    </div>
  </div>

  <!-- LTCG Exemption Bar -->
  <div class="section">
    <div class="section-title">LTCG Exemption Usage ({_inr(LTCG_EXEMPTION_LIMIT)} limit per FY)</div>
    <div style="font-size:11px;color:#64748b;margin-bottom:8px">
      Previously used: {_inr(ltcg_used)} &nbsp;·&nbsp;
      This withdrawal: {_inr(plan.ltcg_exemption_used)} &nbsp;·&nbsp;
      Remaining: {_inr(max(0, LTCG_EXEMPTION_LIMIT - ltcg_total_used))}
    </div>
    <div class="bar-track">
      <div class="bar-fill" style="width:{ltcg_pct:.0f}%;background:{'#16a34a' if ltcg_pct < 80 else '#f59e0b' if ltcg_pct < 100 else '#dc2626'}">
        {_inr(ltcg_total_used)} / {_inr(LTCG_EXEMPTION_LIMIT)}
      </div>
    </div>
  </div>

  <!-- Redemption Table -->
  <div class="section">
    <div class="section-title">Redemption Plan</div>
    <div style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>Fund</th>
            <th style="text-align:right">Redeem Amount</th>
            <th style="text-align:right">Capital Gain</th>
            <th style="text-align:right">Tax</th>
            <th style="text-align:right">Net Proceeds</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
          <tr class="total-row">
            <td>TOTAL</td>
            <td style="text-align:right">{_inr(plan.total_gross)}</td>
            <td style="text-align:right">{_inr(plan.total_gain)}</td>
            <td style="text-align:right;color:#dc2626">{_inr(plan.total_tax)}</td>
            <td style="text-align:right;color:#16a34a">{_inr(plan.total_net)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="footer">
    Portfolio Advisor &nbsp;·&nbsp; Tax-Optimized Withdrawal &nbsp;·&nbsp;
    {date.today().strftime('%d %b %Y')}<br>
    Tax rules: Equity LTCG 12.5% (above {_inr(LTCG_EXEMPTION_LIMIT)}), STCG 20%, Debt at slab rate.
    This is not tax advice — consult a CA for your specific situation.
  </div>

</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"[withdrawal] Report saved → {output_path}")
    return output_path
