# UNEP-WCMC coral reefs & seagrass — build notes (#444)

Four collections across two buckets, all from two UNEP-WCMC downloads.

| dataset | bucket | geometry | features | source layer |
|---|---|---|---|---|
| `unep-wcmc-coral-reefs/polygons` | `public-coral-reefs` | MultiPolygon | 17,504 | `WCMC008_CoralReef2018_Py_v4_1` |
| `unep-wcmc-coral-reefs/points` | `public-coral-reefs` | Point | 925 | `WCMC008_CoralReef2018_Pt_v4_1` |
| `unep-wcmc-seagrass/polygons` | `public-seagrass` | MultiPolygon | 293,147 | `WCMC013_014_Seagrasses_Py_v7_1` |
| `unep-wcmc-seagrass/points` | `public-seagrass` | Point | 17,668 | `WCMC013_014_Seagrasses_Pt_v7_1` |

H3: native resolution **8**, parent resolutions **`0`**.

## Sources and access

Accessed **2026-09-15**. The `data.unep-wcmc.org/datasets/{1,7}` landing pages cited in #444 are
stale — both now redirect to `habitats.oceanplus.org`, a statistics portal with no download. The
working route is the UNEP-WCMC ArcGIS portal item page, whose official `wcmc.io` shortlink
redirects to a plain AWS S3 object over healthy TLS. The expired-certificate workaround described
in the issue is not needed.

| | coral reefs (WCMC-008 v4.1) | seagrass (WCMC-013/014 v7.1) |
|---|---|---|
| landing page | [portal item `06136043…`](https://data-gis.unep-wcmc.org/portal/home/item.html?id=0613604367334836863f5c0c10e452bf) | [portal item `aaa46cd3…`](https://data-gis.unep-wcmc.org/portal/home/item.html?id=aaa46cd3d3d640b2916b8f0a0ffe07cb) |
| download | `https://wcmc.io/WCMC_008` | `https://wcmc.io/WCMC_013_014` |
| staged raw | `s3://public-coral-reefs/raw/WCMC008_CoralReefs2018_v4_1.zip` | `s3://public-seagrass/raw/WCMC013-014_SeagrassPtPy2021_v7_1.zip` |
| bytes | 220,904,276 | 485,748,212 |
| sha256 | `09c7fe54c85b365c3968b8945034ebc649389c2832b0ab4b91dd2e50ee3a7124` | `25b9d1cfecbd0b51af58a3b2b0c11e643074bf02ea084ab634e5d092f5f02d2d` |

Each archive ships **both** a point and a polygon layer, which is why one download feeds two
collections.

## ⚠️ The coral point layer is regional, not global

Measured from the source, not assumed:

```
coral points   extent (-118.290176, 14.708445) - (-83.886970, 32.442383)    925 features
coral polygons extent (-179.999935, -34.298230) - (179.999936, 32.514818) 17,504 features
```

The 925 coral points fall only in the wider Caribbean, Gulf of Mexico and eastern tropical
Pacific. "Global warm-water reefs" is true of the polygon layer; the point collection's STAC must
carry its measured bbox and must not inherit the global claim.

## ⛔ Upstream bug: convert crashes on the multi-layer archive

`cng-convert-to-parquet` **segfaults (exit 139)** on a `.zip` holding more than one shapefile, and
`--layer` does not avoid it — the flag selects only the file used for metadata detection while the
read still unions every vector source in the archive. POINT unioned with MULTIPOLYGON crashes the
process with no traceback. Filed as
[boettiger-lab/datasets#216](https://github.com/boettiger-lab/datasets/issues/216) with a tested
MRE; not patched here (Hard Boundary 2).

The giveaway is in the log — asking for the polygon layer still reports the point one:

```
Found 2 vector source(s) in archive
Using WCMC008_CoralReef2018_Pt_v4_1.shp for metadata detection   <-- --layer was Py
Segmentation fault (core dumped)   exit=139
```

**Workaround (`k8s/wcmc-split-layers.yaml`):** split each archive into one zip per shapefile,
staged beside the original raw, then convert each with no `--layer` at all. A single-source archive
reports `Found 1 vector source(s) in archive` and converts cleanly.

```
s3://public-coral-reefs/raw/WCMC008_CoralReef2018_Py_v4_1.zip     219,412,390
s3://public-coral-reefs/raw/WCMC008_CoralReef2018_Pt_v4_1.zip          42,492
s3://public-seagrass/raw/WCMC013_014_Seagrasses_Py_v7_1.zip       495,851,340
s3://public-seagrass/raw/WCMC013_014_Seagrasses_Pt_v7_1.zip           445,201
```

The split drops the `.xml`, `.sbn` and `.sbx` sidecars, which the reader does not use.

Once #216 lands, the split step can be dropped and the workflows regenerated with `--layer`
against the original archive.

## Measured findings that changed what the STAC says

Recorded because each one contradicts a reasonable assumption, and all four collections now carry
the measured version instead.

**Coral `GIS_AREA_K` is a source-record total, not a per-polygon area.** Summing it raw gives
899,466 km²; collapsing to distinct `(NAME, METADATA_I, GIS_AREA_K)` gives **151,288 km²**, which
is the figure consistent with the reef area UNEP-WCMC publishes. The STAC and README both carry
the dedup SQL.

**Seagrass `AREA_SQKM` is the opposite — genuinely per-polygon.** 290,401 distinct values across
293,147 rows, so `SUM` on the flat GeoParquet is correct (667,004 km²) and de-duplication would
undercount. The coral warning was deliberately *not* copied across; on the hex asset, where the
(feature, cell) expansion does repeat it, the dedup note applies again.

**The seagrass polygon layer is not purely marine.** Alongside *Zostera*, *Posidonia* and
*Halophila* it carries freshwater and brackish genera — *Myriophyllum*, *Najas*, *Vallisneria*,
*Trapa*, *Utricularia*, *Ceratophyllum*, *Hydrilla*. 22 families and 31 genera against the point
layer's 6 and 14.

**Coral mapping effort varies by orders of magnitude.** `Metadata_CoralReefs.dbf` in the archive
holds 81 source records keyed by `METADATA_I`, with nominal scales from as fine as 1:6,000 to as
coarse as 1:15,000,000. Read as "where reefs have been mapped", not an even-effort census.

**Three transcription traps, all caught by the data-backed verifier and none by inspection:**

1. Seagrass taxonomy `values` written from the *point* layer and reused for *polygons* — wrong by
   16 families and 17 genera.
2. `SURVEY_MET` on coral polygons ends in a **literal asterisk**:
   `Assessment of LADS features based on geomorpholog*`. That is upstream's own marker for a label
   cut to fit a 50-character field. The plausible reconstruction ("…geomorphology") was wrong.
3. Casing differs between the two layers of the same product — polygons carry `Expert Verified` /
   `Field survey`, points carry `Expert verified` / `Field Survey`; seagrass points carry both
   `Not Reported` and `Not reported` in one column.

Every `values` array is therefore generated from the published parquet rather than typed. See
`catalog/wcmc-stac/`.

**Other consumer-facing quirks now documented in STAC:** seagrass `habitat` is a 50-character
field truncated mid-word upstream, with near-duplicate variants (`Z. marina`/`Z.marina`,
`sediment`/`sediments`); seagrass `FAMILY`/`GENUS` use pipe-separated compound values
(`Valisneria | najas`) with inconsistent spelling (`Haloragaceae`/`Haloragidaceae`).

## Licence

Both archives carry an identical `LICENSE.txt`: **UNEP-WCMC General Data License (excluding
WDPA)**, last updated 21/07/2014, canonical at
<https://www.unep-wcmc.org/en/general-data-license>. STAC records `license: "other"` plus a
`{"rel": "license"}` link to that page — the page is itself the terms document, so it settles the
redistribution question without additional boilerplate.

Operative clauses, quoted rather than summarised because they are easy to soften by accident:

- **§2 No commercial use** — no Commercial Use of the Data or Derivative Works without prior
  written permission of the Director of UNEP-WCMC.
- **§3 No sub-licensing or redistribution** — *"You may not redistribute the Data in whole or in
  part by any means including (but not limited to) electronic formats such as web downloads,
  through web services … or through file transfer protocols."*
- **§4 Publishing** — permitted *"providing (a) the Data are not downloadable and (b) the
  appropriate proper attribution is clearly visible"*, and: *"If you are planning an analysis that
  either makes use of the dataset(s) in their entirety and/or is a global-scale analysis, you are
  required to notify the Director of UNEP-WCMC."*

This ingest is global and uses the datasets in their entirety, so §4's notification clause applies
on its own terms. Recorded here because it is a fact about the grant that cannot be re-derived
from the data later.

## Edition labels disagree upstream — none was synthesised

| artifact | says |
|---|---|
| coral `READ ME.txt` | "Version: 4.1", released March 2021 |
| coral requested citation | "Version 4.0" |
| seagrass `READ ME.txt` | "**Version: 8.0**", released March 2021 |
| seagrass filename / citation | `v7_1` / "version 7" |
| seagrass polygon `DBF_DATE_LAST_UPDATE` | **2025-02-17** (four years after the stated release) |

STAC carries the distributed filename edition (`v4.1`, `v7.1`) and states the discrepancy. Per
AGENTS.md, a `DBF_DATE_LAST_UPDATE` is a file mtime, not an edition, and is not used as one.

## Requested citations

- **Coral:** UNEP-WCMC, WorldFish Centre, WRI, TNC (2010). *Global distribution of warm-water coral
  reefs, compiled from multiple sources including the Millennium Coral Reef Mapping Project.
  Version 4.0.* Includes contributions from IMaRS-USF and IRD (2005), IMaRS-USF (2005) and
  Spalding et al. (2001). Cambridge (UK): UNEP World Conservation Monitoring Centre.
- **Seagrass:** UNEP-WCMC, Short FT (2020). *Global Distribution of Seagrasses (version 7).*
  Seventh update to the data layer used in Green and Short (2003), superseding version 6.
  Cambridge (UK): UN Environment World Conservation Monitoring Centre.

## Allen Coral Atlas is not in this build

#444 also scoped Allen Coral Atlas. There is no ingestible route: no public bulk download (the
atlas serves per-area exports, account-gated, links expiring after 30 days), the cited Zenodo DOI
`10.5281/zenodo.3833242` resolves to a 2,995-byte code-release stub rather than data, and the only
global source is Google Earth Engine `ACA/reef_habitat/v2_0` — which needs an Earth Engine
credential in `geo-workflows`, contrary to Hard Boundary 3. Recorded on the issue; tracked
separately.

## Rebuild

```bash
kubectl apply -n geo-workflows -f catalog/coral-reefs/k8s/coral-reefs-setup-bucket.yaml
kubectl apply -n geo-workflows -f catalog/seagrass/k8s/seagrass-setup-bucket.yaml
kubectl apply -n geo-workflows -f catalog/coral-reefs/k8s/coral-reefs-stage-raw.yaml
kubectl apply -n geo-workflows -f catalog/seagrass/k8s/seagrass-stage-raw.yaml
kubectl apply -n geo-workflows -f catalog/coral-reefs/k8s/wcmc-split-layers.yaml   # until datasets#216
for d in catalog/coral-reefs/k8s/points catalog/coral-reefs/k8s/polygons \
         catalog/seagrass/k8s/points   catalog/seagrass/k8s/polygons ; do
  kubectl apply -n geo-workflows -f $d/configmap.yaml -f $d/workflow.yaml
  # one hex workflow at a time
done
```


## Published

Six documents on NRP, all four collections passing `verify-stac.py --bucket … --dataset …`:

```
s3://public-coral-reefs/stac-collection.json
s3://public-coral-reefs/README.md
s3://public-coral-reefs/unep-wcmc-coral-reefs/polygons/stac-collection.json
s3://public-coral-reefs/unep-wcmc-coral-reefs/points/stac-collection.json
s3://public-seagrass/stac-collection.json
s3://public-seagrass/README.md
s3://public-seagrass/unep-wcmc-seagrass/polygons/stac-collection.json
s3://public-seagrass/unep-wcmc-seagrass/points/stac-collection.json
```

Both bucket collections are registered as children of the root catalog
(`public-data/stac/catalog.json`).
