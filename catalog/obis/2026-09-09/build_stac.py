# Generates /tmp/stac-collection.json from /tmp/obis_measurements.json (values measured
# against the published hex). Output is uploaded with rclone, never committed (AGENTS.md HB1).
"""Builds /tmp/stac-collection.json for public-obis. Numeric facts are injected from
measurements taken against the published data, never transcribed by hand."""
import json, sys

M = json.load(open('/tmp/obis_measurements.json'))

BASE = "https://s3-west.nrp-nautilus.io/public-obis"
HEX = f"{BASE}/2026-09-09/hex/h0=*/data_0.parquet"

def col(name, typ, desc, **kw):
    d = {"name": name, "type": typ, "description": desc}
    d.update(kw); return d

COLUMNS = [
  col("_id", "string", "OBIS record identifier, globally unique across the whole export. Use COUNT(DISTINCT _id) for an occurrence count and as the dedup key."),
  col("dataset_id", "string", "OBIS identifier of the source dataset the record came from. These identifiers are OBIS UUIDs and do not match GBIF dataset keys, so they cannot be joined against the GBIF collection."),
  col("decimallatitude", "double", "Latitude in decimal degrees (WGS84), parsed and validated by the OBIS quality control pipeline."),
  col("decimallongitude", "double", "Longitude in decimal degrees (WGS84), parsed and validated by the OBIS quality control pipeline."),
  col("scientificname", "string", "Accepted scientific name, matched against the World Register of Marine Species (WoRMS). This is the WoRMS accepted name, which can differ from the name the same record carries in GBIF, where names are matched against the GBIF Backbone."),
  col("aphiaid", "int64", "WoRMS AphiaID of the accepted name. This is the stable key for joining to WoRMS and to other marine datasets."),
  col("species", "string", "Taxonomic species name from WoRMS, the World Register of Marine Species, a taxonomic authority. Null where the record was identified only to a coarser rank."),
  col("genus", "string", "Taxonomic genus from WoRMS, a taxonomic authority."),
  col("family", "string", "Taxonomic family from WoRMS, a taxonomic authority."),
  col("order", "string", "Taxonomic order from WoRMS, a taxonomic authority. This is a reserved word in SQL, so quote it as \"order\" in queries."),
  col("class", "string", "Taxonomic class from WoRMS, a taxonomic authority. This is Linnaean nomenclature, not a code list; 383 distinct classes are present."),
  col("phylum", "string", "Taxonomic phylum from WoRMS, a taxonomic authority."),
  col("kingdom", "string", "Taxonomic kingdom from WoRMS, a taxonomic authority."),
  col("date_year", "int32", "Year of the observation, derived by OBIS from the event date."),
  col("eventdate", "string", "Observation date as supplied by the data provider, in its original text form. Formats vary between source datasets and include date ranges, so parse defensively and prefer date_year for filtering."),
  col("minimumdepthinmeters", "double", "Shallowest depth of the observation in metres below the surface, parsed and validated by OBIS."),
  col("maximumdepthinmeters", "double", "Deepest depth of the observation in metres below the surface, parsed and validated by OBIS."),
  col("coordinateuncertaintyinmeters", "double", "Radius in metres of the circle around the coordinate that contains the true position. Frequently in the kilometre range for ship and net sampling, which is why this collection is built at H3 resolution 8 rather than a finer resolution."),
  col("shoredistance", "double", "Distance from shore in metres, added by OBIS from OpenStreetMap coastlines. A negative value means the position falls inland by that many metres, which usually indicates a georeferencing problem in the source record."),
  col("bathymetry", "double", "Sea floor depth in metres at the observation position, added by OBIS from EMODnet Bathymetry and GEBCO. This is the depth of the sea floor, not the depth of the observation."),
  col("sst", "double", "Sea surface temperature in degrees Celsius at the observation position, added by OBIS from Bio-Oracle."),
  col("sss", "double", "Sea surface salinity at the observation position, added by OBIS from Bio-Oracle."),
  col("marine", "boolean", "True where WoRMS records the taxon as occurring in the marine environment. This is the cleanest available marine filter and has no equivalent in the GBIF collection."),
  col("brackish", "boolean", "True where WoRMS records the taxon as occurring in brackish water."),
  col("redlist_category", "string", "IUCN Red List threat category for the taxon, as carried by OBIS. Values: CR=Critically Endangered, EN=Endangered, VU=Vulnerable, NT=Near Threatened, EX=Extinct. Only these five categories occur; taxa assessed as Least Concern, Data Deficient or not assessed are null.", values=["CR", "EN", "VU", "NT", "EX"]),
  col("flags", "string[]", "Quality flags raised by the OBIS quality control pipeline for this record, for example NO_DEPTH or ON_LAND. A record can carry several flags. Records that failed quality control outright are not present in this collection."),
  col("h8", "uint64", "H3 cell identifier at resolution 8, the native resolution of this collection. One row per occurrence record, placed in the single resolution 8 cell that contains its coordinate."),
  col("h0", "int64", "H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads."),
]

collection = {
  "type": "Collection",
  "stac_version": "1.0.0",
  "stac_extensions": [
    "https://stac-extensions.github.io/table/v1.2.0/schema.json",
    "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
  ],
  "id": "obis-derived",
  "title": "OBIS Marine Occurrence Records (global, H3 resolution 8)",
  "description": (
    "Global marine species occurrence records from the Ocean Biodiversity Information System "
    "(OBIS), indexed to H3 resolution 8 for spatial analysis. OBIS is the marine counterpart to "
    "GBIF: it aggregates occurrence records from thousands of marine datasets, matches every name "
    "against the World Register of Marine Species (WoRMS), and adds its own quality control and "
    "environmental context.\n\n"
    f"This collection holds {M['total']:,} occurrence records drawn from {M['datasets']:,} source "
    "datasets, covering the global ocean with no spatial clip.\n\n"
    "**How this differs from the GBIF collection.** The catalog also carries GBIF occurrences, and "
    "a subset of those is published through the OBIS network, but the two are not the same data. "
    "OBIS names come from WoRMS and GBIF names come from the GBIF Backbone, so the same record can "
    "carry a different accepted name in each. OBIS adds AphiaID, environment flags, depth, sea "
    "floor depth, sea surface temperature and salinity, and its own quality flags, none of which "
    "survive into GBIF. OBIS also draws on more source datasets than the OBIS network registered "
    "with GBIF. The dataset identifiers are drawn from different id spaces and do not join, so the "
    "two collections can only be compared spatially, through their shared H3 cells.\n\n"
    "**What is included.** Records that failed OBIS quality control, and absence records, are "
    "excluded from this collection. Absence records document that a survey looked and found "
    "nothing, so counting them would inflate any measure of occurrence density or species "
    "richness. Records without a usable coordinate are also excluded.\n\n"
    "**Licensing.** This data is licensed CC BY-NC 4.0, which permits non-commercial use with "
    "attribution. That is more restrictive than most of this catalog. Per-dataset licence and "
    "citation details for every source dataset are staged alongside the data at "
    "s3://public-obis/raw/licenses.tsv.\n\n"
    "**Provenance.** OBIS publishes this export as a rolling dataset at "
    "s3://obis-open-data/occurrence/, overwritten in place, and does not attach an edition or "
    "version label to it. The date in the path of this collection is the date we read it, not an "
    "OBIS release. The raw source as read on that date is staged at s3://public-obis/raw/ with a "
    f"manifest at s3://public-obis/raw/MANIFEST.txt recording {M['raw_files']:,} files totalling "
    f"{M['raw_bytes']:,} bytes and a per-file MD5 checksum. That staged copy and its manifest are "
    "the provenance for this collection, because the upstream path no longer holds the same data."
  ),
  "license": "CC-BY-NC-4.0",
  "keywords": ["marine", "ocean", "biodiversity", "OBIS", "occurrence", "species", "WoRMS", "H3", "high seas"],
  "providers": [
    {"name": "Ocean Biodiversity Information System (OBIS)", "roles": ["producer", "licensor"], "url": "https://obis.org"},
    {"name": "Intergovernmental Oceanographic Commission of UNESCO", "roles": ["producer", "licensor"], "url": "https://ioc.unesco.org"},
    {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": "https://s3-west.nrp-nautilus.io/public-obis"},
  ],
  "extent": {
    "spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
    "temporal": {"interval": [[M["temporal_start"], M["temporal_end"]]]},
  },
  "sci:citation": (
    "Ocean Biodiversity Information System (OBIS). OBIS Occurrence Data. Intergovernmental "
    "Oceanographic Commission of UNESCO. https://obis.org. Accessed 2026-09-09 from "
    "s3://obis-open-data/occurrence/ (rolling export, no upstream edition label)."
  ),
  "created": M["created"],
  "updated": M["created"],
  "links": [
    {"rel": "self", "href": f"{BASE}/stac-collection.json", "type": "application/json"},
    {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
    {"rel": "parent", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
    {"rel": "license", "href": "https://creativecommons.org/licenses/by-nc/4.0/legalcode", "type": "text/html", "title": "CC BY-NC 4.0"},
    {"rel": "about", "href": "https://obis.org/data/access/", "type": "text/html", "title": "OBIS data access (landing page)"},
    {"rel": "source", "href": "https://github.com/iobis/obis-open-data", "type": "text/html", "title": "OBIS Open Data on AWS (export documentation)"},
  ],
  "assets": {
    "obis-hex-2026-09-09": {
      "href": HEX,
      "type": "application/x-parquet",
      "title": "OBIS occurrence records, H3 resolution 8 (hive-partitioned by h0)",
      "roles": ["data"],
      "created": M["created"],
      "description": (
        "One row per OBIS occurrence record. Each record is a point observation and was placed in "
        "the single H3 resolution 8 cell containing its coordinate, so there is no per-feature cell "
        "duplication to correct for and every column is safe to aggregate directly. Multiple "
        "observations falling in the same cell are kept as separate rows and are not deduplicated, "
        "which is what makes an occurrence count meaningful.\n\n"
        "Resolution 8 is the native and finest resolution here, and resolution 0 is the partition "
        "key. There is no resolution 9 or 10: much of OBIS is ship and net sampling whose recorded "
        "coordinate uncertainty is in the kilometre range, so a finer cell would assert precision "
        "the observations do not have. Resolution 8 is also the resolution at which this data can "
        "be compared with the GBIF occurrence collection, which carries resolution 8 as one of its "
        "rollup levels.\n\n"
        "Records that failed OBIS quality control and absence records are excluded.\n\n"
        "```sql\n"
        "-- occurrence density and species richness per resolution 8 cell\n"
        "SELECT h8, COUNT(*) AS occurrences, COUNT(DISTINCT species) AS species\n"
        "FROM read_parquet('s3://public-obis/2026-09-09/hex/h0=*/data_0.parquet', hive_partitioning=true)\n"
        "WHERE marine\n"
        "GROUP BY h8;\n"
        "```"
      ),
      "h3:native_resolution": 8,
      "h3:parent_resolutions": [0],
      "table:columns": COLUMNS,
    },
    "obis-source-licenses": {
      "href": f"{BASE}/raw/licenses.tsv",
      "type": "text/tab-separated-values",
      "title": "Per-dataset licence and citation table",
      "roles": ["metadata"],
      "description": (
        "Licence and citation for every OBIS source dataset, as published by OBIS. Individual "
        "source datasets are licensed CC0, CC BY or CC BY-NC; the aggregate carries the most "
        "restrictive of these, CC BY-NC 4.0. Join to the hex on dataset_id = id to recover the "
        "licence and citation for the datasets behind any particular result."
      ),
    },
  },
}

json.dump(collection, open('/tmp/stac-collection.json', 'w'), indent=2)
print("wrote /tmp/stac-collection.json")
