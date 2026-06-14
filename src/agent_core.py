"""
Contract-to-Cash Guardian - Agent Core (custom engine agent brain)
------------------------------------------------------------------
The reasoning layer of the Copilot custom engine agent. It runs Claude (served
via Azure AI Foundry) in a native tool-use loop over the deterministic
reconciliation engine, so every dollar figure is COMPUTED, never hallucinated.

Why a custom engine agent: it surfaces in Microsoft 365 Copilot Chat without a
paid Copilot license (declarative agents are license-gated; custom engine agents
are not). This module is the orchestrator; src/bot.py wraps it as a bot endpoint.

Claude access: the official `anthropic` SDK pointed at your Foundry endpoint.
Set these (see .env.example):
  FOUNDRY_ENDPOINT     base URL, WITHOUT the /v1/messages suffix (SDK appends it)
  FOUNDRY_API_KEY      Azure AI Foundry key
  FOUNDRY_MODEL_NAME   your Claude deployment name (default: claude-opus-4-8)

Tools the agent can call (the multi-IQ chain):
  find_revenue_leakage   -> reconciler (operational truth)            READ, computed
  search_rulebook        -> Foundry IQ: cited contract-clause/policy  READ, grounded
  find_side_commitments  -> Work IQ: emailed human side-agreements    READ, live
  query_portfolio        -> Fabric IQ: structured OneLake analytics   READ, gated
  propose_correction     -> records a PENDING proposal                WRITE, governed
  apply_correction       -> executes ONLY after human approval        WRITE, governed
  get_audit_log          -> full proposal/approval trail              governance

The Fabric IQ tool is registered ONLY when fabric_iq.is_configured() is True (a
Fabric capacity is connected). With no capacity it is never offered to the model,
so the live agent behaves exactly as before — the gate stays shut (see fabric_iq).
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

import fabric_iq
import foundry_iq
import work_iq
from reconciler import run_reconciliation

# --- Claude via Azure AI Foundry -------------------------------------------
MODEL = os.environ.get("FOUNDRY_MODEL_NAME", "claude-opus-4-8")
_FOUNDRY_ENDPOINT = os.environ.get("FOUNDRY_ENDPOINT", "")
_FOUNDRY_API_KEY = os.environ.get("FOUNDRY_API_KEY", "")
MAX_TOOL_ITERATIONS = 8

# In-memory governance ledger (demo). Survives within a running process.
AUDIT_LOG: list[dict] = []


def _client() -> anthropic.Anthropic:
    """Anthropic SDK client pointed at the Foundry-hosted Claude deployment."""
    if not _FOUNDRY_ENDPOINT or not _FOUNDRY_API_KEY:
        raise RuntimeError(
            "FOUNDRY_ENDPOINT and FOUNDRY_API_KEY must be set. Copy .env.example "
            "to .env and fill in your Azure AI Foundry values."
        )
    # base_url is the Foundry base WITHOUT /v1/messages; the SDK appends the path.
    return anthropic.Anthropic(base_url=_FOUNDRY_ENDPOINT, api_key=_FOUNDRY_API_KEY)


SYSTEM_PROMPT = """\
You are the Contract-to-Cash Guardian, an enterprise revenue-integrity agent in
Microsoft 365 Copilot. You find revenue leakage by comparing what was PROMISED
(contracts + emailed commitments), BILLED (invoices), and DELIVERED (SLA data),
then propose GOVERNED corrective actions for a human to approve.

How to handle a request:
1. Call find_revenue_leakage to get the computed, ranked findings (the operational
   truth). NEVER invent or estimate amounts.
2. For each finding you discuss, call search_rulebook with its cited_rule (e.g.
   "Clause 4.2 Annual CPI Escalation") to retrieve the EXACT clause/policy text
   from the Foundry IQ knowledge base, and quote that real text as the citation.
   If search_rulebook returns nothing, fall back to the finding's cited_rule.
3. When a finding could be overridden by a human side-agreement, call
   find_side_commitments(customer) (Work IQ) to check emailed commitments (e.g.
   "we agreed to waive the Q3 increase"). If one applies, say so and adjust the
   recommendation. If it returns nothing, rely on the formal contract only.
4. Corrections are PROPOSALS only: call propose_correction, then ask the user to
   approve before apply_correction. Never claim an action executed without
   approval; after applying, mention the audit-log entry.

Always:
- Lead with the TOTAL $ at risk, then findings ranked by priority.
- Be explicit about money owed TO the customer (SLA credits) vs TO the company
  (under-billing) — a fairness/accuracy tool, not an over-billing one.
- Be concise and lead with the outcome the user asked for.
"""

_BASE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "find_revenue_leakage",
        "description": (
            "Reconcile contracts vs invoices vs SLA data and return ranked, cited "
            "dollar leakage findings with a total at risk. Call this to get real "
            "computed numbers before discussing any finding."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_rulebook",
        "description": (
            "Foundry IQ retrieval. Look up the EXACT contract-clause or pricing/SLA "
            "policy text that backs a finding so you can cite the real rule language. "
            "Pass the clause reference or topic, e.g. 'Clause 4.2 Annual CPI Escalation'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Clause ref or topic to retrieve"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_side_commitments",
        "description": (
            "Work IQ retrieval. Check Microsoft 365 email for a human side-agreement "
            "about a customer that could override the formal contract (e.g. 'we agreed "
            "to waive the Q3 increase'). Pass the customer name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"customer": {"type": "string", "description": "Customer name, e.g. 'Contoso Ltd'"}},
            "required": ["customer"],
            "additionalProperties": False,
        },
    },
    {
        "name": "propose_correction",
        "description": (
            "Record a PROPOSED correction for human approval. Does NOT execute it. "
            "Use after the user asks to draft/fix a finding; then ask them to approve."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "string", "description": "e.g. C-1001"},
                "action": {"type": "string", "description": "What the correction does"},
                "amount_usd": {"type": "number", "description": "Dollar amount"},
                "cited_rule": {"type": "string", "description": "Clause/policy that backs it"},
            },
            "required": ["contract_id", "action", "amount_usd", "cited_rule"],
            "additionalProperties": False,
        },
    },
    {
        "name": "apply_correction",
        "description": (
            "Execute a correction ONLY after a human has approved the proposal. "
            "Requires the proposal_id and the approver's name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "e.g. PROP-0001"},
                "approver": {"type": "string", "description": "Name of approving human"},
            },
            "required": ["proposal_id", "approver"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_audit_log",
        "description": "Return the full proposal/approval audit trail (governance evidence).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

# Fabric IQ tool — structured, portfolio-level analytics over the OneLake Lakehouse
# semantic model. Registered ONLY when a Fabric capacity is connected (gated).
_FABRIC_TOOL: dict[str, Any] = {
    "name": "query_portfolio",
    "description": (
        "Fabric IQ retrieval. Run a structured, PORTFOLIO-LEVEL analytics query over "
        "the OneLake Lakehouse (contracts/invoices/SLA as a semantic model). Use for "
        "aggregate questions the per-finding reconciler doesn't answer — totals, "
        "exposure by customer, renewal risk, SLA breaches across the whole book."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": list(fabric_iq.SUPPORTED_METRICS),
                "description": "Which portfolio metric to compute.",
            }
        },
        "required": ["metric"],
        "additionalProperties": False,
    },
}

# Only offer Fabric IQ to the model when its gate is open (capacity connected).
# With no Fabric capacity this stays out of the tool set, so the live agent is
# unchanged and we never claim a layer the code can't actually reach.
TOOLS: list[dict[str, Any]] = list(_BASE_TOOLS)
if fabric_iq.is_configured():
    TOOLS.append(_FABRIC_TOOL)
    # Only teach the model about Fabric IQ when the gate is open, so the proven
    # prompt is untouched in the (current) no-capacity deployment.
    SYSTEM_PROMPT += (
        "\n\nFor PORTFOLIO-LEVEL questions (totals, exposure by customer, renewal "
        "risk, SLA breaches across the whole book), call query_portfolio (Fabric IQ) "
        "for the structured answer instead of estimating from individual findings."
    )


# --- Tool handlers (the agent's hands) -------------------------------------
def _find_revenue_leakage() -> dict:
    return run_reconciliation()


def _propose_correction(contract_id: str, action: str, amount_usd: float,
                        cited_rule: str) -> dict:
    entry = {
        "id": f"PROP-{len(AUDIT_LOG) + 1:04d}",
        "contract_id": contract_id,
        "action": action,
        "amount_usd": amount_usd,
        "cited_rule": cited_rule,
        "status": "PENDING_APPROVAL",
    }
    AUDIT_LOG.append(entry)
    return entry


def _apply_correction(proposal_id: str, approver: str) -> dict:
    for e in AUDIT_LOG:
        if e["id"] == proposal_id:
            if e["status"] != "PENDING_APPROVAL":
                return {"error": f"{proposal_id} is not pending approval."}
            e["status"] = "APPLIED"
            e["approved_by"] = approver
            return {"applied": True, **e}
    return {"error": f"Proposal {proposal_id} not found."}


def _get_audit_log() -> list[dict]:
    return AUDIT_LOG


def _dispatch_tool(name: str, args: dict) -> Any:
    if name == "find_revenue_leakage":
        return _find_revenue_leakage()
    if name == "search_rulebook":
        return foundry_iq.search_rulebook(args.get("query", ""))
    if name == "find_side_commitments":
        return work_iq.find_side_commitments(args.get("customer", ""))
    if name == "query_portfolio":
        return fabric_iq.query_portfolio(args.get("metric", "summary"))
    if name == "propose_correction":
        return _propose_correction(**args)
    if name == "apply_correction":
        return _apply_correction(**args)
    if name == "get_audit_log":
        return _get_audit_log()
    return {"error": f"Unknown tool: {name}"}


# --- The agentic loop -------------------------------------------------------
def run_agent(user_text: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Run one user turn through Claude + tools.

    Returns (assistant_text, updated_history). `history` is a list of Anthropic
    message dicts; pass it back in to preserve multi-turn memory.
    """
    client = _client()
    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": user_text})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _dispatch_tool(block.name, block.input or {})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })
        messages.append({"role": "user", "content": tool_results})

    final_text = "\n".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    return final_text or "(no response)", messages


if __name__ == "__main__":
    # Quick local smoke test (needs .env / Foundry values in the environment).
    text, _ = run_agent("Find revenue leakage across the contract portfolio.")
    print(text)
