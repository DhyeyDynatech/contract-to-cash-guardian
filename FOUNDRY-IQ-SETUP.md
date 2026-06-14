# Foundry IQ setup — the cited rulebook (Gate #2)

Goal: stand up a **Foundry IQ knowledge base** (backed by **Azure AI Search**) from
the synthetic rulebook in [`knowledge/`](knowledge/), so the agent retrieves the
**real clause/policy text** for every finding instead of asserting it.

You provide the Azure AI Search resource; the code + script do the rest.

---

## 1. Create an Azure AI Search resource (~3 min)
Azure Portal → **Create a resource** → **Azure AI Search** →
- Resource group: your existing one
- Service name: e.g. `c2c-guardian-search`
- **Pricing tier: Free** (or Basic) — fine for this rulebook
- **Create**.

After it deploys, open it and copy:
- **Url** (Overview) → `https://<name>.search.windows.net`
- **Settings → Keys** → a **primary admin key** (needed to create the index)

## 2. Put the values in `.env`
```
AZURE_SEARCH_ENDPOINT=https://<name>.search.windows.net
AZURE_SEARCH_API_KEY=<primary admin key>
AZURE_SEARCH_INDEX=c2c-rulebook
```

## 3. Build + populate the index (one command)
```powershell
.\.venv\Scripts\python.exe scripts\build_rulebook_index.py
```
It chunks [`knowledge/contract-clauses.md`](knowledge/contract-clauses.md) and
[`knowledge/pricing-policy.md`](knowledge/pricing-policy.md) by clause/section,
creates the `c2c-rulebook` index, and uploads the passages. You'll see:
```
Indexed N rulebook passages into 'c2c-rulebook':
  - Clause 4.2 — Annual CPI Escalation  (contract-clauses.md)
  - Clause 6.2 — Uptime Guarantee  (contract-clauses.md)
  ...
```

## 4. Verify retrieval works
```powershell
.\.venv\Scripts\python.exe src\foundry_iq.py
```
Should print the retrieved Clause 4.2 passage (configured=True).

## 5. Give the deployed bot the same values
The Azure App Service bot reads these from **Application settings**, not `.env`.
In the Portal → your `C2CGuardian` Web App → **Settings → Environment variables**, add:
```
AZURE_SEARCH_ENDPOINT = https://<name>.search.windows.net
AZURE_SEARCH_API_KEY  = <key>
AZURE_SEARCH_INDEX    = c2c-rulebook
```
→ **Apply** (restarts the app). Now the live agent cites real clause text.

---

### How it's wired
- The bot's [`search_rulebook`](src/agent_core.py) tool calls
  [`src/foundry_iq.py`](src/foundry_iq.py), which queries the Azure AI Search index.
- The system prompt instructs the agent: *for every finding, retrieve and quote the
  exact clause text via `search_rulebook`.*
- If the Search vars are unset, `search_rulebook` returns nothing and the agent
  falls back to the finding's clause reference — so the bot still runs.

> **Alternative (portal-native Foundry IQ):** instead of step 3 you can create a
> *Foundry IQ knowledge base* in the Azure AI Foundry portal pointing at the same
> `knowledge/` docs — it provisions an Azure AI Search index under the hood. Either
> way, set the three `AZURE_SEARCH_*` values so `search_rulebook` queries that index.
