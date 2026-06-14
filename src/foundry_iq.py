"""
Foundry IQ — grounded, cited rulebook (the project's required IQ layer).
----------------------------------------------------------------------
Agentic knowledge retrieval over the contract clauses + pricing/SLA policy.
When the reconciler flags a finding (e.g. "Contoso under-billed $816 — missed CPI
escalation"), the agent calls `search_rulebook` to pull the ACTUAL clause text
(Clause 4.2 — Annual CPI Escalation) from a Foundry IQ knowledge base and uses it
as the citation. Every finding is therefore backed by real contract language, not
asserted by the model — which is what kills hallucination.

Implementation: a Foundry IQ knowledge base is backed by Azure AI Search. This
module performs real retrieval against that Search index. Populate the index with
`scripts/build_rulebook_index.py` (sources: knowledge/*.md).

Configure (add these at deploy time / in .env / App Service settings):
  AZURE_SEARCH_ENDPOINT   https://<your-search>.search.windows.net
  AZURE_SEARCH_API_KEY    query or admin key
  AZURE_SEARCH_INDEX      index name (default: c2c-rulebook)

If unconfigured, search_rulebook() returns [] and the agent falls back to the
reconciler's clause reference — so the bot still runs without the KB.
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

ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")
INDEX = os.environ.get("AZURE_SEARCH_INDEX", "c2c-rulebook")


def is_configured() -> bool:
    return bool(ENDPOINT and API_KEY)


def search_rulebook(query: str, top: int = 3) -> list[dict[str, Any]]:
    """Retrieve cited clause / policy passages from the Foundry IQ knowledge base.

    Returns a list of {clause, text, source, score}. Empty list if the knowledge
    base isn't configured or the SDK isn't installed (graceful fallback).
    """
    if not is_configured():
        return []
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
    except ImportError:
        return []

    client = SearchClient(ENDPOINT, INDEX, AzureKeyCredential(API_KEY))
    results = client.search(search_text=query, top=top)

    passages: list[dict[str, Any]] = []
    for r in results:
        passages.append({
            "clause": (r.get("title") or "").strip(),
            "text": (r.get("content") or "").strip(),
            "source": r.get("source") or "",
            "score": round(float(r.get("@search.score", 0.0)), 3),
        })
    return passages


if __name__ == "__main__":
    import json
    q = "Clause 4.2 annual CPI escalation"
    print(f"configured={is_configured()} | query={q!r}")
    print(json.dumps(search_rulebook(q), indent=2, default=str))
