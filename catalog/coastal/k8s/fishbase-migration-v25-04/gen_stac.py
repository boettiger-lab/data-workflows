"""Write stac-collection.json and README.md for public-coastal/fishbase-migration-v25-04 (#1072).

usage: gen_stac.py <outdir>

Counts and coded values were measured by build.yaml on 2026-11-25; sizes and SHA-256s of the
staged FishBase files come from its MANIFEST.tsv. The asset's `created` is the object's
Last-Modified.
"""
import json
import re
import sys
import urllib.request

OUT = sys.argv[1]
B = "https://s3-west.nrp-nautilus.io/public-coastal"
D = f"{B}/fishbase-migration-v25-04"
T = f"{D}/fishbase-migration.parquet"
RANGES = "https://s3-west.nrp-nautilus.io/public-iucn/iucn-ranges-2025/hex/h0=*/data_0.parquet"
HF = "https://huggingface.co/datasets/cboettig/fishbase/tree/main/data/fb/v25.04"

x = urllib.request.urlopen(f"{B}/?list-type=2&prefix=fishbase-migration-v25-04/fishbase-migration.parquet").read().decode()
CREATED = re.search(r"<LastModified>([^<]+)<", x).group(1)[:19] + "Z"

MIGRATION = {
    "amphidromous": "moves between fresh water and the sea, but not to breed (402 species)",
    "anadromous": "spawns in fresh water and grows at sea (153)",
    "catadromous": "spawns at sea and grows in fresh water (61)",
    "diadromous": "moves between fresh water and the sea, direction unspecified (1)",
    "non-migratory": "FishBase records it as not migratory (1,625)",
    "oceanodromous": "migrates within the sea (560)",
    "potamodromous": "migrates within fresh water (504)",
    "oceano-estuarine": "migrates between the sea and estuaries (2)",
    "unknown": "FishBase records the migration type as unknown (1)",
}
RL = {"EX": "Extinct", "EW": "Extinct in the Wild", "RE": "Regionally Extinct", "CR": "Critically Endangered",
      "EN": "Endangered", "VU": "Vulnerable", "NT": "Near Threatened", "LC": "Least Concern",
      "DD": "Data Deficient", "NA": "Not Applicable"}

COLS = [
    {"name": "id_no", "type": "int64",
     "description": "IUCN species id, the key that joins this table to the IUCN 2025 range maps (iucn-ranges-2025) and the IUCN taxonomy (iucn-taxonomy-2025)."},
    {"name": "sci_name", "type": "string", "description": "Scientific name, as in the IUCN 2025 range maps (identical to FishBase's genus and species, which is how the two were matched)."},
    {"name": "common_name", "type": "string", "description": "FishBase common name (FBname). Empty for 791 species that have none."},
    {"name": "family", "type": "string", "description": "Family, from FishBase."},
    {"name": "migration", "type": "string",
     "description": "Migration type from FishBase (AnaCat; a trailing question mark, marking an uncertain class, is dropped). Values: "
                    + ", ".join(f"{k}={v}" for k, v in MIGRATION.items()),
     "values": sorted(MIGRATION)},
    {"name": "fishbase_spec_code", "type": "int64", "description": "FishBase species code (SpecCode), for joining back to FishBase tables."},
    {"name": "red_list_category", "type": "string",
     "description": "IUCN Red List category, from the IUCN 2025 taxonomy (latest_category_code). Values: "
                    + ", ".join(f"{k}={v}" for k, v in RL.items()),
     "values": sorted(RL)},
]

COUNT_SQL = f"""-- diadromous fish species whose IUCN range covers a set of resolution 5 cells
SELECT COUNT(DISTINCT r.id_no) AS species
FROM read_parquet('{RANGES}') r
JOIN read_parquet('{T}') f USING (id_no)
WHERE f.migration IN ('anadromous', 'catadromous', 'amphidromous', 'diadromous')
  AND r.presence IN (1, 2) AND r.origin IN (1, 2)
  AND r.h5 IN (/* the area's resolution 5 cells */)"""

DESC = f"""The migration type FishBase records for 3,309 fish species, each matched to its IUCN species id, so that questions such as "which diadromous fishes occur here?" can be answered from the IUCN 2025 range maps with FishBase's definition of migration. Diadromous fishes, which move between fresh water and the sea, are the anadromous, catadromous, amphidromous and diadromous classes: 617 species, the set the coasts explorer counts in its Biodiversity pillar. The table also keeps the oceanodromous, potamodromous, non-migratory and other classes, so any of them is a filter on `migration`.

Use the migration type rather than IUCN's habitat systems: a species listed in both freshwater and marine systems is not necessarily migratory (bull sharks, gobies, pipefish and toadfish are), and some species FishBase classes as diadromous are listed in only one system. To count the species in an area, join on id_no to the IUCN 2025 range hexes at resolution 5, keeping extant and probably extant, native and reintroduced ranges, as the explorer does:

```sql
{COUNT_SQL}
```

Species were matched by exact scientific name, so a species whose FishBase and IUCN names differ, or that has no IUCN range map, is not in the table. FishBase lists 4,045 species with a migration type; 3,309 match an IUCN 2025 range.

Terms: the FishBase fields (common_name, family, migration, fishbase_spec_code) are CC BY-NC 4.0 (cite FishBase, non-commercial use). The IUCN fields (id_no, sci_name, red_list_category) fall under the IUCN Red List Terms of Use, which also restrict commercial use and ask that the Red List be cited.

Source: Froese, R., & Pauly, D. (Eds.) (2025), FishBase, version 04/2025, https://www.fishbase.se, read from the rfishbase snapshot on Hugging Face ({HF}): species.parquet (5,272,364 bytes, SHA-256 02bfae694deed266250e58ecebf4b10af595178944c431612e865cb37dc563e4) and families.parquet (427,298 bytes, SHA-256 3f09bbb09c1c10219277f35b4f8c42aebedd5f1b8e00ebdfdeb0e16574b0e090), accessed 2026-11-25. IUCN species ids and names from the catalog's iucn-ranges-2025 species index; Red List categories from iucn-taxonomy-2025 (IUCN 2025, The IUCN Red List of Threatened Species, version 2025-2)."""

col = {
    "stac_version": "1.1.0",
    "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                        "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
                        "https://stac-extensions.github.io/version/v1.2.0/schema.json",
                        "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"],
    "type": "Collection", "id": "fishbase-migration-v25-04",
    "title": "Fish migration types from FishBase, matched to IUCN 2025 species (v25.04)",
    "description": DESC, "license": "other", "version": "25.04",
    "keywords": ["fishes", "diadromous", "anadromous", "catadromous", "migration", "FishBase", "IUCN", "species list"],
    "sci:citation": "Froese, R., & Pauly, D. (Eds.) (2025). FishBase. World Wide Web electronic publication. https://www.fishbase.se, version 04/2025. Accessed 2026-11-25.",
    "providers": [{"name": "FishBase Consortium", "roles": ["producer", "licensor"], "url": "https://www.fishbase.se"},
                  {"name": "International Union for Conservation of Nature (IUCN)", "roles": ["producer", "licensor"],
                   "url": "https://www.iucnredlist.org"},
                  {"name": "Boettiger Lab", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
    "extent": {"spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]]},
               "temporal": {"interval": [["2025-04-01T00:00:00Z", "2025-12-31T23:59:59Z"]]}},
    "created": CREATED, "updated": CREATED,
    "table:columns": COLS,
    "links": [
        {"rel": "self", "href": f"{D}/stac-collection.json", "type": "application/json"},
        {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
        {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json"},
        {"rel": "license", "href": "https://creativecommons.org/licenses/by-nc/4.0/", "type": "text/html", "title": "CC BY-NC 4.0 (FishBase fields)"},
        {"rel": "license", "href": "https://www.iucnredlist.org/terms/terms-of-use", "type": "text/html", "title": "IUCN Red List Terms of Use (IUCN fields)"},
        {"rel": "about", "href": "https://www.fishbase.se", "type": "text/html", "title": "FishBase"},
        {"rel": "via", "href": HF, "type": "text/html", "title": "FishBase v25.04 snapshot (rfishbase) on Hugging Face"},
        {"rel": "related", "href": "https://s3-west.nrp-nautilus.io/public-iucn/iucn-ranges-2025/stac-collection.json",
         "type": "application/json", "title": "IUCN 2025 species range maps"},
        {"rel": "describedby", "href": f"{D}/README.md", "type": "text/markdown", "title": "README"},
    ],
    "assets": {"fishbase-migration-parquet": {
        "href": T, "type": "application/x-parquet", "roles": ["data"], "created": CREATED,
        "title": "Fish migration types matched to IUCN species (parquet)",
        "description": "One row per species: 3,309 fish species with a FishBase migration type and an IUCN 2025 range map, keyed by the IUCN id_no. A lookup table, with no geometry."}},
}
json.dump(col, open(f"{OUT}/stac-collection.json", "w"), indent=2, ensure_ascii=False)

README = f"""# Fish migration types from FishBase, matched to IUCN 2025 species (v25.04)

{DESC}

## Files

| File | Contents |
|---|---|
| `{T}` | One row per species (3,309) |

## DuckDB

```sql
INSTALL httpfs; LOAD httpfs;
SELECT migration, COUNT(*) AS species FROM read_parquet('{T}') GROUP BY migration ORDER BY species DESC;
```

## Columns

| Column | Description |
|---|---|
""" + "\n".join(f"| `{c['name']}` | {c['description']} |" for c in COLS) + "\n"
open(f"{OUT}/README.md", "w").write(README)
print("wrote collection,", len(COLS), "columns")
