"""
Contract-to-Cash Guardian - Reconciliation Engine
--------------------------------------------------
Core logic that compares PROMISED (contracts) vs BILLED (invoices) vs
DELIVERED (SLA events) and produces ranked, cited revenue-leakage findings.

This module is intentionally pure-Python and dependency-free so it can be:
  - run standalone for the demo (`python src/run_demo.py`)
  - called as a tool by the Foundry agent
  - exposed as MCP tools (see mcp_server/server.py)

No external services required -> perfect for a synthetic-data hackathon demo.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASOF = date(2026, 6, 30)  # demo "today"; the latest billed period end


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load(name: str) -> list[dict[str, Any]]:
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def load_dataset() -> tuple[dict, list, list]:
    contracts = {c["contract_id"]: c for c in _load("contracts.json")}
    invoices = _load("invoices.json")
    sla_events = _load("sla_events.json")
    return contracts, invoices, sla_events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def _anniversaries(start: date, asof: date) -> int:
    """Number of full contract years elapsed on/before `asof`."""
    count, y = 0, 1
    while True:
        try:
            anniv = date(start.year + y, start.month, min(start.day, 28))
        except ValueError:
            break
        if anniv <= asof:
            count, y = count + 1, y + 1
        else:
            break
    return count


def _expected_price(base: float, escalator_pct: float, years: int) -> float:
    return round(base * ((1 + escalator_pct / 100.0) ** years), 2)


def _two_percentages(text: str) -> tuple[float, float]:
    """Extract (credit_pct, step_pct) from an SLA credit terms string."""
    nums = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*%", text or "")]
    credit_pct = nums[0] if len(nums) >= 1 else 0.0
    step_pct = nums[1] if len(nums) >= 2 else 0.1
    return credit_pct, max(step_pct, 0.01)


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    contract_id: str
    customer: str
    leakage_type: str
    amount_usd: float
    confidence: float          # 0..1
    recoverability: float      # 0..1 (claim window / strength)
    cited_rule: str
    evidence: str
    recommended_action: str

    @property
    def priority(self) -> float:
        return round(self.amount_usd * self.confidence * self.recoverability, 2)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------
def detect_price_escalation(contracts, invoices) -> list[Finding]:
    out: list[Finding] = []
    for inv in invoices:
        c = contracts.get(inv["contract_id"])
        if not c or not c.get("annual_escalator_pct"):
            continue
        years = _anniversaries(_parse_date(c["start_date"]), ASOF)
        expected = _expected_price(c["base_monthly_price"], c["annual_escalator_pct"], years)
        gap = round(expected - inv["amount_billed"], 2)
        if gap > 1.0:
            out.append(Finding(
                contract_id=c["contract_id"],
                customer=c["customer"],
                leakage_type="Un-applied price escalation",
                amount_usd=gap,
                confidence=0.95,
                recoverability=0.9,
                cited_rule=c.get("escalation_clause_ref", "N/A"),
                evidence=(f"{years}x annual escalator of {c['annual_escalator_pct']}% => "
                          f"expected ${expected:,.2f}, billed ${inv['amount_billed']:,.2f} "
                          f"on {inv['invoice_id']}"),
                recommended_action=(f"Issue corrected invoice for ${gap:,.2f} to {c['customer']} "
                                    f"and apply escalation to future periods."),
            ))
    return out


def detect_sla_credits(contracts, sla_events) -> list[Finding]:
    out: list[Finding] = []
    for ev in sla_events:
        c = contracts.get(ev["contract_id"])
        if not c:
            continue
        shortfall = round(c["sla_uptime_target_pct"] - ev["actual_uptime_pct"], 4)
        if shortfall <= 0 or ev.get("credit_issued", 0) > 0:
            continue
        credit_pct, step_pct = _two_percentages(c.get("sla_credit_terms", ""))
        buckets = math.floor(shortfall / step_pct)
        owed = round(c["base_monthly_price"] * (credit_pct / 100.0) * buckets, 2)
        if owed > 1.0:
            out.append(Finding(
                contract_id=c["contract_id"],
                customer=c["customer"],
                leakage_type="SLA credit owed (not issued)",
                amount_usd=owed,
                confidence=0.9,
                recoverability=0.95,
                cited_rule=c.get("sla_credit_clause_ref", "N/A"),
                evidence=(f"Uptime {ev['actual_uptime_pct']}% vs target "
                          f"{c['sla_uptime_target_pct']}% ({shortfall:.2f}% short, "
                          f"{buckets} x {credit_pct}% credit) in {ev['period']}"),
                recommended_action=(f"Issue ${owed:,.2f} service credit to {c['customer']} "
                                    f"per {c.get('sla_credit_clause_ref')}."),
            ))
    return out


def detect_renewal_lapse(contracts, invoices) -> list[Finding]:
    out: list[Finding] = []
    billed_ids = {i["contract_id"] for i in invoices}
    for c in contracts.values():
        if c.get("auto_renew", True):
            continue
        renewal = _parse_date(c["renewal_date"])
        if renewal <= ASOF and c["contract_id"] in billed_ids:
            at_risk = round(c["base_monthly_price"] * 12, 2)  # annualized exposure
            out.append(Finding(
                contract_id=c["contract_id"],
                customer=c["customer"],
                leakage_type="Renewal lapse risk (no auto-renew)",
                amount_usd=at_risk,
                confidence=0.7,
                recoverability=0.8,
                cited_rule="Contract term: auto_renew = false; renewal date passed",
                evidence=(f"Renewal date {c['renewal_date']} passed; auto-renew disabled; "
                          f"still billing without a renewed agreement."),
                recommended_action=(f"Trigger renewal outreach to {c['customer']} to re-paper "
                                    f"the contract before churn / unbilled exposure grows."),
            ))
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_reconciliation() -> dict[str, Any]:
    contracts, invoices, sla_events = load_dataset()
    findings: list[Finding] = []
    findings += detect_price_escalation(contracts, invoices)
    findings += detect_sla_credits(contracts, sla_events)
    findings += detect_renewal_lapse(contracts, invoices)
    findings.sort(key=lambda f: f.priority, reverse=True)

    return {
        "as_of": ASOF.isoformat(),
        "contracts_reviewed": len(contracts),
        "total_at_risk_usd": round(sum(f.amount_usd for f in findings), 2),
        "finding_count": len(findings),
        "findings": [{**asdict(f), "priority": f.priority} for f in findings],
    }


if __name__ == "__main__":
    import pprint
    pprint.pp(run_reconciliation())
