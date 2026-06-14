# Work IQ setup — emailed side-agreements (the human-promised side)

Goal: let the agent surface **emailed side-commitments** that can override the formal
contract — e.g. *"we agreed to waive Contoso's Q3 increase"* — so the **promised** side
of the reconciliation reflects what was *actually* agreed, not just the signed PDF.

Work IQ reads a mailbox via **Microsoft Graph** (app-only, `Mail.Read`); the agent calls
it through the `find_side_commitments` tool whenever a finding could be overridden by a
human promise.

---

## Status: LIVE

Configured and **verified** in this deployment. Self-gating: if the four `GRAPH_*` /
`WORK_IQ_MAILBOX` values are unset, `find_side_commitments()` returns `[]` and the agent
relies on the formal contract only — so claims always match what the code can actually
reach (the same graceful-degradation pattern as Foundry IQ and Fabric IQ).

## What you need
- A **Microsoft Entra app registration** (you can reuse the bot's app).
- **Microsoft Graph → Mail.Read (Application)** permission with **admin consent granted**.
- A **client secret** on that app.
- A **mailbox UPN** to read (holding synthetic side-agreement emails for the demo).

---

## Steps

### 1. Grant the app Mail.Read (application)
Entra portal → **App registrations** → your app → **API permissions** → **Add a permission**
→ **Microsoft Graph** → **Application permissions** → search **Mail.Read** → add →
**Grant admin consent**.
> Use **Application** (app-only), not Delegated — the bot reads the mailbox without a
> signed-in user.

### 2. Create a client secret
Same app → **Certificates & secrets** → **New client secret** → copy the value.

### 3. (Demo) plant a synthetic side-agreement email
In the mailbox you'll read, seed a synthetic message such as:
> **Subject:** Contoso Q3 pricing — agreed to waive the increase
> **Body:** As discussed with Contoso, we agreed to **waive** their Q3 annual price
> escalation this cycle. Please **hold** the increase.

Hint words like *waive, waiver, discount, credit, hold, freeze, no increase, as agreed*
are what the agent's commitment filter looks for.
> **Synthetic only** — no real customer email, data, or PII.

### 4. Set the four values
In `.env` for local, **and** in the App Service **Environment variables** for the live bot:
```
GRAPH_TENANT_ID=<entra tenant id>
GRAPH_CLIENT_ID=<app client id>
GRAPH_CLIENT_SECRET=<client secret>
WORK_IQ_MAILBOX=<mailbox UPN, e.g. someone@yourtenant.com>
```

---

## Verify retrieval works
```powershell
.\.venv\Scripts\python.exe src\work_iq.py
```
With all four set, this prints `configured=True` and the matched side-agreement email(s)
for "Contoso Ltd". With any value unset, it prints `configured=False` and `[]` (the gate
staying shut) — never an error.

---

## How it's wired
- The bot's **`find_side_commitments`** tool calls [`src/work_iq.py`](src/work_iq.py), which
  acquires an Entra **app-only token** (`msal`, scope `https://graph.microsoft.com/.default`)
  and queries **Microsoft Graph** `/users/{mailbox}/messages` with a full-text `$search`
  for the customer name.
- It keeps emails that read like a commitment (filtering on hint words — *waive, discount,
  credit, hold, no increase, as agreed*…), falling back to all customer hits so the agent
  can judge relevance itself.
- The system prompt instructs the agent to call it when a finding could be overridden by a
  human promise; if one applies, the agent **adjusts its recommendation** — e.g. the waiver
  applies to Contoso's $816 escalation but **not** the $500 SLA credit.
- If unconfigured or unreachable, the tool returns `[]` and the agent uses the formal
  contract only — claims never exceed what the code can reach.

## Security
App-only **least-privilege** (`Mail.Read` only), secret stored in `.env` / App Service
settings (git-ignored, never committed), **synthetic emails only** — no real customer mail,
data, or PII.
