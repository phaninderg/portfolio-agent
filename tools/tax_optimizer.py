"""
Tax-optimized withdrawal engine.

Computes the optimal fund-wise redemption plan that minimizes total
tax for a given withdrawal amount. Uses FIFO lot tracking per fund
and optimizes across funds by sorting lots by effective tax rate.

Indian MF tax rules (FY 2025-26):
  Equity LTCG (>1yr): 12.5% on gains above 1.25L exemption per FY
  Equity STCG (<=1yr): 20% flat
  Debt / conservative hybrid: taxed at user's income slab rate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from tools.xirr import _to_date
from tools.formatting import is_purchase, is_redemption
from config import (
    EQUITY_LTCG_RATE,
    EQUITY_STCG_RATE,
    LTCG_EXEMPTION_LIMIT,
    EQUITY_LTCG_DAYS,
)


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class TaxLot:
    """A single FIFO lot from one purchase transaction."""
    fund_name: str
    fund_category: str
    fund_type: str            # "equity" or "debt"
    purchase_date: date
    units: float
    purchase_nav: float
    current_nav: float

    @property
    def holding_days(self) -> int:
        return (date.today() - self.purchase_date).days

    @property
    def is_long_term(self) -> bool:
        return self.holding_days > EQUITY_LTCG_DAYS

    @property
    def gain_per_unit(self) -> float:
        return self.current_nav - self.purchase_nav

    @property
    def current_value(self) -> float:
        return self.units * self.current_nav


@dataclass
class FundRedemption:
    """Aggregated redemption from a single fund."""
    fund_name: str
    fund_category: str
    redeem_amount: float      # gross amount to redeem from this fund
    gain: float
    tax: float
    net_proceeds: float
    tax_categories: dict[str, float] = field(default_factory=dict)  # category → tax amount


@dataclass
class WithdrawalPlan:
    """Complete withdrawal plan with summary."""
    fund_redemptions: list[FundRedemption] = field(default_factory=list)
    total_gross: float = 0.0
    total_gain: float = 0.0
    total_tax: float = 0.0
    total_net: float = 0.0
    ltcg_exemption_used: float = 0.0
    tax_by_category: dict[str, float] = field(default_factory=dict)


# ── Fund classification ──────────────────────────────────────────────────────

def classify_fund(fund_category: str | None) -> str:
    """Classify a fund as 'equity' or 'debt' for tax purposes."""
    if not fund_category:
        return "debt"
    cat = fund_category.lower()
    if "equity scheme" in cat:
        return "equity"
    if "index" in cat:
        return "equity"
    if "elss" in cat:
        return "equity"
    if "aggressive hybrid" in cat:
        return "equity"
    if "equity & debt" in cat or "equity and debt" in cat:
        return "equity"
    if "debt scheme" in cat:
        return "debt"
    return "debt"


# ── FIFO lot building ────────────────────────────────────────────────────────

def build_fifo_lots(holding: dict) -> list[TaxLot]:
    """
    Build FIFO lot structure for a holding from its transaction history.
    Returns remaining unconsumed lots (units > 0) sorted oldest-first.
    """
    transactions = holding.get("transactions", [])
    fund_name = holding["fund_name"]
    fund_category = holding.get("fund_category") or ""
    fund_type = classify_fund(fund_category)
    current_nav = holding.get("current_nav") or 0

    lots: list[TaxLot] = []
    sorted_txns = sorted(transactions, key=lambda t: t.get("date", ""))

    for txn in sorted_txns:
        txn_type = str(txn.get("type") or "")
        units = float(txn.get("units", 0))
        nav = float(txn.get("nav", 0))

        if units <= 0 or nav <= 0:
            continue

        if is_purchase(txn_type):
            lots.append(TaxLot(
                fund_name=fund_name,
                fund_category=fund_category,
                fund_type=fund_type,
                purchase_date=_to_date(txn["date"]),
                units=units,
                purchase_nav=nav,
                current_nav=current_nav,
            ))
        elif is_redemption(txn_type):
            units_to_consume = units
            for lot in lots:
                if lot.units <= 0:
                    continue
                consumed = min(lot.units, units_to_consume)
                lot.units -= consumed
                units_to_consume -= consumed
                if units_to_consume <= 0:
                    break

    return [lot for lot in lots if lot.units > 0.001]


# ── Tax computation ──────────────────────────────────────────────────────────

TAX_CATEGORY_LABEL = {
    "equity_ltcg": "Equity LTCG (12.5%)",
    "equity_stcg": "Equity STCG (20%)",
    "debt_slab": "Debt (slab rate)",
}


def _tax_category(lot: TaxLot) -> str:
    if lot.fund_type == "equity":
        return "equity_ltcg" if lot.is_long_term else "equity_stcg"
    return "debt_slab"


def _compute_lot_tax(
    lot: TaxLot,
    units: float,
    ltcg_exemption_remaining: float,
    debt_slab_rate: float,
) -> tuple[float, float, str]:
    """Returns (tax, ltcg_exemption_consumed, tax_category)."""
    gain = units * lot.gain_per_unit
    cat = _tax_category(lot)
    tax = 0.0
    ltcg_consumed = 0.0

    if gain <= 0:
        tax = 0.0
    elif cat == "equity_ltcg":
        taxable = gain
        if ltcg_exemption_remaining > 0:
            exempt = min(taxable, ltcg_exemption_remaining)
            taxable -= exempt
            ltcg_consumed = exempt
        tax = taxable * EQUITY_LTCG_RATE
    elif cat == "equity_stcg":
        tax = gain * EQUITY_STCG_RATE
    elif cat == "debt_slab":
        tax = gain * debt_slab_rate

    return round(tax, 2), round(ltcg_consumed, 2), cat


def _effective_tax_rate(lot: TaxLot, ltcg_remaining: float, debt_slab_rate: float) -> float:
    if lot.current_value <= 0:
        return 999.0
    tax, _, _ = _compute_lot_tax(lot, lot.units, ltcg_remaining, debt_slab_rate)
    return tax / lot.current_value


# ── Optimization ─────────────────────────────────────────────────────────────

def optimize_withdrawal(
    holdings: list[dict],
    target_amount: float,
    ltcg_exemption_used: float,
    debt_slab_rate: float,
) -> WithdrawalPlan:
    """
    Compute the tax-optimal withdrawal plan.

    Sorts all FIFO lots across all funds by effective tax rate and
    greedily fills the target amount from cheapest lots first.
    Returns plan aggregated by fund (not by individual lot).
    """
    plan = WithdrawalPlan()
    ltcg_remaining = max(0, LTCG_EXEMPTION_LIMIT - ltcg_exemption_used)

    all_lots: list[TaxLot] = []
    for h in holdings:
        if not h.get("current_nav") or h["current_nav"] <= 0:
            continue
        all_lots.extend(build_fifo_lots(h))

    if not all_lots:
        return plan

    # Track per-fund aggregates
    fund_agg: dict[str, dict] = {}
    remaining = target_amount

    while remaining > 0.01 and all_lots:
        all_lots.sort(key=lambda lot: _effective_tax_rate(lot, ltcg_remaining, debt_slab_rate))

        lot = all_lots[0]
        if lot.current_value <= 0:
            all_lots.pop(0)
            continue

        # Determine units to redeem
        tax_rate = _effective_tax_rate(lot, ltcg_remaining, debt_slab_rate)
        gross_needed = remaining / max(1 - tax_rate, 0.5)
        units_to_redeem = min(lot.units, gross_needed / lot.current_nav)

        tax, ltcg_consumed, cat = _compute_lot_tax(lot, units_to_redeem, ltcg_remaining, debt_slab_rate)
        gross = round(units_to_redeem * lot.current_nav, 2)
        gain = round(units_to_redeem * lot.gain_per_unit, 2)
        net = round(gross - tax, 2)

        # Scale down if overshooting
        if net > remaining + 0.01:
            ratio = remaining / net
            units_to_redeem *= ratio
            tax, ltcg_consumed, cat = _compute_lot_tax(lot, units_to_redeem, ltcg_remaining, debt_slab_rate)
            gross = round(units_to_redeem * lot.current_nav, 2)
            gain = round(units_to_redeem * lot.gain_per_unit, 2)
            net = round(gross - tax, 2)

        # Aggregate into fund-level
        key = lot.fund_name
        if key not in fund_agg:
            fund_agg[key] = {"fund_category": lot.fund_category, "redeem": 0, "gain": 0, "tax": 0, "net": 0, "tax_cats": {}}
        fund_agg[key]["redeem"] += gross
        fund_agg[key]["gain"] += gain
        fund_agg[key]["tax"] += tax
        fund_agg[key]["net"] += net
        cat_label = TAX_CATEGORY_LABEL.get(cat, cat)
        fund_agg[key]["tax_cats"][cat_label] = fund_agg[key]["tax_cats"].get(cat_label, 0) + tax

        plan.total_gross += gross
        plan.total_gain += gain
        plan.total_tax += tax
        plan.total_net += net
        plan.ltcg_exemption_used += ltcg_consumed
        plan.tax_by_category[cat_label] = plan.tax_by_category.get(cat_label, 0) + tax

        ltcg_remaining -= ltcg_consumed
        lot.units -= units_to_redeem
        remaining -= net

        if lot.units <= 0.001:
            all_lots.pop(0)

    # Build fund-level redemptions
    for fund_name, agg in fund_agg.items():
        plan.fund_redemptions.append(FundRedemption(
            fund_name=fund_name,
            fund_category=agg["fund_category"],
            redeem_amount=round(agg["redeem"]),
            gain=round(agg["gain"]),
            tax=round(agg["tax"]),
            net_proceeds=round(agg["net"]),
            tax_categories=agg["tax_cats"],
        ))

    plan.total_gross = round(plan.total_gross)
    plan.total_gain = round(plan.total_gain)
    plan.total_tax = round(plan.total_tax)
    plan.total_net = round(plan.total_net)
    plan.ltcg_exemption_used = round(plan.ltcg_exemption_used)

    return plan


# ── Console output ───────────────────────────────────────────────────────────

def print_withdrawal_plan(plan: WithdrawalPlan, target: float) -> None:
    """Print withdrawal plan to terminal."""
    print("\n" + "=" * 70)
    print("  TAX-OPTIMIZED WITHDRAWAL PLAN")
    print("=" * 70)
    print(f"  Target: ₹{target:,.0f}  |  Tax: ₹{plan.total_tax:,.0f}  |  Net to hand: ₹{plan.total_net:,.0f}")
    print(f"  LTCG exemption used: ₹{plan.ltcg_exemption_used:,.0f} of ₹{LTCG_EXEMPTION_LIMIT:,}")

    print(f"\n  {'Fund':<40s} {'Redeem':>10s} {'Gain':>10s} {'Tax':>8s} {'Net':>10s}")
    print(f"  {'-'*78}")
    for r in plan.fund_redemptions:
        print(f"  {r.fund_name[:40]:<40s} ₹{r.redeem_amount:>9,} ₹{r.gain:>9,} ₹{r.tax:>7,} ₹{r.net_proceeds:>9,}")
    print(f"  {'-'*78}")
    print(f"  {'TOTAL':<40s} ₹{plan.total_gross:>9,} ₹{plan.total_gain:>9,} ₹{plan.total_tax:>7,} ₹{plan.total_net:>9,}")

    if plan.tax_by_category:
        print(f"\n  Tax breakdown:")
        for cat, amount in plan.tax_by_category.items():
            if amount > 0:
                print(f"    {cat}: ₹{amount:,.0f}")

    print("\n" + "=" * 70)
