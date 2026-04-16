# Portfolio Advisor

A multi-agent system that analyses Indian mutual fund portfolios and provides actionable investment recommendations. Powered by a local LLM (LM Studio / Ollama) — **no portfolio data leaves your machine**.

[View sample report](https://htmlpreview.github.io/?https://github.com/phaninderg/portfolio-agent/blob/main/docs/sample_report.html) — shows all 9 verdict types, year-on-year portfolio performance, per-fund SIP analysis, 10yr/15yr return data, and consolidation recommendations.

## What It Does

### For existing investors (`python main.py full`)
- Parses your CAS PDF (Consolidated Account Statement from MF Central / CAMS / KFintech)
- Fetches live NAV and returns (1yr / 3yr / 5yr / 10yr / 15yr) from mfapi.in
- Cross-validates scheme codes against CAS transaction NAVs to catch wrong fund mappings
- Benchmarks each fund against the appropriate index (Nifty 50, Midcap 150, etc.) via yfinance with alpha across all horizons
- Computes year-on-year portfolio performance (cumulative invested vs actual value) and per-fund SIP analysis (each year's SIPs valued at year-end)
- Scores each fund with an Analyst Agent (trend, alpha, downside protection, consistency across up to 5 horizons)
- Generates per-fund verdicts: CONTINUE, INCREASE_SIP, RESTART_SIP, DECREASE_SIP, PAUSE_SIP, STOP_SIP, WITHDRAW_PARTIAL, WITHDRAW_FULL, SWITCH
- Detects over-diversification (3+ funds in same category) and recommends consolidation into the best performer
- SWITCH verdicts include data-backed alternatives ranked by live returns from the dynamic fund universe
- Produces an interactive HTML dashboard with Chart.js visualisations and a multi-line chat interface for follow-up questions

### For new investors (`python main.py recommend`)
- No CAS PDF needed — just enter your age, risk appetite, goal, and SIP budget
- Dynamically discovers Direct Growth funds from the full mfapi.in master list (~37K schemes)
- Filters to ~5K Direct Growth plans, categorises into 12 segments via regex, applies AMC quality filters (tier-1/tier-2 priority), caps at 15 per segment (~168 candidates)
- Fetches live 1yr / 3yr / 5yr / 10yr / 15yr CAGR for each candidate, drops funds with insufficient track record
- Ranks by weighted composite score (30% 3yr + 25% 5yr + 18% 10yr + 15% 1yr + 12% 15yr, weights redistributed when longer periods unavailable)
- Allocates budget across 12 asset segments with age/horizon adjustments
- LLM personalises reasoning for each pick, highlighting long-term track records
- Generates HTML report with allocation chart, per-fund reasoning, and alternatives considered

## Architecture

```
main.py                     Entry point — routes to the right pipeline
config.py                   All settings from environment variables (.env)

tools/
  parse_cas.py              Parse CAS PDF -> holdings list with full transaction history
  fetch_nav.py              Resolve fund names -> scheme codes (with NAV cross-validation)
                            -> 1yr/3yr/5yr/10yr/15yr returns from mfapi.in
  fetch_benchmark.py        Fetch benchmark index returns (up to 15yr) from yfinance -> alpha
  xirr.py                   XIRR and CAGR calculations (zero dependencies)
  yoy_xirr.py              Year-on-year XIRR: cumulative portfolio + per-fund SIP year-slice
  user_profile.py           Interactive investor profile collector
  fund_discovery.py         Dynamic fund discovery from mfapi.in master list (~37K schemes)
                            -> Direct Growth filter -> segment categorisation -> AMC quality
                            filter -> 7-day disk cache
  fund_universe.py          Allocation engine, live enrichment, composite ranking, fund selection
  formatting.py             Shared formatters, display constants (SEGMENT_ICON/COLOR),
                            LLM response parsing, portfolio stats

agent/
  orchestrator.py           Coordinates all agents: data -> research -> YoY -> analyst -> advisor
  analyst.py                Scores each fund individually (1 LLM call per fund)
  advisor.py                Generates verdicts for all funds (1 LLM call), handles consolidation
  prompts.py                Advisor system prompt with consolidation rules, SIP status rules,
                            bear market rules, and dynamic switch alternatives injection
  recommender.py            New-investor recommendation engine + LLM reasoning
  report.py                 HTML dashboard: YoY portfolio chart, fund cards with dynamic
                            return columns, Chart.js bar charts, action items
  recommend_report.py       HTML dashboard for new investor recommendations
  chat.py                   Interactive multi-line Q&A chat after analysis
```

## Quick Start

### Prerequisites
- Python 3.10+
- [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible local LLM server)
- A loaded chat model in LM Studio (e.g., Llama 3, Mistral, Qwen)

### Setup

```bash
git clone https://github.com/phaninderg/portfolio-agent.git
cd portfolio-agent

python -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required for portfolio analysis (not needed for recommend mode)
CAS_PASSWORD=YOUR_PAN_AND_DOB

# LLM server (default: LM Studio on localhost)
LLM_BASE_URL=http://localhost:1234/v1
```

### Run

```bash
# New investor — get fund recommendations (no CAS PDF needed)
python main.py recommend

# Existing investor — full portfolio analysis (needs CAS PDF in data/)
python main.py full

# Data pipeline only (parse + enrich, no LLM)
python main.py data

# Quick advisor (data + single LLM call, no per-fund scoring)
python main.py advise
```

## Commands

| Command | What it does | Needs CAS PDF | Needs LLM |
|---------|-------------|:---:|:---:|
| `python main.py recommend` | Build a new portfolio from scratch | No | Yes (optional) |
| `python main.py full` | Full analysis: parse + enrich + YoY + score + advise + report + chat | Yes | Yes |
| `python main.py data` | Parse CAS + fetch returns + benchmark comparison | Yes | No |
| `python main.py advise` | Data pipeline + single LLM verdict call | Yes | Yes |

## Full Analysis Pipeline

```
CAS PDF
  |
  v
[1. Parse] ── casparser ── holdings with full transaction history
  |
  v
[2. Enrich Returns] ── mfapi.in ── 1yr/3yr/5yr/10yr/15yr returns per fund
  |                                  (scheme codes validated against CAS NAV)
  v
[3. Enrich Benchmarks] ── yfinance ── benchmark returns + alpha per horizon
  |
  v
[4. Year-on-Year XIRR] ── NAV history ── cumulative portfolio XIRR + per-fund year-slice
  |
  v
[5. Analyst Agent] ── 1 LLM call per fund ── trend, alpha score, flags
  |
  v
[6. Advisor Agent] ── 1 LLM call all funds ── verdicts + consolidation + switch alternatives
  |
  v
[7. HTML Report] ── Chart.js ── YoY chart, fund cards, action items
  |
  v
[8. Interactive Chat] ── streaming LLM ── follow-up Q&A with full portfolio context
```

## Recommend Pipeline

```
Interactive Profile (age, risk, goal, horizon, budget)
  |
  v
[1. Allocation] ── risk profile + age/horizon adjustments ── segment percentages
  |
  v
[2. Discovery] ── mfapi.in master list ── 37K schemes -> 5K Direct Growth -> 168 candidates
  |                (cached 7 days)
  v
[3. Live Enrichment] ── mfapi.in ── 1yr/3yr/5yr/10yr/15yr CAGR per candidate
  |
  v
[4. Ranking] ── weighted composite score ── best fund per segment
  |
  v
[5. LLM Reasoning] ── personalised rationale per pick
  |
  v
[6. HTML Report] ── allocation chart + per-fund cards with alternatives
```

## Report Features

### Year-on-Year Portfolio Performance
- **Portfolio level**: Cumulative invested vs actual value at each Dec 31, with return % labels
- **Per-fund drill-down**: Year-slice SIP analysis — only that year's investments valued at year-end, showing XIRR for each year independently
- Green bars for gains, red for losses, current year marked with asterisk

### Fund Analysis Cards
- Dynamic return columns (3 to 5 columns: 1yr/3yr/5yr + 10yr/15yr when available)
- Fund vs benchmark bar chart per fund
- Returns detail table: Fund / Benchmark / Alpha rows
- Analyst flags (red/green) and trend badges
- SIP status badges (active/inactive/never) with last purchase date
- Monthly SIP history (expandable)

### Verdicts
9 possible actions: CONTINUE, INCREASE_SIP, RESTART_SIP, DECREASE_SIP, PAUSE_SIP, STOP_SIP, WITHDRAW_PARTIAL, WITHDRAW_FULL, SWITCH — each with confidence level and reasoning.

### Consolidation
Detects when 3+ funds overlap in the same category. Recommends merging into the best performer with `consolidate_into` field.

### SWITCH Alternatives
When recommending SWITCH, injects top-ranked alternatives per segment from the dynamic discovery cache — real funds with live return data, not LLM guesswork.

## Asset Segments

| Segment | Conservative | Moderate | Aggressive |
|---------|:-----------:|:--------:|:----------:|
| Large Cap | 15% | 10% | 5% |
| Index Funds | 20% | 15% | 10% |
| Flexi Cap | 10% | 15% | 15% |
| Mid Cap | 5% | 15% | 20% |
| Small Cap | — | 5% | 15% |
| Gold | 15% | 10% | 5% |
| Silver | — | — | 5% |
| Debt / Fixed Income | 20% | 10% | 5% |
| Aggressive Hybrid | 10% | 5% | — |
| International | 5% | 10% | 10% |
| REITs | — | 5% | 5% |

Allocations are further adjusted based on age and investment horizon.

## Configuration

All settings loaded from environment variables. See [`.env.example`](.env.example) for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `CAS_PDF_PATH` | `data/cas.pdf` | Path to your CAS PDF |
| `CAS_PASSWORD` | *(empty)* | PDF password (PAN + DOB as DDMMYYYY) |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible LLM endpoint |
| `LLM_API_KEY` | `not-needed` | API key (not needed for LM Studio) |
| `LLM_TEMPERATURE` | `0.3` | LLM temperature (lower = more deterministic) |
| `USER_AGE` | `30` | Default age for profile |
| `USER_GOAL` | `Retirement corpus` | Default investment goal |
| `USER_HORIZON_YEARS` | `15` | Default horizon in years |
| `USER_RISK_APPETITE` | `Moderate` | Conservative / Moderate / Aggressive |
| `USER_MONTHLY_SIP_BUDGET` | `25000` | Default SIP budget in INR |
| `FUND_CACHE_TTL_DAYS` | `7` | Days to cache the discovered fund universe |
| `FUND_MAX_PER_SEGMENT` | `15` | Max fund candidates per segment |
| `FUND_MIN_TRACK_RECORD` | `3` | Minimum fund age (years) to consider |

## Data Sources

| Source | Used For | Rate Limit |
|--------|----------|-----------|
| [mfapi.in](https://www.mfapi.in/) | Master fund list (~37K schemes), NAV history, returns up to 15yr, scheme code resolution | ~0.3s delay between calls |
| [yfinance](https://github.com/ranaroussi/yfinance) | Benchmark index returns up to 15yr (Nifty 50, Midcap 150, S&P 500, etc.) | ~0.5s delay between calls |
| [casparser](https://github.com/codereverser/casparser) | CAS PDF parsing into structured holdings + transactions | Local only |

## Privacy

- All portfolio data stays on your machine
- LLM runs locally via LM Studio — no data sent to cloud APIs
- No analytics, telemetry, or external tracking
- CAS PDF, output files, and fund discovery cache are gitignored

## Disclaimer

This is an AI-powered educational tool, not SEBI-registered investment advice. Past returns do not guarantee future performance. Always verify fund details on AMC websites and consider consulting a SEBI-registered investment advisor before investing. Mutual fund investments are subject to market risks — read all scheme-related documents carefully.

## License

[MIT](LICENSE)
