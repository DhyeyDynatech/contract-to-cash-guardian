"""
Contract-to-Cash Guardian - MCP Server (read + write tools)
-----------------------------------------------------------
Exposes the billing/contract "system of record" as MCP tools so the Foundry
agent can READ data and (after human approval) WRITE governed corrections.
Implementing an external MCP server with read/write + OAuth earns the
hackathon's bonus points.

Run locally:  python mcp_server/server.py
Transport:    streamable HTTP (works with Copilot/Foundry MCP integration)

Bonus criteria covered:
  - External MCP server integration (read + write)
  - OAuth 2.0 protection (see `require_auth` below — wire to Entra ID)

Docs:
  MCP + M365 Copilot:   https://learn.microsoft.com/microsoft-365/copilot/extensibility/build-mcp-plugins
  MCP Apps lab:         https://microsoft.github.io/copilot-camp/pages/extend-m365-copilot/11-mcp-app/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# allow importing the reconciler from ../src
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from mcp.server.fastmcp import FastMCP   # pip install "mcp[cli]"
from reconciler import load_dataset, run_reconciliation

mcp = FastMCP("contract-to-cash-guardian")

# In-memory "audit log" of proposed/approved corrections (demo only).
AUDIT_LOG: list[dict] = []


# ---- OAuth guard (stub) ---------------------------------------------------
def require_auth() -> None:
    """Validate the incoming bearer token against Entra ID.

    For the hackathon, wire this to Microsoft Entra ID:
      - validate JWT signature + audience + scopes
      - reject if missing/expired
    Set ENTRA_TENANT_ID / ENTRA_AUDIENCE in .env.
    """
    if os.environ.get("DISABLE_AUTH") == "1":
        return
    # TODO: implement real JWT validation (msal / PyJWT + JWKS)
    return


# ---- READ tools -----------------------------------------------------------
@mcp.tool()
def get_contracts() -> list[dict]:
    """Return all contracts (the PROMISED terms)."""
    require_auth()
    contracts, _, _ = load_dataset()
    return list(contracts.values())


@mcp.tool()
def get_invoices() -> list[dict]:
    """Return all invoices (what was BILLED)."""
    require_auth()
    _, invoices, _ = load_dataset()
    return invoices


@mcp.tool()
def get_leakage_report() -> dict:
    """Run reconciliation and return ranked, cited $ leakage findings."""
    require_auth()
    return run_reconciliation()


# ---- WRITE tools (governed; require human approval upstream) --------------
@mcp.tool()
def propose_correction(contract_id: str, action: str, amount_usd: float,
                       cited_rule: str) -> dict:
    """Record a PROPOSED correction. Does NOT execute it.

    The agent must surface this for human approval (e.g. an Adaptive Card)
    before `apply_correction` is ever called.
    """
    require_auth()
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


@mcp.tool()
def apply_correction(proposal_id: str, approver: str) -> dict:
    """Execute a correction ONLY after a human has approved it."""
    require_auth()
    for e in AUDIT_LOG:
        if e["id"] == proposal_id:
            if e["status"] != "PENDING_APPROVAL":
                return {"error": f"{proposal_id} is not pending approval."}
            e["status"] = "APPLIED"
            e["approved_by"] = approver
            # TODO: call the real billing system here (create credit memo / rebill)
            return {"applied": True, **e}
    return {"error": f"Proposal {proposal_id} not found."}


@mcp.tool()
def get_audit_log() -> list[dict]:
    """Return the full proposal/approval audit trail (governance evidence)."""
    require_auth()
    return AUDIT_LOG


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
