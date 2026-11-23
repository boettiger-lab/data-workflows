---
name: duckdb-geo
description: Connect the mcp__duckdb-geo__* query tools (port-forward, shared token). Use when they fail to connect.
---

# Connecting duckdb-geo

- Port-forward: `kubectl port-forward -n geo-workflows svc/duckdb-mcp 8000:8000`. Restart it if it drops; the server is re-created Sundays 03:10 UTC.
- Token: one shared token; ask Carl. Set `GEO_WORKFLOWS_MCP_TOKEN` before starting Claude Code. Never commit it.
- Port-forward access needs the NRP `geo-workflows` group: `kubectl auth can-i create pods --subresource=portforward -n geo-workflows`.
- 401 = no token. Connection refused = no forward.
- Reads anonymously-readable buckets only.
