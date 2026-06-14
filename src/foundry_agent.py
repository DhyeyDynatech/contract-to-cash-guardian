"""
Foundry multi-agent orchestration for Contract-to-Cash Guardian.

This is the pro-code Azure AI Foundry layer. It defines the agents and wires in
the three Microsoft IQ layers, then exposes the orchestrator so it can be
PUBLISHED to Microsoft 365 Copilot Chat from the Foundry portal (which
auto-provisions Azure Bot Service + Entra ID -> satisfies the track's
"hosted in Copilot Chat" requirement).

Fill in the values from your Foundry project (.env). The reconciliation logic
lives in reconciler.py and is registered here as a callable tool so the agent
reasons over REAL computed findings, not hallucinated ones.

Docs:
  Foundry IQ knowledge base -> agent: https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect
  Work IQ tool (A2A/MCP):              https://learn.microsoft.com/azure/foundry/agents/how-to/tools/work-iq
  Fabric IQ ontology as knowledge:     https://learn.microsoft.com/fabric/iq/ontology/how-to-create-agent-foundry-iq
  Publish Foundry agent to Copilot:    https://learn.microsoft.com/azure/ai-foundry/agents/how-to/publish-copilot
"""
from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient          # pip install azure-ai-projects
from azure.identity import DefaultAzureCredential

from reconciler import run_reconciliation

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o")
FOUNDRY_IQ_KB_ID = os.environ.get("FOUNDRY_IQ_KNOWLEDGE_BASE_ID", "")
WORK_IQ_TOOL_ENDPOINT = os.environ.get("WORK_IQ_TOOL_ENDPOINT", "")

client = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())


# ---------------------------------------------------------------------------
# Tool the agent calls to get REAL, grounded findings (no hallucination).
# Register this as a function tool on the orchestrator agent.
# ---------------------------------------------------------------------------
def find_revenue_leakage() -> dict:
    """Reconcile contracts vs invoices vs SLA data and return ranked $ findings."""
    return run_reconciliation()


ORCHESTRATOR_INSTRUCTIONS = """
You are the Contract-to-Cash Guardian, an enterprise revenue-integrity agent.
Goal: find revenue leakage between what was PROMISED (contracts), BILLED
(invoices), and DELIVERED (SLA data), then propose GOVERNED corrective actions.

Rules:
- Always call the `find_revenue_leakage` tool to get computed findings. Never
  invent amounts. Quote the `cited_rule` and `evidence` for every item.
- Use Foundry IQ to retrieve the exact contract clause / pricing policy text
  that backs each finding, and cite it.
- Present findings ranked by priority, with the total $ at risk first.
- Corrections are PROPOSALS ONLY. Never state that an action was executed.
  Ask the user to approve before any write-back via the MCP server.
- Be explicit when money is owed TO the customer (e.g. SLA credits) vs TO the
  company (under-billing). This is a fairness/accuracy tool, not over-billing.
"""


def build_agent():
    """Create (or update) the Foundry agent with tools + IQ grounding.

    NOTE: API surface names may differ slightly by SDK version; adjust to the
    version pinned in requirements.txt. The shape below reflects the
    Foundry Agent Service function-tool + knowledge-base pattern.
    """
    tools = [find_revenue_leakage]  # register as a function tool

    # TODO: attach Foundry IQ knowledge base (clauses, pricing policy, regs)
    #   knowledge = client.agents.knowledge_bases.get(FOUNDRY_IQ_KB_ID)
    # TODO: attach Work IQ tool (A2A) to pull contracts/emails from M365
    #   work_iq = WorkIQTool(endpoint=WORK_IQ_TOOL_ENDPOINT)
    # TODO: attach Fabric IQ ontology as a Foundry IQ knowledge source
    #   (invoices/usage/SLA modeled as business entities in OneLake)
    # TODO: attach the MCP server tools for read/write (mcp_server/server.py)

    agent = client.agents.create_agent(
        model=MODEL,
        name="contract-to-cash-guardian",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        tools=tools,
        # knowledge_bases=[FOUNDRY_IQ_KB_ID],  # uncomment once KB is created
    )
    return agent


if __name__ == "__main__":
    agent = build_agent()
    print(f"Created agent: {agent.id}")
    print("Next: test in the Foundry playground, then Publish -> Microsoft 365 Copilot.")
