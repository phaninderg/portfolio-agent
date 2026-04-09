"""
Interactive user profile collector.
Prompts the investor for age, risk appetite, goal, horizon, and SIP budget.
Derives sensible defaults and recommended categories from the inputs.
"""

from __future__ import annotations


# ── Risk appetite → recommended fund categories ───────────────────────────────

_CATEGORY_MAP: dict[str, list[str]] = {
    "Conservative": ["Large Cap", "Index (Large)", "Aggressive Hybrid", "ELSS"],
    "Moderate":     ["Flexi Cap", "Large Cap", "Mid Cap", "ELSS", "Aggressive Hybrid"],
    "Aggressive":   ["Flexi Cap", "Mid Cap", "Small Cap", "Multi Cap", "ELSS"],
}

# Age-based horizon suggestion: retire at ~60
_RETIRE_AGE = 60


def _suggest_horizon(age: int) -> int:
    return max(3, _RETIRE_AGE - age)


def _suggest_risk(age: int) -> str:
    if age < 35:
        return "Aggressive"
    if age < 50:
        return "Moderate"
    return "Conservative"


# ── Input helpers ─────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    """Print prompt and return stripped input; return default on empty input."""
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val if val else default


def _ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            val = int(raw)
            if lo <= val <= hi:
                return val
            print(f"    Please enter a number between {lo} and {hi}.")
        except ValueError:
            print(f"    Invalid input — enter a whole number.")


def _ask_choice(prompt: str, choices: list[str], default: str) -> str:
    choices_lower = [c.lower() for c in choices]
    label = " / ".join(choices)
    while True:
        raw = _ask(f"{prompt} ({label})", default)
        if raw.lower() in choices_lower:
            return choices[choices_lower.index(raw.lower())]
        print(f"    Choose one of: {label}")


# ── Public API ────────────────────────────────────────────────────────────────

def collect_user_profile(default_profile: dict | None = None) -> dict:
    """
    Interactively collect investor profile from stdin.
    Falls back to default_profile values when the user presses Enter.
    """
    d = default_profile or {}

    print("\n" + "=" * 70)
    print("  INVESTOR PROFILE SETUP")
    print("  Press Enter to keep the value shown in [brackets]")
    print("=" * 70)

    # Age
    default_age = d.get("age", 30)
    age = _ask_int("Age", default_age, lo=18, hi=80)

    # Goal
    default_goal = d.get("goal", "Retirement corpus")
    goal = _ask("Investment goal (e.g. Retirement corpus / Child education / Wealth creation)", default_goal)

    # Horizon
    default_horizon = d.get("horizon_years", _suggest_horizon(age))
    horizon = _ask_int("Investment horizon (years)", default_horizon, lo=1, hi=40)

    # Risk appetite — suggest based on age, but let user override
    suggested_risk = _suggest_risk(age)
    default_risk = d.get("risk_appetite", suggested_risk)
    risk = _ask_choice("Risk appetite", ["Conservative", "Moderate", "Aggressive"], default_risk)

    # Monthly SIP budget
    default_budget = d.get("monthly_sip_budget", 10000)
    budget = _ask_int("Monthly SIP budget (₹)", default_budget, lo=500, hi=10_000_000)

    # Preferred categories — auto-derived from risk, but shown for awareness
    preferred = _CATEGORY_MAP[risk]

    profile = {
        "age":                age,
        "goal":               goal,
        "horizon_years":      horizon,
        "risk_appetite":      risk,
        "monthly_sip_budget": budget,
        "preferred_categories": preferred,
    }

    _print_profile_summary(profile, suggested_risk, age)
    return profile


def _print_profile_summary(profile: dict, suggested_risk: str, age: int) -> None:
    risk = profile["risk_appetite"]
    print("\n  ── Profile confirmed ──────────────────────────────────────────")
    print(f"  Age            : {profile['age']}")
    print(f"  Goal           : {profile['goal']}")
    print(f"  Horizon        : {profile['horizon_years']} years")
    print(f"  Risk Appetite  : {risk}", end="")

    if risk != suggested_risk:
        print(f"  ⚠  (age-based suggestion was {suggested_risk} — your choice overrides this)")
    else:
        print()

    print(f"  SIP Budget     : ₹{profile['monthly_sip_budget']:,}/month")
    print(f"  Fund Categories: {', '.join(profile['preferred_categories'])}")

    # Print a brief risk note so the user knows what it means
    notes = {
        "Conservative": "Focus on large caps, index funds, and hybrid funds. Capital preservation over growth.",
        "Moderate":     "Balanced mix of large + mid caps with some flexi-cap exposure.",
        "Aggressive":   "Higher allocation to mid/small caps. Suitable for 7+ year horizons.",
    }
    print(f"\n  Note: {notes[risk]}")
    print("=" * 70 + "\n")
