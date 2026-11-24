---
name: duckdb-geo
description: Connect the mcp__duckdb-geo__* query tools (public URL, shared token). Use when they fail to connect.
---

# Connecting duckdb-geo

- URL: `https://duckdb-mcp.nrp-nautilus.io/mcp` (set in `.mcp.json`; scripts take `MCP_ENDPOINT`).
- Token: one shared token, sent as `Authorization: Bearer ${GEO_WORKFLOWS_MCP_TOKEN}`. `~/.bashrc`
  exports it from `~/.config/glen/geo-workflows-mcp-token`; ask Carl if it is missing. Start Claude
  Code with it set, then `/mcp` to reconnect. Never commit it.
- 401 = the token was not sent (variable unset, or Claude Code started before it was exported).
- Requests time out after 600 s at the ingress: aggregate in SQL and batch large scans by `h0`.
- Reads anonymously-readable buckets only.
