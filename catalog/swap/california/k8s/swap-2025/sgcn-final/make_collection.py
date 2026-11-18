"""Build the final SWAP 2025 SGCN ranges collection, its README, and the parent edit (#976).

  python3 make_collection.py ranges LIVE.json OUT.json HEX_CREATED README.md
  python3 make_collection.py parent LIVE_PARENT.json OUT.json

Values, counts and null patterns were measured on the converted GeoParquet and hex on
2026-11-18. The 183 "No Range" records share one placeholder polygon in the Pacific
(132.89-132.16 W, 32.64-33.28 N); they are kept, as upstream publishes them, and documented.
"""
import json
import sys

B = "https://s3-west.nrp-nautilus.io/public-swap/california"
D = f"{B}/swap-2025"
ITEM = "https://www.arcgis.com/home/item.html?id=ab68287bb4b2492ea39a313b52746a2b"
SVC = ("https://services2.arcgis.com/Uq9r85Potqm3MfRV/arcgis/rest/services/SGCN_Final_red_gdb/"
       "FeatureServer/0")
ACCESSED = "2026-11-18"
RAW = ("s3://public-swap/california/raw/swap-2025-sgcn-final-ranges.geojson", 45866042,
       "2316d5b390ee47d77d4e12f071c8bed86ee6d692b97fd3bd9b6afbde5b6e31d6")
RETIRED = ("sgcn-species", "sgcn-species-units")
NO_RANGE = "Range = 'No Range'"
LIST = "A comma-separated list; filter with LIKE, e.g. {}."

C = [
    ("_cng_fid", "int64", "Synthetic feature ID added during processing; one per species range. "
     "Use COUNT(DISTINCT _cng_fid) to count species."),
    ("OGC_FID", "int64", "Feature ID assigned by GDAL when the GeoJSON was converted."),
    ("OBJECTID", "int32", "Object ID in CDFW's feature service (not stable across republications)."),
    ("SWAP_Scientific", "string", "Scientific name of the Species of Greatest Conservation Need, "
     "as listed in SWAP 2025. One record per species."),
    ("SWAP_Common", "string", "Common name of the species, as listed in SWAP 2025."),
    ("Range", "string", "Whether CDFW has a range map for the species. 'No Range' records (183) "
     "carry a placeholder polygon in the Pacific Ocean (132.9-132.2 W, 32.6-33.3 N), not a range; "
     "leave them out of spatial analysis with WHERE Range <> 'No Range'.",
     ["See Range Map. [Range may be approximation. Contact species expert for most current and "
      "accurate range.]", "No Range"]),
    ("TaxGroup", "string", "Taxonomic group.",
     ["Plants", "Invertebrates", "Birds", "Mammals", "Fish", "Amphibians", "Reptiles"]),
    ("SciName", "string", "Scientific name from CDFW's species reference (matches SWAP_Scientific)."),
    ("CommonName", "string", "Common name from CDFW's species reference."),
    ("ListingStatus", "string", "Federal and state listing status combined, e.g. 'Federally "
     "Endangered, State Endangered', or 'No listing status'. "
     + LIST.format("ListingStatus LIKE '%State Endangered%'")),
    ("FedLiat", "string", "Federal Endangered Species Act listing status.",
     ["No Federal Listing Status", "Federally Endangered", "Federally Threatened",
      "Federally Proposed", "Federal Candidate For Listing"]),
    ("CalList", "string", "California Endangered Species Act or Native Plant Protection Act "
     "listing status.",
     ["No State Listing Status", "State Endangered", "State Threatened", "State Rare Plant",
      "State Candidate For Listing"]),
    ("FullyProt", "string", "Whether the species is Fully Protected under California law.",
     ["Not Fully Protected", "Fully Protected Species"]),
    ("ConsStatus", "string", "Other conservation status designations that qualified the species "
     "as an SGCN, such as 'CDFW Species of Special Concern', California Rare Plant Ranks, "
     "NatureServe ranks, USFWS Birds of Conservation Concern and State of the Birds alerts, or "
     "'No additional conservation status'. "
     + LIST.format("ConsStatus LIKE '%Species of Special Concern%'")),
    ("ClimateVuln", "string", "Whether CDFW considers the species vulnerable to climate change. "
     "Values as published: Yes=vulnerable, yes=vulnerable (one fish, lower case), No=not "
     "vulnerable, Unknown=unknown (5 animals), N/A=not applicable (535 plants), NA=not "
     "applicable (one plant). Every plant is N/A or NA.",
     ["No", "N/A", "Yes", "Unknown", "NA", "yes"]),
    ("Province_CU", "string", "SWAP provinces and conservation units where the species occurs, "
     "e.g. 'Desert Province (Colorado Desert, Mojave Desert)'; 'Province/Conservation Unit not "
     "available' for 948 records. "
     + LIST.format("Province_CU LIKE '%Mojave Desert%'")),
    ("LifeHistoryLink", "string", "Link to a species account (e.g. NatureServe Explorer). Empty "
     "for 4 records."),
    ("Shape__Area", "float64", "Area of the range polygon in square meters, as computed by the "
     "feature service in Web Mercator, which overstates true area by roughly 40-80% at "
     "California's latitudes."),
    ("Shape__Length", "float64", "Perimeter of the range polygon in meters, as computed by the "
     "feature service in Web Mercator."),
    ("geom", "geometry", "Range polygon (WGS 84)."),
    ("native_res", "int32", "H3 resolution the range was indexed at. Values: 10=range up to "
     "0.75 square degrees, about 7,400 km² (1,173 ranges); 8=larger range (263), with h10 and h9 "
     "empty.", [8, 10]),
    ("h10", "uint64", "H3 cell ID at resolution 10. Empty (null) for ranges indexed at "
     "resolution 8."),
    ("h9", "uint64", "H3 cell ID at resolution 9. Empty (null) for ranges indexed at "
     "resolution 8."),
    ("h8", "uint64", "H3 cell ID at resolution 8, set for every range; the catalog's common join "
     "resolution."),
    ("h0", "int64", "H3 cell ID at resolution 0, the partition key for hive-partitioned reads."),
]
HEX_ONLY = ("native_res", "h10", "h9", "h8", "h0")


def col(c):
    d = {"name": c[0], "type": c[1], "description": c[2]}
    if len(c) > 3:
        d["values"] = c[3]
    return d


flat = [c for c in C if c[0] not in HEX_ONLY]
parquet_cols = [{"name": c[0], "type": c[1]} for c in flat]
hex_cols = [{"name": c[0], "type": c[1]} for c in C if c[1] != "geometry"]
tile_cols = [{"name": c[0], "type": "String" if c[1] == "string" else "Number"}
             for c in flat if c[1] != "geometry"]

DESC = (
    "Ranges of California's Species of Greatest Conservation Need (SGCN) from the California "
    "Department of Fish and Wildlife's State Wildlife Action Plan 2025 (SWAP 2025): one record "
    "for each of 1,436 species across plants (536), invertebrates (359), birds (182), mammals "
    "(170), fish (99), amphibians (47) and reptiles (43). Each record carries the species' "
    "federal and state listing status, other conservation designations, climate vulnerability, "
    "SWAP provinces and conservation units, and a link to a species account. Ranges are drawn "
    "as CDFW maps them and are not clipped to the state line; marine ranges reach about 125.5 W "
    "offshore.\n\n"
    "183 species have no range map (Range = 'No Range'). CDFW gives each of them the same "
    "placeholder polygon in the Pacific Ocean, about 1,000 km off the coast (132.9-132.2 W, "
    "32.6-33.3 N); it is not a range. Leave these records out of any spatial analysis:\n\n"
    "```sql\nSELECT TaxGroup, COUNT(DISTINCT _cng_fid) AS species\nFROM hex\n"
    "WHERE h8 IN (...) AND Range <> 'No Range'\nGROUP BY TaxGroup\n```\n\n"
    "On the hex asset, ranges up to 0.75 square degrees (about 7,400 km²) are indexed at H3 "
    "resolution 10 and larger ranges at resolution 8, so h10 and h9 are empty for the 263 largest "
    "ranges while h8 is set for every range. Join and compare species at h8.\n\n"
    "This is CDFW's final SGCN release. It replaces the earlier v4 service (SWAP_SGCN_V4_gdb, "
    "422 ranges of vertebrates only), from which this collection and two species tables were "
    "built before; the species attributes are now part of each range record. CDFW publishes "
    "the layer as a live feature service with no edition label; it was last edited on "
    f"2026-11-05 and read on {ACCESSED}. Staged copy: {RAW[0]}, {RAW[1]:,} bytes, sha256 "
    f"{RAW[2]}."
)


def ranges(live, hex_created):
    c = {k: live[k] for k in ("stac_version", "type", "id")}
    c["stac_extensions"] = ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"]
    c["title"] = "California SWAP 2025 Species of Greatest Conservation Need ranges"
    c["description"] = DESC
    c["license"] = "CC-BY-4.0"
    c["keywords"] = live.get("keywords", []) + [k for k in ("SGCN", "plants", "invertebrates")
                                                if k not in live.get("keywords", [])]
    c["extent"] = {"spatial": {"bbox": [[-132.888, 32.531, -114.131, 42.02]]},
                   "temporal": {"interval": [["2025-01-01T00:00:00Z", None]]}}
    c["providers"] = [
        {"name": "California Department of Fish and Wildlife (CDFW)",
         "roles": ["producer", "licensor"], "url": ITEM},
        {"name": "Boettiger Lab", "roles": ["processor", "host"],
         "url": "https://boettigerlab.berkeley.edu"}]
    c["sci:citation"] = ("California Department of Fish and Wildlife. SWAP 2025 Species of "
                         f"Greatest Conservation Need (SGCN_Final_red_gdb) [Data set]. {ITEM} "
                         f"(accessed {ACCESSED})")
    c["sci:publications"] = [{"citation": live["sci:citation"]}]
    c["created"] = live.get("created", "2026-03-01T00:00:00Z")
    c["updated"] = "2026-11-18T00:00:00Z"
    c["table:columns"] = [col(x) for x in C]
    c["links"] = [
        {"rel": "self", "href": f"{D}/sgcn-ranges/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json",
         "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "describedby", "href": f"{D}/sgcn-ranges/README.md", "type": "text/markdown"},
        {"rel": "about", "href": ITEM, "type": "text/html",
         "title": "SGCN_Final_red_gdb (CDFW, ArcGIS item)"},
        {"rel": "via", "href": SVC, "type": "application/json",
         "title": "CDFW feature service layer read for this build"},
        {"rel": "about", "href": "https://wildlife.ca.gov/SWAP", "type": "text/html",
         "title": "California State Wildlife Action Plan (CDFW)"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/",
         "type": "text/html", "title": "CC BY 4.0 (from the item's license information)"},
        {"rel": "pmtiles", "href": f"{D}/sgcn-ranges.pmtiles", "type": "application/vnd.pmtiles",
         "title": "SGCN ranges", "pmtiles:layers": ["sgcn-ranges"]},
    ]
    a = live["assets"]
    c["assets"] = {
        "sgcn-ranges-parquet": {
            "href": f"{D}/sgcn-ranges.parquet", "type": "application/vnd.apache.parquet",
            "title": "SGCN ranges (GeoParquet)",
            "description": "One row per species with its range polygon and attributes (WGS 84).",
            "roles": ["data"], "created": "2026-11-18T03:43:15Z", "table:columns": parquet_cols},
        "sgcn-ranges-pmtiles": {
            "href": f"{D}/sgcn-ranges.pmtiles", "type": "application/vnd.pmtiles",
            "title": "SGCN ranges (PMTiles)",
            "description": "Vector tiles of the ranges with all attributes, for web maps. Source "
                           "layer sgcn-ranges.",
            "roles": ["data", "visual"], "vector:layers": ["sgcn-ranges"],
            "created": "2026-11-18T03:44:39Z", "table:columns": tile_cols},
        "sgcn-ranges-hex": {
            "href": f"{D}/sgcn-ranges/hex/h0=*/data_0.parquet",
            "type": "application/vnd.apache.parquet",
            "title": "SGCN ranges on H3 cells (resolution 10, largest ranges at 8)",
            "description": "One row per (species range, H3 cell), partitioned by h0. Ranges up to "
                           "0.75 square degrees are indexed at resolution 10 with parents 9, 8 and "
                           "0; the 263 larger ranges at resolution 8 with h10 and h9 empty "
                           "(native_res says which). h8 is set on every row, so count species per "
                           "area at h8 with COUNT(DISTINCT _cng_fid). Every attribute, including "
                           "Shape__Area and Shape__Length, is a per-range value repeated on every "
                           "cell the range covers: none is safe to SUM on the hex rows. Records "
                           "with Range = 'No Range' sit on a placeholder in the Pacific Ocean; "
                           "leave them out.",
            "roles": ["data"], "h3:native_resolution": 10, "h3:parent_resolutions": [9, 8, 0],
            "created": hex_created, "table:columns": hex_cols},
        "readme": {"href": f"{D}/sgcn-ranges/README.md", "type": "text/markdown",
                   "title": "README", "roles": ["metadata"]},
        "style-sgcn-ranges-taxonomic-group": {
            **a["style-sgcn-ranges-taxonomic-group"],
            "title": "SGCN ranges by taxonomic group",
            "description": "Species ranges coloured by taxonomic group: plants yellow, "
                           "invertebrates tan, birds orange, mammals pink, fish blue, amphibians "
                           "teal, reptiles green. Species without a range map are not drawn."},
        "thumbnail": a["thumbnail"],
    }
    return c


def parent(live):
    p = json.loads(json.dumps(live))
    p["links"] = [l for l in p["links"]
                  if not (l.get("rel") == "child"
                          and any(f"/swap-2025/{r}/" in l["href"] for r in RETIRED))]
    for l in p["links"]:
        if l.get("rel") == "child" and "/swap-2025/sgcn-ranges/" in l["href"]:
            l["title"] = "California SWAP 2025 Species of Greatest Conservation Need ranges"
    return p


README = """# California SWAP 2025 Species of Greatest Conservation Need ranges

Ranges of the 1,436 Species of Greatest Conservation Need (SGCN) in the California Department
of Fish and Wildlife's State Wildlife Action Plan 2025: plants (536), invertebrates (359), birds
(182), mammals (170), fish (99), amphibians (47) and reptiles (43). Each record carries the
species' listing status, other conservation designations, climate vulnerability, SWAP provinces
and conservation units, and a link to a species account.

183 species have no range map (`Range = 'No Range'`). CDFW gives each of them the same
placeholder polygon in the Pacific Ocean (132.9-132.2 W, 32.6-33.3 N), which is not a range.
Leave them out of spatial analysis with `WHERE Range <> 'No Range'`.

This is CDFW's final SGCN release. It replaces the v4 build (422 vertebrate ranges and two
species tables) published here before.

## Files

Base URL: `https://s3-west.nrp-nautilus.io/public-swap/california/swap-2025/`

| Format | Path | Description |
|--------|------|-------------|
| GeoParquet | `sgcn-ranges.parquet` | One row per species with its range polygon |
| PMTiles | `sgcn-ranges.pmtiles` | Vector tiles, source layer `sgcn-ranges` |
| H3 hex Parquet | `sgcn-ranges/hex/h0={cell}/data_0.parquet` | One row per (range, H3 cell) |

Ranges up to 0.75 square degrees (about 7,400 km²) are indexed at H3 resolution 10 (with
parents 9, 8, 0); the 263 larger ranges at resolution 8, with `h10` and `h9` empty. `h8` is set
for every range: join and count species at `h8`.

## MapLibre GL JS

The PMTiles source layer is `sgcn-ranges`.

```javascript
map.addSource("sgcn", {
  type: "vector",
  url: "pmtiles://https://s3-west.nrp-nautilus.io/public-swap/california/swap-2025/sgcn-ranges.pmtiles",
});
map.addLayer({
  id: "sgcn-fill",
  type: "fill",
  source: "sgcn",
  "source-layer": "sgcn-ranges",
  filter: ["!=", ["get", "Range"], "No Range"],
  paint: {
    "fill-color": ["match", ["get", "TaxGroup"],
      "Plants", "#FFD92F", "Invertebrates", "#E5C494", "Birds", "#FC8D62", "Mammals", "#E78AC3",
      "Fish", "#8DA0CB", "Amphibians", "#66C2A5", "Reptiles", "#A6D854", "#BDBDBD"],
    "fill-opacity": 0.3,
  },
});
```

## DuckDB

```sql
INSTALL spatial; LOAD spatial; INSTALL h3 FROM community; LOAD h3;

-- state-listed species by taxonomic group
SELECT TaxGroup, COUNT(*) AS species
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-swap/california/swap-2025/sgcn-ranges.parquet')
WHERE CalList <> 'No State Listing Status'
GROUP BY TaxGroup ORDER BY species DESC;

-- SGCN richness per H3 resolution 8 cell, without the placeholder records
SELECT h8, COUNT(DISTINCT _cng_fid) AS species
FROM read_parquet('https://s3-west.nrp-nautilus.io/public-swap/california/swap-2025/sgcn-ranges/hex/h0=*/data_0.parquet')
WHERE Range <> 'No Range'
GROUP BY h8 ORDER BY species DESC LIMIT 10;
```

## Columns

| Column | Type | Description |
|--------|------|-------------|
COLUMNS

## Source and licence

CDFW, `SGCN_Final_red_gdb` (https://www.arcgis.com/home/item.html?id=ab68287bb4b2492ea39a313b52746a2b),
read from its feature service on 2026-11-18. The service has no edition label; its data were last
edited on 2026-11-05. Staged copy: `s3://public-swap/california/raw/swap-2025-sgcn-final-ranges.geojson`,
45,866,042 bytes, sha256 `2316d5b390ee47d77d4e12f071c8bed86ee6d692b97fd3bd9b6afbde5b6e31d6`.

Licensed by CDFW under Creative Commons Attribution 4.0 (CC BY 4.0). Credit: California Department
of Fish and Wildlife, State Wildlife Action Plan, Science Institute.
"""


def readme():
    return README.replace("COLUMNS", "\n".join(f"| `{c[0]}` | {c[1]} | {c[2]} |" for c in C))


if __name__ == "__main__":
    live = json.load(open(sys.argv[2]))
    if sys.argv[1] == "ranges":
        json.dump(ranges(live, sys.argv[4]), open(sys.argv[3], "w"), indent=2, ensure_ascii=False)
        open(sys.argv[5], "w").write(readme())
    else:
        json.dump(parent(live), open(sys.argv[3], "w"), indent=2, ensure_ascii=False)
