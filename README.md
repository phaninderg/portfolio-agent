# Portfolio Advisor

A multi-agent system that analyses Indian mutual fund portfolios and provides actionable investment recommendations. Powered by a local LLM (LM Studio / Ollama) — **no portfolio data leaves your machine**.

[View sample report](https://htmlpreview.github.io/?https://github.com/phaninderg/portfolio-agent/blob/main/docs/sample_report.html) — shows all verdict types (CONTINUE, INCREASE_SIP, RESTART_SIP, DECREASE_SIP, SWITCH, STOP_SIP, WITHDRAW_PARTIAL, WITHDRAW_FULL, PAUSE_SIP) with 10yr/15yr return data and consolidation recommendations.

## What It Does

### For existing investors (`python main.py full`)
- Parses your CAS PDF (Consolidated Account Statement from MF Central / CAMS / KFintech)
- Fetches live NAV and returns (1yr / 3yr / 5yr / 10yr / 15yr) from [mfapi.in](https://www.mfapi.in/)
- Benchmarks each fund against the appropriate index (Nifty 50, Midcap 150, etc.) via yfinance
- Scores each fund with an Analyst Agent (trend, alpha, downside protection across all available horizons)
- Generates per-fund verdicts: CONTINUE, INCREASE_SIP, SWITCH, STOP_SIP, etc.
- Detects over-diversification (e.g. 3 Large Cap funds) and recommends consolidation
- SWITCH verdicts include data-backed alternatives ranked by live returns from the dynamic fund universe
- Produces an interactive HTML dashboard and a chat interface for follow-up questions

### For new investors (`python main.py recommend`)
- No CAS PDF needed — just enter your age, risk appetite, goal, and SIP budget
- Dynamically discovers Direct Growth funds from the full mfapi.in master list (~37K schemes)
- Filters, categorises into 12 segments, and ranks by live performance (1yr / 3yr / 5yr / 10yr / 15yr CAGR)
- Allocates budget across: equity (large/mid/small cap), index funds, gold, silver, international, debt, hybrid, REITs
- Enforces diversification: no single segment > 25%, minimum 5 asset classes
- Generates a personalised HTML report with allocation chart and per-fund reasoning

## Architecture

```
main.py                     Entry point — routes to the right pipeline
config.py                   All settings from environment variables (.env)

tools/
  parse_cas.py              Parse CAS PDF -> holdings list
  fetch_nav.py              Resolve fund names -> mfapi.in scheme codes -> 1yr/3yr/5yr/10yr/15yr returns
  fetch_benchmark.py        Fetch index returns (up to 15yr) from yfinance -> compute alpha
  xirr.py                   XIRR and CAGR calculations (no dependencies)
  user_profile.py           Interactive investor profile collector
  fund_discovery.py         Dynamic fund discovery: master list fetch, Direct Growth filter,
                            segment categorisation, AMC quality filter, 7-day cache
  fund_universe.py          Allocation engine, live enrichment, ranking, fund selection
  formatting.py             Shared formatters, helpers, and LLM response parsing

agent/
  orchestrator.py           Coordinates all agents in sequence
  analyst.py                Scores each fund (1 LLM call per fund, uses all available horizons)
  advisor.py                Generates verdicts (1 LLM call for all funds)
  recommender.py            New-investor recommendation engine + LLM reasoning
  report.py                 HTML dashboard for existing portfolio analysis
  recommend_report.py       HTML dashboard for new investor recommendations
  prompts.py                System prompts for advisor agent + consolidation rules
  chat.py                   Interactive Q&A chat after analysis
```

## Quick Start

### Prerequisites
- Python 3.10+
- [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible local LLM server)
- A loaded chat model in LM Studio (e.g., Llama 3, Mistral, Qwen)

### Setup

```bash
git clone <repo-url>
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
| `python main.py full` | Full analysis: parse + enrich + score + advise + report + chat | Yes | Yes |
| `python main.py data` | Parse CAS + fetch returns + benchmark comparison | Yes | No |
| `python main.py advise` | Data pipeline + single LLM verdict call | Yes | Yes |

## How the Recommend Pipeline Works

1. **Profile** — Collects age, risk appetite, goal, horizon, SIP budget
2. **Allocation** — Maps risk profile to segment percentages, adjusts for age/horizon
3. **Dynamic Discovery** — Fetches the full mfapi.in master list (~37K schemes), filters for Direct Growth (~5K), categorises into 12 segments via regex, applies AMC quality filters (tier-1/tier-2 priority), caps at 15 per segment (~168 candidates). Results cached for 7 days.
4. **Live Enrichment** — Fetches actual 1yr / 3yr / 5yr / 10yr / 15yr CAGR from mfapi.in for each candidate. Drops funds with < 3yr track record.
5. **Ranking** — Scores each fund (30% 3yr + 25% 5yr + 18% 10yr + 15% 1yr + 12% 15yr, weights redistributed when longer periods unavailable), picks the best per segment
6. **LLM Reasoning** — Local LLM personalises the reasoning for each pick (gracefully falls back to generated reasoning if LLM is unavailable)
7. **Output** — Terminal summary + `output/recommendations.json` + `output/recommend_report.html`

## How the Full Analysis Pipeline Works

1. **Parse** — Extracts holdings from CAS PDF via casparser
2. **Enrich** — Fetches live returns (1yr / 3yr / 5yr / 10yr / 15yr) from mfapi.in, benchmark returns from yfinance, computes alpha across all horizons
3. **Analyse** — Analyst agent scores each fund individually (trend, alpha, downside, consistency) using all available return horizons
4. **Advise** — Advisor agent generates verdicts considering:
   - Fund performance vs benchmark across all horizons (1yr through 15yr)
   - SIP status (active / inactive / never)
   - Portfolio consolidation — flags over-diversification (3+ funds in same category) and recommends merging into the best performer
   - SWITCH recommendations backed by top-ranked alternatives from the dynamic discovery universe
5. **Report** — HTML dashboard with charts showing all available return periods
6. **Chat** — Interactive follow-up Q&A

### Asset Segments Covered

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

All settings are loaded from environment variables. See [`.env.example`](.env.example) for the full list.

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
| [mfapi.in](https://www.mfapi.in/) | Master fund list, NAV history, 1yr/3yr/5yr/10yr/15yr returns | ~0.3s delay between calls |
| [yfinance](https://github.com/ranaroussi/yfinance) | Benchmark index returns up to 15yr (Nifty 50, Midcap 150, etc.) | ~0.5s delay between calls |
| [casparser](https://github.com/codereverser/casparser) | CAS PDF parsing | Local only |

## Privacy

- All portfolio data stays on your machine
- LLM runs locally via LM Studio — no data sent to cloud APIs
- No analytics, telemetry, or external tracking
- CAS PDF and output files are gitignored
- Fund discovery cache stored locally in `data/fund_universe_cache.json`

## Disclaimer

This is an AI-powered educational tool, not SEBI-registered investment advice. Past returns do not guarantee future performance. Always verify fund details on AMC websites and consider consulting a SEBI-registered investment advisor before investing. Mutual fund investments are subject to market risks — read all scheme-related documents carefully.

## License

[MIT](LICENSE)
