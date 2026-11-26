#!/usr/bin/env python3
"""SessionStart check: duckdb-geo must be authenticated access to the NRP server, and nothing else.

Silent when healthy. Otherwise prints one warning to the user and to Claude. Flags:
  - any duckdb-geo entry (global or local scope) whose URL is not the NRP server;
  - a missing token (no GEO_WORKFLOWS_MCP_TOKEN and no token file);
  - the NRP endpoint not answering `initialize` with 200.
Never fails the session and never prints the token.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request

URL = "https://duckdb-mcp.nrp-nautilus.io/mcp"
TOKEN_FILE = os.path.expanduser("~/.config/glen/geo-workflows-mcp-token")
problems = []

# 1. Entries outside .mcp.json that point anywhere but NRP.
try:
    cfg = json.load(open(os.path.expanduser("~/.claude.json")))
except Exception:
    cfg = {}
entry = (cfg.get("mcpServers") or {}).get("duckdb-geo")
if entry and entry.get("url") != URL:
    problems.append(f"global duckdb-geo points at {entry.get('url')}; fix: claude mcp remove duckdb-geo -s user")
paths = {os.environ.get("CLAUDE_PROJECT_DIR", ""), os.getcwd()}
try:
    paths.add(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=5).stdout.strip())
except Exception:
    pass
for p in filter(None, paths):
    entry = ((cfg.get("projects") or {}).get(p, {}).get("mcpServers") or {}).get("duckdb-geo")
    if entry and entry.get("url") != URL:
        problems.append(f"local duckdb-geo for {p} points at {entry.get('url')} and overrides .mcp.json; "
                        f"fix: claude mcp remove duckdb-geo -s local")

# 2. Token.
token = os.environ.get("GEO_WORKFLOWS_MCP_TOKEN", "").strip()
if not token:
    try:
        token = open(TOKEN_FILE).read().strip()
    except OSError:
        problems.append(f"no token: GEO_WORKFLOWS_MCP_TOKEN is unset and {TOKEN_FILE} is missing (ask Carl)")

# 3. Endpoint.
if token:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "session-check", "version": "0"}}}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status != 200:
                problems.append(f"{URL} returned {r.status}")
    except urllib.error.HTTPError as e:
        problems.append(f"{URL} returned {e.code}" + (" (token rejected)" if e.code == 401 else ""))
    except Exception as e:
        problems.append(f"{URL} unreachable: {type(e).__name__}")

if problems:
    msg = "duckdb-geo MCP: " + "; ".join(problems) + ". See skill duckdb-geo, then /mcp."
    print(json.dumps({"systemMessage": msg, "hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": msg}}))
