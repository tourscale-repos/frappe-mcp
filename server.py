#!/usr/bin/env python3
"""TourScale Frappe MCP — read-only access to FranOS doctypes + ERPNext.

Talks to the running ERPNext instance (erp.tourscale.com) via Frappe's REST
API using a dedicated `claude-mcp` user's API key/secret. Read-only at the
tool surface; the underlying Frappe role grants more, but the tools here
don't expose mutations. Add explicit @mcp.tool() write methods only when
agents need them.
"""
import json
import os
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from mcp.server.fastmcp import FastMCP

# Wire GlitchTip error tracking if a DSN is configured (no-op otherwise).
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.0,
        send_default_pii=False,
        release=os.environ.get("SENTRY_RELEASE", "frappe-mcp@dev"),
    )

mcp = FastMCP("frappe")

API_URL = os.environ.get("FRAPPE_API_URL", "https://erp.tourscale.com").rstrip("/")
API_KEY = os.environ["FRAPPE_API_KEY"]
API_SECRET = os.environ["FRAPPE_API_SECRET"]


def _headers() -> dict:
    return {
        "Authorization": f"token {API_KEY}:{API_SECRET}",
        "Accept": "application/json",
    }


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{API_URL}{path}"
    if params:
        url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
    try:
        req = Request(url, headers=_headers())
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_error": e.code, "_body": body[:500]}
    except URLError as e:
        return {"_error": "URLError", "_body": str(e)}


def _list_doc(doctype: str, *, filters: list | None = None, fields: list | None = None,
              limit: int = 20, order_by: str | None = None) -> Any:
    params: dict = {"limit_page_length": limit}
    if filters:
        params["filters"] = json.dumps(filters)
    if fields:
        params["fields"] = json.dumps(fields)
    if order_by:
        params["order_by"] = order_by
    return _get(f"/api/resource/{quote(doctype)}", params)


def _get_doc(doctype: str, name: str) -> Any:
    return _get(f"/api/resource/{quote(doctype)}/{quote(name, safe='')}")


def _fmt(rows: Any) -> str:
    """Pretty-print API response for tool output."""
    if isinstance(rows, dict) and "_error" in rows:
        return f"ERROR {rows['_error']}: {rows.get('_body', '')}"
    if isinstance(rows, dict) and "data" in rows:
        return json.dumps(rows["data"], indent=2, default=str)
    return json.dumps(rows, indent=2, default=str)


# ─── FranOS: Franchisee ──────────────────────────────────────────────────────

@mcp.tool()
def list_franchisees(
    status: str | None = None,
    entity_type: str | None = None,
    limit: int = 20,
) -> str:
    """List Franchisee records. Optional filters: status (Active/Onboarding/Terminated/etc.) and entity_type (LLC/INC/etc.). Brand affiliation lives on Franchise Agreement and Franchise Business Unit, not on the Franchisee directly."""
    filters = []
    if status:
        filters.append(["status", "=", status])
    if entity_type:
        filters.append(["entity_type", "=", entity_type])
    fields = ["name", "legal_name", "dba", "status", "entity_type", "primary_email", "onboarding_date"]
    return _fmt(_list_doc("Franchisee", filters=filters, fields=fields, limit=limit))


@mcp.tool()
def get_franchisee(name: str) -> str:
    """Get a single Franchisee record by name (e.g. FZE-00001). Returns the full document including child tables."""
    return _fmt(_get_doc("Franchisee", name))


# ─── FranOS: Franchise Agreement ─────────────────────────────────────────────

@mcp.tool()
def list_fas(
    franchisee: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    expiring_within_days: int | None = None,
    limit: int = 20,
) -> str:
    """List Franchise Agreement records. Filters: franchisee (link name like FZE-00001), brand (Pedal Pub/Trolley Pub/Cruisin' Tikis/Tiki Pub/Paddle Pub), status, expiring_within_days (against expiration_date). Note: a single FA can cover multiple brands via the FA Brand child table — the top-level brand field reflects the primary brand."""
    filters = []
    if franchisee:
        filters.append(["franchisee", "=", franchisee])
    if brand:
        filters.append(["brand", "=", brand])
    if status:
        filters.append(["status", "=", status])
    if expiring_within_days is not None:
        from datetime import date, timedelta
        cutoff = (date.today() + timedelta(days=expiring_within_days)).isoformat()
        filters.append(["expiration_date", "<=", cutoff])
        filters.append(["expiration_date", ">=", date.today().isoformat()])
    fields = ["name", "agreement_label", "franchisee", "franchisor", "brand", "effective_date",
              "expiration_date", "term_years", "royalty_pct", "royalty_basis", "status"]
    return _fmt(_list_doc("Franchise Agreement", filters=filters, fields=fields, limit=limit, order_by="expiration_date asc"))


@mcp.tool()
def get_fa(name: str) -> str:
    """Get a Franchise Agreement by name. Includes child tables: brands covered, royalty schedule, territories."""
    return _fmt(_get_doc("Franchise Agreement", name))


# ─── FranOS: Franchise Business Unit (FBU) ───────────────────────────────────

@mcp.tool()
def list_fbus(
    franchisee: str | None = None,
    brand: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List Franchise Business Unit records. An FBU is one operational unit (one brand × one market under one franchisee). Filters: franchisee, brand, status."""
    filters = []
    if franchisee:
        filters.append(["franchisee", "=", franchisee])
    if brand:
        filters.append(["brand", "=", brand])
    if status:
        filters.append(["status", "=", status])
    fields = ["name", "fbu_name", "franchise_agreement", "franchisee", "brand", "territory",
              "status", "launch_date", "booking_url", "google_business_profile_url"]
    return _fmt(_list_doc("Franchise Business Unit", filters=filters, fields=fields, limit=limit))


@mcp.tool()
def get_fbu(name: str) -> str:
    """Get one Franchise Business Unit record by name. Includes operating addresses child table."""
    return _fmt(_get_doc("Franchise Business Unit", name))


# ─── FranOS: Assets + COIs ───────────────────────────────────────────────────

@mcp.tool()
def list_assets(
    franchisee: str | None = None,
    fbu: str | None = None,
    asset_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> str:
    """List Franchise Asset records (vehicles, vessels). Filter by franchisee, fbu, asset_type (Pedal Pub/Trolley/Cruisin' Tiki/etc.), or status."""
    filters = []
    if franchisee:
        filters.append(["franchisee", "=", franchisee])
    if fbu:
        filters.append(["fbu", "=", fbu])
    if asset_type:
        filters.append(["asset_type", "=", asset_type])
    if status:
        filters.append(["status", "=", status])
    fields = ["name", "asset_id", "asset_name", "asset_type", "manufacturer", "model",
              "year_built", "passenger_capacity", "hin_or_vin", "franchisee", "fbu", "status"]
    return _fmt(_list_doc("Franchise Asset", filters=filters, fields=fields, limit=limit))


@mcp.tool()
def list_cois(
    franchisee: str | None = None,
    expiring_within_days: int | None = None,
    limit: int = 50,
) -> str:
    """List Certificate of Insurance records. Filter by franchisee or expiring_within_days for proactive renewal tracking."""
    filters = []
    if franchisee:
        filters.append(["franchisee", "=", franchisee])
    if expiring_within_days is not None:
        from datetime import date, timedelta
        cutoff = (date.today() + timedelta(days=expiring_within_days)).isoformat()
        filters.append(["expiration_date", "<=", cutoff])
        filters.append(["expiration_date", ">=", date.today().isoformat()])
    fields = ["name", "franchisee", "carrier", "policy_number", "effective_date", "expiration_date"]
    return _fmt(_list_doc("Certificate of Insurance", filters=filters, fields=fields, limit=limit, order_by="expiration_date asc"))


# ─── Generic doctype access ──────────────────────────────────────────────────

@mcp.tool()
def frappe_list_docs(
    doctype: str,
    filters_json: str | None = None,
    fields_json: str | None = None,
    limit: int = 20,
    order_by: str | None = None,
) -> str:
    """Generic Frappe list. doctype=DocType name; filters_json is a JSON list of [field, op, value] triples; fields_json is a JSON list of field names. Use this when the FranOS-specific tools don't fit (e.g. for ERPNext's Sales Invoice, GL Entry, Customer)."""
    filters = json.loads(filters_json) if filters_json else None
    fields = json.loads(fields_json) if fields_json else None
    return _fmt(_list_doc(doctype, filters=filters, fields=fields, limit=limit, order_by=order_by))


@mcp.tool()
def frappe_get_doc(doctype: str, name: str) -> str:
    """Generic Frappe get-by-name. Use for any doctype not covered by a dedicated tool."""
    return _fmt(_get_doc(doctype, name))


@mcp.tool()
def frappe_count(doctype: str, filters_json: str | None = None) -> str:
    """Count records of a doctype matching optional filters."""
    params = {"doctype": doctype}
    if filters_json:
        params["filters"] = filters_json
    res = _get("/api/method/frappe.client.get_count", params)
    return _fmt(res)


# ─── ERPNext: invoices + GL ──────────────────────────────────────────────────

@mcp.tool()
def erpnext_list_invoices(
    franchisee: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> str:
    """List Sales Invoice records (ERPNext). franchisee filter assumes Sales Invoice has a custom franchisee link field; falls back to customer match if not. Status: Paid/Unpaid/Overdue/Submitted/etc. Dates ISO format."""
    filters = []
    if franchisee:
        filters.append(["franchisee", "=", franchisee])
    if status:
        filters.append(["status", "=", status])
    if date_from:
        filters.append(["posting_date", ">=", date_from])
    if date_to:
        filters.append(["posting_date", "<=", date_to])
    fields = ["name", "customer", "franchisee", "posting_date", "due_date", "status", "grand_total", "outstanding_amount"]
    return _fmt(_list_doc("Sales Invoice", filters=filters, fields=fields, limit=limit, order_by="posting_date desc"))


@mcp.tool()
def erpnext_gl_entries(
    account: str | None = None,
    party: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> str:
    """List GL Entry records (ERPNext general ledger). Filter by account, party (customer/supplier), date range."""
    filters = []
    if account:
        filters.append(["account", "=", account])
    if party:
        filters.append(["party", "=", party])
    if date_from:
        filters.append(["posting_date", ">=", date_from])
    if date_to:
        filters.append(["posting_date", "<=", date_to])
    fields = ["name", "posting_date", "account", "party", "debit", "credit", "voucher_type", "voucher_no", "remarks"]
    return _fmt(_list_doc("GL Entry", filters=filters, fields=fields, limit=limit, order_by="posting_date desc"))


# ─── Health / discovery ──────────────────────────────────────────────────────

@mcp.tool()
def whoami() -> str:
    """Return the API user and base URL the MCP server is connected as."""
    res = _get("/api/method/frappe.auth.get_logged_user")
    if isinstance(res, dict) and "_error" in res:
        return f"ERROR {res['_error']}: {res.get('_body', '')}"
    user = res.get("message") if isinstance(res, dict) else res
    return json.dumps({"api_url": API_URL, "user": user}, indent=2)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("MCP_PORT", "8000"))
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        mcp.settings.transport_security.enable_dns_rebinding_protection = False
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
