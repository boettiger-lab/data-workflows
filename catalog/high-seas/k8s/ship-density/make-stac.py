#!/usr/bin/env python3
"""Generate the ship-density STAC collection (issue #641).

One collection holding all 12 assets (6 COG + 6 hex). The six layers are one product on one
grid with one license and one provenance, and the categories-sum-to-global relation is only
visible if they sit together.

Single authority for schema text: every hex asset gets the SAME per-column descriptions,
generated here, never hand-edited per asset (mcp-data-server#303).

Usage:
  make-stac.py --out /tmp/stac-collection.json [--rows-json measured-rows.json]

Then verify and publish:
  scripts/verify-stac.py --no-data /tmp/stac-collection.json
  rclone copyto /tmp/stac-collection.json nrp:public-high-seas/ship-density/stac-collection.json
"""
import argparse
import json

BUCKET = "public-high-seas"
PREFIX = "ship-density"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}/{PREFIX}"

# Measured on the cluster 2026-08-28 from the published COGs (not from the upstream sidecars,
# whose histograms saturate at 2^31). These are the acceptance truth for the hex SUM check.
LAYERS = {
    "leisure": dict(
        title="Leisure vessels",
        cog_sum=2896072952371, max=2996838, hex_sum=2896072871440,
        vessels=["YACHT", "SAILING VESSEL"],
    ),
    "oil-gas": dict(
        title="Oil and gas",
        cog_sum=561132077068, max=1359913, hex_sum=561132069519,
        vessels=["PLATFORM", "FLOATING STORAGE/PRODUCTION", "DRILLING JACK UP",
                 "DRILLING RIG", "WELL STIMULATION VESSEL"],
        note="Platforms, rigs and FPSOs only, not the vessels servicing them. These are "
             "largely stationary transmitters, so a cell's value reflects dwell time rather "
             "than transit.",
    ),
    "fishing": dict(
        title="Fishing ships",
        cog_sum=509901552478, max=1009771, hex_sum=509901033115,
        vessels=["FISHING VESSEL", "TRAWLER"],
    ),
    "passenger": dict(
        title="Passenger ships",
        cog_sum=59002510, max=112280, hex_sum=59002509,
        vessels=["PASSENGER SHIP", "RO-RO/PASSENGER SHIP"],
        note="SCALE CAVEAT: this layer's magnitudes are far too LOW to be literal AIS position "
             "counts. Its whole global total is equivalent to 0.61 vessels transmitting at the AIS "
             "Class A protocol maximum for the full period, where fishing, oil-gas and leisure sit "
             "at 5,000 to 30,000 vessel-equivalents. Its spatial pattern is nonetheless sound: the "
             "top cells are the world's busiest ferry hubs (Singapore, Merak-Bakauheni, Piraeus, "
             "Sydney, Hong Kong, Dover, Istanbul, Bali), correctly ranked. So use it for relative "
             "geography, not for absolute counts, and note PASSENGER/CARGO SHIP is classified "
             "under commercial. See the collection description on cross-layer comparison.",
    ),
    "commercial": dict(
        title="Commercial ships",
        cog_sum=652072966152319, max=62652999, hex_sum=652072874169118,
        vessels=["BULK CARRIER", "GENERAL CARGO", "TUG", "OFFSHORE SUPPLY SHIP", "CONTAINER SHIP",
                 "OIL/CHEMICAL TANKER", "OIL PRODUCTS TANKER", "CRUDE OIL TANKER", "LPG TANKER",
                 "VEHICLES CARRIER", "RESEARCH/SURVEY VESSEL", "REEFER", "CHEMICAL TANKER",
                 "RO-RO CARGO", "CREW BOAT", "LNG TANKER", "SUPPLY VESSEL", "INLAND TANKER",
                 "LANDING CRAFT", "HOPPER DREDGER", "BUNKERING TANKER", "PATROL VESSEL",
                 "MULTI PURPOSE OFFSHORE VESSEL", "CEMENT CARRIER", "PUSHER TUG",
                 "FIRE FIGHTING VESSEL", "UTILITY VESSEL", "SPECIAL VESSEL",
                 "ANCHOR HANDLING VESSEL", "TANKER", "CARGO/CONTAINERSHIP", "TOWING VESSEL",
                 "ORE CARRIER", "FISH CARRIER", "ASPHALT/BITUMEN TANKER", "DECK CARGO SHIP",
                 "PASSENGER/CARGO SHIP", "LIVESTOCK CARRIER", "SHUTTLE TANKER",
                 "RO-RO/CONTAINER CARRIER", "WATER TANKER", "ORE/OIL CARRIER", "LIMESTONE CARRIER"],
        note="This layer is 99.4% of the global layer, so commercial and global are very nearly "
             "the same surface and are not independent signals. SCALE CAVEAT: its magnitudes are "
             "too HIGH to be literal AIS position counts. The total requires 6.7 MILLION vessels "
             "transmitting at the AIS Class A protocol maximum (one message per 2 seconds), at "
             "100% duty, for the entire six years. Even a generous 200,000-vessel world fleet "
             "under those same maximal assumptions is exceeded 33x. The values are reproduced "
             "faithfully from upstream (they match the upstream ESRI sidecar means to 0.008%, the "
             "antimeridian trim), so this is a property of the source, not of this conversion. "
             "See the collection description on cross-layer comparison.",
    ),
    "global": dict(
        title="All vessel types combined",
        cog_sum=656040131736746, max=65468393, hex_sum=656040039145670,
        vessels=["all ship types combined"],
        note="Verified 2026-08-28: the five category layers sum to this layer EXACTLY at pixel "
             "level (residual 0 across 2.45e9 pixels), so the categories are exhaustive and there "
             "is no unclassified remainder. Note commercial alone accounts for 99.4%, and this "
             "layer therefore inherits commercial's scale problem: see that asset's note and the "
             "collection description.",
    ),
}
ORDER = ["leisure", "oil-gas", "fishing", "passenger", "commercial", "global"]

BBOX = [-180.000311275, -84.987352063, 179.999688725, 85.002647937]
TEMPORAL = ["2015-01-01T00:00:00Z", "2021-02-28T23:59:59Z"]

CITATION = ("Data source: IMF's World Seaborne Trade monitoring system "
            "(Cerdeiro, Komaromi, Liu and Saeed, 2020).")

# NOTE: keep the word "categor*" out of this column description. It is a continuous count, but
# lint-stac-categorical.py treats any "categor" mention in a column description as a declaration
# that the column is a coded categorical and then demands a CODE=Definition list. The vessel
# grouping belongs on the asset description, not here.
VALUE_DESC = (
    "Total number of AIS positions reported in the cell by ships in this layer's vessel group, "
    "summed over "
    "January 2015 to February 2021. A count already integrated per source pixel, aggregated into "
    "H3 with the 'sum' reducer, so SUM(ais_positions) over the hex IS the catalog total for this "
    "layer and needs no dedup. 0 is a real observed value meaning no AIS position was recorded, "
    "and is distinct from the source nodata sentinel 2147483647 (which does not occur: the source "
    "grid has no nodata pixels). Stored as double; all values are integer-valued counts and the "
    "full range is exactly representable."
)

H3_DESC = {
    "h8": "H3 cell ID at resolution 8 (native resolution; one row per cell).",
    "h7": "H3 cell ID at resolution 7 (rollup parent).",
    "h6": "H3 cell ID at resolution 6 (rollup parent).",
    "h5": "H3 cell ID at resolution 5 (rollup parent).",
    "h0": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads.",
}


def reference_totals(m):
    """State both totals honestly.

    The hex SUM does NOT equal the COG pixel sum bit-for-bit: exact_extract area-weights
    partial pixels at cell boundaries in floating point, so a little mass is lost. Measured
    relative shortfall ranges from 1.7e-8 (passenger) to 1.0e-6 (fishing). Publishing "matches
    exactly" would be false, and publishing only one of the two numbers would leave a consumer
    unable to tell whether their own SUM is correct.
    """
    cog = m["cog_sum"]
    hexs = m.get("hex_sum")
    if hexs is None:
        return f"Source COG pixel sum: {cog}."
    short = cog - hexs
    rel = short / cog if cog else 0.0
    return (f"Source COG pixel sum: {cog}. Measured hex SUM(ais_positions): {hexs}, "
            f"short by {short} ({rel:.1e} relative). The difference is floating-point mass loss "
            f"from area-weighting partial pixels at H3 cell boundaries, not missing data. Use the "
            f"hex SUM as the reference when validating your own aggregation.")


def hex_columns():
    cols = [{"name": "ais_positions", "type": "double", "description": VALUE_DESC}]
    for name, typ in (("h8", "uint64"), ("h7", "uint64"), ("h6", "uint64"),
                      ("h5", "uint64"), ("h0", "int64")):
        cols.append({"name": name, "type": typ, "description": H3_DESC[name]})
    return cols


def build(rows=None):
    assets = {}
    for layer in ORDER:
        m = LAYERS[layer]
        vessels = ", ".join(m["vessels"])
        common = (f"AIS position density for {m['title'].lower()}. "
                  f"Vessel types: {vessels}. ")
        extra = (" " + m["note"]) if m.get("note") else ""

        assets[f"{PREFIX}-{layer}-cog"] = {
            "href": f"{BASE}/{layer}-cog.tif",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "title": f"Ship density, {m['title']} (COG)",
            "description": (
                common
                + "Cloud-optimized GeoTIFF, EPSG:4326, 72000 x 33998 at 0.005 degrees "
                  "(about 500 m at the equator). Trimmed from the 360.03-degree source grid to "
                  "exactly 360.0 degrees; the source overshot both sides of the antimeridian by "
                  "about 3 columns. Coverage stops at about 85 degrees north and south. "
                  "Overviews use AVERAGE resampling, rebuilt 2026-08-29: the COG driver's "
                  "default CUBIC has negative side lobes and rang below zero around every "
                  "shipping lane on this near-zero-ocean field (issue #641). Do not rebuild "
                  "them without -co RESAMPLING=AVERAGE -co OVERVIEWS=IGNORE_EXISTING."
                + extra
            ),
            "roles": ["data"],
            "raster:bands": [{
                "name": "ais_positions",
                "data_type": "int32",
                "nodata": 2147483647,
                "unit": "AIS position count",
                "statistics": {"minimum": 0, "maximum": m["max"], "sum": m["cog_sum"]},
            }],
        }

        hex_asset = {
            "href": f"{BASE}/{layer}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"Ship density, {m['title']} (H3 hex)",
            "description": (
                common
                + "H3 resolution 8, hive-partitioned by h0. Built with the 'sum' reducer over a "
                  "count-per-pixel source, so SUM(ais_positions) is the catalog total for this "
                  "layer and no per-feature dedup is needed (this is a raster reduction, not a "
                  "feature conversion, so there is no _cng_fid). Sum reducers emit a full grid: "
                  "cells with no recorded AIS position are present with value 0. Coverage stops "
                  "at about 85 degrees north and south, but a sum reducer still emits those "
                  "partitions, so all 122 are present and the row count is the full res-8 grid. "
                  + reference_totals(m)
                + extra
            ),
            "roles": ["data"],
            "h3:native_resolution": 8,
            "h3:parent_resolutions": [7, 6, 5, 0],
            "table:columns": hex_columns(),
        }
        if rows and layer in rows:
            hex_asset["table:row_count"] = rows[layer]
        assets[f"{PREFIX}-{layer}-hex"] = hex_asset

    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
        ],
        "id": "ship-density",
        "title": "Global Shipping Traffic Density (World Bank / IMF)",
        "description": (
            "Global AIS-derived shipping traffic density, 2015-2021, as six layers: five vessel "
            "categories (commercial, fishing, oil and gas, passenger, leisure) plus a combined "
            "global layer. Pixel and cell values are the total number of AIS positions reported "
            "in that cell over January 2015 to February 2021, at 0.005 degrees (about 500 m at "
            "the equator).\n\n"
            "Produced by the IMF World Seaborne Trade Monitoring System and published by the "
            "World Bank for the WBG Offshore Wind Development Program, with data analysis "
            "supported by the World Bank's ESMAP and PROBLUE programs. "
            f"{CITATION}\n\n"
            "READ BEFORE USE:\n"
            "- Values count AIS *reporting*, not vessels and not traffic volume. Moving and "
            "stationary ships both transmit, and coverage depends on receiver density and on "
            "vessels not going dark. The upstream readme calls the result analogous to the "
            "general intensity of shipping activity.\n"
            "- The five category layers sum to the global layer EXACTLY (verified at pixel level, "
            "residual 0). Commercial alone is 99.4% of global, so commercial and global are "
            "nearly the same surface.\n"
            "- DO NOT COMPARE ABSOLUTE MAGNITUDES ACROSS LAYERS, and do not treat values as "
            "literal counts of the 'hourly AIS positions' the upstream readme describes. The six "
            "layers are not on a mutually consistent scale. Dividing each layer's total by the "
            "world fleet for its vessel group and by the 54,041-hour period gives the implied "
            "per-vessel message rate: fishing one per 27 s, leisure one per 13 s and oil-gas one "
            "per 3.5 s, which are all valid raw-AIS rates (above the 2 s protocol floor) but are "
            "NOT the documented hourly sampling; passenger one per 7.3 HOURS, which is the only "
            "layer consistent with hourly sampling; and commercial one per 0.06 s, which is 33x "
            "FASTER THAN THE AIS CLASS A PROTOCOL ALLOWS and therefore impossible under any "
            "reading. Global inherits commercial's problem, being 99.4% of it. The fleet sizes are "
            "order-of-magnitude assumptions, but the commercial conclusion does not depend on "
            "them: even a 1,000,000-vessel fleet at 100% duty and maximum rate is exceeded 6.7x. "
            "Practical reading: the three middle layers behave like raw message counts, passenger "
            "like hourly counts, and commercial/global like neither.\n"
            "- All values are reproduced faithfully from upstream: they match the upstream ESRI "
            "sidecar means to 0.008%, which is exactly the antimeridian trim. These are properties "
            "of the source, not of this conversion. The World Bank metadata offers no explanation: "
            "its data-quality and lineage fields are empty and the per-layer resource descriptions "
            "are identical boilerplate. Note also that the taxonomy was, per the readme, "
            "'aggregated to suit the needs of the WBG Offshore Wind Development Program', and the "
            "commercial group is a 43-type catch-all including tugs, crew boats, supply and "
            "anchor-handling vessels, patrol, firefighting, utility and 'special' vessels, "
            "dredgers, and generic 'TANKER'/'CARGO/CONTAINERSHIP' labels. Harbour workboats are "
            "numerous and effectively permanently resident in small areas, and stationary ships "
            "transmit too, which explains the direction of commercial's dominance even though it "
            "does not explain the magnitude.\n"
            "- Spatial patterns ARE sound in every layer, including passenger. Verified top cells: "
            "fishing peaks on the Barents Sea cod grounds; passenger peaks at Singapore, "
            "Merak-Bakauheni, Piraeus, Sydney, Hong Kong, Dover, Istanbul and Bali. So each layer "
            "is usable for RELATIVE geography within itself. Cross-layer ratios and absolute "
            "counts are not usable.\n"
            "- Coverage stops at about 85 degrees north and south.\n"
            "- 0 means no AIS position recorded and is a real value. The source declares nodata "
            "2147483647 but no such pixel occurs.\n"
            "- On the hex assets SUM is the correct aggregation and needs no dedup, because these "
            "are raster reductions with a sum reducer rather than per-feature rows."
        ),
        "license": "CC-BY-4.0",
        "keywords": ["shipping", "AIS", "vessel traffic", "marine", "high seas", "oceans"],
        "providers": [
            {"name": "International Monetary Fund", "roles": ["producer"],
             "url": "https://www.imf.org/"},
            {"name": "World Bank Group", "roles": ["licensor", "host"],
             "url": "https://datacatalog.worldbank.org/search/dataset/0037580"},
            {"name": "Boettiger Lab", "roles": ["processor"],
             "url": "https://boettiger-lab.github.io/"},
        ],
        "extent": {
            "spatial": {"bbox": [BBOX]},
            "temporal": {"interval": [TEMPORAL]},
        },
        "sci:citation": CITATION,
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root",
             "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
             "type": "application/json"},
            {"rel": "parent",
             "href": f"https://s3-west.nrp-nautilus.io/{BUCKET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "license",
             "href": "https://datacatalog.worldbank.org/public-licenses?fragment=cc",
             "type": "text/html", "title": "Creative Commons Attribution 4.0"},
            {"rel": "describedby",
             "href": "https://datacatalog.worldbank.org/search/dataset/0037580/global-shipping-traffic-density",
             "type": "text/html", "title": "World Bank Data Catalog entry 0037580"},
        ],
        "assets": assets,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows-json", help='optional {"leisure": 691776122, ...} row counts')
    a = ap.parse_args()
    rows = json.load(open(a.rows_json)) if a.rows_json else None
    doc = build(rows)
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"wrote {a.out}: {len(doc['assets'])} assets, license {doc['license']}")
