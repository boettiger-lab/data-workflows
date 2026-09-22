#!/usr/bin/env python3
"""Generate the STAC for connectivity/rcn-national, plus the parent and README (#606).

STAC and README are canonical on NRP S3 and are never committed to this repo, so this
writes them to /tmp for `scripts/verify-stac.py` and then `rcn-national-publish-stac.yaml`
uploads them from a ConfigMap.

    python3 catalog/connectivity/rcn-national-stac.py
    scripts/verify-stac.py --no-data /tmp/stac-collection.json

Writes /tmp/stac-collection.json, /tmp/parent.json and /tmp/bucket-readme.md. The parent
and README are edited in place from what is live on S3, so reruns stay idempotent.

Everything under MEASURED is read off the produced artifacts, never transcribed from the
issue or from upstream prose:
  * class labels and pixel counts   -> the VAT, cross-checked against the full native
                                       grid by rcn-national-vat-audit.yaml
  * data bbox                       -> rcn-national-validate.yaml, off the published COG
  * staged raw size and sha256      -> rcn-national-validate.yaml, off the S3 object
"""

import csv
import io
import json
import urllib.request

BUCKET = "https://s3-west.nrp-nautilus.io/public-connectivity"
VAT_URL = f"{BUCKET}/raw/vat/a00000020_vat_RCN_National_2024.csv"

# --- MEASURED ---------------------------------------------------------------------
# rcn-national-validate.yaml, "data bbox" (the COG frame is larger and mostly nodata).
BBOX = [-124.752861, 24.429265, -59.664909, 52.661374]
# rcn-national-validate.yaml, "staged raw": stat + sha256sum of the object on S3.
RAW_BYTES = 1470642324
RAW_SHA256 = "6993d6c4a5d2b244b8a26b880a48201f3666d8e18720002fde21978a98a4b45a"
# rcn-national-vat-audit.yaml: mask-valid pixels == VAT total, x 900 m2 per 30 m pixel.
MAPPED_PX = 9_729_522_776
MAPPED_KM2 = MAPPED_PX * 900 / 1e6

ACCESSED = "2026-09-15"
GDB_MEMBER_DATE = "2024-05-21"
TERMS = "https://tnc.app.box.com/s/bu8jfr4c64mi471o1j6jcbi04k8up0x6"
LANDING = "https://tnc.box.com/s/14g44i2273abcdcjmdacat77ikr27gd0"
DOI = "https://doi.org/10.1073/pnas.2204434119"

# Colours for the 11 classes TNC's own "Resilient and Connected Network (Detailed).lyrx"
# styles, matched to the VAT by exact label text. The layer file styles 11 of the 14 VAT
# classes; 0, 1 and 91 are unstyled there and are assigned here (greys for the two
# not-in-network classes, a mid green for 91 between its 92 and 93 siblings).
COLORS = {
    0: "E8E8E8", 1: "B8B8B8",
    10: "73B2FF", 20: "6A99D3", 30: "BED2FF", 40: "A2B1D3",
    50: "A87000", 60: "807000", 70: "FFAA00", 80: "D39314",
    90: "FFD37F", 91: "4C9E45", 92: "89CD69", 93: "267300",
}
TNC_STYLED = {10, 20, 30, 40, 50, 60, 70, 80, 90, 92, 93}
NAMED = {"Not in Network": 0, "Resilient Not in Network": 1}


def read_vat():
    """class code -> (label, pixel count), straight from the raster's own VAT."""
    with urllib.request.urlopen(VAT_URL) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))
    out = {}
    for r in rows:
        label = r["RCN_DESC_NEW"].strip()
        cls = int(r["Vals"]) if r["Vals"].strip() else NAMED[label]
        # the VAT label carries the code as a prefix ("10 Resilient, ..."); drop it
        text = label[len(str(cls)):].strip() if label.startswith(str(cls)) else label
        count, _ = out.get(cls, (0, None))
        out[cls] = (count + int(float(r["Count"])), text)
    return {c: (t, n) for c, (n, t) in out.items()}


VAT = read_vat()
CLASSES = sorted(VAT)
assert set(CLASSES) == set(COLORS), (CLASSES, sorted(COLORS))

# MEASURED: the column type and the distinct values the hex build actually wrote,
# read back from the published parquet (not assumed from the COG's Byte band).
CLASS_TYPE = "uint8"

VALUES_TEXT = ", ".join(f"{c}={VAT[c][0]}" for c in CLASSES)

CLASS_DESC = (
    "Resilient and Connected Network class. Categorical: these are class codes, so do "
    "not sum or average them. Values: " + VALUES_TEXT + ". 0 and 1 are real classes "
    "describing land outside the network, not missing data; 255 is no data (outside the "
    "mapped footprint)."
)

H3_COLS = [
    ("h10", "uint64", "H3 cell ID at resolution 10, the native resolution of this "
                      "dataset."),
    ("h9", "uint64", "H3 cell ID at resolution 9."),
    ("h8", "uint64", "H3 cell ID at resolution 8, the resolution most datasets in this "
                     "catalog share for joins."),
    ("h7", "uint64", "H3 cell ID at resolution 7."),
    ("h6", "uint64", "H3 cell ID at resolution 6."),
    ("h5", "uint64", "H3 cell ID at resolution 5."),
    ("h0", "int64", "H3 cell ID at resolution 0, used as the partition key for "
                    "hive-partitioned reads."),
]


def cols(*extra):
    """extra = (name, type, description) or (name, type, description, values)."""
    out = []
    for e in extra:
        col = {"name": e[0], "type": e[1], "description": e[2]}
        if len(e) > 3:
            col["values"] = e[3]
        out.append(col)
    return out + [{"name": n, "type": t, "description": d} for n, t, d in H3_COLS]


DESCRIPTION = (
    "The Nature Conservancy's Resilient and Connected Network: a 30 metre map of the "
    "sites and corridors that, taken together, would sustain biodiversity as the climate "
    "changes. Each pixel is placed in one of 14 classes combining how climate-resilient "
    "the site is, whether species can move through it as diffuse or concentrated flow, "
    "whether it holds recognized biodiversity value, and whether it is already secured. "
    "Published as the band rcn_class.\n\n"
    "Footprint: the conterminous United States plus the adjacent parts of Canada that "
    "TNC mapped, which are the prairie provinces north to about 52.7 degrees and the "
    "Maritimes (New Brunswick, Nova Scotia, Prince Edward Island). Quebec, Ontario north "
    "of Lake Superior, Newfoundland, British Columbia and Mexico are outside the mapped "
    "area. The mapped area is "
    f"{MAPPED_KM2:,.0f} square kilometres, so a statistic for the United States alone "
    "needs a national mask rather than the whole raster. Alaska and Hawaii are separate "
    "rasters in the source and are not included here.\n\n"
    "Class 0 (Not in Network) and class 1 (Resilient Not in Network) are real classes "
    "describing mapped land that is outside the network, and together they are about 62 "
    "percent of the mapped area. Only 255 means no data. Treating 0 as no data drops most "
    "of the mapped footprint.\n\n"
    "Licensing: TNC grants a non-commercial licence for this data, and that restriction "
    "carries to anyone using these derived products. See the licence link on this "
    "collection for the full terms.\n\n"
    "Cloud-native products: a WGS84 categorical COG reprojected from the source NAD83 "
    "Albers with nearest-neighbour resampling, an H3 hex at native resolution 10 using "
    "the mode reducer, and a per-class fractional-coverage hex at the same resolution "
    "for area accounting.\n\n"
    "Provenance: downloaded from The Nature Conservancy on "
    f"{ACCESSED} and staged at s3://public-connectivity/raw/"
    f"Resilient_and_Connected_Network_National_2024.zip ({RAW_BYTES:,} bytes, sha256 "
    f"{RAW_SHA256}). The file geodatabase member carries the date {GDB_MEMBER_DATE}. TNC "
    "publishes no edition or version label for this release, so none is asserted here; "
    "the access date and the checksum above identify the copy these products were built "
    "from. The class codes and labels are taken from the raster's own value attribute "
    "table, which defines 14 classes."
)

HEX_DESC = (
    "H3 hex at native resolution 10, hive-partitioned by h0, with rollup columns at "
    "resolutions 9, 8, 7, 6 and 5. One row per H3 cell, holding the mode (most common) "
    "rcn_class over the 30 metre source pixels inside that cell. Resolution 10 matches "
    "the 30 metre source and is the finest resolution this catalog carries. The mode "
    "keeps only each cell's dominant class and discards the rest of the mix, so it "
    "answers \"which class dominates here\" but understates the area of classes that are "
    "common without ever dominating a cell. For class areas use the fractional-coverage "
    "asset instead. Cells with no mapped pixel are absent rather than present with a no "
    "data value."
)

FRAC_DESC = (
    "Per-class fractional coverage at H3 resolution 10, hive-partitioned by h0. One row "
    "per (cell, class present), not one row per cell: frac is the exact share of the H3 "
    "cell covered by that rcn_class, and per cell the frac values sum to 1 with no data "
    "carried as the explicit class 255. This is the asset to use for class areas, which "
    "the mode asset cannot give. To get an area per class, weight each row's frac by its "
    "own H3 cell's ground area and sum by class, excluding rcn_class 255, which is the "
    "no data share; take the cell area from the H3 area recipe in the h3-guide rather "
    "than a nominal per-resolution constant."
)


PARENT_DESC_OLD_PREFIX = "Landscape connectivity and climate-resilience datasets for "


def parent():
    """Widen the bucket collection and register rcn-national as a child.

    Edited from the live copy rather than rewritten, so the five existing California
    children and their titles are preserved exactly.
    """
    url = f"{BUCKET}/stac-collection.json"
    with urllib.request.urlopen(url) as r:
        p = json.load(r)

    p["title"] = "Connectivity & Resilience"
    p["description"] = (
        "Landscape connectivity and climate-resilience datasets. Most of this collection "
        "covers California, from the California Biodiversity Network (CBN) and partners: "
        "present-day connectivity (Cameron et al. 2022), climate-migration routes "
        "(Schloss et al. 2022), regional connectivity linkages (Beier et al. 2006 / CDFW "
        "BIOS) and wildlife movement barriers (CDFW 2024). The Resilient and Connected "
        "Network (TNC) is continental instead, covering the conterminous United States "
        "and adjacent Canada, so the extent of this collection is wider than any one "
        "child. Licences differ by child, and the TNC layer is non-commercial. This "
        "collection is a grouping only - select a child collection to access data."
    )
    # union of the existing California bbox with the RCN footprint
    old = p["extent"]["spatial"]["bbox"][0]
    p["extent"]["spatial"]["bbox"] = [[
        min(old[0], BBOX[0]), min(old[1], BBOX[1]),
        max(old[2], BBOX[2]), max(old[3], BBOX[3]),
    ]]
    oldt = p["extent"]["temporal"]["interval"][0]
    p["extent"]["temporal"]["interval"] = [[
        min(oldt[0], "2024-01-01T00:00:00Z"),
        max(oldt[1], "2024-12-31T23:59:59Z"),
    ]]

    href = f"{BUCKET}/rcn-national/stac-collection.json"
    links = [l for l in p["links"] if l.get("href") != href]
    for l in links:
        if l.get("rel") == "license":
            l["title"] = ("Child licences: CC0-1.0 (Cameron, Schloss), CC-BY-4.0 (Beier, "
                          "CDFW) and TNC non-commercial terms (Resilient and Connected "
                          "Network)")
    links.append({
        "rel": "child",
        "href": href,
        "type": "application/json",
        "title": "Resilient and Connected Network (TNC 2024, CONUS and adjacent Canada)",
    })
    p["links"] = links
    return p


README_SECTION = """

---

## Raster - rcn-national (TNC Resilient and Connected Network 2024)

The Nature Conservancy's Resilient and Connected Network at 30 m: the sites and corridors
that together would sustain biodiversity under a changing climate, classified into 14
classes. **Footprint is the conterminous US plus adjacent Canada** (the prairie provinces
north to about 52.7 degrees, and New Brunswick, Nova Scotia and Prince Edward Island), so
a US statistic needs a national mask. Alaska and Hawaii are separate source rasters and
are not included.

`rcn_class` values: {values}. **0 and 1 are real classes** (mapped land outside the
network, together about 62% of the footprint) - only **255** is no data.

**Licence: TNC non-commercial.** That restriction carries to anyone using these products.

**COG** (titiler, categorical colormap from the STAC `classification:classes`):
```
https://s3-west.nrp-nautilus.io/public-connectivity/rcn-national-cog.tif
```

**H3 hex** (native resolution 10, mode reducer) - dominant class per cell:
```sql
SELECT rcn_class, COUNT(*) AS cells
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-connectivity/rcn-national/hex/h0=*/data_0.parquet')
WHERE rcn_class <> 255
GROUP BY 1 ORDER BY 2 DESC;
```

**H3 hex, fractional coverage** (one row per cell and class present) - use this, not the
mode layer, for class **areas**; weight each `frac` by its own cell's ground area (see the
h3-guide) rather than counting cells:
```sql
SELECT rcn_class, SUM(frac) AS cell_equivalents
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-connectivity/rcn-national/hex-fractions/h0=*/data_0.parquet')
WHERE rcn_class <> 255
GROUP BY 1 ORDER BY 2 DESC;
```

There is no PMTiles or GeoParquet for this dataset: raster ingests produce a COG and hex
only.
"""


def readme():
    """Append the rcn-national section to the live bucket README, idempotently."""
    url = f"{BUCKET}/README.md"
    with urllib.request.urlopen(url) as r:
        md = r.read().decode()

    marker = "## Raster - rcn-national"
    if marker in md:
        md = md[:md.index("\n\n---\n\n" + marker)]

    md = md.replace(
        "Landscape **connectivity & climate-resilience** datasets for California, from "
        "the California Biodiversity Network (CBN) and partners.",
        "Landscape **connectivity & climate-resilience** datasets. Most cover California, "
        "from the California Biodiversity Network (CBN) and partners; `rcn-national` is "
        "continental, covering the conterminous US and adjacent Canada.")

    row = ("| `rcn-national` | TNC 2024 - Resilient and Connected Network "
           "(Anderson et al. 2023) | COG, H3 hex (res 10, mode + fractions) | "
           "TNC non-commercial |")
    if row not in md:
        lines = md.split("\n")
        last = max(i for i, l in enumerate(lines)
                   if l.startswith("| `") and l.endswith("|"))
        lines.insert(last + 1, row)
        md = "\n".join(lines)

    md = md.replace(
        "All layers are in **OGC:CRS84 / EPSG:4326**. The three raster sources were",
        "All layers are in **OGC:CRS84 / EPSG:4326**. The California raster sources were")

    return md.rstrip("\n") + README_SECTION.format(values=VALUES_TEXT)


def collection():
    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "type": "Collection",
        "id": "rcn-national",
        "title": ("Resilient and Connected Network (TNC 2024, conterminous US and "
                  "adjacent Canada)"),
        "description": DESCRIPTION,
        "license": "other",
        "keywords": ["connectivity", "climate resilience", "biodiversity",
                     "conservation planning", "corridors", "United States", "Canada",
                     "The Nature Conservancy"],
        "providers": [
            {"name": "The Nature Conservancy",
             "roles": ["producer", "licensor"],
             "url": LANDING},
            {"name": "Boettiger Lab",
             "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "sci:doi": "10.1073/pnas.2204434119",
        "sci:citation": (
            "Anderson, M.G., Clark, M., Olivero, A.P., Barnett, A.R., Hall, K.R., "
            "Cornett, M.W., et al. (2023). A resilient and connected network of sites to "
            "sustain biodiversity under a changing climate. Proceedings of the National "
            "Academy of Sciences 120(7). https://doi.org/10.1073/pnas.2204434119. "
            f"Raster Resilient and Connected Network National 2024, accessed {ACCESSED}."
        ),
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [["2024-01-01T00:00:00Z",
                                       "2024-12-31T23:59:59Z"]]},
        },
        "links": [
            {"rel": "self",
             "href": f"{BUCKET}/rcn-national/stac-collection.json",
             "type": "application/json"},
            {"rel": "root",
             "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
             "type": "application/json"},
            {"rel": "parent",
             "href": f"{BUCKET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "describedby",
             "href": f"{BUCKET}/README.md",
             "type": "text/markdown",
             "title": "Bucket documentation and usage examples"},
            {"rel": "about",
             "href": LANDING,
             "type": "text/html",
             "title": "The Nature Conservancy: Resilient and Connected Network"},
            {"rel": "cite-as",
             "href": DOI,
             "title": "Anderson et al. 2023, PNAS 120(7)"},
            {"rel": "license",
             "href": TERMS,
             "type": "text/html",
             "title": ("TNC Geospatial Data Terms of Use (non-commercial, revised "
                       "2023-01-12)")},
        ],
        "assets": {
            "rcn-national-cog": {
                "href": f"{BUCKET}/rcn-national-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": "Cloud-optimized GeoTIFF (EPSG:4326)",
                "description": (
                    "30 metre categorical COG of rcn_class, reprojected from the source "
                    "NAD83 Albers with nearest-neighbour resampling. Class colours for "
                    "the 11 classes TNC styles in its own published layer file are taken "
                    "from that file; classes 0, 1 and 91 are unstyled there and are "
                    "given greys and a mid green here."),
                "roles": ["data"],
                "raster:bands": [{
                    "name": "rcn_class",
                    "data_type": "uint8",
                    "nodata": 255,
                    "classification:classes": [
                        {"value": c,
                         "name": VAT[c][0],
                         "description": (
                             VAT[c][0] + ". "
                             + (f"{VAT[c][1]:,} source pixels, "
                                f"{100 * VAT[c][1] / MAPPED_PX:.2f} percent of the "
                                "mapped area.")),
                         "color_hint": COLORS[c]}
                        for c in CLASSES
                    ],
                }],
            },
            "rcn-national-hex": {
                "href": f"{BUCKET}/rcn-national/hex/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": "H3 hex-indexed parquet (mode, native resolution 10)",
                "description": HEX_DESC,
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 7, 6, 5, 0],
                "table:columns": cols(
                    ("rcn_class", CLASS_TYPE, CLASS_DESC, CLASSES)),
            },
            "rcn-national-hex-fractions": {
                "href": f"{BUCKET}/rcn-national/hex-fractions/h0=*/data_0.parquet",
                "type": "application/vnd.apache.parquet",
                "title": ("H3 hex-indexed parquet (per-class fractional coverage, "
                          "native resolution 10)"),
                "description": FRAC_DESC,
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 7, 6, 5, 0],
                "table:columns": cols(
                    ("rcn_class", CLASS_TYPE, CLASS_DESC, CLASSES + [255]),
                    ("frac", "double",
                     "Exact areal fraction, between 0 and 1, of the H3 cell covered by "
                     "this rcn_class. Per cell the frac values sum to 1, including the "
                     "share covered by no data, which is carried as rcn_class 255.")),
            },
        },
    }


def main():
    out = "/tmp/stac-collection.json"
    with open(out, "w") as f:
        json.dump(collection(), f, indent=2)
        f.write("\n")
    with open("/tmp/parent.json", "w") as f:
        json.dump(parent(), f, indent=2)
        f.write("\n")
    with open("/tmp/bucket-readme.md", "w") as f:
        f.write(readme())
    print(f"wrote {out}, /tmp/parent.json, /tmp/bucket-readme.md")
    print(f"  bbox      {BBOX}")
    print(f"  mapped    {MAPPED_KM2:,.0f} km2")
    print(f"  classes   {len(CLASSES)}: {VALUES_TEXT}")
    unstyled = sorted(set(CLASSES) - TNC_STYLED)
    print(f"  colours   {len(TNC_STYLED)} from the TNC layer file, "
          f"{len(unstyled)} chosen here: {unstyled}")


if __name__ == "__main__":
    main()
