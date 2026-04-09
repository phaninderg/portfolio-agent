# Portfolio Advisor

A multi-agent system that analyses Indian mutual fund portfolios and provides actionable investment recommendations. Powered by a local LLM (LM Studio / Ollama) — **no portfolio data leaves your machine**.

## What It Does

### For existing investors (`python main.py full`)
- Parses your CAS PDF (Consolidated Account Statement from MF Central / CAMS / KFintech)
- Fetches live NAV and returns from [mfapi.in](https://www.mfapi.in/)
- Benchmarks each fund against the appropriate index (Nifty 50, Midcap 150, etc.) via yfinance
- Scores each fund with an Analyst Agent (trend, alpha, downside protection)
- Generates per-fund verdicts: CONTINUE, INCREASE_SIP, SWITCH, STOP_SIP, etc.
- Produces an interactive HTML dashboard and a chat interface for follow-up questions

### For new investors (`python main.py recommend`)
- No CAS PDF needed — just enter your age, risk appetite, goal, and SIP budget
- Fetches **live returns** from mfapi.in for 30+ curated funds across 12 asset segments
- Ranks funds by actual current performance (weighted composite: 50% 3yr + 30% 5yr + 20% 1yr)
- Allocates budget across: equity (large/mid/small cap), index funds, gold, silver, international, debt, hybrid, REITs
- Enforces diversification: no single segment > 25%, minimum 5 asset classes
- Generates a personalised HTML report with allocation chart and per-fund reasoning

## Architecture

```
main.py                     Entry point — routes to the right pipeline
config.py                   All settings from environment variables (.env)

tools/
  parse_cas.py              Parse CAS PDF → holdings list
  fetch_nav.py              Resolve fund names → mfapi.in scheme codes → live returns
  fetch_benchmark.py        Fetch index returns from yfinance → compute alpha
  xirr.py                   XIRR and CAGR calculations (no dependencies)
  user_profile.py           Interactive investor profile collector
  fund_universe.py          Curated fund database + allocation engine + live enrichment
  formatting.py             Shared formatters, helpers, and LLM response parsing

agent/
  orchestrator.py           Coordinates all agents in sequence
  analyst.py                Scores each fund (1 LLM call per fund)
  advisor.py                Generates verdicts (1 LLM call for all funds)
  recommender.py            New-investor recommendation engine + LLM reasoning
  report.py                 HTML dashboard for existing portfolio analysis
  recommend_report.py       HTML dashboard for new investor recommendations
  prompts.py                System prompts for advisor agent
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
3. **Live Data** — Fetches actual current returns from mfapi.in for all 30+ candidate funds using pre-configured scheme codes
4. **Ranking** — Scores each fund (50% 3yr CAGR + 30% 5yr CAGR + 20% 1yr return), picks the best per segment
5. **LLM Reasoning** — Local LLM personalises the reasoning for each pick (gracefully falls back to static reasoning if LLM is unavailable)
6. **Output** — Terminal summary + `output/recommendations.json` + `output/recommend_report.html`

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

## Data Sources

| Source | Used For | Rate Limit |
|--------|----------|-----------|
| [mfapi.in](https://www.mfapi.in/) | Fund NAV history, returns, scheme codes | ~0.3s delay between calls |
| [yfinance](https://github.com/ranaroussi/yfinance) | Benchmark index returns (Nifty 50, Midcap 150, etc.) | ~0.5s delay between calls |
| [casparser](https://github.com/codereverser/casparser) | CAS PDF parsing | Local only |

## Privacy

- All portfolio data stays on your machine
- LLM runs locally via LM Studio — no data sent to cloud APIs
- No analytics, telemetry, or external tracking
- CAS PDF and output files are gitignored

## Disclaimer

This is an AI-powered educational tool, not SEBI-registered investment advice. Past returns do not guarantee future performance. Always verify fund details on AMC websites and consider consulting a SEBI-registered investment advisor before investing. Mutual fund investments are subject to market risks — read all scheme-related documents carefully.

## License

[MIT](LICENSE)
