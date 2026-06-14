# Fabric IQ setup — structured portfolio analytics (config-gated)

Goal: stand up the third IQ modality — **Fabric IQ** — over a Microsoft **Fabric
OneLake Lakehouse**, so the agent can answer **portfolio-level** questions (totals,
exposure by customer, renewal/SLA risk across the whole book) that the per-finding
reconciler doesn't compute on its own.

Where the other two IQ layers ground on *unstructured* data — **Foundry IQ** on
knowledge (clause text), **Work IQ** on email — **Fabric IQ grounds on the
*structured* business records** (contracts / invoices / SLA events) and the semantic
relationships between them.

---

## Status in this repo: implemented, gated, **dormant**

The integration is **real, reviewable code** in [`src/fabric_iq.py`](src/fabric_iq.py),
wired into the agent in [`src/agent_core.py`](src/agent_core.py). It is **config-gated**
and currently **off**, by design:

- `fabric_iq.is_configured()` returns **False** (the five `FABRIC_*` values are unset),
- so `query_portfolio` is **never registered** as a tool,
- so the live agent is **byte-for-byte unchanged**, and
- we make **no claim** that Fabric IQ ran live.

> **Why it's gated off here (honest note):** this tenant has **no Fabric capacity we can
> use** — app-workspace creation is disabled by the tenant admin, and the free Fabric
> trial capacity is in a different region than the only available workspace. So the gate
> stays shut. Everything below is exactly what flips it on — **no code change required**,
> just the five env vars.

This mirrors the **Work IQ** gate (see [`src/work_iq.py`](src/work_iq.py)); the only
difference is that Work IQ's gate is *open* in this deployment and Fabric IQ's is *shut*.

---

## What you need to enable it

| # | Requirement | Where |
|---|---|---|
| 1 | A **Fabric capacity** (60-day trial **or** a paid F2 SKU) | Fabric portal → Account manager → *Start trial* |
| 2 | A **workspace** assigned to that capacity | Fabric portal → Workspaces → New |
| 3 | A **Lakehouse** in that workspace, with 3 tables loaded | from `data/*.json` (below) |
| 4 | The **SQL analytics endpoint** of that Lakehouse | Lakehouse → Settings → SQL endpoint |
| 5 | A **service principal** (Entra app) added to the workspace | reuse the bot's app; grant Viewer/Member |
| 6 | Tenant setting **"Service principals can use Fabric APIs" = On** | Fabric Admin portal → Tenant settings |

---

## Steps

### 1. Get capacity + a Lakehouse
1. In the Fabric portal, start a **Fabric trial** (or assign an **F2** capacity).
2. Create a **workspace** on that capacity.
3. In the workspace → **+ New item → Lakehouse** → name it e.g. `c2c_lakehouse`.

### 2. Load the three tables
Load the synthetic data as Delta tables whose **names and columns match** the JSON in
[`data/`](data/) (the queries in `fabric_iq.py` reference these exact names):

| Table | Source | Key columns used |
|---|---|---|
| `contracts` | [`data/contracts.json`](data/contracts.json) | `customer`, `base_monthly_price`, `annual_escalator_pct`, `escalation_clause_ref`, `auto_renew`, `renewal_date`, `sla_uptime_target_pct`, `sla_credit_clause_ref` |
| `invoices` | [`data/invoices.json`](data/invoices.json) | `contract_id`, `amount_billed`, `period` |
| `sla_events` | [`data/sla_events.json`](data/sla_events.json) | `contract_id`, `period`, `actual_uptime_pct` |

Easiest path: in the Lakehouse, **Get data → Upload files** (upload the JSON, or convert
to CSV first), then **Load to table** for each. Or use a notebook:
```python
# Fabric notebook (PySpark)
for name in ["contracts", "invoices", "sla_events"]:
    df = spark.read.option("multiline", "true").json(f"Files/{name}.json")
    df.write.mode("overwrite").saveAsTable(name)
```
> Note: `auto_renew` should land as a boolean/bit. The `renewal_risk` query filters
> `WHERE auto_renew = 0`; adjust to `= false` if your load stores it as a boolean.

### 3. Give the service principal access
1. Reuse the bot's Entra app (client id + secret), or create a new one.
2. In the **workspace → Manage access → Add people**, add that app as **Member** (or Viewer).
3. Confirm tenant setting **"Service principals can use Fabric APIs"** is **On**
   (Fabric Admin portal → Tenant settings), with the app in the allowed group.

### 4. Grab the SQL endpoint
Lakehouse → **Settings → SQL analytics endpoint** → copy the **connection string**
(host looks like `xxxxxxxx.datawarehouse.fabric.microsoft.com`). The **database** name
is the Lakehouse name.

### 5. Install the driver (Fabric-only runtime extra)
Not in the default `requirements.txt` (keeps the deploy lean). Install when enabling:
```powershell
.\.venv\Scripts\pip install pyodbc
```
Plus the system **"ODBC Driver 18 for SQL Server"** (already present on most Windows;
on Azure App Service Linux, install the Microsoft ODBC driver in the container).

### 6. Set the five values
In `.env` for local, **and** in the App Service **Environment variables** for the live bot:
```
FABRIC_SQL_ENDPOINT=xxxxxxxx.datawarehouse.fabric.microsoft.com
FABRIC_LAKEHOUSE=c2c_lakehouse
FABRIC_TENANT_ID=<entra tenant id>
FABRIC_CLIENT_ID=<service principal app id>
FABRIC_CLIENT_SECRET=<service principal secret>
```

---

## Verify retrieval works
```powershell
.\.venv\Scripts\python.exe src\fabric_iq.py
```
With all five set, this prints `configured=True` and the `exposure_by_customer` rows
straight from the Lakehouse. With any unset, it prints `configured=False` and an empty
result (the gate staying shut) — never an error.

Supported metrics (the `query_portfolio` enum):
`summary`, `exposure_by_customer`, `escalation_candidates`, `renewal_risk`, `sla_breaches`.

---

## How it's wired
- The bot's **`query_portfolio`** tool calls [`src/fabric_iq.py`](src/fabric_iq.py),
  which authenticates a Microsoft Entra **service-principal token**
  (`https://database.windows.net/.default`) and runs a fixed, parameter-free analytical
  query (no free-form SQL → no injection surface) against the Lakehouse SQL endpoint.
- In [`src/agent_core.py`](src/agent_core.py), the tool is **registered only when**
  `fabric_iq.is_configured()` is True, and a matching line is appended to the system
  prompt only then — so the proven, no-capacity deployment is untouched.
- If anything is unset or unreachable, `query_portfolio` returns an empty result with a
  short note and the agent falls back to the reconciler — same graceful-degradation
  contract as Foundry IQ and Work IQ.
