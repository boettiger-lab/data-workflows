#!/usr/bin/env python3
"""Generate the Bio-ORACLE v3.0 STAC collections (data-workflows #53).

One generator for all 18 leaf collections plus the bucket-level parent, so the
shared per-column and per-asset text is identical everywhere by construction.
The mcp-data-server renderer folds identical per-column descriptions across
assets and keeps the first it sees, so a hand-edit of one collection would
silently lose the other version; a single source avoids that.

Measured ranges are passed in from the built hex (--stats), never copied from
the source documentation: the rule is to document what was ingested.
"""
import argparse
import json
import os

BUCKET = "public-bio-oracle"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"

CITATION_V3 = ("Assis, J., Fernandez Bejarano, S.J., Salazar, V.W., Schepers, L., Gouvea, L., "
               "Fragkopoulou, E., Leclercq, F., Vanhoorne, B., Tyberghein, L., Serrao, E.A., "
               "Verbruggen, H., De Clerck, O. (2024) Bio-ORACLE v3.0. Pushing marine data layers "
               "to the CMIP6 Earth system models of climate change research. Global Ecology and "
               "Biogeography. https://doi.org/10.1111/geb.13813")
CITATION_V1 = ("Tyberghein, L., Verbruggen, H., Pauly, K., Troupin, C., Mineur, F., De Clerck, O. "
               "(2012) Bio-ORACLE: A global environmental dataset for marine species distribution "
               "modelling. Global Ecology and Biogeography, 21, 272-281. "
               "https://doi.org/10.1111/j.1466-8238.2011.00656.x")

# name, prefix, value_column, title, quantity, units, period(None for terrain), circular_partner
LAYERS = [
    ("thetao-mean", "depthmean", "thetao_mean", "Sea Water Temperature",
     "sea water temperature", "degrees Celsius", ("2000", "2019"), None),
    ("so-mean", "depthmean", "so_mean", "Sea Water Salinity",
     "sea water salinity", "practical salinity units", ("2000", "2019"), None),
    ("sws-mean", "depthmean", "sws_mean", "Sea Water Current Velocity",
     "sea water current velocity", "metres per second", ("2000", "2019"), None),
    ("swd-mean-sin", "depthmean", "swd_sin", "Sea Water Current Direction (sine component)",
     "the sine of the sea water current direction", "dimensionless, -1 to 1", ("2000", "2019"),
     ("swd-mean-cos", "swd_cos", "swd_sin")),
    ("swd-mean-cos", "depthmean", "swd_cos", "Sea Water Current Direction (cosine component)",
     "the cosine of the sea water current direction", "dimensionless, -1 to 1", ("2000", "2019"),
     ("swd-mean-sin", "swd_sin", "swd_cos")),
    ("no3-mean", "depthmean", "no3_mean", "Nitrate",
     "nitrate concentration", "millimoles per cubic metre", ("2000", "2018"), None),
    ("po4-mean", "depthmean", "po4_mean", "Phosphate",
     "phosphate concentration", "millimoles per cubic metre", ("2000", "2018"), None),
    ("si-mean", "depthmean", "si_mean", "Silicate",
     "silicate concentration", "millimoles per cubic metre", ("2000", "2018"), None),
    ("o2-mean", "depthmean", "o2_mean", "Dissolved Oxygen",
     "dissolved molecular oxygen concentration", "millimoles per cubic metre", ("2000", "2018"), None),
    ("dfe-mean", "depthmean", "dfe_mean", "Dissolved Iron",
     "dissolved iron concentration", "millimoles per cubic metre", ("2000", "2018"), None),
    ("phyc-mean", "depthmean", "phyc_mean", "Primary Productivity (Phytoplankton Carbon)",
     "phytoplankton carbon concentration, the Bio-ORACLE primary productivity layer",
     "millimoles per cubic metre", ("2000", "2020"), None),
    ("ph-mean", "depthmean", "ph_mean", "pH",
     "pH", "pH units", ("2000", "2018"), None),
    ("bathymetry-mean", "terrain", "bathymetry_mean", "Bathymetry (mean depth)",
     "mean sea floor depth, negative below sea level", "metres", None, None),
    ("slope", "terrain", "slope", "Sea Floor Slope",
     "sea floor slope", "degrees", None, None),
    ("aspect-sin", "terrain", "aspect_sin", "Sea Floor Aspect (sine component)",
     "the sine of the sea floor aspect", "dimensionless, -1 to 1", None,
     ("aspect-cos", "aspect_cos", "aspect_sin")),
    ("aspect-cos", "terrain", "aspect_cos", "Sea Floor Aspect (cosine component)",
     "the cosine of the sea floor aspect", "dimensionless, -1 to 1", None,
     ("aspect-sin", "aspect_sin", "aspect_cos")),
    ("tpi", "terrain", "topographic_position_index", "Topographic Position Index",
     "topographic position index, the difference between a cell and the mean of its neighbours",
     "metres", None, None),
    ("tri", "terrain", "terrain_ruggedness_index", "Terrain Ruggedness Index",
     "terrain ruggedness index", "metres", None, None),
]

NO_H8 = (
    "This dataset has no h8 column, and that is deliberate rather than a defect. The Bio-ORACLE "
    "source grid is 0.05 degrees, about 5.5 km, so one source pixel covers roughly 31 square "
    "kilometres. An h6 cell is 36.1 square kilometres, which matches the pixel; an h8 cell is 0.74 "
    "square kilometres, which would replicate each measured value across about 42 identical cells "
    "and publish apparent detail the source does not have. To combine this with an h8-native "
    "dataset such as GBIF or OBIS occurrences, roll that dataset up to h6 or h5 with "
    "h3_cell_to_parent, rather than expecting an h8 column here."
)

REDUCER = (
    "Every value is an area-weighted mean of the source pixels falling inside the cell, so the "
    "columns are already averages. Combining cells means averaging again, weighted by cell area, "
    "not adding. There is no meaningful catalog-wide SUM of this column."
)


def build(layer, stats):
    name, prefix, col, title, quantity, units, period, circ = layer
    st = stats[name]
    ds_path = f"{prefix}/{name}"
    hexhref = f"{BASE}/{ds_path}/hex/h0=*/data_0.parquet"
    coghref = f"{BASE}/{ds_path}/{name}-cog.tif"
    realm = ("depth-mean realm, the average over the water column"
             if prefix == "depthmean" else "benthic realm, describing the sea floor")

    rng = (f"Observed range across this dataset: {st['vmin']:.6g} to {st['vmax']:.6g}, "
           f"mean {st['vmean']:.6g}.")

    desc = [
        f"Global marine {quantity} from Bio-ORACLE version 3.0, aggregated to H3 hexagonal cells "
        f"at resolution 6. Values are the {realm}.",
    ]
    if period:
        desc.append(f"Baseline experiment, {period[0]}-{period[1]}, decade 2010. These are "
                    "modelled climatological means, not individual observations.")
    else:
        desc.append("Terrain characteristics are static and carry no time dimension.")
    desc.append(f"Units: {units}. {rng}")
    desc.append(NO_H8)
    if circ:
        partner_name, partner_col, own_col = circ
        desc.append(
            f"This collection carries only the {'sine' if own_col.endswith('sin') else 'cosine'} "
            f"component of a compass bearing. Pair it with {BASE}/{prefix}/{partner_name}/"
            "stac-collection.json and recombine with "
            f"(degrees(atan2(sin, cos)) + 360) % 360 to get a bearing in degrees. The component "
            "on its own is not a direction."
        )
    desc.append(f"Cite both: {CITATION_V3} And: {CITATION_V1}")

    hexdesc = [
        f"One row per H3 cell at resolution 6 over the global ocean, holding {quantity} in "
        f"{units}.",
        REDUCER,
        "Cells are the unit of aggregation and every row is a distinct cell, so no de-duplication "
        "is needed before aggregating. This is a raster reduction rather than a feature "
        "conversion, so there is no _cng_fid column.",
        NO_H8,
    ]
    if circ:
        partner_name, partner_col, own_col = circ
        sin_p = name if own_col.endswith("sin") else partner_name
        cos_p = partner_name if own_col.endswith("sin") else name
        sin_c = own_col if own_col.endswith("sin") else partner_col
        cos_c = partner_col if own_col.endswith("sin") else own_col
        hexdesc.append(
            "This column is one component of a circular quantity and is not interpretable alone. "
            "Recover the bearing by joining the sine and cosine collections on h6:\n\n"
            "```sql\n"
            "SELECT s.h6,\n"
            f"       (degrees(atan2(s.{sin_c}, c.{cos_c})) + 360) %% 360 AS bearing_degrees,\n"
            f"       sqrt(s.{sin_c}*s.{sin_c} + c.{cos_c}*c.{cos_c}) AS directional_consistency\n"
            f"FROM read_parquet('{BASE}/{prefix}/{sin_p}/hex/h0=*/data_0.parquet') s\n"
            f"JOIN read_parquet('{BASE}/{prefix}/{cos_p}/hex/h0=*/data_0.parquet') c USING (h6)\n"
            "```".replace("%%", "%")
        )

    cols = [
        {"name": col, "type": "float32",
         "description": f"Area-weighted mean {quantity} within the cell, in {units}. {rng} "
                        + REDUCER},
        {"name": "h6", "type": "uint64",
         "description": "H3 cell ID at resolution 6 (native resolution; one row per cell)."},
        {"name": "h5", "type": "uint64",
         "description": "H3 cell ID at resolution 5, for joining against coarser datasets."},
        {"name": "h0", "type": "int64",
         "description": "H3 cell ID at resolution 0, used as the partition key for "
                        "hive-partitioned reads."},
    ]

    coll = {
        "type": "Collection", "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": f"bio-oracle-{prefix}-{name}",
        "title": f"Bio-ORACLE v3.0 — {title} ({'depth-mean' if prefix == 'depthmean' else 'benthic terrain'})",
        "description": "\n\n".join(desc),
        "license": "other",
        "sci:citation": CITATION_V3,
        "sci:doi": "10.1111/geb.13813",
        "sci:publications": [
            {"doi": "10.1111/geb.13813", "citation": CITATION_V3},
            {"doi": "10.1111/j.1466-8238.2011.00656.x", "citation": CITATION_V1},
        ],
        "keywords": ["marine", "ocean", "Bio-ORACLE", "species distribution modelling",
                     "H3", title],
        "providers": [
            {"name": "Bio-ORACLE (Ghent University, University of Algarve, VLIZ)",
             "roles": ["producer", "licensor"], "url": "https://bio-oracle.org/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
            "temporal": {"interval": [[f"{period[0]}-01-01T00:00:00Z",
                                       f"{period[1]}-12-31T23:59:59Z"]]} if period
            else {"interval": [[None, None]]},
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/{ds_path}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": "https://bio-oracle.org/downloads-to-email.php",
             "type": "text/html",
             "title": "Bio-ORACLE terms: released under the GNU General Public License"},
            {"rel": "cite-as", "href": "https://doi.org/10.1111/geb.13813", "type": "text/html",
             "title": "Assis et al. 2024, Bio-ORACLE v3.0"},
        ],
        "assets": {
            f"{name}-hex": {
                "href": hexhref, "type": "application/x-parquet", "roles": ["data"],
                "title": f"{title} H3 hex at resolution 6",
                "description": "\n\n".join(hexdesc),
                "h3:native_resolution": 6,
                "h3:parent_resolutions": [5, 0],
                "table:columns": cols,
            },
            f"{name}-cog": {
                "href": coghref, "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data"],
                "title": f"{title} cloud-optimized GeoTIFF (WGS84, 0.05 degrees)",
                "description": (
                    f"Global 7200 x 3600 WGS84 grid at 0.05 degrees, float32, {units}. Converted "
                    "from the Bio-ORACLE NetCDF distribution. No-data is NaN rather than a numeric "
                    "sentinel, because bathymetry reaches about -10700 metres and a -9999 sentinel "
                    "would fall inside the physically valid range of that layer."
                ),
                "raster:bands": [{
                    "name": col, "data_type": "float32", "nodata": "nan", "unit": units,
                    "statistics": {"minimum": st["cog_min"], "maximum": st["cog_max"],
                                   "mean": st["cog_mean"]},
                }],
            },
        },
    }
    return coll


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", required=True, help="JSON of per-layer measured stats")
    ap.add_argument("--out-dir", default="/tmp/stac")
    a = ap.parse_args()
    stats = json.load(open(a.stats))
    os.makedirs(a.out_dir, exist_ok=True)

    children = []
    for layer in LAYERS:
        name, prefix = layer[0], layer[1]
        if name not in stats:
            print(f"skip {name}: no stats")
            continue
        coll = build(layer, stats)
        d = os.path.join(a.out_dir, prefix, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "stac-collection.json"), "w") as f:
            json.dump(coll, f, indent=2)
        children.append({"rel": "child", "id": coll["id"],
                         "href": f"{BASE}/{prefix}/{name}/stac-collection.json",
                         "type": "application/json", "title": coll["title"]})
        print(f"wrote {prefix}/{name}/stac-collection.json")

    parent = {
        "type": "Collection", "stac_version": "1.0.0",
        "id": "bio-oracle",
        "title": "Bio-ORACLE v3.0 — Global Marine Environmental Layers",
        "description": (
            "Global marine environmental layers from Bio-ORACLE version 3.0, aggregated to H3 "
            "hexagonal cells at resolution 6. This bucket holds the 2010-decade baseline, "
            "depth-mean realm: temperature, salinity, current velocity and direction, nitrate, "
            "phosphate, silicate, dissolved oxygen, dissolved iron, primary productivity and pH, "
            "together with the static benthic terrain layers bathymetry, slope, aspect, "
            "topographic position index and terrain ruggedness index.\n\n"
            "These are the standard covariates for marine species distribution modelling. Joined "
            "on h6, they give a per-cell environmental profile that can be combined with "
            "occurrence records elsewhere in this catalog.\n\n"
            "Current direction and aspect are compass bearings and are each published as a "
            "separate sine and cosine collection, because a bearing cannot be averaged "
            "arithmetically across the 0/360 wrap. Recombine with "
            "(degrees(atan2(sin, cos)) + 360) % 360.\n\n"
            + NO_H8 + "\n\n"
            f"Cite both: {CITATION_V3} And: {CITATION_V1}"
        ),
        "license": "other",
        "keywords": ["marine", "ocean", "Bio-ORACLE", "species distribution modelling", "H3"],
        "providers": [
            {"name": "Bio-ORACLE (Ghent University, University of Algarve, VLIZ)",
             "roles": ["producer", "licensor"], "url": "https://bio-oracle.org/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": f"{BASE}/"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
            "temporal": {"interval": [["2000-01-01T00:00:00Z", "2020-12-31T23:59:59Z"]]},
        },
        "links": [
            {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": ROOT, "type": "application/json"},
            {"rel": "license", "href": "https://bio-oracle.org/downloads-to-email.php",
             "type": "text/html",
             "title": "Bio-ORACLE terms: released under the GNU General Public License"},
        ] + children,
    }
    with open(os.path.join(a.out_dir, "stac-collection.json"), "w") as f:
        json.dump(parent, f, indent=2)
    print(f"wrote bucket-level stac-collection.json with {len(children)} children")


if __name__ == "__main__":
    main()
