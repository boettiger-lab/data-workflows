---
name: duckdb-geo
description: Connect the mcp__duckdb-geo__* query tools (public NRP ingress, shared token). Use when they fail to connect.
---

# Connecting duckdb-geo

- URL: `https://duckdb-mcp.nrp-nautilus.io/mcp`, the public NRP ingress (set in `.mcp.json`; scripts
  take `MCP_ENDPOINT`). There is no port-forward: a `localhost:8000` entry is stale and must go.
- Token: `.mcp.json` sends `GEO_WORKFLOWS_MCP_TOKEN` if it is exported, otherwise it reads
  `~/.config/glen/geo-workflows-mcp-token`. Ask Carl if the file is missing. Never commit or print it.
- **ECONNREFUSED or a localhost URL** means a local-scope entry is shadowing `.mcp.json` (local beats
  project). Check with `claude mcp get duckdb-geo`, remove it with `claude mcp remove duckdb-geo -s local`,
  then `/mcp` to reconnect.
- Probe the endpoint outside Claude Code:
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' -X POST https://duckdb-mcp.nrp-nautilus.io/mcp \
    -H "Authorization: Bearer $(cat ~/.config/glen/geo-workflows-mcp-token)" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
  ```
  200 = up. 401 = no token or the wrong one.
- Authenticated access to the NRP server is the only configuration. Never configure another URL
  (a port-forward, the cirrus deployment, a mirror), in any scope, even as a fallback. If NRP is
  down, say so and wait; do not reroute.
- A SessionStart hook (`.claude/hooks/check-duckdb-geo.py`) warns when any `duckdb-geo` entry
  points elsewhere, the token is missing, or the endpoint does not answer 200. It is silent when healthy.
- Requests time out after 600 s at the ingress: aggregate in SQL and batch large scans by `h0`.
- Reads anonymously-readable buckets only.
