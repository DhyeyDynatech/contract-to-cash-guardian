"""
Fabric IQ — structured business data + ontology (the enterprise data plane).
----------------------------------------------------------------------------
The third IQ modality. Foundry IQ grounds on unstructured KNOWLEDGE (clause text);
Work IQ grounds on unstructured WORK data (emails). Fabric IQ grounds on the
STRUCTURED business records — contracts, invoices, SLA events — and the semantic
relationships between them (Contract ↔ Customer ↔ Invoice ↔ SLA event).

In production those records live in a Microsoft Fabric OneLake **Lakehouse**, and
this module queries them through the Lakehouse's **SQL analytics endpoint**
(T-SQL over Delta tables, Microsoft Entra service-principal auth). The agent calls
`query_portfolio` for PORTFOLIO-LEVEL questions the per-finding reconciler can't
answer on its own — "total exposure by customer", "which customers breached SLA",
"renewal risk across the book".

Status: CONFIG-GATED and (in this deployment) DORMANT. Activating it needs a Fabric
capacity + a Lakehouse on it + the service principal added to that workspace — none
of which are available in this tenant (workspace creation is disabled and the trial
capacity is in a different region). So `is_configured()` returns False, the tool is
never registered, the live agent is unchanged, and we DO NOT claim it runs live.
The code below is the genuine integration; it goes live the moment the five
FABRIC_* values are supplied — no code change. This mirrors the Work IQ gate
(see src/work_iq.py), with the one honest difference that this gate stays shut here.

Configure (only when a Fabric capacity is available):
  FABRIC_SQL_ENDPOINT   <name>.datawarehouse.fabric.microsoft.com  (Lakehouse SQL endpoint)
  FABRIC_LAKEHOUSE      the Lakehouse name (used as the SQL database)
  FABRIC_TENANT_ID      Entra tenant id
  FABRIC_CLIENT_ID      service principal with Viewer/Member on the Fabric workspace
  FABRIC_CLIENT_SECRET  that SP's client secret
Runtime extra (Fabric only): pip install pyodbc + the system "ODBC Driver 18 for SQL Server".
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

SQL_ENDPOINT = os.environ.get("FABRIC_SQL_ENDPOINT", "")
LAKEHOUSE = os.environ.get("FABRIC_LAKEHOUSE", "")
TENANT_ID = os.environ.get("FABRIC_TENANT_ID", "")
CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("FABRIC_CLIENT_SECRET", "")

# Fixed, parameter-free analytical queries over the Lakehouse semantic model.
# Keyed by metric name so the agent picks a known query (no free-form SQL → no
# injection surface). Column/table names mirror data/*.json so the same records
# that the reconciler reads as JSON are queried here as Delta tables.
_QUERIES: dict[str, str] = {
    "summary": (
        "SELECT COUNT(*) AS contracts, "
        "SUM(base_monthly_price) AS monthly_recurring, "
        "SUM(base_monthly_price) * 12 AS annual_contract_value "
        "FROM contracts"
    ),
    "exposure_by_customer": (
        "SELECT customer, "
        "SUM(base_monthly_price) * 12 AS annual_contract_value, "
        "COUNT(*) AS contracts "
        "FROM contracts GROUP BY customer "
        "ORDER BY annual_contract_value DESC"
    ),
    "escalation_candidates": (
        "SELECT contract_id, customer, base_monthly_price, annual_escalator_pct, "
        "escalation_clause_ref FROM contracts "
        "WHERE annual_escalator_pct > 0 ORDER BY annual_escalator_pct DESC"
    ),
    "renewal_risk": (
        "SELECT contract_id, customer, renewal_date, base_monthly_price "
        "FROM contracts WHERE auto_renew = 0 ORDER BY renewal_date"
    ),
    "sla_breaches": (
        "SELECT c.customer, e.period, e.actual_uptime_pct, "
        "c.sla_uptime_target_pct, c.sla_credit_clause_ref "
        "FROM sla_events e JOIN contracts c ON e.contract_id = c.contract_id "
        "WHERE e.actual_uptime_pct < c.sla_uptime_target_pct "
        "ORDER BY (c.sla_uptime_target_pct - e.actual_uptime_pct) DESC"
    ),
}

SUPPORTED_METRICS = tuple(_QUERIES.keys())


def is_configured() -> bool:
    return bool(SQL_ENDPOINT and LAKEHOUSE and TENANT_ID and CLIENT_ID and CLIENT_SECRET)


def _access_token() -> str | None:
    """Entra service-principal token for the Fabric SQL endpoint (SQL DB audience)."""
    try:
        import msal
    except ImportError:
        return None
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(
        scopes=["https://database.windows.net/.default"]
    )
    return result.get("access_token")


def _connect():
    """Open a pyodbc connection to the Lakehouse SQL endpoint using an Entra token.

    Returns a live connection, or None if the driver/token isn't available (the
    caller then degrades to an empty result — the gate staying shut).
    """
    try:
        import struct

        import pyodbc
    except ImportError:
        return None

    token = _access_token()
    if not token:
        return None

    # pyodbc passes the Entra access token via the SQL_COPT_SS_ACCESS_TOKEN attr,
    # packed as a UTF-16-LE length-prefixed struct (the documented pattern).
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    SQL_COPT_SS_ACCESS_TOKEN = 1256

    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={SQL_ENDPOINT},1433;"
        f"Database={LAKEHOUSE};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


def query_portfolio(metric: str = "summary") -> dict[str, Any]:
    """Run a structured portfolio query against the Fabric Lakehouse.

    Returns {metric, rows:[...]} on success, or a graceful {metric, rows:[], note}
    when Fabric IQ isn't configured / reachable (the gate is shut) so the agent
    falls back to the reconciler. `metric` must be one of SUPPORTED_METRICS.
    """
    metric = (metric or "summary").strip()
    if metric not in _QUERIES:
        return {"metric": metric, "rows": [],
                "note": f"Unknown metric. Supported: {', '.join(SUPPORTED_METRICS)}."}
    if not is_configured():
        return {"metric": metric, "rows": [],
                "note": "Fabric IQ not configured — no Fabric capacity connected."}

    conn = _connect()
    if conn is None:
        return {"metric": metric, "rows": [],
                "note": "Fabric IQ configured but driver/token unavailable."}
    try:
        cursor = conn.cursor()
        cursor.execute(_QUERIES[metric])
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        return {"metric": metric, "rows": rows}
    except Exception as error:  # noqa: BLE001 - degrade gracefully like the other IQs
        return {"metric": metric, "rows": [], "note": f"Fabric query failed: {error}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import json

    print(f"configured={is_configured()} | metrics={SUPPORTED_METRICS}")
    print(json.dumps(query_portfolio("exposure_by_customer"), indent=2, default=str))
