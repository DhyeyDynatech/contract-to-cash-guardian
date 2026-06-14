"""
Demo CLI for Contract-to-Cash Guardian.
Run:  python src/run_demo.py
Prints a ranked revenue-leakage report from the synthetic dataset.
"""
from reconciler import run_reconciliation


def main() -> None:
    report = run_reconciliation()
    print("=" * 72)
    print("  CONTRACT-TO-CASH GUARDIAN  -  Revenue Leakage Report")
    print("=" * 72)
    print(f"  As of:              {report['as_of']}")
    print(f"  Contracts reviewed: {report['contracts_reviewed']}")
    print(f"  Findings:           {report['finding_count']}")
    print(f"  TOTAL AT RISK:      ${report['total_at_risk_usd']:,.2f}")
    print("-" * 72)
    for i, f in enumerate(report["findings"], 1):
        print(f"\n  [{i}] {f['leakage_type']}  —  {f['customer']} ({f['contract_id']})")
        print(f"      Amount:        ${f['amount_usd']:,.2f}")
        print(f"      Confidence:    {f['confidence']:.0%}   Recoverability: {f['recoverability']:.0%}")
        print(f"      Priority:      {f['priority']:,.2f}")
        print(f"      Cited rule:    {f['cited_rule']}")
        print(f"      Evidence:      {f['evidence']}")
        print(f"      Action:        {f['recommended_action']}")
    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
