# Master Services Agreement — Standard Clause Library (Synthetic)

> Synthetic reference text for the Contract-to-Cash Guardian Foundry IQ knowledge
> base. Clause numbers match the `escalation_clause_ref` and
> `sla_credit_clause_ref` values in `data/contracts.json`, so every finding the
> reconciler reports can be grounded in the exact clause text below.
> No real customer, pricing, or contract data.

---

## Section 4 — Fees and Price Adjustment

### Clause 4.2 — Annual CPI Escalation
The monthly subscription fee shall increase automatically on each anniversary of
the **Service Commencement Date** by the **Annual Escalator** stated in the Order
Form. Escalation is **compounding**: the fee for contract year *n* equals the base
monthly fee multiplied by **(1 + Annual Escalator)ⁿ**, where *n* is the number of
completed anniversaries as of the billing period.

- The escalation applies **whether or not** the supplier issues a notice; failure
  to apply it does not waive it.
- Where escalations for prior years were not billed, the supplier may issue a
  **corrected invoice** for the cumulative shortfall and apply the correct
  escalated rate to all future periods.
- *Example:* a $10,000 base fee with a 4% Annual Escalator, two anniversaries
  elapsed, bills at $10,000 × 1.04² = **$10,816.00** per month.

> Applies to: Contoso Ltd (C-1001, 4%), Adventure Works (C-1004, 5%).

### Clause 5.1 — Price Adjustment
Equivalent to Clause 4.2 for agreements executed on the **Standard Commercial
Schedule**. The supplier shall adjust the recurring fee on each anniversary by the
contracted percentage, compounding annually. Unapplied adjustments accrue and are
recoverable via a corrected invoice.

> Applies to: Fabrikam Inc (C-1002, 3%).

---

## Section 6–8 — Service Levels and Credits

All Service Level Credits below are **owed to the customer** when the measured
availability for a billing period falls below the contracted target. Credits are
**self-effecting**: the supplier is obligated to issue them proactively; a credit
not issued remains a liability of the supplier.

### Clause 6.2 — Uptime Guarantee
Target availability: **99.5%** per calendar month. For each **0.5%** (or part
thereof, rounded down to whole increments) by which measured availability falls
below target, the customer is owed a credit of **10% of the monthly fee**.

- Credit = monthly fee × 10% × floor(shortfall ÷ 0.5%).
- *Example:* 98.7% vs 99.5% target = 0.8% short → 1 full 0.5% increment → 10%
  credit. On a $20,000 fee that is **$2,000.00**.

> Applies to: Northwind Traders (C-1003).

### Clause 7.3 — Service Level Credits
Target availability: **99.9%** per calendar month. For each **0.1%** below target,
the customer is owed a credit of **5% of the monthly fee**.

- Credit = monthly fee × 5% × floor(shortfall ÷ 0.1%).
- *Example:* 99.8% vs 99.9% target = 0.1% short → 1 increment → 5% credit. On a
  $10,000 fee that is **$500.00**.

> Applies to: Contoso Ltd (C-1001), Adventure Works (C-1004).

### Clause 8.1 — Availability Credits
Target availability: **99.5%** per calendar month, **10% of the monthly fee** per
**0.5%** below target (same mechanics as Clause 6.2). Credits are calculated per
billing period and issued without requiring a customer claim.

> Applies to: Fabrikam Inc (C-1002).

---

## Section 11 — Term and Renewal

### Clause 11.1 — Term, Renewal, and Auto-Renewal
Each agreement states a **Renewal Date** and whether it **auto-renews**.

- **Auto-renew = true:** the agreement extends automatically for successive terms
  under the same commercial terms (including the escalation clause).
- **Auto-renew = false:** the agreement **does not extend automatically**. Service
  delivered or billed after the Renewal Date without a signed renewal is
  **out-of-contract exposure** — the supplier is billing without an enforceable
  agreement and should re-paper the contract before the next billing cycle.
- Annualized exposure for a lapsed non-auto-renew contract = monthly fee × 12.

> Applies to: Fabrikam Inc (C-1002) — Renewal Date 2026-01-01, auto-renew = false.
