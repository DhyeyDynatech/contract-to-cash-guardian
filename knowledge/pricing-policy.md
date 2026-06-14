# Revenue & Billing Integrity Policy (Synthetic)

> Synthetic company policy for the Contract-to-Cash Guardian Foundry IQ knowledge
> base. Describes *how* the company is required to bill, so the agent can cite a
> governing rule (not just a contract clause) for each finding. No real data.

## Purpose
Billing must reflect, exactly, three things in agreement: what the contract
**promised**, what was **delivered**, and what is **billed**. Any gap is a
revenue-integrity defect and must be surfaced, cited, and corrected — in **either
direction** (money owed *to the company* or *to the customer*).

## Policy 1 — Price escalations are mandatory and compounding
Every contracted annual escalator (Clause 4.2 / Clause 5.1) **must be applied on
each anniversary**, compounding. Billing teams may not silently omit an
escalation. Cumulative unbilled escalation is recoverable via a corrected invoice
and the escalated rate must be applied to all future periods. *Under-billing the
company is as much a defect as over-billing the customer.*

## Policy 2 — SLA credits are self-effecting liabilities
When measured availability falls below the contracted target (Clauses 6.2 / 7.3 /
8.1), the resulting service credit is **owed to the customer automatically**. The
company must issue the credit proactively in the breaching period; an
un-issued credit is an undisclosed liability and a fairness defect. Credits are
computed as: monthly fee × credit-rate × floor(shortfall ÷ step).

## Policy 3 — No billing outside an enforceable agreement
For contracts with **auto-renew = false** (Clause 11.1), billing past the Renewal
Date without a signed renewal is **out-of-contract exposure**. Account teams must
re-paper the agreement before the next cycle; until then the annualized fee is
flagged at-risk (monthly fee × 12).

## Policy 4 — Every correction is a governed proposal
No correction is ever auto-applied. The agent **proposes** a correction with the
dollar amount and the citing clause/policy, a human **approves**, and only then is
it applied — with a full audit-log entry. Findings always state whether money is
owed **to the customer** (e.g., SLA credits) or **to the company** (under-billing).

## Policy 5 — Numbers come from the system of record, never from the model
All dollar figures must originate from the reconciliation engine
(`find_revenue_leakage` / `get_leakage_report`), never from the language model.
The agent's role is to **explain and cite** computed findings, not to estimate
amounts. This is what keeps the agent's output auditable and hallucination-free.
