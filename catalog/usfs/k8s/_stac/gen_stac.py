#!/usr/bin/env python3
"""Generate STAC collections + bucket collection + README for the four USFS
administrative / proclaimed / surface-ownership layers (issue #585).

Writes to /tmp only — this repo never contains STAC JSON or README files.
Adapted from catalog/usfs/k8s/roadless-areas-2001/gen_stac.py (#584).
"""
import json, os

BUCKET = "public-usfs"
BASE = f"https://s3-west.nrp-nautilus.io/{BUCKET}"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
EDW = "https://data.fs.usda.gov/geodata/edw/edw_resources/shp"
LICENSE_LINK = {"rel": "license", "href": "https://www.usa.gov/government-works",
                "type": "text/html", "title": "US Government work — public domain"}

REGION_DEF = ("USDA Forest Service administrative region. Values: 01=Northern, 02=Rocky Mountain, "
              "03=Southwestern, 04=Intermountain, 05=Pacific Southwest, 06=Pacific Northwest, "
              "08=Southern, 09=Eastern, 10=Alaska. There is no Region 07.")
REGIONS = ["01", "02", "03", "04", "05", "06", "08", "09", "10"]

# Shared columns. Text per column NAME must be IDENTICAL everywhere it appears
# (the renderer folds per-column text across assets, first-seen wins).
CNG = ("_cng_fid", "int64",
       "Stable per-feature identifier assigned during conversion, unique for every source polygon. "
       "Use this as the feature key.", None)
OGC = ("OGC_FID", "int64", "Sequential row identifier carried over from the source shapefile.", None)
ACRES = ("GIS_ACRES", "double",
         "Area of the source polygon in acres, as published by the Forest Service. This is a total "
         "for the whole polygon.", None)
SHP_A = ("SHAPE_AREA", "double",
         "Area of the source polygon in the publisher's own projected coordinate system. Provided "
         "for reference; use GIS_ACRES for acreage.", None)
SHP_L = ("SHAPE_LEN", "double",
         "Perimeter of the source polygon in the publisher's own projected coordinate system.", None)
GEOM = ("geom", "geometry", "Feature geometry (GeoParquet), in EPSG:4326.", None)
FORESTNAME = ("FORESTNAME", "string", "Name of the national forest or grassland.", None)
FORESTNUMB = ("FORESTNUMB", "string", "Forest number within the region. Identifies the forest inside its region rather than nationally, so the same number recurs across regions.", None)

# H3 columns — kept grain-neutral so the same text is valid on every hex asset.
H3 = [("h10", "uint64", "H3 cell identifier at resolution 10.", None),
      ("h9", "uint64", "H3 cell identifier at resolution 9.", None),
      ("h8", "uint64", "H3 cell identifier at resolution 8. This is the shared join key used "
                       "across datasets in this catalog.", None),
      ("h0", "int64", "H3 cell identifier at resolution 0, used as the partition key for "
                      "hive-partitioned reads.", None)]


def cols(entries, lean=False):
    out = []
    for name, typ, desc, values in entries:
        c = {"name": name, "type": typ}
        if not lean:
            c["description"] = desc
        if values is not None:
            c["values"] = values
        out.append(c)
    return out


def hex_note(n_features, n_rows, acres, label):
    """Per-feature duplication note. Must contain 'repeated on every ... cell'."""
    return (
        f"One row per (polygon, resolution 10 cell) pair — {n_rows:,} rows for {n_features:,} "
        f"{label}, since a polygon that covers many cells appears on many rows. Every attribute "
        f"column is therefore repeated on every cell the polygon covers, so counts and totals must "
        f"go through _cng_fid:\n\n```sql\n"
        f"-- correct: {n_features:,} polygons, {acres:,} acres\n"
        f"SELECT COUNT(DISTINCT _cng_fid) FROM read_parquet('…/hex/h0=*/data_0.parquet');\n"
        f"SELECT SUM(GIS_ACRES) FROM (SELECT DISTINCT _cng_fid, GIS_ACRES\n"
        f"                            FROM read_parquet('…/hex/h0=*/data_0.parquet'));\n"
        f"-- wrong: COUNT(*) returns {n_rows:,} cells, not polygons\n"
        f"-- wrong: SUM(GIS_ACRES) over raw rows counts each polygon once per cell\n```\n\n"
        f"For the area of a selection, prefer the H3 footprint of its distinct cells over summing "
        f"GIS_ACRES. Use this asset to join against other hex datasets in this catalog; "
        f"resolution 8 is the shared join key."
    )


OWNERSHIP_DESC = (
    "Surface ownership within the boundaries of the National Forest System, as published by the "
    "Forest Service — 117,190 parcels covering 204,298,788 acres. This is the layer that answers "
    "\"how much land does the Forest Service actually own?\"\n\n"
    "**This is ownership, not an administrative boundary, and the difference is tens of millions "
    "of acres.** The Forest Service publishes three other national layers in this catalog — "
    "administrative-forest, proclaimed-forest and ranger-district — that look similar and are "
    "commonly mistaken for ownership. They are administrative envelopes: they enclose inholdings "
    "and private, state and other-federal parcels that the Forest Service does not own. "
    "Administrative forest boundaries total 236,835,251 acres and proclaimed boundaries "
    "225,145,181 acres, against 193,174,461 acres of Forest Service surface ownership — a gap of "
    "43.7 and 32.0 million acres. Using an envelope as a denominator for \"share of Forest "
    "Service land\" understates the share by roughly a sixth.\n\n"
    "The OWNERCLASS column separates the two interests carried here:\n\n```sql\n"
    "-- National Forest System land: 193,174,461 acres\n"
    "SELECT SUM(GIS_ACRES) FROM read_parquet('" + BASE + "/nfs-surface-ownership.parquet')\n"
    "WHERE OWNERCLASS = 'USDA FOREST SERVICE';\n```\n\n"
    "The 10,993,819 acres of NON-FS parcels are retained rather than removed: they are the "
    "inholdings, and they are the reason this layer is more precise than an envelope. A further "
    "130,508 acres are unpartitioned riparian interest.\n\n"
    "The national Forest Service total agrees with an independent source in this catalog — "
    "pad-us-4-1/fee filtered to Mang_Name = 'USFS' gives 193,275,732 acres, a difference of "
    "101,271 acres or 0.05%.\n\n"
    "There is no state column. Attributing acreage to a state requires a spatial join against a "
    "state boundary layer, for example census-2024/state at resolution 8."
)

ENVELOPE_WARNING = (
    "**This is an administrative boundary, not ownership.** It encloses inholdings and private, "
    "state and other-federal parcels that the Forest Service does not own, so it is larger than "
    "the land the agency actually holds. For Forest Service ownership use nfs-surface-ownership "
    "in this catalog, which totals 193,174,461 acres. Using this layer as the denominator for a "
    "\"share of Forest Service land\" figure understates that share."
)

LAYERS = {
    "nfs-surface-ownership": dict(
        title="National Forest System Surface Ownership",
        src="S_USA.SurfaceOwnership.zip",
        description=OWNERSHIP_DESC,
        features=117190, rows=55509398, acres=204298788, label="parcels",
        bbox=[-150.008, 17.739, -64.734, 61.519],
        columns=[
            CNG, OGC,
            ("SURFACEOWN", "string", "Forest Service identifier for the surface ownership parcel.", None),
            ("CASENAME", "string", "Name of the land record case that established this parcel.", None),
            ("LOCALCASEI", "string", "Local case identifier used by the administering unit.", None),
            ("OWNERCLASS", "string",
             "Who holds the surface interest. Values: USDA FOREST SERVICE=National Forest System "
             "land owned by the Forest Service, NON-FS=land inside the boundary that the Forest "
             "Service does not own, UNPARTITIONED RIPARIAN INTEREST=riparian interest not "
             "apportioned between owners.",
             ["NON-FS", "UNPARTITIONED RIPARIAN INTEREST", "USDA FOREST SERVICE"]),
            ("STATUSMETH", "string", "How the parcel came into or left federal ownership.",
             ["Donation", "Exchange", "Grant", "Interchange", "Mining Law", "Non-Applicable",
              "Original Forest Reserve", "Public Land Law", "Purchase", "Quitclaim",
              "Reconveyance", "Sale", "Settlement", "Surplus Property", "Transfer"]),
            ("STATUS", "string", "Current ownership status of the parcel.",
             ["Acquired", "Disposed", "Non-FS, Excludes Disposals", "Reserved Public Domain",
              "Unpartitioned Riparian Interest"]),
            ("RECORDEDAC", "double", "Acreage as recorded in the land record, which may differ "
                                     "from the acreage measured from the mapped boundary.", None),
            ACRES,
            ("PILT_IND", "string", "Whether the parcel is subject to Payments in Lieu of Taxes, the federal programme that compensates local governments for untaxable federal land. Values: FS Subject to=subject to payments made by the Forest Service, State Subject to=subject to payments administered by the state, Utah Subject to=subject to the arrangement specific to Utah, No=not subject to payments in lieu of taxes.",
             ["FS Subject to", "No", "State Subject to", "Utah Subject to"]),
            ("PAYMENTTYP", "string", "Which receipts-sharing payment programme applies.",
             ["BWCA Receipts Payment", "Bankhead-Jones Title III recpt", "NF 25% receipts",
              "Not subject to receipts payments", "O and C NF", "O and C Special Act lands"]),
            ("ACTIONDATE", "date", "Date of the land record action affecting this parcel.", None),
            ("ACTIONFISC", "int32", "Federal fiscal year of the land record action.", None),
            ("ACTIONCALY", "int32", "Calendar year of the land record action.", None),
            ("COMMENTS", "string", "Free-text notes recorded with the parcel.", None),
            ("YEARPROPER", "int64", "Year the property was acquired or established.", None),
            ("PROPERTYTA", "int64", "Property tracking identifier.", None),
            ("REGION", "string", REGION_DEF, REGIONS),
            ("NFS_LANDUN", "string", "Numeric identifier of the National Forest System land unit.", None),
            ("LANDSTATUS", "string", "Land status record identifier for the parcel.", None),
            ("FISCALLAND", "string", "Fiscal classification of the land for federal property accounting. Values: GPP&E=general property, plant and equipment, Public Domain=land that has never left federal ownership, Stewardship=land held for stewardship purposes. May be empty.",
             ["GPP&E", "Public Domain", "Stewardship"]),
            ("MISSIONDEP", "string", "Whether the parcel is depended on for the agency's mission. "
                                     "May be empty.",
             ["Mission Dependent, Not Critical", "Mission-Critical", "Not Mission Dependent"]),
            ("PREDOMINAN", "string", "Predominant use of the parcel. May be empty.",
             ["All Other Land", "Housing", "Office Building Locations",
              "Research and Development", "Training Land"]),
            ("HISTORICAL", "string", "Historic-property evaluation status. May be empty.",
             ["Evaluated, Not Historic", "National Historic Landmark - NHL",
              "National Register Eligible - NRE", "National Register Listed - NRL",
              "Non-contributing element of NHL/NRL district", "Not Evaluated", "Not applicable"]),
            ("NFSLANDUNI", "string", "Name of the National Forest System land unit "
                                     "administering the parcel.", None),
            SHP_A, SHP_L,
        ]),
    "administrative-forest": dict(
        title="National Forest System Administrative Forest Boundaries",
        src="S_USA.AdministrativeForest.zip",
        description=(
            "Administrative boundaries of the national forests and grasslands as managed by the "
            "Forest Service — 112 units totalling 236,835,251 acres.\n\n" + ENVELOPE_WARNING +
            "\n\nAdministrative boundaries exceed Forest Service surface ownership by 43,660,790 "
            "acres, or 22.6%. They describe which unit administers an area, which is the right "
            "layer for questions about management responsibility and the wrong one for questions "
            "about how much land the agency owns."),
        features=112, rows=None, acres=236835251, label="administrative units",
        bbox=[-150.008, 18.034, -65.700, 61.519],
        columns=[CNG, OGC,
                 ("ADMINFORES", "string", "Forest Service identifier for the administrative unit.", None),
                 ("REGION", "string", REGION_DEF, REGIONS), FORESTNUMB,
                 ("FORESTORGC", "string", "Forest Service organisation identifier for the administrative unit, unique to each of the 112 units.", None),
                 FORESTNAME, ACRES, SHP_A, SHP_L]),
    "proclaimed-forest": dict(
        title="National Forest System Proclaimed Forest Boundaries",
        src="S_USA.ProclaimedForest.zip",
        description=(
            "Proclaimed boundaries of the national forests — the outer limits established by "
            "presidential proclamation or by Act of Congress — 154 units totalling 225,145,181 "
            "acres.\n\n" + ENVELOPE_WARNING +
            "\n\nProclaimed boundaries exceed Forest Service surface ownership by 31,970,720 "
            "acres. A proclaimed boundary records where the Forest Service is authorised to hold "
            "land, not where it does; much of the land inside one was never acquired."),
        features=154, rows=None, acres=225145181, label="proclaimed units",
        bbox=[-150.008, 18.231, -65.700, 61.519],
        columns=[CNG, OGC,
                 ("PROCLAIMED", "string", "Forest Service identifier for the proclaimed unit.", None),
                 FORESTNAME, ACRES, SHP_A, SHP_L]),
    "ranger-district": dict(
        title="National Forest System Ranger District Boundaries",
        src="S_USA.RangerDistrict.zip",
        description=(
            "Ranger district boundaries — the administrative subdivision of the national forests "
            "and grasslands — 503 districts totalling 237,098,674 acres.\n\n" + ENVELOPE_WARNING +
            "\n\nRanger districts subdivide the administrative forest boundaries, so their total "
            "tracks that layer rather than ownership, exceeding Forest Service surface ownership "
            "by 43,924,213 acres. Use this layer to attribute an area to the district office that "
            "administers it."),
        features=503, rows=None, acres=237098674, label="ranger districts",
        bbox=[-150.008, 18.034, -65.700, 61.519],
        columns=[CNG, OGC,
                 ("RANGERDIST", "string", "Forest Service identifier for the ranger district.", None),
                 ("REGION", "string", REGION_DEF, REGIONS), FORESTNUMB,
                 ("DISTRICTNU", "string", "District number within the forest.", None),
                 ("DISTRICTOR", "string", "Forest Service organisation identifier for the ranger district, unique to each of the 503 districts.", None),
                 FORESTNAME,
                 ("DISTRICTNA", "string", "Name of the ranger district.", None),
                 ACRES, SHP_A, SHP_L]),
}


def dataset_collection(ds, meta, hex_rows):
    b = meta["bbox"]
    extent = f"({b[0]}, {b[1]}, {b[2]}, {b[3]})"
    flat_cols = cols(meta["columns"]) + cols([GEOM])
    hex_cols = cols(meta["columns"]) + cols(H3)
    pm_cols = cols(meta["columns"], lean=True)
    title = meta["title"]
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": ds,
        "title": f"{title} — national",
        "description": meta["description"],
        "license": "public-domain",
        "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json"],
        "extent": {"spatial": {"bbox": [b]},
                   "temporal": {"interval": [["2025-06-22T00:00:00Z", None]]}},
        "providers": [
            {"name": "USDA Forest Service, Enterprise Data Warehouse",
             "roles": ["producer", "licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": [
            {"rel": "self", "href": f"{BASE}/{ds}/stac-collection.json", "type": "application/json"},
            {"rel": "root", "href": ROOT, "type": "application/json"},
            {"rel": "parent", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
            LICENSE_LINK,
            {"rel": "via", "href": f"{EDW}/{meta['src']}", "type": "application/zip",
             "title": "Source shapefile (Forest Service Enterprise Data Warehouse)"},
        ],
        "assets": {
            f"{ds}-parquet": {
                "href": f"{BASE}/{ds}.parquet",
                "type": "application/x-parquet",
                "title": f"{title} {extent} — GeoParquet",
                "description": (f"One row per source polygon ({meta['features']:,} rows). Use this "
                                f"asset for boundary geometry and for true distance or buffer work."),
                "roles": ["data"],
                "table:columns": flat_cols,
            },
            f"{ds}-pmtiles": {
                "href": f"{BASE}/{ds}.pmtiles",
                "type": "application/vnd.pmtiles",
                "title": f"{title} {extent} — PMTiles",
                "roles": ["data", "visual"],
                "vector:layers": [ds],
                "table:columns": pm_cols,
            },
            f"{ds}-hex": {
                "href": f"{BASE}/{ds}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "title": f"{title} {extent} — H3 Hex (resolution 10)",
                "description": hex_note(meta["features"], hex_rows, meta["acres"], meta["label"]),
                "roles": ["data"],
                "h3:native_resolution": 10,
                "h3:parent_resolutions": [9, 8, 0],
                "table:columns": hex_cols,
            },
        },
    }


BUCKET_DESC = (
    "Geospatial datasets administered by the USDA Forest Service and published from the Forest "
    "Service Enterprise Data Warehouse: the Inventoried Roadless Areas of the 2001 Roadless Area "
    "Conservation Rule, Forest Service surface ownership, and the administrative, proclaimed and "
    "ranger-district boundaries.\n\n"
    "**Choosing between the boundary layers matters more than it looks.** Only "
    "nfs-surface-ownership records what the Forest Service owns — 193,174,461 acres. The "
    "administrative, proclaimed and ranger-district layers are envelopes that also enclose "
    "inholdings and private, state and other-federal land, and they run 32 to 44 million acres "
    "larger. For any \"share of Forest Service land\" figure, the denominator is surface "
    "ownership.\n\n"
    "Forest Service activity records (FACTS) are published separately in the public-facts bucket, "
    "and Forest Service wildfire products in public-fire."
)


def bucket_collection():
    children = [("roadless-areas-2001", "Inventoried Roadless Areas (2001 Roadless Rule) — national")]
    children += [(ds, f"{m['title']} — national") for ds, m in LAYERS.items()]
    links = [
        {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": ROOT, "type": "application/json"},
        {"rel": "parent", "href": ROOT, "type": "application/json"},
        LICENSE_LINK,
    ]
    links += [{"rel": "child", "href": f"{BASE}/{ds}/stac-collection.json",
               "type": "application/json", "title": t} for ds, t in children]
    return {
        "stac_version": "1.0.0", "type": "Collection", "id": "usfs-datasets",
        "title": "USDA Forest Service (USFS) Datasets",
        "description": BUCKET_DESC,
        "license": "public-domain",
        "extent": {"spatial": {"bbox": [[-150.008, 17.739, -64.734, 61.519]]},
                   "temporal": {"interval": [["2001-01-12T00:00:00Z", None]]}},
        "providers": [
            {"name": "USDA Forest Service", "roles": ["producer", "licensor"],
             "url": "https://data.fs.usda.gov/geodata/edw/datasets.php"},
            {"name": "Boettiger Lab / cirrus", "roles": ["processor", "host"], "url": f"{BASE}/"},
        ],
        "links": links,
    }


README = """# `public-usfs` — USDA Forest Service datasets

Cloud-optimized Forest Service geospatial data published from the
[Forest Service Enterprise Data Warehouse](https://data.fs.usda.gov/geodata/edw/datasets.php).
US Government work, public domain.

| Dataset | What it is | Acres |
|---|---|---|
| `roadless-areas-2001` | Inventoried Roadless Areas of the 2001 Roadless Rule | 58,419,694 |
| `nfs-surface-ownership` | **Forest Service surface ownership** | 193,174,461 (Forest Service class) |
| `administrative-forest` | Administrative boundaries of forests and grasslands | 236,835,251 |
| `proclaimed-forest` | Proclaimed forest boundaries | 225,145,181 |
| `ranger-district` | Ranger district boundaries | 237,098,674 |

## Which boundary layer do I want?

Only `nfs-surface-ownership` records what the Forest Service **owns**. The other three are
administrative envelopes that also enclose inholdings and private, state and other-federal land,
so they run 32 to 44 million acres larger. For any "share of Forest Service land" figure, the
denominator is surface ownership.

```sql
-- National Forest System land: 193,174,461 acres
SELECT SUM(GIS_ACRES)
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-usfs/nfs-surface-ownership.parquet')
WHERE OWNERCLASS = 'USDA FOREST SERVICE';
```

There is no state column on any of these four layers. To attribute acreage to a state, join
against a state boundary layer at resolution 8 — `census-2024/state` in this catalog.

## Query with DuckDB

```sql
INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;

-- ownership by class
SELECT OWNERCLASS, COUNT(*) AS parcels, SUM(GIS_ACRES) AS acres
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-usfs/nfs-surface-ownership.parquet')
GROUP BY OWNERCLASS ORDER BY acres DESC;

-- hex: one row per (polygon, resolution 10 cell), so dedup before totalling
SELECT SUM(GIS_ACRES) FROM (
  SELECT DISTINCT _cng_fid, GIS_ACRES
  FROM read_parquet(
    'https://s3-west.nrp-nautilus.io/public-usfs/nfs-surface-ownership/hex/h0=*/data_0.parquet'));
```

## Map with MapLibre GL JS

The `source-layer` is the dataset name — `nfs-surface-ownership`, `administrative-forest`,
`proclaimed-forest`, `ranger-district`, `roadless-areas-2001`.

```js
map.addSource('nfs', {
  type: 'vector',
  url: 'pmtiles://https://s3-west.nrp-nautilus.io/public-usfs/nfs-surface-ownership.pmtiles'
});
map.addLayer({
  id: 'nfs-fill',
  type: 'fill',
  source: 'nfs',
  'source-layer': 'nfs-surface-ownership',   // = the dataset name
  paint: {
    'fill-color': [
      'match', ['get', 'OWNERCLASS'],
      'USDA FOREST SERVICE', '#2d6a4f',
      'NON-FS', '#b7791f',
      '#999999'
    ],
    'fill-opacity': 0.6
  }
});
```

## Formats

Each dataset publishes three assets: a GeoParquet (`<name>.parquet`) for geometry and
distance work, PMTiles (`<name>.pmtiles`) for web maps, and H3 hex parquet
(`<name>/hex/h0=*/data_0.parquet`) at native resolution 10 with parents 9, 8 and 0 for
spatial joins. Resolution 8 is the shared join key across this catalog.
"""


if __name__ == "__main__":
    import sys
    rows = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    os.makedirs("/tmp/usfs-stac", exist_ok=True)
    for ds, meta in LAYERS.items():
        n = rows.get(ds)
        if n is None:
            print(f"  !! no hex row count for {ds}; pass a JSON map as argv[1]")
            continue
        out = f"/tmp/usfs-stac/{ds}-stac-collection.json"
        json.dump(dataset_collection(ds, meta, n), open(out, "w"), indent=2, ensure_ascii=False)
        print("wrote", out)
    out = "/tmp/usfs-stac/bucket-stac-collection.json"
    json.dump(bucket_collection(), open(out, "w"), indent=2, ensure_ascii=False)
    print("wrote", out)
    open("/tmp/usfs-stac/README.md", "w").write(README)
    print("wrote /tmp/usfs-stac/README.md")
