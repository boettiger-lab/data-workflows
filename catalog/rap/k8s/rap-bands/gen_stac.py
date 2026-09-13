#!/usr/bin/env python3
"""Generate the four public-rap STAC collections (#666, #667, #607).

Asset timestamps, sizes and bboxes are MEASURED from the live objects, never hardcoded.
Run only after the COG and hex jobs have landed.
"""
import json, subprocess, email.utils, datetime, pathlib, urllib.request

OUT = pathlib.Path(__file__).parent / "stac"
OUT.mkdir(exist_ok=True)
BASE = "https://s3-west.nrp-nautilus.io/public-rap"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------- measurement helpers

def head(url):
    try:
        r = subprocess.run(["curl", "-sI", "--max-time", "60", url],
                           capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None, None
    created = size = None
    for line in r.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "last-modified":
            created = email.utils.parsedate_to_datetime(v).astimezone(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif k == "content-length":
            size = int(v)
    return created, size

def cog_info(url):
    """Measured band count and WGS84 bounds from the published COG."""
    q = urllib.parse.quote(url, safe="")
    with urllib.request.urlopen(
            f"https://titiler.nrp-nautilus.io/cog/info?url={q}", timeout=180) as r:
        d = json.load(r)
    return d["count"], [round(x, 4) for x in d["bounds"]]

# ---------------------------------------------------------------- per-product constants

RAP_LANDING = "https://rangeland.ntsg.umt.edu/data/rap/rap-vegetation-cover/v3/"
RAP_CITATION = (
    "Allred, B.W., B.T. Bestelmeyer, C.S. Boyd, C. Brown, K.W. Davies, M.C. Duniway, "
    "L.M. Ellsworth, T.A. Erickson, S.D. Fuhlendorf, T.V. Griffiths, V. Jansen, M.O. Jones, "
    "J. Karl, A. Knight, J.D. Maestas, J.J. Maynard, S.E. McCord, D.E. Naugle, H.D. Starns, "
    "D. Twidwell, and D.R. Uden. 2021. Improving Landsat predictions of rangeland fractional "
    "cover with multitask learning and uncertainty. Methods in Ecology and Evolution. "
    "https://doi.org/10.1111/2041-210X.13564. RAP Vegetation Cover v3.0, 2025 edition "
    "(released 2026-02-24); accessed 2026-06-13.")
RAP_PROV = (
    "Provenance: retrieved from " + RAP_LANDING + " on 2026-06-13. Upstream republishes each "
    "annual edition in place at a stable URL with no dated archive, so the staged copy is the "
    "citable artifact: s3://public-rap/raw/vegetation-cover-v3-2025.tif, 37,594,614,065 bytes, "
    "SHA-256 012e29a570865ecf6845578a50fe7e3ea0fe68621bb4b150cb00308f20ea0e84. The 2025 edition "
    "was released upstream on 2026-02-24.")
RAP_SUIT = (
    "The producers note that these estimates are produced across a broad region but are primarily "
    "intended for rangeland ecosystems, and may be less reliable in other ecosystems such as "
    "forests and agricultural land. This matters most in the eastern United States, where cover "
    "values are generally low and less well constrained.")

S2_LANDING = "https://rangeland.ntsg.umt.edu/data/rangeland-s2/"
S2_CITATION = (
    "Allred, B.W., S.E. McCord, T.J. Assal, B.T. Bestelmeyer, C.S. Boyd, A.C. Brooks, S.M. Cady, "
    "M.C. Duniway, S.D. Fuhlendorf, S.A. Green, G.R. Harrison, E.R. Jensen, E.J. Kachergis, "
    "A. Knight, C.M. Mattilio, B.A. Mealor, D.E. Naugle, D. O'Leary, P.J. Olsoy, E.S. Peirce, "
    "J.R. Reinhardt, R.K. Shriver, J.T. Smith, J.D. Tack, A.M. Tanner, E.P. Tanner, D. Twidwell, "
    "N.P. Webb, and S.L. Morford. 2025. Sentinel-2 based estimates of rangeland fractional cover "
    "and canopy gap class for the western United States. Scientific Data 12:1889. "
    "https://doi.org/10.1038/s41597-025-06160-9. Accessed 2026-09-13.")
S2_EXTENT_NOTE = (
    "Coverage is the western United States. Upstream publishes this product only for UTM zones 10 "
    "through 13, so the data stop at about 101 degrees west; there is no data further east. That "
    "is the product's extent rather than a gap in this copy — the same publisher does carry the "
    "eastern zones for its companion plant-functional-type product, and deliberately does not "
    "here.")
TILESET = {
    "arte": dict(n=764, bytes=11_545_139_799,
                 digest="0028a1f0fece3a604509afa31e0d3e7b854ff4905c7f6e2fc68a684ed14911ce"),
    "iag":  dict(n=764, bytes=12_787_749_406,
                 digest="7298448be84cb2b2137af1db7bd32f4f377f277b3dcd15e9fc6171d133fee949"),
}

def s2_prov(var):
    t = TILESET[var]
    return (f"Provenance: retrieved from {S2_LANDING}{var}/ on 2026-09-13, staged at "
            f"s3://public-rap/raw/{var}/ as {t['n']} GeoTIFF tiles totalling {t['bytes']:,} bytes "
            f"(117 in UTM zone 10, 201 in zone 11, 217 in zone 12, 229 in zone 13). Upstream "
            f"republishes in place with no dated archive, so the staged tile set is the citable "
            f"artifact; its manifest digest, the SHA-256 over the sorted list of tile names, "
            f"ETags and sizes, is {t['digest']}. Tiles are 75 by 75 km with a 250 m overlap on "
            f"each side, and pixels outside a tile's reference UTM zone are masked upstream.")

# ---------------------------------------------------------------- collection builder

def build(ds, var, title, blurb, caveat, extent_note, licence, licence_url, licence_title,
          citation, doi, provenance, pixel_note, keywords, version=None):
    cog_href = f"{BASE}/{ds}-cog.tif"
    hex_href = f"{BASE}/{ds}/hex/h0=*/data_0.parquet"

    nbands, bbox = cog_info(cog_href)
    if nbands != 1:
        raise SystemExit(f"{ds}: COG reports {nbands} bands; expected 1. Do not publish.")
    cog_created, cog_size = head(cog_href)

    desc = "\n\n".join(x for x in [
        blurb, extent_note, caveat, pixel_note,
        ("The hex layer is an area-weighted aggregation to H3 resolution 10 using the mean "
         "reducer: each cell holds the mean percent cover of the source pixels falling inside "
         "it, and there is one row per cell."),
        provenance,
    ] if x)

    col_desc = (f"Area-weighted mean percent cover of {var['long']} in the cell, from 0 to 100. "
                "Continuous value — averaging across cells is meaningful. For an area total, "
                "weight each cell by its H3 cell area rather than counting cells, because H3 "
                "cells are not equal-area.")

    hex_desc = (
        "One row per H3 cell at resolution 10, holding the area-weighted mean of the source "
        "pixels in that cell. Because the reducer is a mean rather than a sum, the value is "
        "already an intensity: combine cells by averaging, weighted by cell area, rather than "
        "adding them.\n\n"
        "```sql\n"
        "-- mean cover over a region, weighted by cell area\n"
        f"SELECT SUM({var['col']} * h3_cell_area(h10, 'km^2')) / SUM(h3_cell_area(h10, 'km^2'))\n"
        f"FROM read_parquet('{hex_href}')\n"
        "WHERE h0 = 577199624117288959;\n"
        "```\n\n"
        "Cells covering only no-data pixels are absent rather than present with a fill value, so "
        "there are no sentinel values to filter. Partitioned by h0 for hive-partitioned reads; h8 "
        "is the resolution shared with the rest of the catalog for joins.")

    cog_asset = {
        "href": cog_href,
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "title": f"{title} — cloud-optimized GeoTIFF",
        "roles": ["data"],
        "description": ("Single-band cloud-optimized GeoTIFF in EPSG:4326. Values are uint8 "
                        "percent cover from 0 to 100, with 255 as no data."),
        "raster:bands": [{"name": var["col"], "data_type": "uint8", "nodata": 255,
                          "unit": "percent"}],
    }
    if cog_created: cog_asset["created"] = cog_created
    if cog_size:    cog_asset["file:size"] = cog_size

    hex_created, _ = head(f"{BASE}/{ds}/hex/h0=577199624117288959/data_0.parquet")
    hex_asset = {
        "href": hex_href,
        "type": "application/x-parquet",
        "title": f"{title} — H3 hex, resolution 10",
        "roles": ["data"],
        "description": hex_desc,
        "h3:native_resolution": 10,
        "h3:parent_resolutions": [9, 8, 0],
        "table:columns": [
            {"name": var["col"], "type": "double", "description": col_desc},
            {"name": "h10", "type": "uint64",
             "description": "H3 cell ID at resolution 10, the native resolution of this layer."},
            {"name": "h9", "type": "uint64", "description": "H3 cell ID at resolution 9."},
            {"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
            {"name": "h0", "type": "int64",
             "description": "H3 cell ID at resolution 0, used as the partition key for "
                            "hive-partitioned reads."},
        ],
    }
    if hex_created: hex_asset["created"] = hex_created

    col = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": ds,
        "title": title,
        "description": desc,
        "license": licence,
        "keywords": keywords,
        "providers": [
            {"name": "NTSG, University of Montana", "roles": ["producer", "licensor"],
             "url": "https://rangeland.ntsg.umt.edu/"},
            {"name": "Boettiger Lab", "roles": ["processor", "host"],
             "url": "https://s3-west.nrp-nautilus.io"},
        ],
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [["2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
        },
        "sci:doi": doi,
        "sci:citation": citation,
        "created": cog_created or NOW,
        "updated": NOW,
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{ds}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": licence_url, "type": "text/html", "title": licence_title},
            {"rel": "about", "href": RAP_LANDING if ds.endswith("-cover") else S2_LANDING,
             "type": "text/html", "title": "Product documentation"},
            {"rel": "cite-as", "href": f"https://doi.org/{doi}", "type": "text/html"},
        ],
        "assets": {f"{ds}-cog": cog_asset, f"{ds}-hex": hex_asset},
    }
    if version:
        col["version"] = version
        col["stac_extensions"].append(
            "https://stac-extensions.github.io/version/v1.2.0/schema.json")
    print(f"{ds}: bands={nbands} bbox={bbox} cog={cog_size:,}B" if cog_size else ds)
    return col


def rap(ds, band, col, long, title_name, blurb_extra, sibling):
    return build(
        ds=ds, var={"col": col, "long": long},
        title=f"RAP {title_name} Cover 2025 (CONUS)",
        blurb=(f"Percent cover of {long} across the conterminous United States in 2025, "
               f"aggregated to H3 hexagonal cells. {blurb_extra}\n\nSource: Rangeland Analysis "
               f"Platform (RAP) Vegetation Cover version 3.0 from NTSG at the University of "
               f"Montana, band {band} of six. Values are percent cover from 0 to 100; 255 marks "
               f"no data."),
        caveat=RAP_SUIT,
        extent_note=(f"The companion collection {sibling} holds the other herbaceous functional "
                     f"group from the same source product, so the two can be compared cell by "
                     f"cell at any shared resolution."),
        licence="CC0-1.0",
        licence_url="https://creativecommons.org/publicdomain/zero/1.0/",
        licence_title="Creative Commons CC0 1.0 Universal",
        citation=RAP_CITATION, doi="10.1111/2041-210X.13564", provenance=RAP_PROV,
        pixel_note=("Source pixels are approximately 30 m, so each H3 resolution 10 cell "
                    "averages roughly 17 of them."),
        keywords=["rangeland", "vegetation cover", "RAP", "NTSG", "H3", long],
        version="3.0")


def s2(ds, col, long, title_name, species, caveat_extra, accuracy):
    return build(
        ds=ds, var={"col": col, "long": long},
        title=f"RAP {title_name} Cover 2025 — rangeland-s2",
        blurb=(f"Percent cover of {long} in the western United States in 2025, aggregated to H3 "
               f"hexagonal cells. {species}\n\nSource: the NTSG rangeland-s2 Sentinel-2 product "
               f"from the University of Montana, 10 m tiles mosaicked and reprojected to WGS84. "
               f"Values are percent cover from 0 to 100; 255 marks no data."),
        caveat=f"{caveat_extra} {accuracy}",
        extent_note=S2_EXTENT_NOTE,
        licence="CC-BY-4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        licence_title="Creative Commons Attribution 4.0 International",
        citation=S2_CITATION, doi="10.1038/s41597-025-06160-9", provenance=s2_prov(col),
        pixel_note=("Source pixels are 10 m, so each H3 resolution 10 cell averages roughly 150 "
                    "of them."),
        keywords=["rangeland", "vegetation cover", "rangeland-s2", "Sentinel-2", "NTSG", "H3", long])


COLLECTIONS = [
    rap("rap-afg-cover", 1, "afg", "annual forb and grass", "Annual Forb & Grass",
        "Annual forbs and grasses include invasive annual grasses such as cheatgrass, so this "
        "layer is commonly read as an indicator of annual grass invasion in rangelands.",
        "rap-pfg-cover"),
    rap("rap-pfg-cover", 4, "pfg", "perennial forb and grass", "Perennial Forb & Grass",
        "Perennial forbs and grasses are the native perennial herbaceous cover that annual grass "
        "invasion tends to displace.",
        "rap-afg-cover"),
    s2("rap-arte", "arte", "sagebrush", "Sagebrush (Artemisia)",
       "The modelled taxa are Artemisia arbuscula, A. cana, A. nova, A. tridentata and "
       "A. tripartita.",
       "The producers note that sagebrush estimates are reliable only within the known sagebrush "
       "biome, and that interpretations outside that range should be made with caution.",
       "Against a held-out test set the producers report a mean absolute error of 3.2 percent and "
       "an r-squared of 0.64."),
    s2("rap-iag", "iag", "invasive annual grass", "Invasive Annual Grass",
       "The modelled taxa are Bromus tectorum, B. arvensis, B. rubens, B. hordeaceus, "
       "Eremopyrum triticeum, Schismus species, Taeniatherum caput-medusae and Ventenata dubia.",
       "The producers note that native annual forbs and grasses can be misidentified as invasive "
       "annual grass, and recommend corroborating predictions against local expertise.",
       "Against a held-out test set the producers report a mean absolute error of 3.4 percent and "
       "an r-squared of 0.60."),
]

for c in COLLECTIONS:
    p = OUT / f"{c['id']}-stac-collection.json"
    p.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {p.name}")

# ---------------------------------------------------------------- parent bucket collection

def parent(cols):
    """Bucket-level meta-collection.

    license "various" is correct and deliberate here: the two products genuinely differ
    (RAP Vegetation Cover v3 is CC0-1.0, rangeland-s2 is CC-BY-4.0). Per the stac-authoring
    rules a meta-collection with child links may use "various" WITHOUT a license link --
    the real licences live on the children, which is what redistribution gating keys on.
    A single parent-level link would misrepresent one of the two.
    """
    bboxes = [c["extent"]["spatial"]["bbox"][0] for c in cols]
    union = [min(b[0] for b in bboxes), min(b[1] for b in bboxes),
             max(b[2] for b in bboxes), max(b[3] for b in bboxes)]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "public-rap",
        "title": "Rangeland vegetation cover (RAP / rangeland-s2)",
        "description": (
            "Rangeland vegetation-cover products from NTSG at the University of Montana, "
            "aggregated to H3 hexagonal cells.\n\n"
            "Two different upstream products live here and they do not cover the same area or "
            "carry the same licence. The RAP Vegetation Cover v3 layers (annual and perennial "
            "forb and grass) are 30 m, cover the conterminous United States, and are released "
            "under CC0 1.0. The rangeland-s2 layers (sagebrush and invasive annual grass) are "
            "10 m, cover only the western United States out to about 101 degrees west, and are "
            "released under CC BY 4.0, which requires attribution. Each collection states its "
            "own licence and citation."),
        "license": "various",
        "keywords": ["rangeland", "vegetation cover", "RAP", "rangeland-s2", "NTSG", "H3"],
        "extent": {
            "spatial": {"bbox": [union]},
            "temporal": {"interval": [["2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z"]]},
        },
        "created": NOW,
        "updated": NOW,
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
        ] + [
            {"rel": "child", "href": f"{BASE}/{c['id']}/stac-collection.json",
             "type": "application/json", "title": c["title"]}
            for c in cols
        ],
    }

p = OUT / "parent-stac-collection.json"
p.write_text(json.dumps(parent(COLLECTIONS), indent=2, ensure_ascii=False) + "\n")
print(f"  wrote {p.name} (4 child links, license=various)")
