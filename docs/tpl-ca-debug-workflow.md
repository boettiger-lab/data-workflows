# Debugging tpl-ca App Queries: Log Review + MCP Data Exploration

This document describes how to diagnose failed or poor-quality queries from the
[tpl-ca](https://tpl-ca.nrp-nautilus.io) app: pull the relevant logs, reconstruct
what the agent did, and then validate correct queries yourself using the same MCP
data server the app uses.

## Step 1 — Check which pods are running

The `llm-proxy` deployment has multiple replicas. Requests are load-balanced across
all of them, so a single conversation may be spread across pods.

```bash
kubectl -n biodiversity get pods | grep -E "llm-proxy|tpl-ca"
```

## Step 2 — Pull logs from all llm-proxy pods

The proxy logs every request and response with structured JSON. The key fields are:
- `message_count` — number of messages in the conversation so far (proxy sees whole history each turn)
- `user_message` — preview of what triggered this turn (a tool result, a user message)
- `tool_calls` — what tools the model called in its response
- `content_preview` — first ~100 chars of any text response

```bash
# Quick summary: requests/responses from all pods, last N hours
for pod in $(kubectl -n biodiversity get pods -l app=llm-proxy -o name | sed 's|pod/||'); do
  kubectl -n biodiversity logs $pod --since=3h
done | grep -E "REQUEST|RESPONSE" | sort
```

To see the full log including tool errors (which appear as `user_message` on the next
request):

```bash
for pod in $(kubectl -n biodiversity get pods -l app=llm-proxy -o name | sed 's|pod/||'); do
  kubectl -n biodiversity logs $pod --since=3h
done | sort | grep -v "^INFO:"
```

## Step 3 — Reconstruct a conversation

Each REQUEST line carries `message_count`. A fresh conversation starts at 2 (system +
user). The pattern repeats: user/tool-result → model response → next request carries
the accumulated history.

To find a specific conversation (e.g. about senate districts):

```bash
for pod in $(kubectl -n biodiversity get pods -l app=llm-proxy -o name | sed 's|pod/||'); do
  kubectl -n biodiversity logs $pod --since=6h
done | grep -E "REQUEST|RESPONSE" | grep -i "senate\|sldu\|assembly\|sldl\|almanac" | sort
```

The `user_message` field on each REQUEST is a preview of the most recent tool result
or user turn — this lets you trace what the model saw. The `tool_calls` on each
RESPONSE tells you what it decided to do next.

**Reading the flow:**
1. Small `message_count` (2–4) = fresh conversation, first user message
2. Each round-trip adds ~4–6 to `message_count` (user + model + tool call + tool result)
3. `user_message` showing `"No results found."` or a SQL error = a tool call failed
4. `has_tool_calls: false` with `has_content: true` = model gave a final answer (no more tools)

## Step 4 — Check the MCP data server directly

The app uses the `duckdb-geo` MCP server at `https://duckdb-mcp.nrp-nautilus.io/mcp`.
This server is also configured for Claude Code (this session), so you can use the same
tools the app uses.

### Available MCP tools (duckdb-geo)

| Tool | Purpose |
|------|---------|
| `list_datasets` | List all datasets in the STAC catalog with their S3 paths |
| `get_dataset` | Get full metadata for one dataset by collection ID |
| `query` | Run read-only DuckDB SQL against S3 parquet files |

### Browsing the catalog

Start by listing datasets — this shows you what paths and column schemas the agent
would see:

```
list_datasets()
```

Then get details on a specific collection:

```
get_dataset("conservation-almanac-2024")
get_dataset("census-2025-sldu")
```

The returned text includes the exact `read_parquet(...)` paths the agent should use,
derived from the STAC `assets` hrefs.

**Note on dataset IDs:** The collection ID must match exactly. If `get_dataset` returns
"not found", the dataset may have been added after the server pod last started — this
is a known issue (see [mcp-data-server#11](https://github.com/boettiger-lab/mcp-data-server/issues/11)).
In that case, browse the STAC catalog directly:

```bash
curl -s https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json | python3 -m json.tool
```

### Running queries

The `query` tool runs DuckDB SQL. The server pre-configures the NRP S3 endpoint, so
use `s3://` paths (not `https://`). The hex parquet files use hive partitioning — use
`h0=*/data_0.parquet` glob:

```sql
-- Check what's in the TPL hex data
SELECT state, COUNT(*) as n
FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet')
GROUP BY state ORDER BY n DESC LIMIT 10
```

```sql
-- Standard senate district × TPL join (California only)
SELECT
    d.NAMELSAD,
    d.GEOID,
    COUNT(DISTINCT t.tpl_id) AS num_projects,
    ROUND(SUM(t.acres), 0)   AS total_acres,
    ROUND(SUM(t.amount), 0)  AS total_dollars
FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet') t
JOIN read_parquet('s3://public-census/census-2025/sldu/hex/h0=*/data_0.parquet') d
    ON t.h10 = d.h10
WHERE d.STATEFP = '06'
GROUP BY d.NAMELSAD, d.GEOID
ORDER BY num_projects DESC
```

**Geometry column gotcha:** If a query selects `*` from a flat GeoParquet (e.g.
`sldl.parquet` or `sldu.parquet`), it will crash with:
```
Not implemented Error: Unsupported type "GEOMETRY('OGC:CRS84')" for DuckDB -> NumPy conversion
```
Exclude the geometry column explicitly: `SELECT * EXCLUDE geom`. Or just use the hex
parquet files, which don't have geometry columns at all.
See [mcp-data-server#10](https://github.com/boettiger-lab/mcp-data-server/issues/10).

### Checking if hex data is complete

If a join returns 0 results unexpectedly, check whether the hex repartition job
finished:

```bash
# Is the repartition job still running?
kubectl -n biodiversity get jobs | grep repartition

# How many h0 partition files exist?
curl -s "https://s3-west.nrp-nautilus.io/public-census/?prefix=census-2025/sldl/hex/" \
  | grep -oP '(?<=<Key>)[^<]+' | wc -l
```

A complete national dataset at resolution 10 should have 15–25 h0 partitions for US
coverage (out of 122 global cells). Fewer than 5 means the repartition is still running
or failed.

## Step 5 — Common failure patterns and fixes

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| Results show CO, NH, FL instead of CA | Missing `WHERE state = 'California'` or `WHERE STATEFP = '06'` | Always filter to CA |
| `"Dataset not found"` | Stale MCP registry (pod started before dataset was published) | See mcp-data-server#11; check STAC catalog directly |
| `IO Error: No files found` for hex path | Wrong S3 path (e.g. `census-2025-sldu` instead of `census-2025/sldu`) or repartition incomplete | Check S3 listing above |
| `GEOMETRY('OGC:CRS84') for NumPy conversion` | Selected geometry column from GeoParquet | Use hex paths or `EXCLUDE geom` |
| Join returns 0 rows | Repartition still running; h0 partitions not yet written | Check repartition job status |
| `st_intersects not in catalog` | Spatial extension not loaded | Use H3 hex join instead; never use geometry functions |

## S3 path conventions

| Dataset | Flat parquet | Hex parquet |
|---------|-------------|-------------|
| TPL Conservation Almanac | `s3://public-tpl/conservation-almanac-2024.parquet` | `s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet` |
| CA Senate districts (SLDU) | `s3://public-census/census-2025/sldu.parquet` | `s3://public-census/census-2025/sldu/hex/h0=*/data_0.parquet` |
| CA Assembly districts (SLDL) | `s3://public-census/census-2025/sldl.parquet` | `s3://public-census/census-2025/sldl/hex/h0=*/data_0.parquet` |
| Congressional districts | `s3://public-census/census-2024/cd.parquet` | `s3://public-census/census-2024/cd/hex/h0=*/data_0.parquet` |

S3 paths translate from STAC HTTPS hrefs by stripping `https://s3-west.nrp-nautilus.io/`
and replacing with `s3://`. The hex directory href in STAC ends with `/hex/` — append
`h0=*/data_0.parquet` for DuckDB queries.

## Key column names

| Dataset | H3 join key | State filter | District name |
|---------|------------|-------------|---------------|
| TPL almanac hex | `h10` | `state = 'California'` or `state_id = 'CA'` | — |
| SLDU hex | `h10` | `STATEFP = '06'` | `NAMELSAD` |
| SLDL hex | `h10` | `STATEFP = '06'` | `NAMELSAD` |
| Congressional districts hex | `h8` | `STATEFP = '06'` | `NAMELSAD` |

Both TPL and legislative district hex files carry h3 columns at multiple resolutions:
`h10`, `h9`, `h8`, `h0`. Join at the finest resolution both datasets share (`h10` for
all the above) for most accurate results.
