# `roadless-areas-2001` — build notes and measured evidence

USFS Inventoried Roadless Areas designated by the 2001 Roadless Area Conservation Rule
(36 CFR 294 Subpart B). Issue: boettiger-lab/data-workflows#584. First dataset in the new
`public-usfs` bucket.

## Source

```
https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadlessArea_2001.zip
```

Verified 2026-08-19: HTTP 200, `application/zip`, **41,740,635 bytes**,
`Last-Modified: Sun, 11 May 2025 17:11:45 GMT`. Zip contents include the FGDC metadata
sidecar `S_USA.RoadlessArea_2001.shp.xml` (40,825 bytes), staged separately under
`raw/` so provenance can be cited without unpacking the archive.

Landing page: <https://www.fs.usda.gov/managing-land/planning/roadless>.
Credit (FGDC `idCredit`): US Forest Service, Geospatial Service and Technology Center
(GSTC), National Inventoried Roadless Areas Program. FGDC `pubDate` 2023-10-03.

## Measured schema (read from the source shapefile, 2026-08-19)

11,391 **Polygon** features (not MultiPolygon), **EPSG:4269 (NAD83)** → reprojected to
EPSG:4326 by `cng-convert-to-parquet`. Source extent
`(-150.008, 18.246) … (-65.707, 61.519)` — Alaska coverage is the Southeast/Chugach
panhandle, so **the layer does not cross the antimeridian** and the h0 dateline cell is
not in play. The southern limit is Puerto Rico.

| Column | Type | Measured domain / range |
|---|---|---|
| `REGION` | int32 | `1,2,3,4,5,6,8,9,10` — **no Region 7** (confirmed in FGDC `attrdef`) |
| `FOREST` | string | 122 distinct forest names |
| `STATE` | string | 39 distinct 2-letter codes (incl. `PR`) |
| `NAME` | string | 2,618 distinct; **1,219 names occur on more than one polygon**; **4 NULLs** |
| `CATEGORY` | string | `1B` (3,365), `1B-1` (178), `1C` (7,848) |
| `ACRES` | double | min 0.010261, max 1,160,364.68 — per-feature total |
| `SHAPE_AREA` | double | per-feature total |
| `SHAPE_LEN` | double | per-feature total |

Per-polygon acreage by state and category:
`1B` 19,970,735 ac · `1B-1` 4,211,812 ac · `1C` 34,237,147 ac.

`NAME` is **not** a feature key (1,219 duplicated names, 4 NULLs) — use the synthesized
`_cng_fid` as the stable per-feature key.

### Authoritative `CATEGORY` domain (from the FGDC `edom` entries, not inferred)

- `1B` — Inventoried Roadless Areas where road construction and reconstruction is prohibited.
- `1B-1` — Inventoried Roadless Areas that are recommended for wilderness designation in the
  forest plan and where road construction and reconstruction is prohibited.
- `1C` — Inventoried Roadless Areas where road construction and reconstruction is **not**
  prohibited.

⚠️ The FGDC metadata attaches the same caveat to all three: *"The category descriptions are
based on forest plan direction prior to adoption of the Roadless Rule. This information is
displayed for historical reference. However, the Roadless Rule prohibits road construction in
all IRAs, regardless of the attribute descriptions."* So `CATEGORY = '1C'` does **not** mean
road construction was permitted under the 2001 Rule; it records pre-rule forest-plan
direction. This must not be read as a rule-status field.

## Acceptance criteria — reproduced from the source before the build

Computed by iterating the source shapefile (`scripts` in the session scratchpad, GDAL/OGR):

| Quantity | Computed | Issue target | ✓ |
|---|---|---|---|
| `SUM(ACRES)` all features | 58,419,694 | 58,419,694 | ✓ |
| `SUM(ACRES) WHERE STATE IN ('ID','CO')` | 13,718,692 (23.5%) | — | — |
| `SUM(ACRES) WHERE STATE NOT IN ('ID','CO')` | **44,701,002** | 44,701,002 | ✓ |
| West-10 ÷ rule-affected | **95.61%** | 95.6% | ✓ |
| West-10 ÷ all-IRA | 73.16% | 73.2% | ✓ |
| Montana | 6,395,401 | 6,395,401 | ✓ |
| Feature count | 11,391 | 11,391 | ✓ |

West-10 = `AK, AZ, CA, MT, NV, NM, OR, UT, WA, WY`.

**The denominator is load-bearing.** The 2026-08-18 announcement's ">44 million acres" and
">95% in 10 Western states" are both computed against the **44.7M rule-affected** base
(`STATE NOT IN ('ID','CO')`), not the 58.4M all-IRA total — West-10 over the full 58.4M is
73.16%, not 95.61%. Both totals go in the STAC collection description so a consumer cannot
silently pick the wrong base.

The proposed rescission does not apply to Idaho or Colorado, which adopted state-specific
roadless rules (2008 and 2012). There is **no rule-type attribute** — the split is by
`STATE`. The FGDC abstract states the position directly: *"Idaho and Colorado have adopted
state-specific roadless rules. The Idaho and Colorado Roadless Areas boundaries, represented
in separate datasets, supersede the 2001 Roadless Area Boundaries."* So the ID and CO
polygons here are the **superseded** 2001 boundaries — they are retained (not clipped out)
because they are the untouched-comparison stratum and part of the "95% in 10 states"
denominator, but they are not the operative boundaries for those two states.

Probed and confirmed **404** on the EDW shapefile endpoint, so there is no companion EDW
layer to ingest here: `S_USA.RoadlessArea_Idaho2008`, `…_Colorado2012`, `…_Idaho`,
`…_Colorado`, `S_USA.IdahoRoadlessArea`, `S_USA.ColoradoRoadlessArea`.

## Pipeline

| Setting | Value | Why |
|---|---|---|
| dataset | `roadless-areas-2001` | PMTiles `source-layer` = `roadless-areas-2001` |
| bucket | `public-usfs` | new bucket; also hosts #585, #588, #591 |
| H3 native | `10` | parents `9,8,0`; small-to-moderate polygons, res 10 keeps sub-acre slivers from vanishing, and `h8` is the catalog join key |
| `--max-completions` | `12` | fixed chunk size is 1000 → `ceil(11391/1000) = 12`. The default 200 would schedule 188 no-op pods |
| `--hex-memory` | `16Gi` | largest single feature is Juneau-Skagway Icefield, 1,160,365 ac ≈ 4,700 km² ≈ 313k res-10 cells — comfortable, with headroom |
| `--row-group-size` | 100000 (default) | total geometry is ~55 MB, far below the ~2.8 GB httpfs `stoi` cliff |
| namespace | `geo-workflows` | |

Run order (the bucket is new, so `setup-bucket` must precede `stage-raw`):

```bash
kubectl apply -n geo-workflows -f workflow-rbac.yaml           # once per namespace
kubectl apply -n geo-workflows -f roadless-areas-2001-setup-bucket.yaml
kubectl apply -n geo-workflows -f roadless-areas-2001-stage-raw.yaml
kubectl apply -n geo-workflows -f configmap.yaml -f workflow.yaml
```

`stage-raw` asserts the exact 41,740,635-byte length and the `PK` zip magic before upload,
so an HTML error page served with HTTP 200 fails the job instead of poisoning the build.

## Post-build verification

```sql
-- flat: the four acceptance numbers, from the ingested parquet
SELECT COUNT(*)                                                   AS features,
       SUM(ACRES)                                                 AS all_ira_acres,
       SUM(ACRES) FILTER (WHERE STATE NOT IN ('ID','CO'))         AS rule_affected_acres,
       SUM(ACRES) FILTER (WHERE STATE IN ('AK','AZ','CA','MT','NV','NM','OR','UT','WA','WY'))
         / SUM(ACRES) FILTER (WHERE STATE NOT IN ('ID','CO')) * 100 AS west10_pct
FROM read_parquet('s3://public-usfs/roadless-areas-2001.parquet');
-- expect 11391 | 58419694 | 44701002 | 95.61

-- hex coverage: every feature must survive hexing (the #494 silent-cap check)
SELECT COUNT(DISTINCT _cng_fid) FROM
  read_parquet('s3://public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet');
-- expect 11391
```

Then the h0 partition gate and the STAC gate:

```bash
scripts/check-hex-coverage.sh nrp:public-usfs/roadless-areas-2001/hex/ --expect-count <N>
scripts/verify-stac.py --bucket public-usfs --dataset roadless-areas-2001
```

## Notes

- **No backup/mirror registration happens in this repo.** Issue #584 (and #585/#586/#588)
  cite `AGENTS.md:661` for "root-catalog registration + MinIO backup" on a new bucket. That
  instruction is stale: `AGENTS.md` Step 7 on `main` now states the backup and source.coop
  tiers are owned end to end by geo-agent-ops and that data-workflows supplies them nothing.
  The only obligation here is an accurate SPDX `license` plus a license link in the STAC.
  `catalog/sync/` no longer exists on `main`.
- License: US Forest Service work, no upstream restriction beyond a no-warranty disclaimer
  and "Data may be viewed and used by any and all entities" (FGDC `useLimit`) → US federal
  work, `public-domain`.
- The FGDC access constraint is worth carrying into STAC: source scales vary, external
  features cannot be expected to align, and the National Forest Planning Record Documents
  (Appendix C) / RARE II documents remain the official version of the inventory. Relevant to
  any road-proximity buffering in #588.
