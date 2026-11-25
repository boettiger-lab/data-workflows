"""Write stac-collection.json and README.md for public-coastal/tidal-wetland-change-v1-0-1 (#800).

usage: gen_stac.py <outdir>

Band codes come from the Earth Engine catalog entry JCU/Murray/GIC/global_tidal_wetland_change/2019
and were checked against the files (a San Francisco Bay window, 2026-11-25). Totals were measured
by consolidate.yaml on 2026-11-25. Each asset's `created` is the object's Last-Modified.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
D = f"{B}/tidal-wetland-change-v1-0-1"
PX = 0.00026949458523585647
PAPER = "https://doi.org/10.1126/science.abm9583"
ABOUT = "https://www.globalintertidalchange.org/data-usage"


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


L = listing("tidal-wetland-change-v1-0-1/")


def created(prefix):
    v = [t for k, t in L.items() if k.startswith(prefix)]
    assert v, f"nothing published under {prefix}"
    return max(v)[:19] + "Z"


STEPS = {4: "2002-2004", 7: "2005-2007", 10: "2008-2010", 13: "2011-2013", 16: "2014-2016", 19: "2017-2019"}
STEP_COLORS = {4: "FFFFB2", 7: "FED976", 10: "FEB24C", 13: "FD8D3C", 16: "F03B20", 19: "BD0026"}
TYPES = {2: ("tidal-flat", "Tidal flat", "D8B365"), 3: ("mangrove", "Mangrove", "1B7837"),
         5: ("tidal-marsh", "Tidal marsh", "5AB4AC")}
CH = {"loss": ("Loss", "D7301F"), "gain": ("Gain", "2B8CBE")}

assets, renders = {}, {}
for c, (title, color) in CH.items():
    key = f"{c}-cog"
    assets[key] = {
        "href": f"{D}/{c}-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "roles": ["data"], "created": created(f"tidal-wetland-change-v1-0-1/{c}-cog.tif"),
        "title": f"Tidal wetland {c}, 1999–2019 (cloud-optimized GeoTIFF, 30 m)",
        "description": f"1 where tidal wetland {c} was detected between 1999–2001 and 2017–2019, no data elsewhere.",
        "raster:bands": [{"name": c, "data_type": "uint8", "nodata": 0, "spatial_resolution": PX,
                          "classification:classes": [{"value": 1, "name": c, "title": title,
                                                      "description": f"Tidal wetland {c}.", "color_hint": color}]}]}
    renders[c] = {"title": f"Tidal wetland {c} 1999–2019", "assets": [key], "resampling": "nearest",
                  "colormap": {"1": f"#{color}"}, "nodata": 0}

    key = f"{c}-year-cog"
    assets[key] = {
        "href": f"{D}/{c}-year-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "roles": ["data"], "created": created(f"tidal-wetland-change-v1-0-1/{c}-year-cog.tif"),
        "title": f"Time step of tidal wetland {c} (cloud-optimized GeoTIFF, 30 m)",
        "description": (f"The three-year time step in which the {c} was detected, coded by its end year "
                        f"(4 = 2002–2004 … 19 = 2017–2019); no data where there was no {c}, or no step was "
                        f"assigned."),
        "raster:bands": [{"name": f"{c}_year", "data_type": "uint8", "nodata": 0, "spatial_resolution": PX,
                          "classification:classes": [{"value": v, "name": f"y{v}", "title": STEPS[v],
                                                      "description": f"{c.capitalize()} detected in {STEPS[v]}.",
                                                      "color_hint": STEP_COLORS[v]} for v in STEPS]}]}
    renders[f"{c}-year"] = {"title": f"Time step of tidal wetland {c}", "assets": [key], "resampling": "nearest",
                            "colormap": {str(v): f"#{STEP_COLORS[v]}" for v in STEPS}, "nodata": 0}

    key = f"{c}-type-cog"
    assets[key] = {
        "href": f"{D}/{c}-type-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "roles": ["data"], "created": created(f"tidal-wetland-change-v1-0-1/{c}-type-cog.tif"),
        "title": f"Ecosystem type of tidal wetland {c} (cloud-optimized GeoTIFF, 30 m)",
        "description": f"Which tidal ecosystem the {c} affected; no data where there was no {c}, or no type was assigned.",
        "raster:bands": [{"name": f"{c}_type", "data_type": "uint8", "nodata": 0, "spatial_resolution": PX,
                          "classification:classes": [{"value": v, "name": n, "title": t,
                                                      "description": f"{c.capitalize()} of {t.lower()}.",
                                                      "color_hint": col} for v, (n, t, col) in TYPES.items()]}]}
    renders[f"{c}-type"] = {"title": f"Ecosystem type of tidal wetland {c}", "assets": [key],
                            "resampling": "nearest", "colormap": {str(v): f"#{col}" for v, (_, _, col) in TYPES.items()},
                            "nodata": 0}

for w, label in (("start", "1999–2001"), ("end", "2017–2019")):
    key = f"tw-probability-{w}-cog"
    assets[key] = {
        "href": f"{D}/tw-probability-{w}-cog.tif", "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "roles": ["data"], "created": created(f"tidal-wetland-change-v1-0-1/tw-probability-{w}-cog.tif"),
        "title": f"Tidal wetland probability {label} (cloud-optimized GeoTIFF, 30 m)",
        "description": (f"Agreement of the random-forest classifier that the pixel was tidal wetland (tidal flat, "
                        f"mangrove or tidal marsh) in {label}, 0 to 100. 0 is a value (not tidal wetland); 255 "
                        f"marks areas outside the mapped tiles."),
        "raster:bands": [{"name": f"tw_probability_{w}", "data_type": "uint8", "nodata": 255,
                          "spatial_resolution": PX, "unit": "percent"}]}
    renders[f"tw-probability-{w}"] = {"title": f"Tidal wetland probability {label}", "assets": [key],
                                      "colormap_name": "viridis", "rescale": [[0, 100]], "nodata": 255}

COLS = [
    {"name": "change", "type": "string", "description": "Kind of change. Values: loss=tidal wetland lost, gain=tidal wetland gained",
     "values": ["gain", "loss"]},
    {"name": "ecosystem", "type": "string",
     "description": ("Tidal ecosystem affected by the change. Values: tidal flat=Tidal flat, mangrove=Mangrove, "
                     "tidal marsh=Tidal marsh, unassigned=change pixels the source gives no ecosystem type"),
     "values": ["mangrove", "tidal flat", "tidal marsh", "unassigned"]},
    {"name": "period", "type": "string",
     "description": ("Three-year time step in which the change was detected. Values: "
                     + ", ".join(f"{s}={s}" for s in STEPS.values())
                     + ", unassigned=change pixels the source gives no time step"),
     "values": list(STEPS.values()) + ["unassigned"]},
    {"name": "area_km2", "type": "double",
     "description": "Area of this change, ecosystem and time step in the H3 cell, in km²: the share of the cell the 30 m change pixels cover, times the cell's area."},
    {"name": "h10", "type": "uint64", "description": "H3 cell id at resolution 10 (native resolution)."},
    {"name": "h8", "type": "uint64", "description": "H3 cell id at resolution 8."},
    {"name": "h0", "type": "uint64", "description": "H3 cell id at resolution 0, used as the partition key for hive-partitioned reads."},
]
assets["tidal-wetland-change-hex"] = {
    "href": f"{D}/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
    "created": created("tidal-wetland-change-v1-0-1/hex/"),
    "title": "Tidal wetland loss and gain per H3 cell, by ecosystem and time step (resolution 10)",
    "description": (
        "Tidal wetland loss and gain for every H3 resolution 10 cell (about 0.015 km²) where any change was mapped, "
        "one row per cell, change, ecosystem and time step, with the resolution 8 and 0 parents. Cells with no change "
        "have no row, so treat a missing row as zero. Built with the fractions reducer from 30 m pixels: every row is "
        "a distinct share of its cell, never repeated, so the sum is the total within any filter:\n\n```sql\n-- net tidal marsh change per resolution 8 cell, 1999-2019\n"
        f"SELECT h8, SUM(CASE change WHEN 'gain' THEN area_km2 ELSE -area_km2 END) AS net_km2\n"
        f"FROM read_parquet('{D}/hex/h0=*/data_0.parquet')\nWHERE ecosystem = 'tidal marsh' GROUP BY h8\n```"),
    "h3:native_resolution": 10, "h3:parent_resolutions": [8, 0]}

DESC = f"""Where the world's tidal wetlands (tidal flats, mangroves and tidal marshes) were lost and gained between 1999 and 2019, mapped at 30 m from over a million Landsat images (Murray et al. 2022). Each change is assigned the ecosystem it affected and the three-year time step in which it was detected.

Over the 20 years the maps show 13,850 km² of loss and 9,782 km² of gain, a net loss of about 4,070 km²; the paper reports about 13,700 km² lost and 9,700 km² gained. By ecosystem, loss was 6,963 km² of tidal flat, 5,547 km² of mangrove and 1,059 km² of tidal marsh; gain was 6,699, 1,833 and 1,162 km². 282 km² of loss and 88 km² of gain carry no ecosystem type or time step in the source and are kept as "unassigned", so the totals match the change maps.

Eight 30 m cloud-optimized GeoTIFFs reproduce the source bands as published: loss and gain, their time step and their ecosystem type, and the classifier's probability of tidal wetland at the start (1999–2001) and end (2017–2019). The H3 table gives change area per resolution 10 cell by change, ecosystem and time step, with resolution 8 parents for joining to other catalog layers:

```sql
SELECT ecosystem, change, ROUND(SUM(area_km2)) AS km2
FROM read_parquet('{D}/hex/h0=*/data_0.parquet') GROUP BY ALL ORDER BY ALL
```

The extent of these ecosystems is in the catalog's tidal flat and tidal marsh collections and in Global Mangrove Watch.

Source: Murray, N. J., et al. (2022), High-resolution mapping of losses and gains of Earth's tidal wetlands, Science 376, 744–749, {PAPER}. Data: Global Tidal Wetland Change v1.0, release v1.0.1, gs://gic-archive/gic-2019-v1-0/v1-0-1/ (8 bands × 147 tiles, 39.8 GB, files dated 2022-03 to 2022-08), CC BY 4.0 ({ABOUT}; Earth Engine JCU/Murray/GIC/global_tidal_wetland_change/2019), accessed 2026-11-25. Every tile was checked against the MD5 Google Cloud Storage publishes; sizes, MD5s and SHA-256s were recorded at staging."""

now = max(a["created"] for a in assets.values())
col = {
    "stac_version": "1.1.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
                        "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                        "https://stac-extensions.github.io/version/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/render/v2.0.0/schema.json",
                        "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"],
    "type": "Collection", "id": "tidal-wetland-change-v1-0-1",
    "title": "Global tidal wetland change 1999–2019 (Murray et al. 2022, v1.0.1)",
    "description": DESC, "license": "CC-BY-4.0", "version": "1.0.1",
    "keywords": ["tidal wetlands", "tidal flats", "mangroves", "tidal marshes", "wetland loss", "Landsat", "change detection", "global"],
    "sci:doi": "10.1126/science.abm9583",
    "sci:citation": ("Murray, N. J., Worthington, T. A., Bunting, P., Duce, S., Hagger, V., Lovelock, C. E., Lucas, R., "
                     "Saunders, M. I., Sheaves, M., Spalding, M., Waltham, N. J., & Lyons, M. B. (2022). High-resolution "
                     "mapping of losses and gains of Earth's tidal wetlands. Science, 376(6594), 744–749. Data: Global "
                     "Tidal Wetland Change v1.0.1, gs://gic-archive/gic-2019-v1-0/v1-0-1/, accessed 2026-11-25."),
    "providers": [{"name": "Murray et al. (2022), Global Intertidal Change", "roles": ["producer", "licensor"], "url": ABOUT},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180.0, -60.0, 180.0, 60.0]]},
               "temporal": {"interval": [["1999-01-01T00:00:00Z", "2019-12-31T23:59:59Z"]]}},
    "created": now, "updated": now,
    "table:columns": COLS,
    "renders": renders,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC BY 4.0"},
        {"rel": "about", "href": ABOUT, "type": "text/html", "title": "Global Intertidal Change: data usage"},
        {"rel": "via", "href": ABOUT, "type": "text/html", "title": "Global Intertidal Change: data usage"},
        {"rel": "cite-as", "href": PAPER, "type": "text/html"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
    ],
    "assets": assets,
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

README = f"""# Global tidal wetland change 1999–2019 (Murray et al. 2022, v1.0.1)

{DESC}

## Files

| File | Contents |
|---|---|
""" + "".join(f"| `{a['href']}` | {a['title']} |\n" for a in assets.values()) + f"""
## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
-- tidal marsh loss and gain per resolution 8 cell
SELECT h8, change, SUM(area_km2) AS km2
FROM read_parquet('{D}/hex/h0=*/data_0.parquet')
WHERE ecosystem = 'tidal marsh' GROUP BY h8, change;
```

## Map (TiTiler)

```
https://titiler.nrp-nautilus.io/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={D}/loss-cog.tif&colormap={{"1":"#D7301F"}}&resampling=nearest
```

## Columns

| Column | Description |
|---|---|
""" + "\n".join(f"| `{c['name']}` | {c['description']} |" for c in COLS) + "\n"
open(f"{OUT}/README.md", "w").write(README)
print("wrote", len(assets), "assets,", len(COLS), "columns,", len(renders), "renders")
