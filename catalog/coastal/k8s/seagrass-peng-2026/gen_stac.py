"""Write stac-collection.json and README.md for public-coastal/seagrass-peng-2026 (#788).

usage: gen_stac.py <outdir>

Totals and counts were measured by consolidate.yaml on 2026-11-25; the staged files' sizes, MD5s
and SHA-256s come from raw/seagrass-peng-2026/MANIFEST.tsv written by stage-raw.yaml (2026-11-24).
Each asset's `created` is the object's Last-Modified, read from the bucket listing.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
D = f"{B}/seagrass-peng-2026"
PX = 8.983152841195215e-05
ZENODO = "https://doi.org/10.5281/zenodo.18612239"
PAPER = "https://doi.org/10.1038/s41586-026-10704-3"
PERIODS = {"2019-2020": dict(cells="19,128,811", km2="148,938"),
           "2023-2024": dict(cells="19,184,126", km2="142,915")}


def listing(prefix):
    out, token = {}, ""
    while True:
        url = f"{B}/?list-type=2&prefix={prefix}" + (f"&continuation-token={urllib.parse.quote(token)}" if token else "")
        x = urllib.request.urlopen(url).read().decode()
        out.update(dict(re.findall(r"<Key>([^<]+)</Key><LastModified>([^<]+)</LastModified>", x)))
        m = re.search(r"<NextContinuationToken>([^<]+)<", x)
        if not m:
            return out
        token = m.group(1)


L = listing("seagrass-peng-2026/")


def created(prefix):
    v = [t for k, t in L.items() if k.startswith(prefix)]
    assert v, f"nothing published under {prefix}"
    return max(v)[:19] + "Z"


COLOR = "#1B7837"
COLS = [
    {"name": "period", "type": "string",
     "description": "Period the seagrass map covers. Values: 2019-2020=Sentinel-2 imagery of 2019 and 2020, "
                    "2023-2024=Sentinel-2 imagery of 2023 and 2024",
     "values": ["2019-2020", "2023-2024"]},
    {"name": "seagrass_km2", "type": "double",
     "description": "Area of mapped seagrass in the H3 cell, in km²: the true area of the 10 m seagrass pixels "
                    "falling in the cell, weighted by how much of each pixel the cell covers."},
    {"name": "h10", "type": "uint64", "description": "H3 cell id at resolution 10 (native resolution)."},
    {"name": "h8", "type": "uint64", "description": "H3 cell id at resolution 8."},
    {"name": "h0", "type": "uint64", "description": "H3 cell id at resolution 0, used as the partition key for hive-partitioned reads."},
]

assets, renders = {}, {}
for p, m in PERIODS.items():
    key = f"seagrass-{p}-cog"
    assets[key] = {
        "href": f"{D}/seagrass-{p}-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "roles": ["data"], "created": created(f"seagrass-peng-2026/seagrass-{p}-cog.tif"),
        "title": f"Seagrass extent {p} (cloud-optimized GeoTIFF, 10 m)",
        "description": (f"Global seagrass map for {p} at about 10 m, as published: 1 where seagrass was mapped, "
                        f"no data elsewhere. The producers' 10 m tiles mosaicked into one file, values unchanged."),
        "raster:bands": [{"name": "seagrass", "data_type": "uint8", "nodata": 0, "spatial_resolution": PX,
                          "classification:classes": [{"value": 1, "name": "seagrass", "title": "Seagrass",
                                                      "description": "Seagrass mapped from Sentinel-2 imagery.",
                                                      "color_hint": COLOR[1:]}]}]}
    renders[f"seagrass-{p}"] = {"title": f"Seagrass extent {p} (10 m)", "assets": [key],
                                "resampling": "nearest", "colormap": {"1": COLOR}, "nodata": 0}

assets["seagrass-hex"] = {
    "href": f"{D}/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
    "created": created("seagrass-peng-2026/hex/"),
    "title": "Seagrass area per H3 cell, both periods (resolution 10)",
    "description": (
        "Seagrass area for every H3 resolution 10 cell (about 0.015 km²) that holds any mapped seagrass, one row "
        "per period and cell, with the resolution 8 and 0 parents. Cells with no mapped seagrass have no row, so "
        "treat a missing row as zero. The two periods are stacked in one table, so pick one before summing:\n\n"
        "```sql\n"
        "-- seagrass area per resolution 8 cell in 2023-2024\n"
        f"SELECT h8, SUM(seagrass_km2) AS km2\nFROM read_parquet('{D}/hex/h0=*/data_0.parquet')\n"
        "WHERE period = '2023-2024' GROUP BY h8\n"
        "```\n\nThe area integrates each pixel's true size, so the global sum matches the map: "
        + "; ".join(f"{p}: {m['km2']} km² in {m['cells']} cells" for p, m in PERIODS.items()) + "."),
    "h3:native_resolution": 10, "h3:parent_resolutions": [8, 0],
    "table:columns": [{"name": c["name"], "type": c["type"]} for c in COLS]}

DESC = f"""Seagrass meadows mapped worldwide from Sentinel-2 satellite imagery at about 10 m, for two periods, 2019–2020 and 2023–2024 (Peng et al. 2026). The map covers clear, shallow coastal water, where seagrass can be seen from space, and gives 148,938 km² of seagrass in 2019–2020 and 142,915 km² in 2023–2024, a net loss of 4.0%. The paper reports 148,506 km² for its maps, mostly subtidal (142,545 km²) with 5,961 km² intertidal, and that 4% of the seagrass was lost between the two periods.

How it differs from the UNEP-WCMC global seagrass compilation (version 7.1): that layer gathers mapped meadows from hundreds of surveys of different dates and methods, so it is patchy, and covering whole survey polygons overstates small beds. This map applies one method everywhere at one resolution, so it is consistent from place to place and can be compared between periods. It cannot see meadows in turbid water or below the depth that light reaches, so those are missing, and its total is lower than compiled estimates of 160,000 to 600,000 km². Where this map shows no seagrass, none was detected; that is not proof that none grows there.

Each period is a global 10 m cloud-optimized GeoTIFF (1 = seagrass). The H3 table gives seagrass area per resolution 10 cell for both periods, with resolution 8 parents for joining to other catalog layers:

```sql
SELECT period, ROUND(SUM(seagrass_km2)) AS km2
FROM read_parquet('{D}/hex/h0=*/data_0.parquet') GROUP BY period
```

Source: Peng, J., et al. (2026), Global high-resolution mapping of seagrass to support conservation, Nature 655, 663–669, {PAPER}. Data: "Global 10-meter seagrass maps", Zenodo record 18612240 ({ZENODO}, published 2026-02-14, no version label), CC BY 4.0, accessed 2026-11-24. Staged files: GlobalSeagrass2019_2020.zip (438,032,562 bytes, MD5 2046bf6c62d85f4d57e678bf6ef1cd07, SHA-256 f0fe80e60f78c4bc2f1e5c0cef07511f7dc39e76edc9ad2d55900cfd7f08c232, 299 tiles) and GlobalSeagrass2023_2024.zip (448,760,997 bytes, MD5 d371628f0e343244eb47f188f0a89726, SHA-256 7f5b62c9343b43aa611acc74bf17da031655a42b0da7a1abc9e18a6b746c010e, 301 tiles)."""

now = max(a["created"] for a in assets.values())
col = {
    "stac_version": "1.1.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
                        "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                        "https://stac-extensions.github.io/render/v2.0.0/schema.json",
                        "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"],
    "type": "Collection", "id": "seagrass-peng-2026",
    "title": "Global seagrass extent from Sentinel-2, 2019–2020 and 2023–2024 (10 m)",
    "description": DESC, "license": "CC-BY-4.0",
    "keywords": ["seagrass", "coastal ecosystems", "blue carbon", "Sentinel-2", "habitat change", "global"],
    "sci:doi": "10.1038/s41586-026-10704-3",
    "sci:citation": ("Peng, J., Li, J., Krause, J. R., Lyons, M. B., Murray, N. J., Schill, S. R., Roelfsema, C. M., "
                     "& Asner, G. P. (2026). Global high-resolution mapping of seagrass to support conservation. "
                     "Nature, 655(8123), 663–669. Data: Global 10-meter seagrass maps, Zenodo, "
                     "https://doi.org/10.5281/zenodo.18612239, accessed 2026-11-24."),
    "providers": [{"name": "Peng et al. (2026)",
                   "roles": ["producer", "licensor"], "url": ZENODO},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180.0, -51.29, 180.0, 72.34]]},
               "temporal": {"interval": [["2019-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]}},
    "created": now, "updated": now,
    "table:columns": COLS,
    "renders": renders,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC BY 4.0"},
        {"rel": "about", "href": ZENODO, "type": "text/html", "title": "Global 10-meter seagrass maps on Zenodo"},
        {"rel": "via", "href": ZENODO, "type": "text/html", "title": "Global 10-meter seagrass maps on Zenodo"},
        {"rel": "cite-as", "href": PAPER, "type": "text/html"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
    ],
    "assets": assets,
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

README = f"""# Global seagrass extent from Sentinel-2, 2019–2020 and 2023–2024 (10 m)

{DESC}

## Files

| File | Contents |
|---|---|
| `{D}/seagrass-2019-2020-cog.tif` | Seagrass 2019–2020, 10 m COG (1 = seagrass, 0 = no data) |
| `{D}/seagrass-2023-2024-cog.tif` | Seagrass 2023–2024, 10 m COG |
| `{D}/hex/h0=*/data_0.parquet` | Seagrass area per H3 resolution 10 cell, both periods |

## DuckDB

```sql
INSTALL httpfs; LOAD httpfs; INSTALL h3 FROM community; LOAD h3;
-- seagrass area per resolution 8 cell in each period
SELECT period, h8, SUM(seagrass_km2) AS km2
FROM read_parquet('{D}/hex/h0=*/data_0.parquet')
GROUP BY period, h8;
```

## Map (TiTiler)

```
https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={D}/seagrass-2023-2024-cog.tif&colormap={{"1":"{COLOR}"}}&resampling=nearest
```

## Columns

| Column | Description |
|---|---|
""" + "\n".join(f"| `{c['name']}` | {c['description']} |" for c in COLS) + "\n"
open(f"{OUT}/README.md", "w").write(README)
print("wrote", len(assets), "assets,", len(COLS), "columns")
