"""Generate the STAC collection for the CHELSA v2.1 present-day baseline (data-workflows #448).

Separate from gen_chelsa_stac.py because the schema genuinely differs: the baseline is an
observational climatology with one raster per variable, so it carries plain `bio1`, `bio4`, ...
rather than five GCM members plus median/min/max. Per-column text that IS shared with the futures
(the H3 index columns) is kept word-for-word identical, since the renderer folds identical
descriptions across a collection and keeps the first it sees.
"""
import argparse
import json
import sys

VARS = [
    ("bio1",  "Annual mean air temperature", "degrees Celsius"),
    ("bio4",  "Temperature seasonality, the standard deviation of monthly mean temperature multiplied by 100", "degrees Celsius x 100"),
    ("bio5",  "Maximum air temperature of the warmest month", "degrees Celsius"),
    ("bio6",  "Minimum air temperature of the coldest month", "degrees Celsius"),
    ("bio12", "Annual precipitation", "millimetres"),
    ("bio15", "Precipitation seasonality, the coefficient of variation of monthly precipitation", "percent"),
    ("bio17", "Precipitation of the driest quarter", "millimetres"),
]
BASE = "https://s3-west.nrp-nautilus.io/public-bioclimate"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="1981-2010")
    ap.add_argument("--ranges", required=True)
    ap.add_argument("--bio12-clipped", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rng = json.loads(args.ranges)
    y0, y1 = args.period.split("-")
    akey = f"baseline-{args.period}-hex"

    cols = []
    for v, what, units in VARS:
        lo, hi = rng[v]
        d = (f"{what}, in {units}, observed over {y0}-{y1}. "
             f"Observed range across this dataset: {lo} to {hi}.")
        if v == "bio12":
            d += (" The source encoding tops out at 6553.5 millimetres, which is below the wettest "
                  f"places on Earth, so cells at that value are a lower bound rather than a "
                  f"measurement. {args.bio12_clipped:,} cells reach it. Exclude them when looking "
                  "at extremes: WHERE bio12 < 6553.5")
        cols.append({"name": v, "type": "float32", "description": d})
    cols += [
        {"name": "h8", "type": "uint64", "description": "H3 cell identifier at resolution 8. This is the native resolution of this dataset and the usual key for joining against other datasets in this catalog."},
        {"name": "h5", "type": "uint64", "description": "H3 cell identifier at resolution 5, for joining against datasets held at that resolution."},
        {"name": "h4", "type": "uint64", "description": "H3 cell identifier at resolution 4, for joining against datasets held at that resolution."},
        {"name": "h0", "type": "int64",  "description": "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads."},
    ]

    d = {
        "type": "Collection", "stac_version": "1.0.0",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "id": f"chelsa-2-1-baseline-{args.period}",
        "title": f"CHELSA 2.1 Bioclimate — observed baseline, {y0}-{y1} (global land)",
        "description": (
            f"Observed bioclimatic conditions for {y0}-{y1} from CHELSA version 2.1, aggregated to "
            "H3 hexagonal cells at resolution 8 over the global land surface. Seven variables are "
            "included: annual mean temperature, temperature seasonality, maximum temperature of "
            "the warmest month, minimum temperature of the coldest month, annual precipitation, "
            "precipitation seasonality, and precipitation of the driest quarter.\n\n"
            "This is the reference period the future projections in this bucket are measured "
            "against. Because it shares the same cells at the same resolution, the change under a "
            "given scenario is a direct join:\n\n"
            "```sql\n"
            "SELECT AVG(f.bio1_median - b.bio1) AS warming_degrees_c\n"
            f"FROM read_parquet('{BASE}/chelsa-2-1/ssp585-2071-2100/hex/h0=*/data_0.parquet') f\n"
            f"JOIN read_parquet('{BASE}/chelsa-2-1/baseline-{args.period}/hex/h0=*/data_0.parquet') b\n"
            "  USING (h8)\n"
            "```\n\n"
            "Unlike the future collections, this one holds a single observed value per variable "
            "rather than five climate models with a median and range — there is no ensemble to "
            "summarise, because these are conditions that occurred rather than projections.\n\n"
            "Footprint: global land. The CHELSA source is a worldwide surface that also covers the "
            "ocean, so this dataset is restricted to cells that intersect the WWF Terrestrial "
            "Ecoregions of the World, which includes Antarctica. That leaves 195,048,994 cells "
            "across 108 partitions, identical to the future collections so every cell pairs.\n\n"
            "Annual precipitation is limited by the source encoding to 6553.5 millimetres. Cells at "
            "that value are a lower bound rather than a measurement, and should be excluded from "
            "any analysis of precipitation extremes."
        ),
        "license": "CC0-1.0",
        "keywords": ["climate", "bioclimate", "CHELSA", "baseline", "temperature", "precipitation", "H3"],
        "providers": [
            {"name": "CHELSA (Swiss Federal Institute for Forest, Snow and Landscape Research WSL)",
             "roles": ["producer", "licensor"], "url": "https://chelsa-climate.org/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 83.7]]},
            "temporal": {"interval": [[f"{y0}-01-01T00:00:00Z", f"{y1}-12-31T23:59:59Z"]]},
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/chelsa-2-1/baseline-{args.period}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://chelsa-climate.org/terms-of-use/", "type": "text/html",
             "title": "CHELSA terms of use (CC0 1.0)"},
            {"rel": "cite-as", "href": "https://doi.org/10.1038/sdata.2017.122", "type": "text/html",
             "title": "Karger et al. 2017, Climatologies at high resolution for the earth's land surface areas"},
        ],
        "assets": {
            akey: {
                "href": f"{BASE}/chelsa-2-1/baseline-{args.period}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet", "roles": ["data"],
                "title": f"Observed bioclimate H3 hex, seven variables at resolution 8 ({y0}-{y1})",
                "description": (
                    "One row per H3 cell at resolution 8, covering the global land surface, holding "
                    "seven observed bioclimatic variables. Each value is the area-weighted mean of "
                    "the roughly 1 km CHELSA source pixels falling inside that cell, so the columns "
                    "are already averages: combining cells means averaging again, weighted by cell "
                    "area, rather than adding.\n\n"
                    "Cells are the unit of aggregation and every row is a distinct cell, so no "
                    "de-duplication is needed before aggregating.\n\n"
                    "To pair a cell with its projected future, join on h8 against any of the "
                    "scenario collections in this bucket; they share the same cells exactly. "
                    "Coarser datasets can be met at h5 or h4, which are carried as columns for "
                    "that purpose.\n\n"
                    "For an area-weighted combination of cells, see the H3 guidance the data "
                    "server publishes; cell area varies with latitude and should not be assumed "
                    "constant."
                ),
                "h3:native_resolution": 8,
                "h3:parent_resolutions": [5, 4, 0],
                "table:columns": cols,
            }
        },
    }
    with open(args.out, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"{d['id']}: {len(cols)} columns -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
