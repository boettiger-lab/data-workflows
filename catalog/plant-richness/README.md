# CBN plant-richness family (Kling et al. 2018) — build notes

Issue: [#229](https://github.com/boettiger-lab/data-workflows/issues/229). Two California
Biodiversity Network rasters from Kling et al. (2018), *Phil. Trans. R. Soc. B*
(https://royalsocietypublishing.org/doi/full/10.1098/rstb.2017.0397), processed to
cloud-native COG + H3 hex on `public-ca30x30` (flat layout, per the 2026-06-17 scope lock):

| `--dataset` | S3 prefix | value col | source raster |
|---|---|---|---|
| `plant-richness` | `public-ca30x30/plant-richness/` | `richness` | `species_D.tif` |
| `rarity-weighted-endemic-plant-richness` | `public-ca30x30/rarity-weighted-endemic-plant-richness/` | `rwe` | `endemicspecies_E.tif` |

Each dataset is built **3 ways** from one WGS84 reprojection of the EPSG:3310 source:

1. full continuous COG + `hex-max/` (reducer `max` — peak richness per cell)
2. (same COG) + `hex-mean/` (reducer `mean` — area-weighted mean per cell)
3. 80th-percentile hotspot COG (pixels ≥ P80) + `p80-hex/` (reducer `max`)

`max` is the correct reducer for richness/peak quantities (SUM double-counts species,
MEAN averages away hotspots); `hex-mean` is kept to retain all data.

## Generating the job YAMLs

```bash
bash gen-jobs.sh      # writes k8s/<dataset>/*.yaml for both datasets
```

`gen-jobs.sh` emits, per dataset: `<ds>-cog.yaml`, `<ds>-hex-max.yaml`,
`<ds>-hex-mean.yaml`, `<ds>-p80-cog.yaml`, `<ds>-p80-hex.yaml`.
Hex jobs read the **WGS84 COG** (so `MAX(hex)` validates exactly against the COG) and use
`cng-datasets raster` with `--method exact-extract` (area-weighted, one row per cell).

### Two source quirks handled in the build

1. **CRS authority missing.** The source GeoTIFFs carry a valid CA-Albers WKT but no EPSG
   authority code ("unnamed" PROJCS), which makes the tool's `AutoIdentifyEPSG()` crash
   (`Unsupported SRS`). We re-tag them to EPSG:3310 (lossless metadata edit; the WKT
   `IsSame(3310)`) and stage `raw/<src>_epsg3310.tif` as the build input.
2. **Dual fill value after reproject.** The 3310→4326 warp emits a *second* near-nodata
   value (~`-3.3999997e38`) next to the declared `-3.4e38`, which a single `--nodata`
   cannot exclude (it leaked ~850k fill pixels into the first hex/percentile pass). The
   `-cog` job therefore **normalizes** all fill (`< -1e30`) to one exact float32 sentinel
   and re-flags nodata, so downstream hex (`--nodata -3.4e38`) and the P80 pass exclude
   all fill cleanly.

## Running (k8s, namespace `biodiversity`)

One k8s hex workflow at a time (122 completions / 61 parallel ≈ 61 pods each; the
namespace pod quota is 200). Single-pod COG / P80 jobs can overlap a hex job.

```bash
kubectl apply -n biodiversity -f k8s/plant-richness/workflow-rbac.yaml   # once
for ds in plant-richness rarity-weighted-endemic-plant-richness; do
  D=k8s/$ds
  kubectl apply -n biodiversity -f $D/$ds-cog.yaml        # build + clean WGS84 COG
  kubectl apply -n biodiversity -f $D/$ds-p80-cog.yaml    # compute P80, mask, write hotspot COG
  kubectl apply -n biodiversity -f $D/$ds-hex-max.yaml    # wait for completion before the next hex job
  kubectl apply -n biodiversity -f $D/$ds-hex-mean.yaml
  kubectl apply -n biodiversity -f $D/$ds-p80-hex.yaml
done
```

## Results (validated via duckdb-geo MCP)

| dataset | full range | P80 | hex cells (max/mean) | p80-hex cells |
|---|---|---|---|---|
| plant-richness | 1.481–553.87 | **317.72** | 528,686 | 145,903 |
| rarity-weighted-endemic-plant-richness | 0.0–0.10399 | **0.003853** | _see PR_ | _see PR_ |

All hex layers: no fill cells, `MAX(hex)` == COG max, every cell ∈ [COG min, COG max]
(p80-hex ∈ [P80, COG max]); res-0 rollup via `GROUP BY h0 + MAX`.

STAC + README live on NRP (not in this repo): `s3://public-ca30x30/<dataset>/stac-collection.json`.
