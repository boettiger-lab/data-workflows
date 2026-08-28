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
        sum=2896072952371, max=2996838,
        vessels=["YACHT", "SAILING VESSEL"],
    ),
    "oil-gas": dict(
        title="Oil and gas",
        sum=561132077068, max=1359913,
        vessels=["PLATFORM", "FLOATING STORAGE/PRODUCTION", "DRILLING JACK UP",
                 "DRILLING RIG", "WELL STIMULATION VESSEL"],
        note="Platforms, rigs and FPSOs only, not the vessels servicing them. These are "
             "largely stationary transmitters, so a cell's value reflects dwell time rather "
             "than transit.",
    ),
    "fishing": dict(
        title="Fishing ships",
        sum=509901552478, max=1009771,
        vessels=["FISHING VESSEL", "TRAWLER"],
    ),
    "passenger": dict(
        title="Passenger ships",
        sum=59002510, max=112280,
        vessels=["PASSENGER SHIP", "RO-RO/PASSENGER SHIP"],
        note="WARNING: this layer is anomalously sparse upstream. Its total is four orders of "
             "magnitude below fishing and seven below commercial, and its maximum cell value is "
             "likewise far below theirs, so the layer is uniformly small rather than merely "
             "concentrated. Note also that PASSENGER/CARGO SHIP is classified under commercial, "
             "not here. Do NOT read this as total passenger traffic and do NOT compare it "
             "like-for-like against the other categories.",
    ),
    "commercial": dict(
        title="Commercial ships",
        sum=652072966152319, max=62652999,
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
             "the same surface and are not independent signals.",
    ),
    "global": dict(
        title="All vessel types combined",
        sum=656040131736746, max=65468393,
        vessels=["all ship types combined"],
        note="Verified 2026-08-28: the five category layers sum to this layer EXACTLY at pixel "
             "level (residual 0 across 2.45e9 pixels), so the categories are exhaustive and there "
             "is no unclassified remainder. Note commercial alone accounts for 99.4%.",
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
                  "about 3 columns. Coverage stops at about 85 degrees north and south."
                + extra
            ),
            "roles": ["data"],
            "raster:bands": [{
                "name": "ais_positions",
                "data_type": "int32",
                "nodata": 2147483647,
                "unit": "AIS position count",
                "statistics": {"minimum": 0, "maximum": m["max"], "sum": m["sum"]},
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
                  "at about 85 degrees north and south, so polar h0 partitions are absent. "
                  f"Reference total: SUM(ais_positions) = {m['sum']}, matching the source COG "
                  "pixel sum exactly."
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
            "World Bank for the WBG Offshore Wind Development Program. "
            f"{CITATION}\n\n"
            "READ BEFORE USE:\n"
            "- Values count AIS *reporting*, not vessels and not traffic volume. Moving and "
            "stationary ships both transmit, and coverage depends on receiver density and on "
            "vessels not going dark. The upstream readme calls the result analogous to the "
            "general intensity of shipping activity.\n"
            "- The five category layers sum to the global layer EXACTLY (verified at pixel level, "
            "residual 0). Commercial alone is 99.4% of global, so commercial and global are "
            "nearly the same surface.\n"
            "- The passenger layer is anomalously sparse upstream, four orders of magnitude below "
            "fishing. Do not read it as total passenger traffic. See that asset's description.\n"
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
