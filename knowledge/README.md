# Foundry IQ — Knowledge Base Sources

These documents are the **grounding corpus** for the Contract-to-Cash Guardian's
Foundry IQ knowledge base, so the agent can cite the **exact clause / policy text**
behind every finding (this is what satisfies the hackathon's Foundry IQ gate and
reduces hallucination).

> **Primary (live) path:** the deployed bot indexes these files into **Azure AI Search**
> via [`scripts/build_rulebook_index.py`](../scripts/build_rulebook_index.py) and queries
> them through [`src/foundry_iq.py`](../src/foundry_iq.py) — see
> **[FOUNDRY-IQ-SETUP.md](../FOUNDRY-IQ-SETUP.md)**. The portal steps below are an
> equivalent alternative (a Foundry IQ knowledge base created in the Azure AI Foundry portal).

| File | Purpose |
|---|---|
| `contract-clauses.md` | The clause library every finding cites (Clause 4.2, 5.1, 6.2, 7.3, 8.1, renewal terms). |
| `pricing-policy.md`   | The company billing/revenue policy: when escalations apply, when SLA credits are owed, renewal handling. |

**Why these match the demo:** the clause references here are the same ones in
`data/contracts.json` (e.g. `escalation_clause_ref`, `sla_credit_clause_ref`), so
when the reconciler reports "Contoso — Clause 4.2 — $816", the agent can retrieve
the literal Clause 4.2 text from this knowledge base and quote it.

> Synthetic content only. No real customer data, contracts, or PII.

## How to load (Azure AI Foundry portal)
1. Open your Foundry project → **Knowledge** (or **Knowledge bases**) → **+ Create**.
2. Add `contract-clauses.md` and `pricing-policy.md` as sources; let it index/vectorize.
3. Copy the knowledge base ID into `.env` → `FOUNDRY_IQ_KNOWLEDGE_BASE_ID`.
4. Attach it to the agent (uncomment the `knowledge_bases=[...]` line in
   `src/foundry_agent.py`, or attach it in the portal), then **Publish → Microsoft 365 Copilot**.
