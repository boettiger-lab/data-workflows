"""Generate the STAC collection for one CHELSA future-bioclimate (ssp, period) combination.

One generator for all nine collections, so the per-column text is identical everywhere by
construction. The mcp-data-server renderer folds identical per-column descriptions across assets
and keeps the first it sees, so a hand-edit of one collection would silently lose the other
version; a single source avoids that entirely.

Measured ranges are passed in per combination — they differ by scenario and period, and the rule
is to document what was ingested rather than what the source documentation claims.
"""
import argparse
import json
import sys

MEMBERS = [("gfdl_esm4", "GFDL-ESM4"), ("ipsl_cm6a_lr", "IPSL-CM6A-LR"),
           ("mpi_esm1_2_hr", "MPI-ESM1-2-HR"), ("mri_esm2_0", "MRI-ESM2-0"),
           ("ukesm1_0_ll", "UKESM1-0-LL")]

VARS = [
    ("bio1",  "Annual mean air temperature", "degrees Celsius"),
    ("bio4",  "Temperature seasonality, the standard deviation of monthly mean temperature multiplied by 100", "degrees Celsius x 100"),
    ("bio5",  "Maximum air temperature of the warmest month", "degrees Celsius"),
    ("bio6",  "Minimum air temperature of the coldest month", "degrees Celsius"),
    ("bio12", "Annual precipitation", "millimetres"),
    ("bio15", "Precipitation seasonality, the coefficient of variation of monthly precipitation", "percent"),
    ("bio17", "Precipitation of the driest quarter", "millimetres"),
]

SSP_LABEL = {"ssp126": "SSP1-2.6", "ssp370": "SSP3-7.0", "ssp585": "SSP5-8.5"}
SSP_BLURB = {
    "ssp126": "SSP1-2.6 is a low-emissions pathway in which warming stabilises and eases back "
              "slightly late in the century.",
    "ssp370": "SSP3-7.0 is a high-emissions pathway with warming continuing throughout the century.",
    "ssp585": "SSP5-8.5 is the highest-emissions pathway considered here, with the largest warming "
              "by 2100.",
}
BASE = "https://s3-west.nrp-nautilus.io/public-bioclimate"


def columns(rng, clipped):
    cols = []
    for v, what, units in VARS:
        lo, hi = rng[v]
        rtxt = f"Observed range across this dataset: {lo} to {hi}."
        for suf, gcm in MEMBERS:
            cols.append({"name": f"{v}_{suf}", "type": "float32",
                         "description": f"{what}, in {units}, from the {gcm} climate model. {rtxt}"})
        med = (f"Median {what[0].lower()}{what[1:]}, in {units}, across the five climate models. "
               f"This is the recommended single value when one number is wanted for a cell. {rtxt}")
        if v == "bio12":
            med += (" The source encoding tops out at 6553.5 millimetres, which is below the "
                    f"wettest places on Earth, so cells at that value are a lower bound rather "
                    f"than a measurement. {clipped:,} cells reach it in the median. Exclude them "
                    "when looking at extremes: WHERE bio12_median < 6553.5")
        cols.append({"name": f"{v}_median", "type": "float32", "description": med})
        cols.append({"name": f"{v}_min", "type": "float32",
                     "description": f"Lowest value of {what[0].lower()}{what[1:]}, in {units}, among the five "
                                    f"climate models for this cell. With {v}_max it gives the full spread of "
                                    "model results."})
        cols.append({"name": f"{v}_max", "type": "float32",
                     "description": f"Highest value of {what[0].lower()}{what[1:]}, in {units}, among the five "
                                    f"climate models for this cell. The difference between {v}_max and {v}_min "
                                    "shows how much the models disagree about this place."})
    cols += [
        {"name": "h8", "type": "uint64", "description": "H3 cell identifier at resolution 8. This is the native resolution of this dataset and the usual key for joining against other datasets in this catalog."},
        {"name": "h5", "type": "uint64", "description": "H3 cell identifier at resolution 5, for joining against datasets held at that resolution."},
        {"name": "h4", "type": "uint64", "description": "H3 cell identifier at resolution 4, for joining against datasets held at that resolution."},
        {"name": "h0", "type": "int64",  "description": "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads."},
    ]
    return cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssp", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--ranges", required=True, help='JSON {"bio1":[lo,hi], ...}')
    ap.add_argument("--bio12-clipped", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rng = json.loads(args.ranges)
    ssp, period = args.ssp, args.period
    label = SSP_LABEL[ssp]
    y0, y1 = period.split("-")
    slug = f"{ssp}-{period}"
    akey = f"{slug}-hex"

    d = {
        "type": "Collection", "stac_version": "1.0.0",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "id": f"chelsa-2-1-{slug}",
        "title": f"CHELSA 2.1 Future Bioclimate — {label}, {y0}-{y1} (global land)",
        "description": (
            f"Downscaled CMIP6 bioclimatic variables for {y0}-{y1} under the {label} scenario, from "
            "CHELSA version 2.1, aggregated to H3 hexagonal cells at resolution 8 over the global "
            "land surface. Seven variables are included: annual mean temperature, temperature "
            "seasonality, maximum temperature of the warmest month, minimum temperature of the "
            "coldest month, annual precipitation, precipitation seasonality, and precipitation of "
            "the driest quarter.\n\n"
            f"{SSP_BLURB[ssp]} Companion collections in this bucket cover the other scenario and "
            "period combinations, so a cell can be compared across pathways by joining them on h8.\n\n"
            "Each cell carries the value from all five global climate models CHELSA provides for "
            "this scenario, kept as separate columns, together with their median, minimum and "
            "maximum. Keeping every model means any summary a consumer needs can be computed "
            "directly, and the disagreement between models stays visible rather than being averaged "
            "away.\n\n"
            "Footprint: global land. The CHELSA source is a worldwide surface that also covers the "
            "ocean, so this dataset is restricted to cells that intersect the WWF Terrestrial "
            "Ecoregions of the World, which includes Antarctica. That leaves 195,048,994 cells "
            "across 108 partitions. The source grid spans 84 degrees North to 90 degrees South; no "
            "land falls above its northern edge, so nothing is lost to it.\n\n"
            "Annual precipitation is limited by the source encoding to 6553.5 millimetres. Cells at "
            "that value are a lower bound rather than a measurement, and should be excluded from "
            "any analysis of precipitation extremes.\n\n"
            "These are projections, not observations. Every value is conditional on the scenario "
            "and on the climate model that produced it."
        ),
        "license": "CC0-1.0",
        "keywords": ["climate", "bioclimate", "CMIP6", "CHELSA", "temperature", "precipitation",
                     "projection", "H3", label],
        "providers": [
            {"name": "CHELSA (Swiss Federal Institute for Forest, Snow and Landscape Research WSL)",
             "roles": ["producer", "licensor"], "url": "https://chelsa-climate.org/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 83.7]]},
            "temporal": {"interval": [[f"{y0}-01-01T00:00:00Z", f"{y1}-12-31T23:59:59Z"]]},
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/chelsa-2-1/{slug}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://chelsa-climate.org/terms-of-use/", "type": "text/html",
             "title": "CHELSA terms of use (CC0 1.0)"},
            {"rel": "cite-as", "href": "https://doi.org/10.1038/sdata.2017.122", "type": "text/html",
             "title": "Karger et al. 2017, Climatologies at high resolution for the earth's land surface areas"},
        ],
        "assets": {
            akey: {
                "href": f"{BASE}/chelsa-2-1/{slug}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet", "roles": ["data"],
                "title": f"Future bioclimate H3 hex, seven variables at resolution 8 ({label}, {y0}-{y1})",
                "description": (
                    "One row per H3 cell at resolution 8, covering the global land surface, holding "
                    "seven bioclimatic variables. Each value is the area-weighted mean of the "
                    "roughly 1 km CHELSA source pixels falling inside that cell, so the columns are "
                    "already averages: combining cells means averaging again, weighted by cell area, "
                    "rather than adding. For each variable the five climate model columns, the "
                    "median, the minimum and the maximum all describe the same cell, so they are "
                    "alternative readings of one place rather than quantities to be summed "
                    "together.\n\n"
                    "Cells are the unit of aggregation and every row is a distinct cell, so no "
                    "de-duplication is needed before aggregating.\n\n"
                    "To combine this with other datasets in this catalog, join on h8. Coarser "
                    "datasets can be met at h5 or h4, which are carried as columns for that "
                    "purpose.\n\n"
                    "```sql\n"
                    f"-- compare this scenario against another for the same cells\n"
                    f"SELECT AVG(a.bio1_median - b.bio1_median) AS warming_difference_c\n"
                    f"FROM read_parquet('{BASE}/chelsa-2-1/{slug}/hex/h0=*/data_0.parquet') a\n"
                    f"JOIN read_parquet('{BASE}/chelsa-2-1/ssp126-{period}/hex/h0=*/data_0.parquet') b\n"
                    "  USING (h8)\n"
                    "```\n\n"
                    "For an area-weighted combination of cells, see the H3 guidance the data server "
                    "publishes; cell area varies with latitude and should not be assumed constant."
                ),
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [5, 4, 0],
                "table:columns": columns(rng, args.bio12_clipped),
            }
        },
    }
    with open(args.out, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"{d['id']}: {len(d['assets'][akey]['table:columns'])} columns -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
