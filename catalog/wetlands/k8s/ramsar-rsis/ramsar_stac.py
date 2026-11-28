"""STAC update for the Ramsar rebuild from the 2026-11-28 RSIS download (#1074), applied to the LIVE
wetlands-ramsar collection by ramsar-rsis-publish.yaml after the staged files are copied in place.

  ramsar_stac.py <collection.json>

Counts measured on the staged build with duckdb-geo, 2026-11-28: 8,346 flat rows, 2,536 sites
(1,658 with RSIS boundaries in 7,468 parcels, 878 centroid-only), 3 boundary rows of site 2599
without geometry, hex 13,379,224 rows over 81 h0 partitions, cover_frac NULL on exactly the 878
centroid rows.
"""
import json
import sys

DESC = """Ramsar Sites of International Importance: the Ramsar Convention Secretariat's site boundaries and site points from the Ramsar Sites Information Service (RSIS), downloaded 2026-11-28. 2,536 sites: 1,658 with mapped boundaries (7,468 polygon parcels) and 878 recorded only as a point. Available as GeoParquet, PMTiles and an H3 hex at resolution 9 with `cover_frac`.

Each row is a parcel or a site point; count sites with `COUNT(DISTINCT ramsarid)`. `Area (ha)` is the officially reported site area, given for point-only sites too, and repeated on every row of a site, so read it once per `ramsarid`:

```sql
SELECT SUM("Area (ha)") FROM (SELECT DISTINCT ramsarid, "Area (ha)" FROM read_parquet('https://s3-west.nrp-nautilus.io/public-wetlands/ramsar/ramsar_wetlands.parquet'))
```

`source` says which geometry a row has: 'RSIS boundary' (a mapped parcel) or 'RSIS centroid' (the site's point, for the 878 sites RSIS has no boundary for). Every geometry is the Secretariat's own; a site without a boundary is not filled from another dataset.

Provenance: RSIS GeoServer WFS layers `ramsar_sdi:features_published` (7,468 features, 255,675,740 bytes, sha256 36ef8d03aee1193fbfea7c5ab4c9cf9a922a50fd63f36cba935147630d99ca8e) and `ramsar_sdi:features_centroid_published` (2,536 features, 880,536 bytes, sha256 7c26949976af7e04548258407697c51ce2b6b7321b2836ee64683f7d0bf178ad), fetched in pages on 2026-11-28 and kept unchanged at `ramsar/source/`. Site attributes come from the RSIS site export (2,551 sites, last publication 2025-12-04), joined on `ramsarid`; the 21 sites absent from it carry only the RSIS name, country and official area. Three boundary rows of site 2599 (Madongho Wetland) have no geometry and appear only in the flat file.

WDPA (collection `wdpa`) also records Ramsar sites, as `DESIG_ENG = 'Wetland of International Importance (Ramsar Site)'`: 2,179 sites with polygon boundaries in its June 2026 edition. This collection is the Ramsar Secretariat's site list (2,536 sites). The two share no identifier. For Ramsar sites within WDPA or protected-area statistics, use the WDPA records."""

HEX = """Resolution columns: h9 (native), h8, h0. h8 and h0 are parent keys of each h9 cell, for joins and partitioning (h0 is the partition key), not units of area.

One row per (parcel, resolution-9 cell the parcel overlaps), including cells it covers only in part, with `cover_frac`, the share of the cell's area inside the parcel (1 for a cell wholly inside it). A point-only site has one row, the cell under its point, with `cover_frac` NULL: the hex holds no area for these 878 sites, so use their `Area (ha)`.

Area covered by Ramsar sites, with overlapping parcels counted once: take `MAX(cover_frac)` per cell, then weight each cell by its area.

```sql
SELECT h9, MAX(cover_frac) AS f FROM read_parquet('s3://public-wetlands/ramsar/hex/h0=*/data_0.parquet')
WHERE cover_frac IS NOT NULL GROUP BY h9
```

Site attributes, `Area (ha)` included, repeat on every row of a site: count sites with `COUNT(DISTINCT ramsarid)` and read `Area (ha)` once per `ramsarid`."""

COLS = {
    "ramsarid": "Ramsar Site identifier (RIS ID), the site's key in the Ramsar Sites Information Service. A site with several parcels has several rows (8,346 rows for 2,536 sites), so count sites with `COUNT(DISTINCT ramsarid)`.",
    "Area (ha)": "Officially reported site area in hectares, from RSIS; given for point-only sites as well. Repeated on every row of a site and every hex cell it covers, so read it once per `ramsarid`.",
    "source": "Which geometry the row has. Values: RSIS boundary=a mapped parcel of the site, RSIS centroid=the site's point, for a site RSIS has no boundary for.",
    "h9": "H3 cell ID at resolution 9 (native): a cell the parcel overlaps, or the cell under a site's point.",
    "cover_frac": "Share of the h9 cell's area inside the parcel, from just above 0 to 1 (1 when the cell is wholly inside). NULL for a point-only site. Polygon edges are taken as straight lines in longitude and latitude, as in H3.",
    "Does the wetland extend onto the territory of one or more other countries?": "True when the wetland continues into another country (a transboundary wetland), from the RSIS site record.",
    "Ramsar Advisory Mission?": "True when the site has received a Ramsar Advisory Mission, from the RSIS site record.",
}
NEW = {"cover_frac": "float32",
       "Does the wetland extend onto the territory of one or more other countries?": "boolean",
       "Ramsar Advisory Mission?": "boolean"}
PMT_TYPE = {"float32": "Number", "boolean": "Boolean"}

path = sys.argv[1]
c = json.load(open(path))
assert c["id"] == "wetlands-ramsar", c["id"]
c["description"] = DESC
c["sci:citation"] = ("Ramsar Convention Secretariat. Ramsar Sites Information Service (RSIS) [Data set]. "
                     "https://rsis.ramsar.org/ (accessed 2026-11-28)")
d = c["table:columns"]
names = {x["name"] for x in d}
for n, t in NEW.items():
    if n not in names:
        d.append({"name": n, "type": t})
for x in d:
    if x["name"] in COLS:
        x["description"] = COLS[x["name"]]
    if x["name"] == "source":
        x["values"] = ["RSIS boundary", "RSIS centroid"]
A = c["assets"]
A["ramsar-hex"]["description"] = HEX
for key, new in (("ramsar-parquet", [n for n in NEW if n != "cover_frac"]),
                 ("ramsar-pmtiles", [n for n in NEW if n != "cover_frac"]),
                 ("ramsar-hex", list(NEW))):
    cols = A[key].get("table:columns")
    if cols is None:
        continue
    have = {x["name"] for x in cols}
    for n in new:
        if n in have:
            continue
        t = PMT_TYPE[NEW[n]] if key == "ramsar-pmtiles" else NEW[n]
        if key == "ramsar-hex":  # keep h9, h8, h0 last; cover_frac after h9
            i = next(i for i, x in enumerate(cols) if x["name"] == ("h8" if n == "cover_frac" else "h9"))
            cols.insert(i, {"name": n, "type": t})
        else:
            cols.append({"name": n, "type": t})
if "partition:file_count" in c:
    c["partition:file_count"] = 81
c["updated"] = "2026-11-28T00:00:00Z"
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("wetlands-ramsar updated")
