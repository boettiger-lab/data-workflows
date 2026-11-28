"""Answer-first metadata fixes from the GLEN benchmark studies (#1077), applied to a LIVE collection.

  edit.py <collection.json>

Each edit is keyed by collection id and leaves everything else on the collection as it is.
Idempotent: a lead already in place is left as it is.

1. Every hex asset (one with an integer `h3:native_resolution`) gets a first line naming its
   resolution columns and saying that the coarser ones are parent keys, not units of area.
2. Collection-specific leads, column texts and corrections below. Every number was measured
   on 2026-11-28 with duckdb-geo against the published data:
   - presence hexes: features in flat vs DISTINCT _cng_fid in hex (WCB 3,915 vs 3,583; firep,
     GDE vegetation equal); GDE wetlands features under one cell = 199.2 km2 of polygon area
     carried as 1,076.2 km2 of cells.
   - PAD-US 4.1 Combined: FeatClass x Category pairs (Marine/Marine 1,739, no other Marine);
     58 State_Nm codes incl. UNKF (579 records).
   - GBIF: `issue` NULL on 0.12% of rows in one h0; 148 publisher datasets with country 'ZZ'.
   - hydrothermal vents: 304 'active, confirmed', 362 'active, inferred', 55 'inactive'.
"""
import json
import re
import sys

LEAD_MARK = "Resolution columns:"


def res_lead(a):
    n = a.get("h3:native_resolution")
    if not isinstance(n, int):
        return None
    parents = [p for p in a.get("h3:parent_resolutions", []) if p != n]
    cols = [f"h{n} (native)"] + [f"h{p}" for p in sorted(parents, reverse=True)]
    if parents:
        coarser = ", ".join(f"h{p}" for p in sorted(parents, reverse=True))
        one = len(parents) == 1
        tail = (f" {coarser} {'is the parent key' if one else 'are parent keys'} of each h{n} "
                f"cell, for joins and partitioning (h0 is the partition key), "
                f"{'not a unit' if one else 'not units'} of area.")
    else:
        tail = ""
    return f"{LEAD_MARK} {', '.join(cols)}.{tail}"


def set_lead(a, *paras):
    """Put the given paragraphs first in the asset description (no-op if already there)."""
    lead = "\n\n".join(p for p in paras if p)
    d = a.get("description", "")
    if not d.startswith(lead):
        a["description"] = lead + ("\n\n" + d if d else "")


PRESENCE = (
    "Presence only, with no coverage fraction: a feature has one row for each resolution-10 "
    "cell whose centre lies inside it. {small} So measure area on distinct h10 cells, never on "
    "h9 or h8: a coarser cell counts as covered when any one of its children is. A feature "
    "smaller than a cell is carried as a whole cell, so the hex overstates the area of small "
    "features; for a feature's own area use its area column, read once per `_cng_fid`."
)
SMALL_KEPT = "A feature that contains no cell centre gets the one cell under a point on it."
SMALL_DROPPED = ("A feature that contains no cell centre has no rows (332 of 3,915 projects); "
                 "the flat GeoParquet has every feature.")

PARENT_TXT = ("H3 cell ID at resolution {r}, the parent of the native cell. A join and partition "
              "key, not a unit of area.")

CONUS = "('AK','HI','PR','GU','VI','AS','MP','UM')"

CWHR_XWALK = (
    "| cwhr13 class | cwhr classes (whrnum) |\n|---|---|\n"
    "| 10 Agriculture | 60, 61, 66, 67, 68, 69, 70, 71, 75, 78 |\n"
    "| 20 Barren/Other | 6 |\n"
    "| 31 Conifer Forest | 11, 14, 20 Eastside Pine, 24, 27, 29, 35, 42, 44, 45, 48 Subalpine Conifer, 51, 58 |\n"
    "| 32 Conifer Woodland | 26, 40 |\n"
    "| 41 Desert Shrub | 4, 17, 18, 19 |\n"
    "| 42 Desert Woodland | 15, 25, 41 |\n"
    "| 51 Hardwood Forest | 5, 36, 37 |\n"
    "| 52 Hardwood Woodland | 8, 9 Blue Oak Woodland, 10, 55, 56, 77 |\n"
    "| 60 Herbaceous | 3, 39, 72 |\n"
    "| 70 Shrub | 1, 7, 12, 13, 30, 32, 34, 50 |\n"
    "| 80 Urban | 53 |\n"
    "| 90 Water | 21, 28, 43, 57, 79 |\n"
    "| 100 Wetland | 22, 49, 59 |"
)
CWHR_LEAD = (
    "Named habitat types such as blue oak woodland, eastside pine or subalpine conifer are `cwhr` "
    "classes (`whrnum`, about 60 types). `cwhr13` holds the 13 major groups they roll up into, "
    "for example 52 Hardwood Woodland. Each cwhr class belongs to one group:\n\n" + CWHR_XWALK
)


def presence(small):
    return {"lead": PRESENCE.format(small=small),
            "cols": {"h9": PARENT_TXT.format(r=9), "h8": PARENT_TXT.format(r=8)}}


EDITS = {
    "calfire-2025-firep": {"hex": {"firep-hex": presence(SMALL_KEPT)}},
    "gde-wetlands": {"hex": {"gde-wetlands-hex": presence(SMALL_KEPT)}},
    "gde-vegetation": {"hex": {"gde-vegetation-hex": presence(SMALL_KEPT)}},
    "wcb-approved-projects": {"hex": {"wcb-approved-projects-hex": presence(SMALL_DROPPED)}},
    "pad-us-4.1-combined": {
        "hex": {"combined-hex": {
            "lead": PRESENCE.format(small=SMALL_KEPT) + (
                "\n\nFee, Easement, Designation, Marine and Proclamation records stack on the same "
                "ground, so the protected area of any selection is its distinct h10 cells, counted "
                "once. Adding `GIS_Acres` across records counts overlapping land more than once.\n\n"
                "```sql\n-- contiguous-US land at GAP status 1 or 2: the cells, each counted once\n"
                "SELECT DISTINCT h10, h0 FROM read_parquet('s3://public-padus/padus-4-1/combined/hex/h0=*/data_0.parquet')\n"
                f"WHERE GAP_Sts IN ('1','2') AND Category <> 'Marine'\n"
                f"  AND State_Nm NOT IN {CONUS[:-1]},'UNKF')\n```"),
            "cols": {"h9": PARENT_TXT.format(r=9), "h8": PARENT_TXT.format(r=8)}}},
        "cols": {
            "State_Nm": {"append": (
                " 'UNKF' marks records with no state, mostly offshore. For the contiguous "
                f"United States use `State_Nm NOT IN {CONUS[:-1]},'UNKF')` rather than listing the "
                "48 states and DC.")},
            "Category": {"append": (
                " For marine areas, Category = 'Marine' and FeatClass = 'Marine' select the same "
                "1,739 records.")},
            "GIS_Acres": {"append": (
                " Records of different classes overlap (an easement or designation over fee land), "
                "so a sum of this column across records counts that ground more than once.")},
        },
    },
    "gbif-derived": {
        "desc_sub": [
            ("(native h10 = one ~15 m² cell per point;", "(native h10 = one cell of about 15,000 m² per point;"),
        ],
        "desc_lead": (
            "Querying the occurrence hex (`gbif-hex`): one row per occurrence; resolution columns "
            "h10 (native) down to h0. Two filters, used differently:\n\n"
            "```sql\n-- always: drop records with bad coordinates (issue can be NULL, so coalesce)\n"
            "NOT list_has_any(coalesce(issue, []), ['ZERO_COORDINATE','COORDINATE_INVALID',\n"
            "                                       'COORDINATE_OUT_OF_RANGE','COUNTRY_COORDINATE_MISMATCH'])\n"
            "-- only for maps or counts at resolution 8 or finer: keep records located to about a cell\n"
            "AND (coordinateuncertaintyinmeters IS NULL OR coordinateuncertaintyinmeters <= 1000)\n```\n\n"
            "The uncertainty gate is not a default: it removes records that are correctly placed at "
            "coarser resolutions, so leave it out of species lists and counts by country or region."),
        "cols": {
            "issue": {"description": (
                "GBIF interpretation flags (array of Darwin Core issue names); NULL when GBIF raised "
                "none. Drop records with bad coordinates with "
                "`NOT list_has_any(coalesce(issue, []), ['ZERO_COORDINATE','COORDINATE_INVALID',"
                "'COORDINATE_OUT_OF_RANGE','COUNTRY_COORDINATE_MISMATCH'])`. Without the coalesce, "
                "the rows where issue is NULL are dropped as well.")},
            "coordinateuncertaintyinmeters": {"description": (
                "Reported coordinate uncertainty in metres; NULL for many records. Gate on it only "
                "for maps or counts at resolution 8 or finer, keeping NULLs: "
                "`coordinateuncertaintyinmeters IS NULL OR coordinateuncertaintyinmeters <= 1000`.")},
            "publishing_country": {"append": (
                " 'ZZ' means the publishing organization has no registered country (148 datasets).")},
        },
    },
    "overture-divisions-countries-2026-02-18": {
        "hex": {"countries-hex": {"lead": (
            "Land only: built from the land region polygons, so it holds no territorial sea and no "
            "estuary or tidal water lying outside them. A coastal wetland or marine site can fall "
            "partly outside every country here.")}},
    },
    "cwhr": {"desc_lead": CWHR_LEAD},
    "cwhr13": {"desc_lead": CWHR_LEAD},
    "ca30x30-ecoregion": {
        "desc_lead": (
            "Columns differ between the three hex assets. `CA_Ecoregi` (the ecoregion) is only on "
            "the resolution-10 asset, `ecoregion-hex`. `land_area_km2` is only on the resolution-9 "
            "and resolution-8 assets; at resolution 10 a cell is all land, so its land area is the "
            "cell's own area. An ecoregion's cells:\n\n```sql\nSELECT DISTINCT h10, h0 FROM "
            "read_parquet('s3://public-ca30x30/ecoregion/hex/h0=*/data_0.parquet') WHERE CA_Ecoregi = 'Sierra Nevada'\n```"),
    },
    "gfw-fishing-effort": {
        "hex": {"fishing-effort-hex": {"lead": (
            "This hex is the queryable table; the COGs are display rasters. Its resolution columns "
            "are h6 and h0 only, so join a resolution-8 layer through "
            "`h3_cell_to_parent(other.h8, 6) = h6`. Each row's hours are the 0.1° fleet-monthly "
            "values apportioned to the cell by area, so a SUM is correct.")}},
    },
    "census-2024-county": {
        "cols": {
            "STATEFP": {"description": (
                "State FIPS code, two-character text ('08' is Colorado, '36' New York). The county "
                "table has no state name or postal code: to select a state by name, join "
                "census-2024-state on STATEFP.\n\n```sql\nSELECT c.NAME FROM read_parquet('s3://"
                "public-census/census-2024/county.parquet') c\nJOIN read_parquet('s3://public-census/"
                "census-2024/state.parquet') s USING (STATEFP)\nWHERE s.STUSPS = 'CO'\n```")},
        },
    },
    "census-2024-state": {
        "cols": {
            "STUSPS": {"append": (
                f" Contiguous United States (48 states and DC): `STUSPS NOT IN {CONUS}`.")},
        },
    },
    "hydrothermal-vents": {
        "cols": {
            "activity": {"description": (
                "Hydrothermal activity status. Values: 'active, confirmed' = venting seen at the "
                "seafloor (304 fields); 'active, inferred' = inferred from plume or chemical "
                "signals in the water column, not yet seen (362); 'inactive' = no current venting "
                "(55). Confirmed active vents are `activity = 'active, confirmed'`; include 'active, "
                "inferred' only when a question asks for inferred vents too."),
                "values": ["active, confirmed", "active, inferred", "inactive"]},
        },
    },
    "wdpa": {
        "hex": {"wdpa-hex": {"lead": (
            "Area covered by protected areas, with overlapping parcels counted once: take "
            "`MAX(cover_frac)` per cell, then weight each cell by its area. Adding `cover_frac` across "
            "parcels in a cell counts their overlap twice.\n\n```sql\n"
            "SELECT h9, MAX(cover_frac) AS f FROM read_parquet('s3://public-wdpa/"
            "wdpa/hex/h0=*/data_0.parquet')\nWHERE <filters> GROUP BY h9\n```\n\nFor a share of "
            "land, limit cells to land first, for example by a semi join on h8 and h0 against the "
            "Overture countries hex for the country.")}},
    },
}


def apply(c):
    cid = c["id"]
    e = EDITS.get(cid, {})
    touched = []
    for k, a in c.get("assets", {}).items():
        rl = None if cid == "swap-2025-sgcn-ranges" else res_lead(a)
        custom = e.get("hex", {}).get(k, {})
        if rl or custom:
            set_lead(a, rl, custom.get("lead"))
            touched.append(k)
    for old, new in e.get("desc_sub", []):
        for a in [c] + list(c["assets"].values()):
            if old in a.get("description", ""):
                a["description"] = a["description"].replace(old, new)
    if "desc_lead" in e and not c["description"].startswith(e["desc_lead"]):
        c["description"] = e["desc_lead"] + "\n\n" + c["description"]
    cols = dict(e.get("cols", {}))
    for k, a in e.get("hex", {}).items():
        for n, t in a.get("cols", {}).items():
            cols[n] = {"description": t}
    dictionary = c.get("table:columns", [])
    lists = [dictionary] + [a.get("table:columns", []) for a in c.get("assets", {}).values()]
    seen = set()
    for cl in lists:
        for col in cl:
            ce = cols.get(col["name"])
            if not ce or (cl is not dictionary and "description" not in col):
                continue
            if "append" in ce:
                if ce["append"].strip() not in col.get("description", ""):
                    col["description"] = col.get("description", "").rstrip() + ce["append"]
            else:
                col["description"] = ce["description"]
                if "values" in ce:
                    col["values"] = ce["values"]
            seen.add(col["name"])
    missing = set(cols) - seen
    assert not missing, f"{cid}: columns not found: {missing}"
    return touched


if __name__ == "__main__":
    path = sys.argv[1]
    c = json.load(open(path))
    t = apply(c)
    json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"{c['id']}: hex leads on {t}")
