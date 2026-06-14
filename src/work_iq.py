"""
Work IQ — the human-promised side (live IQ layer).
--------------------------------------------------
The "promised" layer isn't only the signed PDF — real commitments hide in email
("we agreed to waive Contoso's Q3 increase"). Work IQ surfaces those side-
agreements from Microsoft 365 so the reconciliation reflects what was actually
promised, not just the formal contract.

Implementation: real Microsoft Graph retrieval (app-only, Mail.Read) over a
mailbox of synthetic side-agreement emails. The agent calls `find_side_commitments`
when a finding could be overridden by a human promise.

Status: LIVE in this deployment (Mail.Read application permission + admin consent
configured on the Graph app, retrieval verified). Self-gating: if unconfigured,
find_side_commitments() returns [] and the agent relies on the formal contract only
— so claims always match what the code can actually do.

Configure:
  GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET   app with Mail.Read
  WORK_IQ_MAILBOX                                          mailbox UPN to read
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Load .env for standalone runs (the bot already loads it before import; this is
# a no-op on Azure App Service where values come from App Settings).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "")
CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")
MAILBOX = os.environ.get("WORK_IQ_MAILBOX", "")

# Words that signal a commercial side-commitment in an email.
_COMMITMENT_HINTS = ("waive", "waiver", "discount", "credit", "hold", "freeze",
                     "no increase", "skip the escalation", "honor", "as agreed")


def is_configured() -> bool:
    return bool(TENANT_ID and CLIENT_ID and CLIENT_SECRET and MAILBOX)


def _graph_token() -> str | None:
    try:
        import msal
    except ImportError:
        return None
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")


def find_side_commitments(customer: str, top: int = 5) -> list[dict[str, Any]]:
    """Search the mailbox for emailed side-commitments about a customer.

    Returns [{subject, from, received, preview, web_link}]. Empty list if Work IQ
    isn't configured (graceful fallback to the formal contract only).
    """
    if not is_configured():
        return []
    try:
        import requests
    except ImportError:
        return []

    token = _graph_token()
    if not token:
        return []

    # Full-text $search for the customer, then keep emails that read like a
    # commitment (fall back to all customer hits so the agent can judge).
    url = f"https://graph.microsoft.com/v1.0/users/{MAILBOX}/messages"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "ConsistencyLevel": "eventual",
        },
        params={
            "$search": f'"{customer}"',
            "$top": "25",
            "$select": "subject,from,receivedDateTime,bodyPreview,webLink",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        return []

    messages = resp.json().get("value", [])

    def _is_commitment(m: dict) -> bool:
        blob = f"{m.get('subject', '')} {m.get('bodyPreview', '')}".lower()
        return any(h in blob for h in _COMMITMENT_HINTS)

    flagged = [m for m in messages if _is_commitment(m)]
    chosen = flagged or messages

    out: list[dict[str, Any]] = []
    for m in chosen[:top]:
        sender = (m.get("from") or {}).get("emailAddress", {}).get("address", "")
        out.append({
            "subject": m.get("subject", ""),
            "from": sender,
            "received": m.get("receivedDateTime", ""),
            "preview": (m.get("bodyPreview") or "").strip(),
            "web_link": m.get("webLink", ""),
        })
    return out


if __name__ == "__main__":
    import json
    print(f"configured={is_configured()}")
    print(json.dumps(find_side_commitments("Contoso Ltd"), indent=2, default=str))
