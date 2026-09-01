#!/usr/bin/env python3
"""Build the public-ecoregion STAC tree for the EPA Omernik ecoregion imports.

data-workflows #633.  Runs on the cluster (ghcr.io/boettiger-lab/datasets:latest),
reads the published GeoParquet + hex with DuckDB over the INTERNAL S3 endpoint, and
writes four collection JSONs plus two READMEs to an output directory:

    <bucket root>/stac-collection.json                     new parent collection
    wwf-ecoregions-2017/stac-collection.json               the pre-existing WWF collection, relocated
    epa-ecoregions-l3/stac-collection.json                 new
    epa-ecoregions-l4/stac-collection.json                 new

Every `values` enumeration and every inline CODE=Definition map is derived FROM THE
DATA, never transcribed, so `scripts/verify-stac.py`'s data-backed
`values == SELECT DISTINCT` check passes by construction.

Provenance (#417) is likewise measured, not transcribed: the job writes an `rclone lsjson
--hash` manifest of every published object and of the staged raw archives, and this script
reads sizes, checksums and modification times from it.  Pass the manifest path as argv[2]
and the access date (YYYY-MM-DD, the date the raw was pulled from EPA) as argv[3].
"""
import json
import os
import sys
import urllib.request

import duckdb

NRP = "https://s3-west.nrp-nautilus.io"
BUCKET = "public-ecoregion"
ROOT_CATALOG = f"{NRP}/public-data/stac/catalog.json"
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stac"
MANIFEST = sys.argv[2] if len(sys.argv) > 2 else "/tmp/objects.json"
ACCESS_DATE = sys.argv[3] if len(sys.argv) > 3 else None

# Publication dates read from each source's own FGDC metadata (*.shp.xml <pubdate>),
# not inferred: us_eco_l3 / us_eco_l4 = 20130416, ak_eco_l3 = 2012 (caldate 20120508).
SOURCE_PUBDATES = {
    "us_eco_l3.zip": "2013-04-16",
    "us_eco_l4.zip": "2013-04-16",
    "ak_eco_l3.zip": "2012-05-08",
}

DATASETS = {
    "epa-ecoregions-l3": {
        "level": "III",
        "title": "EPA Ecoregions of the United States, Level III (Omernik) — CONUS + Alaska",
        "extent_note": (
            "Covers the conterminous United States (1,250 polygons, from EPA's `us_eco_l3`) and "
            "Alaska (366 polygons, from EPA's `ak_eco_l3`), merged into a single layer of 1,616 "
            "polygons and distinguished by the `region` column. Hawaii, Puerto Rico and the other "
            "territories are NOT covered: the Omernik framework extends only to CONUS and Alaska. "
            "For those areas use the global WWF terrestrial ecoregions collection in this bucket."
        ),
        "sources": ["us_eco_l3.zip", "ak_eco_l3.zip"],
        "temporal_start": "2012-05-08T00:00:00Z",
    },
    "epa-ecoregions-l4": {
        "level": "IV",
        "title": "EPA Ecoregions of the United States, Level IV (Omernik) — CONUS",
        "extent_note": (
            "Covers the conterminous United States only (5,896 polygons, from EPA's `us_eco_l4`). "
            "**Alaska is absent because EPA publishes no Level IV subdivision for Alaska** — this "
            "is an upstream limit, not a processing shortcut. For Alaska at the finest available "
            "Omernik tier use the Level III collection (`epa-ecoregions-l3`), which does include "
            "Alaska. Hawaii, Puerto Rico and the territories are outside the Omernik framework "
            "entirely."
        ),
        "sources": ["us_eco_l4.zip"],
        "temporal_start": "2013-04-16T00:00:00Z",
    },
}

# ---------------------------------------------------------------- column prose

# Columns whose full value domain is enumerated as a `values` array.  For a *CODE
# column the description also gets a generated inline `code=NAME` map (built from the
# paired name column); for a *NAME column the "ecoregion name" phrasing carries it.
# Only levels with a small, genuinely flat domain are enumerated — see NA_L3CODE /
# US_L4CODE below for the compositional tiers that are deliberately not enumerated.
ENUMERATED = {
    "NA_L1CODE": ("NA_L1NAME", "North American (CEC) Level I ecoregion identifier — the coarsest "
                  "tier of the Omernik/CEC hierarchy."),
    "NA_L2CODE": ("NA_L2NAME", "North American (CEC) Level II ecoregion identifier — the second "
                  "tier, nested inside Level I."),
    "US_L3CODE": ("US_L3NAME", "United States Level III ecoregion identifier, the primary key of "
                  "the Level III framework."),
}

NAME_COLS = {
    "NA_L1NAME": "North American (CEC) Level I ecoregion name.",
    "NA_L2NAME": "North American (CEC) Level II ecoregion name.",
    "NA_L3NAME": "North American (CEC) Level III ecoregion name — the continent-wide label, which "
                 "differs from the US-specific US_L3NAME.",
    "US_L3NAME": "United States Level III ecoregion name.",
}

# ALL-CAPS vs Title-Case is genuinely inconsistent in the upstream EPA attributes, and
# it is the single most likely thing to make an agent's WHERE clause silently return
# zero rows, so it is called out on every name column.
CASING_WARNING = (
    " Spelling and letter-case are reproduced verbatim from the source: the Level I and "
    "Level II names are ALL-CAPS while the Level III and Level IV names are Title Case, so "
    "match against the enumerated values rather than assuming a casing convention."
)


def load_manifest(path):
    """rclone lsjson output -> {relative path: {Size, ModTime, Hashes}}.
    Sizes, checksums and timestamps are READ FROM THE OBJECTS, never transcribed (#417)."""
    try:
        with open(path) as f:
            return {o["Path"]: o for o in json.load(f)}
    except Exception as e:
        print(f"  WARNING: no object manifest at {path} ({e}) — provenance fields omitted")
        return {}


MANIFEST_OBJ = {}


def obj(path):
    return MANIFEST_OBJ.get(path)


def rfc3339(modtime):
    """rclone ModTime is already RFC 3339; normalise to whole seconds + Z."""
    if not modtime:
        return None
    t = modtime.replace("Z", "+00:00")
    from datetime import datetime, timezone
    return (datetime.fromisoformat(t).astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def fingerprint(path):
    """'raw/us_eco_l3.zip (28,424,315 bytes, MD5 ab..cd)' from the staged object itself."""
    o = obj(path)
    if not o:
        return f"{path} (fingerprint unavailable)"
    md5 = (o.get("Hashes") or {}).get("md5") or (o.get("Hashes") or {}).get("MD5")
    parts = [f"{o['Size']:,} bytes"]
    if md5:
        parts.append(f"MD5 {md5}")
    if o.get("ModTime"):
        parts.append(f"staged {rfc3339(o['ModTime'])}")
    return f"{path} ({', '.join(parts)})"


def q(con, sql):
    return con.execute(sql).fetchall()


def numeric_key(v):
    """Sort '1','2','10','101' numerically and '8.1.1' lexically-by-part."""
    try:
        return (0, [float(p) for p in str(v).split(".")], "")
    except ValueError:
        return (1, [], str(v))


def col_descriptions(con, table, is_l3):
    """Build the canonical per-column description/values map from the DATA."""
    cols = {}

    cols["_cng_fid"] = dict(type="int64", description=(
        "Universal per-feature row identifier synthesized by the cng-datasets converter. "
        "Row-unique and identical across the GeoParquet, PMTiles and hex assets — use it for "
        "COUNT(DISTINCT _cng_fid) feature counts and to dedup hex rows back to one row per "
        "ecoregion polygon."))

    cols["fid"] = dict(type="int64", description=(
        "Row identifier inherited from the intermediate GeoPackage written by the preprocessing "
        "step. Row-unique, but an artifact of preprocessing rather than an upstream EPA "
        "identifier — prefer _cng_fid, which is the catalog-wide convention."))

    for code_col, (name_col, lead) in ENUMERATED.items():
        rows = q(con, f"SELECT DISTINCT {code_col} AS c, {name_col} AS n FROM {table}")
        pairs = sorted(rows, key=lambda r: numeric_key(r[0]))
        inline = ", ".join(f"{c}={n}" for c, n in pairs)
        vals = sorted({r[0] for r in rows}, key=numeric_key)
        cols[code_col] = dict(type="string", values=vals, description=(
            f"{lead} {len(vals)} values in this release. Values: {inline}"))

    for name_col, lead in NAME_COLS.items():
        if name_col not in {c for c, in q(con, f"SELECT column_name FROM (DESCRIBE SELECT * FROM {table})")}:
            continue
        vals = sorted({r[0] for r in q(con, f"SELECT DISTINCT {name_col} FROM {table}")},
                      key=lambda s: str(s))
        cols[name_col] = dict(type="string", values=vals,
                              description=f"{lead} {len(vals)} distinct ecoregion names."
                                          + CASING_WARNING)

    # --- compositional tiers: deliberately NOT enumerated -------------------
    n_na_l3 = q(con, f"SELECT COUNT(DISTINCT NA_L3CODE) FROM {table}")[0][0]
    n_us_l3 = q(con, f"SELECT COUNT(DISTINCT US_L3CODE) FROM {table}")[0][0]
    cols["NA_L3CODE"] = dict(type="string", description=(
        "North American (CEC) Level III ecoregion identifier. Compositional: the parent NA_L2CODE "
        f"value, a '.', and a sequence number within that Level II unit (e.g. 8.1.1 inside Level II "
        f"8.1) — the meaning is defined by the CEC hierarchy, not by a flat enumeration. "
        f"{n_na_l3} distinct values here versus {n_us_l3} US_L3CODE values, because the US and "
        "continent-wide Level III partitions are not one-to-one. Human-readable labels are in "
        "NA_L3NAME."))

    for lvl in ("1", "2", "3", "4"):
        key = f"L{lvl}_KEY"
        if not q(con, f"SELECT COUNT(*) FROM (DESCRIBE SELECT * FROM {table}) WHERE column_name='{key}'")[0][0]:
            continue
        n_key = q(con, f"SELECT COUNT(DISTINCT {key}) FROM {table}")[0][0]
        extra = {}
        if n_key <= 30:
            # Low-cardinality enough to be a genuine enum; the values are
            # "<identifier>  <NAME>" phrases, i.e. self-describing.
            extra["values"] = sorted({r[0] for r in q(con, f"SELECT DISTINCT {key} FROM {table}")},
                                     key=numeric_key)
        cols[key] = dict(type="string", **extra, description=(
            f"Convenience label for the Level {'I' * int(lvl) if int(lvl) < 4 else 'IV'} unit, "
            "compositional: the EPA identifier concatenated with the name (e.g. "
            "'8.1.1  Eastern Great Lakes and Hudson Lowlands'). Redundant with the paired "
            "identifier and name columns; retained verbatim from the source."))

    if not is_l3:
        n_l4c = q(con, f"SELECT COUNT(DISTINCT US_L4CODE) FROM {table}")[0][0]
        n_l4n = q(con, f"SELECT COUNT(DISTINCT US_L4NAME) FROM {table}")[0][0]
        cols["US_L4CODE"] = dict(type="string", description=(
            "United States Level IV ecoregion identifier — the finest tier of the Omernik "
            "hierarchy. Compositional: the parent US_L3CODE value followed by a lowercase letter "
            f"suffix (e.g. 23a, 23b inside Level III 23); all {n_l4c} values in this release "
            "follow that construction, so it is not a flat enumerable domain. Human-readable "
            "labels are in US_L4NAME."))
        cols["US_L4NAME"] = dict(type="string", description=(
            "United States Level IV ecoregion name — the finest tier of the Omernik hierarchy. "
            f"{n_l4n} distinct names across {n_l4c} Level IV units: a descriptive name such as "
            "'Cropland' recurs under different Level III parents, so this column alone is NOT "
            "unique — use L4_KEY when a unique label is needed." + CASING_WARNING))

    if is_l3:
        rows = q(con, f"SELECT region, COUNT(*) FROM {table} GROUP BY region ORDER BY region")
        counts = {r[0]: r[1] for r in rows}
        cols["region"] = dict(type="string", values=sorted(counts), description=(
            "Which EPA source file the polygon came from, added by the preprocessing step because "
            "EPA publishes CONUS and Alaska as separate Level III products in different "
            f"projections. Values: AK=Alaska, from ak_eco_l3 ({counts.get('AK', 0)} polygons), "
            f"CONUS=Conterminous United States, from us_eco_l3 "
            f"({counts.get('CONUS', 0)} polygons)."))

    proj = ("USA Contiguous Albers Equal Area Conic (USGS version, ESRI:102039) for CONUS and "
            "NAD83 / Alaska Albers (EPSG:3338) for Alaska") if is_l3 else \
           ("USA Contiguous Albers Equal Area Conic, USGS version (ESRI:102039)")
    cols["Shape_Leng"] = dict(type="double", description=(
        "Perimeter of the source polygon in metres, as published by EPA and computed in the source "
        f"projection ({proj}). Carried through verbatim — NOT recomputed after reprojection to "
        "EPSG:4326. A per-polygon total."))
    cols["Shape_Area"] = dict(type="double", description=(
        "Area of the source polygon in square metres, as published by EPA and computed in the "
        f"source equal-area projection ({proj}). Carried through verbatim — NOT recomputed after "
        "reprojection to EPSG:4326. A per-polygon total. Note that for the merged Level III layer "
        "the two regions use different (though both equal-area) projections."
        if is_l3 else
        "Area of the source polygon in square metres, as published by EPA and computed in the "
        f"source equal-area projection ({proj}). Carried through verbatim — NOT recomputed after "
        "reprojection to EPSG:4326. A per-polygon total."))

    cols["geom"] = dict(type="geometry",
                        description="Feature geometry (GeoParquet, EPSG:4326). MultiPolygon.")
    return cols


# ------------------------------------------------------------------- assets

# Columns that are a per-polygon total and are therefore REPEATED on every hex row the
# polygon covers.  Named explicitly in the hex asset description (AGENTS.md requires the
# warning at asset level, not per column, so the #303 renderer cannot drop it).
PER_FEATURE_TOTALS = ["Shape_Area", "Shape_Leng"]

LEAN_KEYS = ("name", "type", "values")


def as_columns(cols, order):
    """Ordered list of full STAC column objects."""
    out = []
    for name in order:
        c = cols[name]
        obj = {"name": name, "type": c["type"], "description": c["description"]}
        if "values" in c:
            obj["values"] = c["values"]
        out.append(obj)
    return out


def lean_columns(cols, order):
    """PMTiles mirror: name + type + values only, prose stays canonical on the GeoParquet."""
    out = []
    for name in order:
        c = cols[name]
        obj = {"name": name, "type": c["type"]}
        if "values" in c:
            obj["values"] = c["values"]
        out.append(obj)
    return out


def build_collection(ds, meta, con, hex_stats):
    is_l3 = ds.endswith("l3")
    table = f"read_parquet('s3://{BUCKET}/{ds}.parquet')"
    cols = col_descriptions(con, table, is_l3)

    schema_order = [c for (c,) in q(con, f"SELECT column_name FROM (DESCRIBE SELECT * FROM {table})")]
    flat_order = schema_order
    hex_order = [c for c in schema_order if c != "geom"] + ["h8", "h0"]
    pmt_order = [c for c in schema_order if c != "geom"]

    cols["h8"] = dict(type="uint64", description=(
        "H3 cell identifier at resolution 8 — the native resolution of this hex asset (one row "
        "per (ecoregion polygon, h8 cell) pair). Resolution 8 is the catalog's universal join "
        "key, so this joins directly to any other hex asset carrying h8, e.g. "
        "`public-usfs/roadless-areas-2001` (native h10 with an h8 parent) via USING (h8)."))
    cols["h0"] = dict(type="int64", description=(
        "H3 cell identifier at resolution 0, used as the Hive partition key for partitioned "
        "reads. Always present so a query can prune partitions."))

    bbox_l3 = [172.4617, 24.5439, -66.9498, 71.3905]   # crosses the antimeridian: xmin > xmax
    bboxes = ([bbox_l3, [-124.7331, 24.5439, -66.9498, 49.3844], [172.4617, 51.2199, -129.9797, 71.3905]]
              if is_l3 else [[-124.7331, 24.5439, -66.9498, 49.3844]])

    n_feat, = q(con, f"SELECT COUNT(*) FROM {table}")[0]
    lvl = meta["level"]

    antimeridian_note = (
        " The Aleutian Islands place 13 polygons east of the antimeridian (longitudes 172.46°E to "
        "179.78°E), so the collection bbox is given in the STAC antimeridian form with xmin > xmax, "
        "and the hex partition set includes the dateline resolution-0 cell 576707042908045311. No "
        "single polygon straddles the antimeridian, so no geometry spans the globe."
        if is_l3 else "")

    description = (
        f"US EPA Ecoregions of the United States, Level {lvl}, from the Omernik & Griffith "
        f"framework — the US-native ecoregion standard, nested inside the North American (CEC) "
        f"Level I/II tiers. {n_feat:,} polygons. {meta['extent_note']}\n\n"
        f"Every polygon carries the FULL hierarchy as attributes (NA_L1CODE/NAME, NA_L2CODE/NAME, "
        f"US_L3CODE/NAME"
        + (", US_L4CODE/NAME" if not is_l3 else "") +
        f"), so Levels I and II require no separate dataset — group this layer by the level you "
        f"want. Distinct classes present: "
        + ", ".join(f"{n} Level {l}" for l, n in [
            ("I", q(con, f"SELECT COUNT(DISTINCT NA_L1CODE) FROM {table}")[0][0]),
            ("II", q(con, f"SELECT COUNT(DISTINCT NA_L2CODE) FROM {table}")[0][0]),
            ("III", q(con, f"SELECT COUNT(DISTINCT US_L3CODE) FROM {table}")[0][0]),
        ] + ([("IV", q(con, f"SELECT COUNT(DISTINCT US_L4CODE) FROM {table}")[0][0])] if not is_l3 else []))
        + ".\n\n"
        f"Delivered as GeoParquet for analysis, PMTiles for web mapping, and H3 hexagonal parquet "
        f"at native resolution 8 (parent resolution 0) for spatial joins and aggregation."
        f"{antimeridian_note}\n\n"
        "Reprojected from the source Albers equal-area projections to EPSG:4326 with GDAL during "
        "preprocessing; geometry is otherwise unmodified. Attribute spelling and letter-case are "
        "verbatim from EPA — note that Level I/II names are ALL-CAPS while Level III/IV names are "
        "Title Case."
    )

    if is_l3:
        description += (
            "\n\nMerge note: the two source products use disjoint Level III numbering (CONUS 1–85, "
            "Alaska 101–120), so US_L3CODE and US_L3NAME are unique across the merged layer and "
            "safe to group by without also grouping by `region`."
        )

    # Data-derived: which identifier columns have more than one spelling of the paired
    # name.  Upstream EPA inconsistencies, not processing errors — and the reason the
    # collection tells consumers to GROUP BY the identifier rather than the name.
    variants = []
    for code_col, name_col in (("NA_L2CODE", "NA_L2NAME"), ("NA_L3CODE", "NA_L3NAME"),
                               ("US_L3CODE", "US_L3NAME")):
        for code, names in q(con, f"""
                SELECT {code_col}, string_agg(DISTINCT {name_col}, ' / ')
                FROM {table} GROUP BY 1 HAVING COUNT(DISTINCT {name_col}) > 1
                ORDER BY 1"""):
            variants.append(f"{code_col} {code} → {names}")

    quirks = [
        "Group by an identifier column rather than a name column. The identifier columns are "
        "internally consistent, but a few of EPA's own names carry more than one spelling for the "
        "same unit, so grouping by the name splits that unit in two. Measured in this release:",
    ]
    quirks += [f"- {v}" for v in variants] or ["- (none in this release)"]
    quirks.append(
        "These are EPA's own spellings, preserved verbatim rather than silently normalised. "
        "Every identifier→name relationship is otherwise one-to-one.")
    if is_l3:
        quirks.append(
            "Also note 104 distinct NA_L3CODE values versus 105 US_L3CODE values: the US and "
            "continent-wide Level III partitions are not one-to-one.")
    else:
        quirks.append(
            "Also note 954 distinct US_L4NAME values across 967 Level IV units: a descriptive "
            "name recurs under different Level III parents. Use L4_KEY (or the identifier plus "
            "name) for a unique label.")
    description += "\n\n" + "\n".join(quirks)

    # Provenance (#417): the staged raw is the durable record — EPA overwrites in place and
    # has already moved these files once (the former gaftp.epa.gov paths now 404).
    src_lines = [f"- {fingerprint('raw/' + src)}, published by EPA {SOURCE_PUBDATES[src]}"
                 for src in meta["sources"]]
    description += (
        "\n\nProvenance. EPA publishes these files without a version label and overwrites them "
        "in place, and the previous download host has already stopped serving them, so the copy "
        "staged in this bucket is the durable record of what was ingested"
        + (f", retrieved {ACCESS_DATE}" if ACCESS_DATE else "") + ":\n"
        + "\n".join(src_lines) +
        "\nThe dates above are each source's own publication date, taken from its FGDC metadata. "
        "The temporal extent below reports those publication dates: an Omernik ecoregion map "
        "describes contemporary conditions and carries no observation window, and EPA issues no "
        "edition number, so the publication date is the only edition stamp available.")

    # Counting note: a region is a SET of disjoint polygons, so the row count is not the
    # region count (data-backed by scripts/audit-feature-dup.py --key US_L3CODE).
    key_col = "US_L3CODE" if is_l3 else "US_L4CODE"
    n_units, = q(con, f"SELECT COUNT(DISTINCT {key_col}) FROM {table}")[0]
    multi, = q(con, f"SELECT COUNT(*) FROM (SELECT {key_col} FROM {table} "
                    f"GROUP BY 1 HAVING COUNT(*) > 1)")[0]
    description += (
        f"\n\nCounting: one row is one polygon, not one ecoregion. The {n_feat:,} polygons "
        f"make up {n_units} Level {lvl} ecoregions, {multi} of which are split into several "
        f"separate polygons.\n\n"
        "```sql\n"
        f"-- how many ecoregions\nSELECT COUNT(DISTINCT {key_col}) FROM ...;\n"
        "-- how many polygons\nSELECT COUNT(DISTINCT _cng_fid) FROM ...;\n"
        "-- area of each ecoregion: on this flat asset every polygon contributes its own area,\n"
        "-- so this total is correct here; on the hex asset the same value repeats on every\n"
        "-- cell a polygon covers and needs the de-duplication shown on that asset\n"
        f"SELECT {key_col}, SUM(Shape_Area) FROM ... GROUP BY 1;\n"
        "```")

    hex_desc = (
        f"The Level {lvl} ecoregion map tiled onto H3 hexagonal cells at resolution 8, "
        "Hive-partitioned by the resolution 0 cell so a query can prune partitions. This is the "
        "asset to use for spatial joins, and for aggregating any other catalog layer by "
        "ecoregion.\n\n"
        "One row is one ecoregion polygon within one resolution 8 cell, so a polygon that spans "
        f"many cells appears on many rows. The two source measurements, "
        f"{' and '.join(PER_FEATURE_TOTALS)}, describe the whole polygon and are therefore "
        "repeated on every hex cell that polygon covers. Reduce to one row per polygon before "
        "totalling them, keyed on _cng_fid:\n\n"
        "```sql\n"
        "-- correct: one row per polygon, then the total\n"
        "SELECT SUM(Shape_Area) FROM (SELECT DISTINCT _cng_fid, Shape_Area FROM ...);\n"
        "-- wrong: summing over hex rows counts each polygon once per cell it covers\n"
        "```\n\n"
        "To measure extent from the hexagons themselves rather than from those source "
        "measurements, use the area method described in the H3 guide.\n\n"
        "The classification columns (US_L3CODE and US_L3NAME, and the NA_L1, NA_L2 and NA_L3 "
        "identifier and name pairs"
        + (", plus US_L4CODE and US_L4NAME" if not is_l3 else ", plus region") +
        ") are labels rather than measurements, so grouping by them is always safe. Each polygon "
        "belongs to exactly one ecoregion at each level, so counting distinct cells per ecoregion "
        "gives a valid cell count. The h8, h0 and _cng_fid columns are safe to aggregate."
    )

    assets = {
        f"{ds}-parquet": {
            "href": f"{NRP}/{BUCKET}/{ds}.parquet",
            "type": "application/x-parquet",
            "title": f"EPA Ecoregions Level {lvl} (GeoParquet)",
            "description": (
                f"Flat GeoParquet, {n_feat:,} polygons, EPSG:4326. One row per source polygon; "
                "`_cng_fid` is row-unique. This is the canonical attribute schema for the "
                "collection."),
            "roles": ["data"],
            "table:columns": as_columns(cols, flat_order),
        },
        f"{ds}-pmtiles": {
            "href": f"{NRP}/{BUCKET}/{ds}.pmtiles",
            "type": "application/vnd.pmtiles",
            "title": f"EPA Ecoregions Level {lvl} (PMTiles)",
            "description": (
                f"Vector tiles for web mapping. The MapLibre `source-layer` is `{ds}` — using any "
                "other layer name renders a blank map. Column prose lives on the "
                f"`{ds}-parquet` asset; the `values` enumerations are repeated here because they "
                "are what styling and filter expressions need."),
            "roles": ["visual"],
            "vector:layers": [ds],
            "table:columns": lean_columns(cols, pmt_order),
        },
        f"{ds}-hex": {
            "href": f"{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "title": f"EPA Ecoregions Level {lvl} (H3 hex, resolution 8)",
            "description": hex_desc,
            "roles": ["data"],
            "h3:native_resolution": 8,
            "h3:parent_resolutions": [0],
            "table:columns": as_columns(cols, hex_order),
        },
    }
    # No `raw` ASSET is published on purpose: the mirror-scope auditor keys the raw/ backup
    # exclusion on asset hrefs, so a raw asset would flip the whole bucket into the
    # mirrored-exempt list (#545). The staged archives are cited in the description with a
    # measured fingerprint instead, which is just as citable and carries no href.
    for key, rel in ((f"{ds}-parquet", f"{ds}.parquet"),
                     (f"{ds}-pmtiles", f"{ds}.pmtiles")):
        o = obj(rel)
        if o:
            assets[key]["created"] = rfc3339(o["ModTime"])
            assets[key]["file:size"] = o["Size"]
    hex_obj = sorted((k for k in MANIFEST_OBJ if k.startswith(f"{ds}/hex/")),
                     key=lambda k: MANIFEST_OBJ[k]["ModTime"])
    if hex_obj:
        assets[f"{ds}-hex"]["created"] = rfc3339(MANIFEST_OBJ[hex_obj[-1]]["ModTime"])

    return {
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
            "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        ],
        "type": "Collection",
        "id": ds,
        "title": meta["title"],
        "description": description,
        "license": "public-domain",
        "keywords": ["ecoregions", "Omernik", "EPA", "Level " + lvl, "biogeography",
                     "United States", "CONUS"] + (["Alaska"] if is_l3 else []),
        "providers": [
            {"name": "US Environmental Protection Agency (EPA), Office of Research and Development",
             "roles": ["producer", "licensor"],
             "url": "https://www.epa.gov/eco-research/ecoregions"},
            {"name": "Commission for Environmental Cooperation (CEC)",
             "roles": ["producer"],
             "url": "http://www.cec.org/north-american-environmental-atlas/terrestrial-ecoregions-level-i/"},
            {"name": "Boettiger Lab", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "extent": {
            "spatial": {"bbox": bboxes},
            # Publication dates from each source's FGDC metadata; open end because these
            # remain EPA's current Level III/IV maps.
            "temporal": {"interval": [[meta["temporal_start"], None]]},
        },
        "sci:citation": (
            "US Environmental Protection Agency, Office of Research and Development. "
            f"Level {lvl} Ecoregions of the "
            + ("Conterminous United States and Alaska" if is_l3 else "Conterminous United States")
            + ". "
            + " ".join(f"{src} published {SOURCE_PUBDATES[src]}." for src in meta["sources"])
            + (f" Retrieved {ACCESS_DATE} from "
               "https://www.epa.gov/eco-research/ecoregions-north-america and staged at "
               f"{NRP}/{BUCKET}/raw/." if ACCESS_DATE else "")),
        "sci:doi": "10.1007/BF02394200",
        "summaries": {
            "feature_count": [n_feat],
            "h3:native_resolution": [8],
            "h3:parent_resolutions": [0],
            "proj:epsg": [4326],
        },
        "created": min((a["created"] for a in assets.values() if "created" in a), default=None),
        "updated": max((a["created"] for a in assets.values() if "created" in a), default=None),
        "links": [
            {"rel": "self", "href": f"{NRP}/{BUCKET}/{ds}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT_CATALOG, "type": "application/json"},
            {"rel": "parent", "href": f"{NRP}/{BUCKET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "describedby", "href": f"{NRP}/{BUCKET}/{ds}/README.md",
             "type": "text/markdown"},
            {"rel": "license", "href": "https://edg.epa.gov/EPA_Data_License.htm",
             "type": "text/html",
             "title": "EPA data are public domain by default (17 U.S.C. § 105)"},
            {"rel": "about", "href": "https://www.epa.gov/eco-research/ecoregions",
             "type": "text/html"},
            {"rel": "source",
             "href": "https://dmap-prod-oms-edc.s3.us-east-1.amazonaws.com/ORD/Ecoregions/",
             "type": "text/html",
             "title": "EPA download host the archives were actually retrieved from"},
            {"rel": "cite-as", "href": "https://doi.org/10.1007/BF02394200", "type": "text/html",
             "title": "Omernik, J.M. (1987) Ecoregions of the conterminous United States"},
        ],
        "assets": assets,
    }


# --------------------------------------------------- WWF relocation + parent

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def relocate_wwf():
    """Return the existing WWF collection with self/parent/describedby repointed at its
    new home under wwf-ecoregions-2017/.  Idempotent: prefers the already-relocated copy
    so a re-run never picks up the new parent collection by mistake.  Asset hrefs are
    absolute and are NOT touched — no data files move."""
    new_url = f"{NRP}/{BUCKET}/wwf-ecoregions-2017/stac-collection.json"
    for url in (new_url, f"{NRP}/{BUCKET}/stac-collection.json"):
        try:
            doc = fetch_json(url)
        except Exception:
            continue
        if doc.get("id") == "wwf-ecoregions-2017":
            break
    else:
        raise SystemExit("FATAL: could not locate the WWF collection (id=wwf-ecoregions-2017) "
                         "at either the bucket root or its relocated path — refusing to guess.")

    links = [l for l in doc.get("links", [])
             if l.get("rel") not in ("self", "parent", "root")]
    doc["links"] = [
        {"rel": "self", "href": new_url, "type": "application/json"},
        {"rel": "root", "href": ROOT_CATALOG, "type": "application/json"},
        {"rel": "parent", "href": f"{NRP}/{BUCKET}/stac-collection.json",
         "type": "application/json"},
    ] + links
    return doc


def build_parent(children):
    return {
        "stac_version": "1.0.0",
        "type": "Collection",
        "id": "ecoregion",
        "title": "Ecoregions",
        "description": (
            "Terrestrial ecoregion classifications: the global WWF/Olson framework and the "
            "US-native EPA Omernik framework at Levels III and IV.\n\n"
            "Which one to use:\n"
            "- **United States (CONUS or Alaska)** — prefer the EPA Omernik collections. They are "
            "the US standard and are far finer than the global layer: 85 Level III regions in CONUS "
            "alone (1,616 polygons including Alaska) and 967 Level IV subdivisions, versus 847 WWF "
            "ecoregions for the entire planet. Both EPA collections also carry the North American "
            "(CEC) Level I and Level II tiers as attributes, so coarse groupings need no extra "
            "dataset.\n"
            "- **Anywhere else, or a global analysis** — use the WWF collection. Omernik does not "
            "extend beyond CONUS and Alaska, so Hawaii, Puerto Rico and the territories are covered "
            "only by WWF.\n"
            "- **Level IV in Alaska does not exist** — EPA publishes no Alaska Level IV. Alaska's "
            "finest Omernik tier is Level III.\n\n"
            "All three collections publish an H3 hex asset whose native resolution is 8, so they "
            "join to each other and to the rest of the catalog on `h8` directly."),
        "license": "various",
        "keywords": ["ecoregions", "biomes", "biogeography", "WWF", "EPA", "Omernik", "CEC"],
        "providers": [
            {"name": "Boettiger Lab", "roles": ["processor", "host"],
             "url": "https://github.com/boettiger-lab"},
        ],
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [["2001-01-01T00:00:00Z", None]]},
        },
        "links": [
            {"rel": "self", "href": f"{NRP}/{BUCKET}/stac-collection.json",
             "type": "application/json"},
            {"rel": "root", "href": ROOT_CATALOG, "type": "application/json"},
            {"rel": "parent", "href": ROOT_CATALOG, "type": "application/json"},
        ] + [
            {"rel": "child", "id": c["id"], "href": c["self"], "type": "application/json",
             "title": c["title"]} for c in children
        ],
    }


# ------------------------------------------------------------------- README

def build_readme(ds, coll, con):
    is_l3 = ds.endswith("l3")
    lvl = coll["title"].split("Level ")[1].split(" ")[0]
    n_feat = coll["summaries"]["feature_count"][0]
    grp = "US_L3NAME" if is_l3 else "US_L4NAME"
    src_layers = "`us_eco_l3` / `ak_eco_l3`" if is_l3 else "`us_eco_l4_no_st`"
    return f"""# {coll['title']}

{n_feat:,} polygons · EPSG:4326 · H3 native resolution 8 (parent 0) · license: **public domain**
(US federal work, 17 U.S.C. § 105 — see <https://edg.epa.gov/EPA_Data_License.htm>)

{coll['description']}

## Assets

| Asset | URL |
|---|---|
| GeoParquet | `{NRP}/{BUCKET}/{ds}.parquet` |
| PMTiles | `{NRP}/{BUCKET}/{ds}.pmtiles` |
| H3 hex (res 8) | `{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet` |

STAC: `{NRP}/{BUCKET}/{ds}/stac-collection.json`

## Web map (MapLibre GL JS)

**The `source-layer` is `{ds}`.** It is the last path segment of the dataset name, NOT the
EPA shapefile layer name ({src_layers}). Using anything else renders a blank map — this is
the single most common mistake.

```js
map.addSource('ecoregions', {{
  type: 'vector',
  url: 'pmtiles://{NRP}/{BUCKET}/{ds}.pmtiles'
}});

map.addLayer({{
  id: 'ecoregions-fill',
  type: 'fill',
  source: 'ecoregions',
  'source-layer': '{ds}',        // <-- REQUIRED: must be exactly this
  paint: {{
    'fill-color': [
      'match', ['get', 'NA_L1NAME'],
      'TUNDRA',                          '#B4D6E4',
      'NORTHERN FORESTS',                '#2E6B34',
      'EASTERN TEMPERATE FORESTS',       '#68AB5F',
      'GREAT PLAINS',                    '#DCCA8F',
      'NORTH AMERICAN DESERTS',          '#D3A96B',
      'MEDITERRANEAN CALIFORNIA',        '#C97B84',
      'NORTHWESTERN FORESTED MOUNTAINS', '#4A7D6E',
      '#CCCCCC'                          // fallback
    ],
    'fill-opacity': 0.7
  }}
}});
```

Note the Level I / Level II names are **ALL-CAPS** in the source while Level III / Level IV
names are **Title Case**. Match the values exactly as enumerated in the STAC `values` arrays.

## Query with DuckDB

```sql
INSTALL spatial; LOAD spatial;
INSTALL httpfs;  LOAD httpfs;

-- Flat GeoParquet: one row per polygon
SELECT US_L3CODE, US_L3NAME, NA_L1NAME{', region' if is_l3 else ''}
FROM read_parquet('{NRP}/{BUCKET}/{ds}.parquet')
ORDER BY CAST(US_L3CODE AS INTEGER)
LIMIT 10;

-- Roll up to Level I: the hierarchy is already on every row, no join needed
SELECT NA_L1CODE, NA_L1NAME, COUNT(*) AS polygons
FROM read_parquet('{NRP}/{BUCKET}/{ds}.parquet')
GROUP BY 1, 2 ORDER BY CAST(NA_L1CODE AS DOUBLE);
```

### H3 hex — area, and joining to other catalog layers

`h8` is the catalog's universal join key, so this layer joins straight to any other
res-8-carrying hex asset.

```sql
-- Area per Level III region from the H3 footprint (exact per cell; never a per-resolution constant)
SELECT {grp},
       ROUND(SUM(h3_cell_area(h8, 'km^2'))) AS km2
FROM (SELECT DISTINCT {grp}, h8
      FROM read_parquet('{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet'))
GROUP BY 1 ORDER BY km2 DESC LIMIT 10;

-- Inventoried Roadless Areas broken down by ecoregion
WITH ira AS (
  SELECT DISTINCT h8
  FROM read_parquet('{NRP}/public-usfs/roadless-areas-2001/hex/h0=*/data_0.parquet')
), eco AS (
  SELECT DISTINCT h8, {grp}, NA_L1NAME
  FROM read_parquet('{NRP}/{BUCKET}/{ds}/hex/h0=*/data_0.parquet')
)
SELECT e.NA_L1NAME, e.{grp},
       ROUND(SUM(h3_cell_area(i.h8, 'km^2'))) AS roadless_km2
FROM ira i JOIN eco e USING (h8)
GROUP BY 1, 2 ORDER BY roadless_km2 DESC;
```

⚠️ **Never `SUM(Shape_Area)` or `SUM(Shape_Leng)` on the hex asset.** They are per-polygon
totals repeated on every cell the polygon covers. Dedup first
(`SELECT DISTINCT _cng_fid, Shape_Area …`), or derive area from the H3 footprint as above.

## Provenance

Source: EPA Office of Research and Development, Ecoregions of North America
(<https://www.epa.gov/eco-research/ecoregions>), staged to `{NRP}/{BUCKET}/raw/`.
Reprojected from the source Albers equal-area projections to EPSG:4326 with GDAL, then
converted, tiled and hexed with [`cng-datasets`](https://github.com/boettiger-lab/datasets).
Build recipe: `catalog/ecoregion/k8s/epa-ecoregions*/` in
[boettiger-lab/data-workflows](https://github.com/boettiger-lab/data-workflows) (issue #633).

Cite the framework as Omernik, J.M. (1987) *Ecoregions of the conterminous United States*,
Annals of the Association of American Geographers 77(1):118-125, and Omernik, J.M. &
Griffith, G.E. (2014) *Ecoregions of the conterminous United States: evolution of a
hierarchical spatial framework*, Environmental Management 54(6):1249-1266.
"""


# ---------------------------------------------------------------------- main

def main():
    global MANIFEST_OBJ
    MANIFEST_OBJ = load_manifest(MANIFEST)
    print(f"  object manifest: {len(MANIFEST_OBJ)} objects")
    os.makedirs(OUTDIR, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""
        CREATE OR REPLACE SECRET s3sec (
          TYPE S3,
          KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
          SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}',
          ENDPOINT '{os.environ.get("AWS_S3_ENDPOINT", "rook-ceph-rgw-nautiluss3.rook")}',
          USE_SSL {'true' if str(os.environ.get("AWS_HTTPS", "false")).lower() == "true" else 'false'},
          URL_STYLE 'path'
        )""")

    children = []
    for ds, meta in DATASETS.items():
        coll = build_collection(ds, meta, con, None)
        d = os.path.join(OUTDIR, ds)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "stac-collection.json"), "w") as f:
            json.dump(coll, f, indent=2, ensure_ascii=False)
        with open(os.path.join(d, "README.md"), "w") as f:
            f.write(build_readme(ds, coll, con))
        children.append({"id": ds, "title": meta["title"],
                         "self": f"{NRP}/{BUCKET}/{ds}/stac-collection.json"})
        print(f"  wrote {ds}/stac-collection.json  "
              f"({len(coll['assets'])} assets, "
              f"{len(coll['assets'][ds + '-parquet']['table:columns'])} flat columns)")

    wwf = relocate_wwf()
    os.makedirs(os.path.join(OUTDIR, "wwf-ecoregions-2017"), exist_ok=True)
    with open(os.path.join(OUTDIR, "wwf-ecoregions-2017", "stac-collection.json"), "w") as f:
        json.dump(wwf, f, indent=2, ensure_ascii=False)
    print("  wrote wwf-ecoregions-2017/stac-collection.json (relocated, assets untouched)")

    children.insert(0, {"id": wwf["id"], "title": wwf.get("title", "WWF Terrestrial Ecoregions"),
                        "self": f"{NRP}/{BUCKET}/wwf-ecoregions-2017/stac-collection.json"})
    with open(os.path.join(OUTDIR, "stac-collection.json"), "w") as f:
        json.dump(build_parent(children), f, indent=2, ensure_ascii=False)
    print(f"  wrote stac-collection.json (parent, {len(children)} children)")


if __name__ == "__main__":
    main()
