# Frappe MCP

Read-only Model Context Protocol server for the TourScale ERPNext / FranOS instance at [erp.tourscale.com](https://erp.tourscale.com). Lets agents query Franchisees, Franchise Agreements, FBUs, Assets, COIs, and ERPNext invoices/GL entries.

## What it exposes

| Tool | Purpose |
|---|---|
| `whoami` | Connectivity probe — returns the API user identity |
| `list_franchisees(status, brand, limit)` | Franchisees with optional filters |
| `get_franchisee(name)` | Full Franchisee doc by name (e.g. `FZE-00001`) |
| `list_fas(franchisee, status, expiring_within_days, limit)` | Franchise Agreements; expiring window key for Compliance Watchdog |
| `get_fa(name)` | One FA with child tables (brands/royalty/territory) |
| `list_fbus(franchisee, brand, limit)` | FBUs |
| `get_fbu(name)` | One FBU with operating addresses |
| `list_assets(franchisee, asset_type, limit)` | Vehicles/vessels |
| `list_cois(franchisee, expiring_within_days, limit)` | Certificate of Insurance, with renewal-window filter |
| `frappe_list_docs(doctype, filters_json, fields_json, limit, order_by)` | Generic escape hatch for any doctype |
| `frappe_get_doc(doctype, name)` | Generic get-by-name |
| `frappe_count(doctype, filters_json)` | Count records |
| `erpnext_list_invoices(franchisee, status, date_from, date_to, limit)` | Sales Invoices |
| `erpnext_gl_entries(account, party, date_from, date_to, limit)` | GL ledger entries |

## How auth works

Talks to ERPNext REST API as the `claude-mcp@tourscale.com` user via API key + secret (Frappe-native auth scheme: `Authorization: token <key>:<secret>`).

The user has the `System Manager` role on ERPNext. The **MCP layer is the trust boundary** — the tools above are read-only by design. Don't add write tools casually; agents that need to mutate should call narrow, purpose-specific tools, not generic CRUD.

To rotate keys: re-run the `generate_keys` flow in `bench --site erp.tourscale.local console`, update `FRAPPE_API_KEY` + `FRAPPE_API_SECRET` in master env, restart `ts-frappe-mcp`.

## Deployment

- Container: `ts-frappe-mcp` on `tourscale-net`
- Port: bound to `127.0.0.1:8096` (loopback only — reach via local agent client or SSH tunnel)
- Compose entry lives in `/opt/tourscale/docker-compose.services.yml`
- Env file: `/opt/tourscale/frappe-mcp/.env` (sourced from master env)

## Local dev

```bash
FRAPPE_API_URL=https://erp.tourscale.com \
FRAPPE_API_KEY=... \
FRAPPE_API_SECRET=... \
python3 server.py
```

Then call tools via any MCP client (Claude Code, FastMCP debug tools, etc.).
