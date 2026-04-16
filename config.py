"""
Central configuration — all settings loaded from environment variables.
Copy .env.example to .env and fill in your values.
"""

import os
from pathlib import Path

# Load .env file if python-dotenv is installed (optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

_ROOT = Path(__file__).parent

# ── CAS PDF ──────────────────────────────────────────────────────────────────
CAS_PDF_PATH = os.getenv("CAS_PDF_PATH", str(_ROOT / "data" / "cas.pdf"))
CAS_PASSWORD = os.getenv("CAS_PASSWORD", "")

# ── User Profile Defaults (overridden by interactive prompt) ─────────────────
USER_PROFILE = {
    "age":                int(os.getenv("USER_AGE", "30")),
    "goal":               os.getenv("USER_GOAL", "Retirement corpus"),
    "horizon_years":      int(os.getenv("USER_HORIZON_YEARS", "15")),
    "risk_appetite":      os.getenv("USER_RISK_APPETITE", "Moderate"),
    "monthly_sip_budget": int(os.getenv("USER_MONTHLY_SIP_BUDGET", "25000")),
    "preferred_categories": ["Flexi Cap", "Mid Cap", "Small Cap"],
}

# ── LLM (LM Studio / Ollama / any OpenAI-compatible API) ────────────────────
LLM_BASE_URL    = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY     = os.getenv("LLM_API_KEY", "not-needed")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))


def _detect_llm_model() -> str:
    """Auto-detect the loaded chat model from the LLM server."""
    try:
        import requests as _r
        models = _r.get(f"{LLM_BASE_URL}/models", timeout=3).json().get("data", [])
        for m in models:
            mid = m.get("id", "").lower()
            if not any(k in mid for k in ("embed", "embedding", "nomic")):
                return m["id"]
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return "local-model"


LLM_MODEL = _detect_llm_model()

# ── mfapi.in ─────────────────────────────────────────────────────────────────
MFAPI_BASE   = "https://api.mfapi.in/mf"
MFAPI_SEARCH = "https://api.mfapi.in/mf/search"

# ── Tax Rules (FY 2025-26) ────────────────────────────────────────────────────
EQUITY_LTCG_RATE       = float(os.getenv("EQUITY_LTCG_RATE", "0.125"))       # 12.5%
EQUITY_STCG_RATE       = float(os.getenv("EQUITY_STCG_RATE", "0.20"))        # 20%
LTCG_EXEMPTION_LIMIT   = int(os.getenv("LTCG_EXEMPTION_LIMIT", "125000"))    # 1.25L per FY
EQUITY_LTCG_DAYS       = int(os.getenv("EQUITY_LTCG_DAYS", "365"))           # >365 days = long term

# ── Fund Discovery ────────────────────────────────────────────────────────────
FUND_DISCOVERY_CACHE_TTL_DAYS    = int(os.getenv("FUND_CACHE_TTL_DAYS", "7"))
FUND_DISCOVERY_MAX_PER_SEGMENT   = int(os.getenv("FUND_MAX_PER_SEGMENT", "15"))
FUND_DISCOVERY_MIN_TRACK_RECORD  = int(os.getenv("FUND_MIN_TRACK_RECORD", "3"))

# ── Output paths ─────────────────────────────────────────────────────────────
REPORT_HTML_PATH  = str(_ROOT / "output" / "report.html")
SCHEME_CODES_PATH = str(_ROOT / "scheme_codes.json")
