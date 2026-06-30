# Ingest recipe — CC0 Dryad economic + scenario layers → H3 hex

Target bucket **`public-nci-frontiers`** (public-read set). Source = the CC0 input deposit
(`10.5061/dryad.qjq2bvqw5`), staged to `s3://public-nci-frontiers/raw/inputs/...` by `k8s/stage-raw.yaml`
(/ local unzip + push). Hex via `cng-datasets raster-workflow` (local venv `.venv/bin/cng-datasets`
generates YAML; apply to cluster).

## ⚠️ Layers are MIXED resolution — pre-flighted with rasterio (see scripts/)

| Group | Native grid | H3 native res | parent-resolutions |
|---|---|---|---|
| Economic crop/palm/grazing revenue + methane | **5 arcmin (~9 km), 4320×2160** | **5** | `4,3,0` |
| All 300 m layers (FLII, forestry, transition costs, LULC, masks) | **300 m, 129600×64800** | **8** | `7,6,5,0` |

Res 5 matches our IUCN biodiversity grid and the paper's ~8 000-ha parcel; the 300 m layers carry an `h5`
parent column so everything rolls up to a common res-5 decision unit.

> **⚠️ Memory:** res-8 hex of a 300 m global raster needs **`--hex-memory 64Gi`** — `exact_extract` on the
> densest h0 cells (~5.76 M cells) OOMs at 32Gi (`exit 137`) and can blow `maxFailedIndexes` and fail the
> job (observed on `flii` and `forestry-return`). The res-5 economic layers are fine at 16–32Gi.

## Reducers + nodata (per pre-flight)

| Layer(s) | `--value-column` | reducer | `--nodata` |
|---|---|---|---|
| `crop-current` (totalproductionvaluecurrent_NoPalmOilRevR…) | `crop_current_usd_ha` | `mean` | `0` (0 = background) |
| `crop-irrigated`, `crop-rainfed` (…irrigated/rainfed_NoPalmOilRevR…) | `crop_{irrig,rainfed}_usd_ha` | `mean` | `0` |
| `palm-current` (…current_OnlyPalmOilRevR…) | `palm_current_usd_ha` | `mean` | `0` |
| `grazing-return` (potential_meat_returns…) | `grazing_usd_ha` | `mean` | `-9999` |
| `grazing-methane` (potential_methane…) | `methane_kg_ha_yr` | `mean` | `0` |
| `forestry-return` (forestry_land_share_return…) | `forestry_usd_ha` | `mean` | `-99999` |
| `flii` (flii.tif, uint16 0–10000) | `flii` | `mean` | (none; 0 = nonforest, keep) |
| `lulc-current` (current_lulc/modifiedESA…), `lulc-potential` (potential_vegetation…) | `lulc` | `mode` | `0` |
| transition costs `tran_cost_*` (USD/pixel; float32 nodata None **or** uint8 nodata 255) | `tcost_{scn}_usd` | `sum` | `255` for uint8 files, none for float32 |
| masks (irrigation/rainfed/sustainable, suitability, slope expansion/intensification, riparian, wdpa_merged) | `mask` | `max` | `7` or `255` per file |

Revenue/methane are **densities (per-ha)**: `mean` gives area-weighted mean density per cell; a per-cell
**total** = `mean × cell_ground_area_ha` downstream (constant at fixed res, so mean is monotonic with total
for ranking). Transition costs are **per-pixel totals** → `sum`.

### Ephemeral / PVC + job hardening (per AGENTS.md)

- **Ephemeral cap = 50Gi namespace-wide.** Generated hex YAMLs request **20Gi** here — fine. Per AGENTS, the **122-pod hex step belongs on per-pod ephemeral**, not the PVC: each pod localizes one COG via rclone, and our largest is forestry **2.8 GB** (FLII 0.8 GB; crop/grazing tiny) — all far under 50Gi. The **`rechunk-scratch` PVC is reserved for single-pod steps whose file genuinely exceeds 50Gi** (e.g. the original 8.5 GB Dryad download / any multi-tile `preprocess-cog`). We have none of those in the hex step; the 8.5 GB download was staged off-cluster (laptop → S3), so no PVC was needed there either. If a future >50Gi single-pod stage step is added, mount `rechunk-scratch` with a per-job `subPath` and set `TMPDIR=/scratch`.
- **Res-8 jobs hardened** (`forestry-return`, `flii`): `backoffLimit: 0` → **`backoffLimitPerIndex: 2` + `maxFailedIndexes: 10`** (absorb preemptions without failing the whole 122-pod job) and ephemeral bumped to **45Gi**. Res-5 economic jobs stay at defaults (tiny/fast).
- Confirmed generated YAMLs already **mount the `rclone-config` secret** (needed for COG localization + S3 write) and use image **`:latest`** (antimeridian seam fix).

## Campaign waves (pod-quota: one k8s hex job at a time; res-5 jobs are tiny, res-8 are 122-pod)

**Wave 1 — economic objective (res 5, fast):** crop-current, crop-irrigated, crop-rainfed, palm-current,
grazing-return, grazing-methane. These are 4320×2160 — trivial to hex.

**Wave 2 — biodiversity sub-index (v) + forestry (res 8):** flii, forestry-return.

**Wave 3 — scenario layers (res 8):** lulc-current, lulc-potential, then transition costs (restoration,
sustainable_current, the extensification/intensified crop scenarios first), then the binary masks.

## Generation (local venv) + apply

```bash
B=public-nci-frontiers; R=s3://$B/raw/inputs
gen() { # gen <dataset> <relpath> <value-col> <reducer> <h3res> <parents> [nodata]
  .venv/bin/cng-datasets raster-workflow --dataset "$1" --source-url "$R/$2" --bucket $B \
    --value-column "$3" --hex-resampling "$4" --h3-resolution "$5" --parent-resolutions "$6" \
    ${7:+--nodata "$7"} --hex-memory 32Gi --max-parallelism 61 \
    --output-dir "catalog/nci-frontiers/k8s/$1"
}
# Wave 1 (res 5)
gen crop-current   cropland/oil_palm_split/totalproductionvaluecurrent_NoPalmOilRevR_nolabor_machinerycosts.tif  crop_current_usd_ha mean 5 "4,3,0" 0
gen crop-irrigated cropland/oil_palm_split/totalproductionvalueirrigated_NoPalmOilRevR_nolabor_machinerycosts.tif crop_irrig_usd_ha   mean 5 "4,3,0" 0
gen crop-rainfed   cropland/oil_palm_split/totalproductionvaluerainfed_NoPalmOilRevR_nolabor_machinerycosts.tif   crop_rainfed_usd_ha mean 5 "4,3,0" 0
gen palm-current   cropland/oil_palm_split/totalproductionvaluecurrent_OnlyPalmOilRevR_nolabor_machinerycosts.tif palm_current_usd_ha mean 5 "4,3,0" 0
gen grazing-return  "grazing/potential_meat_returns-t_per_ha_global_price_landshare_md5_d7cfbe4828d5b9a2e11ef1b6e2ccc174.tif" grazing_usd_ha  mean 5 "4,3,0" -9999
gen grazing-methane "grazing/potential_methane_filled_0.5_md5_9a8735eb022a44bc5a00b809bea69bcb.tif"               methane_kg_ha_yr mean 5 "4,3,0"
# Wave 2 (res 8)
gen forestry-return forestry/forestry_land_share_return_tcost_before_2022_07_23.tif forestry_usd_ha mean 8 "7,6,5,0" -99999
gen flii            biodiversity/GlobalLayers/flii.tif                              flii            mean 8 "7,6,5,0"
# (Wave 3 transition costs + masks generated similarly; sum / max reducers, nodata per table.)

# apply one at a time, waiting between (200-pod quota):
for d in crop-current crop-irrigated crop-rainfed palm-current grazing-return grazing-methane; do
  kubectl apply -f catalog/nci-frontiers/k8s/$d/configmap.yaml -f catalog/nci-frontiers/k8s/$d/workflow.yaml
  kubectl -n biodiversity wait job/$d-workflow --for=condition=complete --timeout=3600s
done
```

After hexing: STAC per layer, then the faithful multi-alternative frontier (POC 6 extended to the paper's
13 alternatives using crop_current/irrigated/rainfed + transition costs + restoration), or the authors'
Julia code on the same inputs.
