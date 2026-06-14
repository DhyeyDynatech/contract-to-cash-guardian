"""
Build the Foundry IQ knowledge-base index in Azure AI Search and upload the
rulebook (knowledge/*.md), chunked by clause / policy section.

Run ONCE after you create an Azure AI Search resource and set, in .env:
    AZURE_SEARCH_ENDPOINT   https://<your-search>.search.windows.net
    AZURE_SEARCH_API_KEY    an ADMIN key (needed to create the index)
    AZURE_SEARCH_INDEX      index name (default: c2c-rulebook)

Then:
    python scripts/build_rulebook_index.py

Re-running recreates the index. After this, the bot's `search_rulebook` tool
(src/foundry_iq.py) retrieves real clause text to cite. See FOUNDRY-IQ-SETUP.md.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")
INDEX = os.environ.get("AZURE_SEARCH_INDEX", "c2c-rulebook")
KNOWLEDGE = ROOT / "knowledge"
SOURCES = ["contract-clauses.md", "pricing-policy.md"]


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) chunks at ## / ### headings."""
    chunks: list[tuple[str, str]] = []
    title, buf = None, []
    for line in text.splitlines():
        if re.match(r"^#{2,3}\s+", line):
            if title and "\n".join(buf).strip():
                chunks.append((title, "\n".join(buf).strip()))
            title = re.sub(r"^#{2,3}\s+", "", line).strip()
            buf = []
        elif title:
            buf.append(line)
    if title and "\n".join(buf).strip():
        chunks.append((title, "\n".join(buf).strip()))
    return chunks


def _slug(s: str, i: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()[:48] or "doc"
    return f"{base}-{i}"


def main() -> None:
    if not ENDPOINT or not API_KEY:
        sys.exit("Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY (ADMIN key) in .env first.")

    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchableField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
    )

    docs: list[dict] = []
    for src in SOURCES:
        path = KNOWLEDGE / src
        if not path.exists():
            print(f"  (skip, missing) {src}")
            continue
        for title, content in chunk_markdown(path.read_text(encoding="utf-8")):
            docs.append({
                "id": _slug(title, len(docs)),
                "title": title,
                "content": content,
                "source": src,
            })
    if not docs:
        sys.exit("No chunks found in knowledge/*.md")

    cred = AzureKeyCredential(API_KEY)
    index_client = SearchIndexClient(ENDPOINT, cred)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
    ]
    try:
        index_client.delete_index(INDEX)
    except Exception:
        pass
    index_client.create_index(SearchIndex(name=INDEX, fields=fields))

    SearchClient(ENDPOINT, INDEX, cred).upload_documents(documents=docs)
    print(f"Indexed {len(docs)} rulebook passages into '{INDEX}':")
    for d in docs:
        print(f"  - {d['title']}  ({d['source']})")


if __name__ == "__main__":
    main()
