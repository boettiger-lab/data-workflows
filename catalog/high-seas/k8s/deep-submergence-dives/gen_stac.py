"""Generate the STAC collection for public-high-seas/deep-submergence-dives.

Usage: gen_stac.py <source.geojson> <out.json> <raw_size_bytes> <raw_sha256>
Size and sha256 must be measured from the staged object in s3://public-high-seas/raw/.
"""
import json, sys
src, out, raw_size, raw_sha = sys.argv[1:5]
P = [f['properties'] for f in json.load(open(src))['features']]
def vals(k): return sorted({p[k] for p in P if p[k] is not None})
B = "https://s3-west.nrp-nautilus.io/public-high-seas"
N = "deep-submergence-dives"
TYPE_DEF = {"HOV": "human-occupied vehicle (crewed submersible)",
            "ROV": "remotely operated vehicle, tethered to a ship",
            "AUV": "autonomous underwater vehicle",
            "Lander": "camera lander or drop camera set on the seafloor",
            "Camera Tow": "camera sled or system towed behind a ship"}
assert set(vals("Type")) == set(TYPE_DEF)
cols = [
 {"name": "_cng_fid", "type": "int64", "description": "Row identifier assigned at conversion. One per dive record; use it for COUNT(DISTINCT) and for joining the hex back to this table."},
 {"name": "OBJECTID", "type": "int64", "description": "Record number from the source file (1 to 43,422)."},
 {"name": "Latitude", "type": "double", "description": "Latitude of the dive, decimal degrees (WGS 84), as reported by the operator. Precision varies by record: some positions are given only to the whole degree."},
 {"name": "Longitude", "type": "double", "description": "Longitude of the dive, decimal degrees (WGS 84), as reported by the operator. Precision varies by record: some positions are given only to the whole degree."},
 {"name": "Institution", "type": "string", "description": "Institution that operated the vehicle or supplied the dive record. Acronyms: WHOI=Woods Hole Oceanographic Institution, JAMSTEC=Japan Agency for Marine-Earth Science and Technology, NIWA=National Institute of Water and Atmospheric Research (New Zealand), MBARI=Monterey Bay Aquarium Research Institute, HBOI=Harbor Branch Oceanographic Institute, HURL=Hawaii Undersea Research Laboratory, IFREMER=French Research Institute for Exploitation of the Sea, OET=Ocean Exploration Trust, MARUM=Center for Marine Environmental Sciences (University of Bremen), NOAA_OE=NOAA Ocean Exploration, GEOMAR=GEOMAR Helmholtz Centre for Ocean Research Kiel, SOI=Schmidt Ocean Institute, NOC=National Oceanography Centre (UK), NMFS=NOAA National Marine Fisheries Service, CSIRO=Commonwealth Scientific and Industrial Research Organisation (Australia), NSTC Taiwan=National Science and Technology Council (Taiwan).", "values": vals("Institution")},
 {"name": "Platform", "type": "string", "description": "Name of the vehicle or camera system (for example ALVIN, Ventana, Shinkai 6500). Missing for one record."},
 {"name": "Type", "type": "string", "description": "Vehicle class. Values: " + ", ".join(f"{k}={v}" for k, v in TYPE_DEF.items()), "values": list(TYPE_DEF)},
 {"name": "Country", "type": "string", "description": "Country of the operating institution.", "values": vals("Country")},
 {"name": "Year", "type": "int64", "description": "Year of the dive (1958 to 2024)."},
 {"name": "Decade", "type": "int64", "description": "Decade of the dive, as its first year (1950 = 1950 to 1959).", "values": vals("Decade")},
 {"name": "Depth", "type": "int64", "description": "Dive depth in metres, negative downward (-200 to -10,936). Every record is 200 m or deeper."},
 {"name": "DepthZone", "type": "string", "description": "Depth band of the dive.", "values": vals("DepthZone")},
 {"name": "Geomorphology_Description", "type": "string", "description": "Seafloor geomorphic feature at the dive location (for example Canyon, Seamount, Abyssal Plains). Fan=submarine fan, a sediment deposit at the base of a slope. Missing for 10 records.", "values": vals("Geomorphology_Description")},
 {"name": "Jurisdiction", "type": "string", "description": "Whether the dive falls inside a national Exclusive Economic Zone or in areas beyond national jurisdiction. Values: EEZ=inside an Exclusive Economic Zone, High Seas=beyond national jurisdiction", "values": vals("Jurisdiction")},
 {"name": "Sovereign", "type": "string", "description": "Sovereign state of the Exclusive Economic Zone containing the dive. Empty for high-seas dives."},
 {"name": "GeoArea", "type": "string", "description": "Named marine area containing the dive, such as an Exclusive Economic Zone (for example \"Japanese Exclusive Economic Zone\") or \"High Seas\"."},
 {"name": "Basin", "type": "string", "description": "Ocean basin containing the dive. Missing for 11 records.", "values": vals("Basin")},
]
geom = {"name": "geom", "type": "geometry", "description": "Dive location as a point (WGS 84 / OGC:CRS84)."}
h = [{"name": "h8", "type": "uint64", "description": "H3 cell ID at resolution 8."},
     {"name": "h0", "type": "int64", "description": "H3 cell ID at resolution 0, used as the partition key for hive-partitioned reads."}]
lean = [{k: c[k] for k in ("name", "type", "values") if k in c} for c in cols]
n = len(P)
desc = (
 f"Locations of {n:,} deep-sea dives and camera deployments at 200 m or deeper, 1958 to 2024, "
 "by human-occupied submersibles (HOV), remotely operated vehicles (ROV), autonomous underwater vehicles (AUV), "
 "camera landers and towed cameras. Each point is one dive or deployment, with the operating institution, vehicle, year, depth, "
 "seafloor feature, and whether it fell inside an Exclusive Economic Zone or on the high seas. "
 "The dataset was compiled to estimate how much of the deep seafloor has been seen directly "
 "(Bell et al. 2025, Science Advances), and it shows that visual exploration is concentrated in a few countries' waters.\n\n"
 f"**Coverage.** Global. {sum(p['Jurisdiction']=='High Seas' for p in P):,} dives are on the high seas and "
 f"{sum(p['Jurisdiction']=='EEZ' for p in P):,} inside Exclusive Economic Zones. The compilation is not a complete census of all deep dives: "
 "it holds the records that operators shared with the authors.\n\n"
 "**Location precision.** Positions are as reported by each operator, and precision varies: some are given only to the whole degree, "
 f"and many dives share one reported position (the {n:,} records fall on 29,289 distinct points). "
 "Treat a point as the nominal dive site, not a track. In the hex asset each point is assigned to one H3 cell at resolution 8 (about 0.74 km²); dives in the same cell are kept as separate rows.\n\n"
 "**Source.** Supplied directly by the authors of Bell et al. 2025 and received 2026-10-08. "
 f"Staged raw: s3://public-high-seas/raw/DeepSubmergenceMetadata.geojson ({int(raw_size):,} bytes, sha256 {raw_sha}). "
 "No edition label is published for this version. The paper's Zenodo supplement holds an earlier table with different points and attributes; "
 "this collection is built from the supplied file only."
)
c = {
 "type": "Collection", "id": N, "stac_version": "1.0.0",
 "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                     "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
 "title": "Deep-sea dive locations (deep submergence vehicles, 1958 to 2024)",
 "description": desc,
 "license": "CC-BY-4.0",
 "keywords": ["deep sea", "submersible", "ROV", "AUV", "HOV", "exploration", "seafloor", "high seas", "ocean"],
 "sci:doi": "10.1126/sciadv.adp8602",
 "sci:citation": "Bell, K.L.C., Johannes, K.N., Kennedy, B.R.C., Poulton, S.E. (2025). How little we've seen: A visual coverage estimate of the deep seafloor. Science Advances 11(19): eadp8602. doi:10.1126/sciadv.adp8602. Dive data supplied by the authors, received 2026-10-08.",
 "providers": [
   {"name": "Ocean Discovery League", "roles": ["producer", "licensor"], "url": "https://oceandiscoveryleague.org"},
   {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"], "url": "https://github.com/boettiger-lab"}],
 "extent": {"spatial": {"bbox": [[-180.0, -78.4833, 180.0, 81.56314]]},
            "temporal": {"interval": [["1958-01-01T00:00:00Z", "2024-12-31T23:59:59Z"]]}},
 "links": [
   {"rel": "self", "href": f"{B}/{N}/stac-collection.json", "type": "application/json"},
   {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json"},
   {"rel": "parent", "href": f"{B}/stac-collection.json", "type": "application/json", "title": "High Seas & Ocean Governance Datasets"},
   {"rel": "license", "href": "https://creativecommons.org/licenses/by/4.0/", "type": "text/html", "title": "CC-BY-4.0"},
   {"rel": "cite-as", "href": "https://doi.org/10.1126/sciadv.adp8602", "type": "text/html"},
   {"rel": "about", "href": "https://doi.org/10.1126/sciadv.adp8602", "type": "text/html", "title": "Bell et al. 2025, Science Advances"},
   {"rel": "related", "href": "https://doi.org/10.5281/zenodo.13948032", "type": "text/html", "title": "Zenodo supplement to Bell et al. 2025 (licence statement)"},
   {"rel": "describedby", "href": f"{B}/{N}/README.md", "type": "text/markdown"}],
 "assets": {
   f"{N}-parquet": {"href": f"{B}/{N}.parquet", "type": "application/x-parquet", "roles": ["data"],
     "title": "Deep-sea dive locations GeoParquet",
     "description": f"{n:,} dive points in GeoParquet (WGS 84 / OGC:CRS84), one row per dive.",
     "table:columns": cols + [geom]},
   f"{N}-pmtiles": {"href": f"{B}/{N}.pmtiles", "type": "application/vnd.pmtiles", "roles": ["visual"],
     "title": "Deep-sea dive locations PMTiles",
     "description": f"Vector tiles of the dive points for web maps. MapLibre source-layer name: '{N}'.",
     "vector:layers": [N], "table:columns": lean},
   f"{N}-hex": {"href": f"{B}/{N}/hex/h0=*/data_0.parquet", "type": "application/x-parquet", "roles": ["data"],
     "title": "Deep-sea dive locations H3 hex (resolution 8)",
     "description": "Each dive point is assigned to one H3 cell at resolution 8 (about 0.74 km² per cell), hive-partitioned by h0. "
       "One row per dive, so several dives at the same site share a cell and are kept as separate rows. "
       "Count dives per cell with COUNT(DISTINCT _cng_fid). Depth and Year are per-dive values: average or filter them, but a SUM has no meaning.",
     "h3:native_resolution": 8, "h3:parent_resolutions": [0],
     "table:columns": cols + h}},
}
json.dump(c, open(out, "w"), indent=2)
