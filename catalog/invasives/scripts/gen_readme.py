#!/usr/bin/env python3
"""Generate the public-invasives bucket README (data-workflows #610).

Writes /tmp/invasives-README.md -> s3://public-invasives/README.md

Every table is derived from `gen_stac.py`'s measured constants rather than retyped, so the
README, the STAC asset descriptions and the build notes cannot drift apart.
"""
import contextlib
import io
import os
from importlib import util

_HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.pop("READY_LAYERS", None)          # README documents the full phase-1 set
_spec = util.spec_from_file_location("inhabit_stac", os.path.join(_HERE, "gen_stac.py"))
g = util.module_from_spec(_spec)
with contextlib.redirect_stdout(io.StringIO()):   # gen_stac prints; keep it out of the README
    _spec.loader.exec_module(g)

OUT = []
def w(s=""): OUT.append(s)

TEMPLATE = """# public-invasives

Invasive-species habitat-suitability surfaces. Canonical STAC:
<https://s3-west.nrp-nautilus.io/public-invasives/stac-collection.json>

Currently one collection: **`inhabit-v4-2024`** — USGS Invasive Species Habitat Tool (INHABIT)
v4.0, June 2024, for 12 fire-cycle-relevant invasive plants across the contiguous United States.

STAC: <https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/stac-collection.json>

---

## Read this before you use it

**These are modelled POTENTIAL habitat surfaces, not occurrence records.** A high-suitability
pixel says the environment could support the species, not that the species is there. Phrase every
result as "suitable habitat for X" — never "X is present". What the data supports is an argument
about invasion *pressure and vulnerability*.

Four more constraints that change answers, not just wording:

| | |
|---|---|
| **`-masked` is the default for roadless work** | The `-masked` variants suppress suitability outside the MESS training envelope. Roadless country is disproportionately high-elevation, undersampled terrain — exactly where unrestricted extrapolation is least trustworthy. Retention varies ~3× by species (table below). |
| **`fifth` (0.05) is the canonical threshold** | Named up front so an analysis cannot pick the threshold that suits its conclusion. `first` (0.01, inclusive) and `tenth` (0.10, targeted) are the sensitivity band and land in phase 2. |
| **Class `-1` is a class, not fill** | It is the MESS extrapolation flag. NoData is `-128`. `-1` reaches 48% of a raster (red brome) — a sign test that drops negatives deletes half the map. |
| **CONUS only** | INHABIT v4 excludes Alaska, where the Tongass and Chugach are the largest roadless acreage in the National Forest System. Any national claim from this data is a CONUS claim. |

## Species

| Species | Common name | ScienceBase child item |
|---|---|---|
@@SPECIES@@

## Products

Phase 1 (published) is four products per species = 48 layers, each as a COG and an H3 res-10 hex:

| Product | Reducer | Warp resampling | Value |
|---|---|---|---|
| `occurrence-masked` | `mean` | bilinear | relative suitability 0–100 for occurrence |
| `abundance-masked` | `mean` | bilinear | relative suitability 0–100 for abundance (≥5% cover) |
| `high-abundance-masked` | `mean` | bilinear | relative suitability 0–100 for high abundance (≥25% cover) |
| `integrated-binary-fifth` | `mode` | **nearest** | class code, see below |

`mean` for the continuous surfaces because relative suitability is a normalized index, not a
per-pixel amount — **`SUM` is meaningless; aggregate with `AVG` or `MAX`**. `mode` for the class
raster, and **nearest-neighbour** on the warp: bilinear on class codes invents codes with no
upstream referent.

Phase 2 adds the unmasked continuous surfaces and the `first` / `tenth` thresholds — additively
into the same collection, same grid, no rebuild.

### `integrated-binary-*` class codes

Labels are from the release's own documentation, not inferred: `INHABIT_VersionHistory.txt`
("categorical map combining unsuitable, occurrence suitable, abundance suitable, and high
abundance suitable") and Jarnevich et al. 2024 ("…while highlighting any areas of environmental
extrapolation"). The FGDC gives the domain `-1 .. 3` but no labels.

| Code | Class | Meaning |
|---:|---|---|
@@CLASSES@@

@@NESTING@@

`mode` keeps only each cell's dominant class and discards the mix, so this hex **cannot** answer
"how much area is high-abundance-suitable" without undercounting to plurality cells. At ~1.55
source pixels per res-10 cell the loss is small but one-directional. Per-class fractional
coverage is not produced by this pipeline.

## How much surface `-masked` removes

Data pixels retained by the MESS-restricted variant, as a percent of the plain product
(measured — exact full-raster bincount over all 108 source rasters):

| Species | occurrence | abundance | high abundance |
|---|---:|---:|---:|
@@RETENTION@@

Two things to carry from this table. **For buffelgrass, `-masked` discards two thirds of CONUS** —
a masked tabulation for that species is a statement about a third of the country, and the
masked-vs-plain choice moves the answer more than any threshold choice does. Red brome and
medusahead are next. **Cheatgrass — the species most of the fire argument rests on — is barely
touched at 95%.**

One anomaly, recorded rather than smoothed over: for *Aegilops cylindrica* `abundance`, the masked
file's value histogram is identical to the plain product (100.0% retained; the files differ by 476
bytes of TIFF metadata). Its `high-abundance` counterpart *is* genuinely masked. So for that one
species × product, `-masked` implies a safeguard that did nothing.

## Road-bias audit — it fires, and it splits the species

`gHM` (Global Human Modification — built substantially from roads, and already in this catalog as
`global-human-modification`) is a predictor in **all 12** models. Restricted to the **occurrence**
models, which is what a distance-to-road gradient actually leans on:

| Species | gHM share, occurrence models | rank | Road-distance gradient |
|---|---:|---|---|
@@GHM@@

Method: mean `AUCdiff` per predictor from each species' `variableImportance.csv`, pooled over the
five SAHM algorithms and data splits, negatives clipped to zero, expressed as a share of the
positive total. Full per-model-group breakdown in `catalog/invasives/BUILD.md`.

**Consequence.** Cheatgrass is the cleanest of the 12 and has *no* KDE-background occurrence model
at all — its only occurrence model uses the bias-mitigated target-background design. Medusahead
and red brome are also clean. **Tamarisk is not**: at 17.1% (rank 3/25) a tamarisk road-distance
gradient is substantially the model reproducing its own predictor. Report tamarisk, Russian olive,
jointed goatgrass, buffelgrass and Russian thistle as suitability-only.

This does **not** invalidate the suitability surfaces — human modification is a legitimate
predictor of invasion. It invalidates only the inference "suitability rises near roads, therefore
roads drive invasion" for the high-gHM species.

## Grid

| | |
|---|---|
| Source | Albers Conical Equal Area, NAD83 / GRS 1980, **98.4693338923368 m** (FGDC `absres`; the papers round to "90 m"), 44319 × 30671 |
| Published COG | EPSG:4326, **0.001096100359°**, 57745 × 25711, origin (−128.386308874497, 51.268044444672) — identical for all 48 layers, asserted at build time |
| H3 | native **10**, parents **9, 8, 0** (≈1.55 source pixels per res-10 cell). `h8` is the catalog's universal join key |

## Query examples

### DuckDB — suitability is an index, so AVG never SUM

```sql
INSTALL httpfs; LOAD httpfs;
INSTALL h3 FROM community; LOAD h3;

-- Mean cheatgrass occurrence suitability per res-8 cell
SELECT h8, AVG(suitability) AS mean_suitability, COUNT(*) AS n_res10_cells
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/occurrence-masked/hex/h0=*/data_0.parquet')
GROUP BY h8;
```

```sql
-- Integrated class distribution. `-1` is the extrapolation flag, NOT unsuitable:
-- exclude it explicitly rather than letting it fall in with class 0.
SELECT suitability_class, COUNT(*) AS cells
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/integrated-binary-fifth/hex/h0=*/data_0.parquet')
GROUP BY suitability_class ORDER BY suitability_class;

-- Occurrence-suitable ground is `>= 1` (classes 1+2+3), not `= 1`.
SELECT COUNT(*) AS occurrence_suitable_cells
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/integrated-binary-fifth/hex/h0=*/data_0.parquet')
WHERE suitability_class >= 1;
```

```sql
-- Join two species at h8 (both are native res 10, so h8 is present in both)
SELECT a.h8, AVG(a.suitability) AS cheatgrass, AVG(b.suitability) AS medusahead
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/occurrence-masked/hex/h0=*/data_0.parquet') a
JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/taeniatherum_caput_medusae/occurrence-masked/hex/h0=*/data_0.parquet') b
  USING (h10)
GROUP BY a.h8;
```

### MapLibre GL JS (COG via titiler)

Raster layers have no PMTiles; render the COG through a titiler raster-tile endpoint. Use a
**categorical** colormap for `integrated-binary-*` — a continuous ramp misreads the `-1`
extrapolation flag as a suitability level.

```js
// Continuous suitability, 0-100
map.addSource("cheatgrass-occ", {
  type: "raster",
  tiles: [
    "https://titiler.../cog/tiles/{z}/{x}/{y}.png" +
    "?url=https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/occurrence-masked.tif" +
    "&rescale=0,100&colormap_name=inferno"
  ],
  tileSize: 256,
});
map.addLayer({ id: "cheatgrass-occ", type: "raster", source: "cheatgrass-occ" });

// Integrated class map - discrete colours from the STAC classification:classes color_hint
const cmap = encodeURIComponent(JSON.stringify({
  "-1": [123, 104, 166, 255],  // novel environmental conditions (MESS extrapolation)
  "0":  [242, 242, 242, 255],  // unsuitable
  "1":  [254, 217, 118, 255],  // occurrence suitable
  "2":  [253, 141,  60, 255],  // abundance suitable
  "3":  [189,   0,  38, 255],  // high abundance suitable
}));
map.addSource("cheatgrass-class", {
  type: "raster",
  tiles: [
    "https://titiler.../cog/tiles/{z}/{x}/{y}.png" +
    "?url=https://s3-west.nrp-nautilus.io/public-invasives/inhabit-v4-2024/bromus_tectorum/integrated-binary-fifth.tif" +
    "&colormap=" + cmap
  ],
  tileSize: 256,
});
map.addLayer({ id: "cheatgrass-class", type: "raster", source: "cheatgrass-class" });
```

## Not held, deliberately

- **INHABIT v3.0** ([doi:10.5066/P9V54H5K](https://doi.org/10.5066/P9V54H5K)) — superseded, and v4
  changed the ensemble from *model agreement* to *continuous relative suitability*, so v3 and v4
  pixel values are not comparable.
- **The 2026-02-11 integrated management summaries**
  ([doi:10.5066/P14G2CHI](https://doi.org/10.5066/P14G2CHI)) — pre-summarized to 118,433
  administrative units, none of which is the inventoried-roadless-area boundary.
- **INHABIT Global V1** ([doi:10.5066/P13AJ46S](https://doi.org/10.5066/P13AJ46S)) — could close
  the Alaska gap later, but different grid and different models; not pixel-comparable with v4 CONUS.
- **The other 247 v4 species** — a follow-up, not a silent expansion.

## Licence

USGS data release; FGDC `useconst` and `accconst` are both "None" → **US federal work, public
domain**.

## Citation

@@CITE@@
"""


def species_rows():
    return "\n".join(f"| *{sci}* | {common} | `{sb}` |"
                      for _slug, sci, common, sb in g.SPECIES)


def class_rows():
    return "\n".join(f"| `{v}` | {n} | {d} |" for v, n, d, _c in g.CLASSES)


def retention_rows():
    rows = []
    for slug, sci, common, _sb in g.SPECIES:
        r = [g.MASKED_RETENTION[f"{slug}|{p}"]
             for p in ("occurrence", "abundance", "high-abundance")]
        rows.append((min(r), common, sci, r))
    # worst-affected first: the species where the masked/plain choice matters most
    bold = lambda x: f"**{x}%**" if x < 70 else f"{x}%"
    return "\n".join(f"| *{sci}* ({common}) | {bold(r[0])} | {bold(r[1])} | {bold(r[2])} |"
                      for _m, common, sci, r in sorted(rows))


def ghm_rows():
    verdict = lambda s: ("defensible" if s < 5 else "caution" if s < 10
                         else "**circular — do not report**")
    rows = [(g.GHM[slug][3], sci, common, g.GHM[slug])
            for slug, sci, common, _sb in g.SPECIES]
    return "\n".join(
        f"| *{sci}* ({common}) | {h[3]}% | {h[4]}/{h[5]} | {verdict(h[3])} |"
        for _s, sci, common, h in sorted(rows))


md = (TEMPLATE
      .replace("@@SPECIES@@", species_rows())
      .replace("@@CLASSES@@", class_rows())
      .replace("@@RETENTION@@", retention_rows())
      .replace("@@GHM@@", ghm_rows())
      .replace("@@NESTING@@", "**" + g.NESTING + "**")
      .replace("@@CITE@@", g.CITE))

with open("/tmp/invasives-README.md", "w", encoding="utf-8") as fh:
    fh.write(md)
print(f"wrote /tmp/invasives-README.md — {len(md.splitlines())} lines, "
      f"{len(g.SPECIES)} species, {len(g.CLASSES)} classes")
