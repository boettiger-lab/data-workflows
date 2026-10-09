import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vals import ACT_CODES
ACTIVITY_VALUES = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "activity_values.txt")).read().split("~")

B = "https://s3-west.nrp-nautilus.io/public-fire"
D = "twig-treatment-index-2026-08"

# ---- shared per-column text. IDENTICAL on the flat GeoParquet and the hex (mcp-data-server#303
# folds per-column descriptions across assets by NAME, first-seen wins, so any divergence is
# silently dropped). Grain and hex-only caveats live in the hex asset description instead.
COLS = [
 {"name":"_cng_fid","type":"int64","description":"Synthetic per-feature identifier assigned during conversion, unique across the dataset. Use it to count or de-duplicate features."},
 {"name":"unique_id","type":"string","description":"TWIG's own identifier for the treatment record, unique across the dataset. Built from the source system's key: the event or activity number for FACTS records, and the NFPORS identifier joined to the treatment identifier for NFPORS records."},
 {"name":"objectid","type":"int32","description":"Row identifier assigned by the publisher's feature service at export time. Stable only within this edition; use unique_id to refer to a treatment across editions."},
 {"name":"fid","type":"int64","description":"Row number carried over from the GeoPackage used to stage this dataset. It duplicates objectid and has no meaning upstream."},
 {"name":"name","type":"string","description":"Human-readable name for the treatment, entered by staff in the source system. Names are optional, are not unique, and may contain spelling errors, so they suit map labels rather than joins. Ten records retain trailing spaces."},
 {"name":"state","type":"string","description":"Two-letter state or territory code recorded in the source system. This is an attribute, not a value derived from the polygon, so it can disagree with where the polygon actually falls; records where the publisher detected such a conflict carry SPATIAL in the error column."},
 {"name":"acres","type":"double","description":"Area of the treatment polygon in acres, computed by the source system on a curved earth. This is the area measure to use; see SHAPE__Area for why the square-degree column is not."},
 {"name":"treatment_date","type":"date","description":"Completion date for work that has happened, or the planned date for work that has not. This is the most complete date in the dataset and the one to use for time series. Values are dirty: they run from 1202-02-10 to 2926-10-03, so any analysis needs an explicit sane-date window."},
 {"name":"date_current","type":"date","description":"Date the record was last edited in its source system. Ranges from 2007-09-06 to 2026-06-29, with 1,912 records carrying no value. This tracks record-keeping activity, not fieldwork."},
 {"name":"identifier_database","type":"string","description":"Source system the record came from. Values: FACTS Common Attributes=US Forest Service activity records beyond the hazardous-fuels subset, FACTS Hazardous Fuels=US Forest Service hazardous fuel treatments, NFPORS=National Fire Plan Operations and Reporting System (Department of the Interior), NASF=National Association of State Foresters, IFPRS=Interagency Fuel Treatment Decision Support System","values":["FACTS Common Attributes","FACTS Hazardous Fuels","NFPORS","NASF","IFPRS"]},
 {"name":"status","type":"string","description":"Whether the treatment has been carried out. Values: Completed=work finished, Planned=scheduled but not yet done, Started=under way, Other=anything else. Completed and Planned must be separated before any tabulation of accomplished work.","values":["Completed","Planned","Started","Other"]},
 {"name":"twig_category","type":"string","description":"Broad class of treatment, assigned by the publisher and the only classification that applies to records from every source system. Values: Mechanical=hand or machine work such as thinning, Planned Ignition=prescribed and pile burning, Unplanned Ignition=wildfire managed for resource benefit, Chemical=herbicide and similar, Biological=grazing and biological control, Other=anything else","values":["Mechanical","Planned Ignition","Unplanned Ignition","Chemical","Biological","Other"]},
 {"name":"category","type":"string","description":"Treatment class as recorded in the source system, which is less consistent than twig_category and is absent for 736,822 records. Values: Mechanical=hand or machine work, Fire=fire of any kind, Prescribed Burn=planned burning, Planned Ignition=planned burning, Unplanned Ignition=wildfire managed for benefit, Chemical=herbicide and similar, Biological=grazing and biological control, Planting=tree or seed planting, Reforestation=re-establishing forest cover, Invasive Species=invasive plant work, Insect and Disease Control=pest and pathogen work, Preparation for Treatment=site preparation, Wildlife Habitat=habitat work, Compliance=compliance activity, Asset Repair and Replacement=facility work, Other=anything else, N/A=not applicable. One record carries an empty string rather than a value","values":["Mechanical","Fire","Other","Prescribed Burn","Planned Ignition","Chemical","Biological","Planting","N/A","Unplanned Ignition","Preparation for Treatment","Invasive Species","Insect and Disease Control","Reforestation","Asset Repair and Replacement","Compliance","Wildlife Habitat",""]},
 {"name":"type","type":"string","description":"Finer treatment type from the source system, such as Broadcast Burn or Biomass Removal. Entered without a controlled vocabulary, so it contains 215 distinct values including near-duplicates and misspellings."},
 {"name":"activity","type":"string","description":"Human-readable name of the Forest Service activity, filled in automatically from activity_code, so it is the definition of that code on the same row. Present only for records from the two FACTS systems.","values":ACTIVITY_VALUES},
 {"name":"activity_code","type":"string","description":"Four-digit Forest Service activity code. The name of each individual code is carried on the same row in the activity column, so no separate lookup is needed. The leading digit groups them: 1000=fire, 2000=range, 3000=cultural resources and recreation, 4000=timber and silviculture, 5000=soil, air and watershed, 6000=wildlife, 7000=engineering, 8000=minerals, 9000=administrative. Present only for records from the two FACTS systems.","values":ACT_CODES},
 {"name":"method","type":"string","description":"How the treatment was carried out, as recorded in the source system. Free text, not a controlled vocabulary."},
 {"name":"equipment","type":"string","description":"Equipment used, as recorded in the source system. Free text, not a controlled vocabulary."},
 {"name":"agency","type":"string","description":"Agency or agencies responsible. A single record may name several, comma-separated, for example 'BIA, Tribal', so match with a containment test rather than equality."},
 {"name":"fund_source","type":"string","description":"Broad funding category derived by the publisher from the fund code. Values: Other, Harvest Activity, Hazardous Fuels Reduction, No Funding Code, Cooperative Work Knutson-Vandenberg, BIL=Bipartisan Infrastructure Law, CFLR=Collaborative Forest Landscape Restoration, FMReg=Fire Management Regional, National Forest System, Multiple=record lists several codes, Good Neighbor Program","values":["Other","Harvest Activity","Hazardous Fuels Reduction","No Funding Code","Cooperative Work Knutson-Vandenberg","BIL","CFLR","FMReg","National Forest System","Multiple","Good Neighbor Program"]},
 {"name":"fund_code","type":"string","description":"Budget line-item code from the source system for Forest Service records, or an indication of whether Bipartisan Infrastructure Law money was used for Interior records. A record may carry several comma-separated codes, so match with a containment test rather than equality; the resulting 598 distinct combinations are not a flat vocabulary. The publisher states the full code definitions are not readily available, so use fund_source for the grouped categories."},
 {"name":"total_cost","type":"double","description":"Estimated direct cost in US dollars, computed by the publisher as cost_per_uom multiplied by acres. A rough estimate: it excludes planning and overhead, is not inflation-adjusted, and inherits any error in either input."},
 {"name":"cost_per_uom","type":"double","description":"Estimated direct cost per unit of measure, in US dollars at the time of the work. Entered by hand and not reconciled against financial records; implausibly high values are flagged with HIGH_COST in the error column."},
 {"name":"uom","type":"string","description":"Unit the cost was estimated in. Values: ACRES=area in acres, MILES=length in miles, EACH=a count of items. 145,076 records carry no value, which the publisher treats as acres. Records measured in miles or each cannot enter an acreage-based cost total.","values":["ACRES","MILES","EACH"]},
 {"name":"error","type":"string","description":"Quality flags the publisher attached to the record, semicolon-separated when more than one applies, so test with a containment match rather than equality. Codes: DUPLICATE_KEEP=record has duplicates and is the one to keep, DUPLICATE_DROP=a duplicate of a kept record, BUFFERED_LINE=polygon was synthesized by buffering a line, BUFFERED_POINT=polygon was synthesized by buffering a point, MODIFIED_SHAPE=geometry was altered, SPATIAL=the state attribute disagrees with where the polygon falls, HIGH_COST=cost per acre above $10,000 and probably an error, CHECK_UOM=unit of measure is not acres so the cost total may be wrong, LARGE_AREA=implausibly large polygon. 1,405,075 records carry no flag.","values":["DUPLICATE_DROP","DUPLICATE_KEEP","BUFFERED_LINE","BUFFERED_POINT","MODIFIED_SHAPE","BUFFERED_LINE;MODIFIED_SHAPE","SPATIAL","HIGH_COST","CHECK_UOM","DUPLICATE_DROP;MODIFIED_SHAPE","DUPLICATE_KEEP;MODIFIED_SHAPE","HIGH_COST;MODIFIED_SHAPE","LARGE_AREA;MODIFIED_SHAPE","DUPLICATE_DROP;SPATIAL","DUPLICATE_KEEP;SPATIAL","BUFFERED_POINT;SPATIAL","HIGH_COST;DUPLICATE_KEEP","HIGH_COST;DUPLICATE_DROP","MODIFIED_SHAPE;SPATIAL","CHECK_UOM;MODIFIED_SHAPE"]},
 {"name":"SHAPE__Area","type":"double","description":"Polygon area in square degrees, because the source service computed it in longitude and latitude rather than a projected system. It is not square metres and is not comparable between latitudes; use acres for area."},
 {"name":"SHAPE__Length","type":"double","description":"Polygon perimeter in degrees, computed in longitude and latitude by the source service, so it is not metres and is not comparable between latitudes."},
]
GEOM = {"name":"geom","type":"geometry","description":"Treatment polygon in WGS84 (EPSG:4326). One record carries no geometry."}
H3COLS = [
 {"name":"h10","type":"uint64","description":"H3 cell identifier at resolution 10."},
 {"name":"h9","type":"uint64","description":"H3 cell identifier at resolution 9."},
 {"name":"h8","type":"uint64","description":"H3 cell identifier at resolution 8."},
 {"name":"h0","type":"int64","description":"H3 cell identifier at resolution 0, used as the partition key for hive-partitioned reads."},
 {"name":"native_res","type":"int32","description":"The H3 resolution this feature was indexed at. Values: 10=indexed at resolution 10, which covers 1,490,993 treatments, 9=indexed at resolution 9, the 71 next largest, 8=indexed at resolution 8, the 7 largest. Tells you which of the h10, h9 and h8 columns is populated for the row.","values":["10","9","8"]},
]

HEX_DESC = (
 "Treatment polygons indexed to H3 cells, one row per treatment and cell, hive-partitioned by h0. "
 "Covers 1,491,071 of the 1,491,072 treatments. The one record that carries no geometry polyfills to zero cells and is therefore absent from the hex; it is present in the GeoParquet.\n\n"
 "Resolution varies with polygon size, which is what native_res records: 1,490,993 treatments are at "
 "resolution 10, the 71 largest at resolution 9, and the 7 largest at resolution 8. A single "
 "21,000 square kilometre polygon would generate roughly 1.4 billion cells at resolution 10, so the "
 "largest polygons are held at a coarser resolution deliberately.\n\n"
 "h8 is populated on every row and is the column to join on. h10 is NULL for the 78 treatments held "
 "at resolution 9 or 8, and h9 is NULL for the 7 held at resolution 8, so joining on the finest "
 "column silently drops the largest features. Join at the coarsest resolution every row carries, "
 "which is h8, or roll finer data up with h3_cell_to_parent:\n\n"
 "```sql\n"
 "-- correct: join on h8, which every row carries\n"
 "SELECT * FROM twig t JOIN other o ON t.h8 = o.h8;\n"
 "-- wrong: h10 is NULL for the 78 largest treatments, which vanish from the result\n"
 "SELECT * FROM twig t JOIN other o ON t.h10 = o.h10;\n"
 "```\n\n"
 "acres, total_cost, cost_per_uom, SHAPE__Area and SHAPE__Length are totals for the whole treatment, "
 "repeated on every cell it covers. Add them up only after reducing to one row per treatment, keyed on "
 "unique_id or _cng_fid:\n\n"
 "```sql\n"
 "-- correct: one row per treatment before summing\n"
 "SELECT SUM(acres) FROM (SELECT DISTINCT unique_id, acres FROM twig WHERE status = 'Completed');\n"
 "-- wrong: counts each treatment once per cell it covers\n"
 "SELECT SUM(acres) FROM twig WHERE status = 'Completed';\n"
 "```\n\n"
 "For treated ground rather than reported acreage, count distinct cells instead, which also removes the "
 "overlap between treatments that the acreage columns double-count."
)

DESC = (
 "Fuel treatments and related land management activities across the United States, compiled by the "
 "Southwest Ecological Restoration Institutes from five federal and state reporting systems. "
 "1,491,072 treatment polygons covering the 50 states, Puerto Rico and Guam.\n\n"
 "This is the interagency record. It carries US Forest Service activity data alongside Department of the "
 "Interior, state forester and interagency fuel-treatment records, so it reaches beyond any single "
 "agency's reporting. It complements rather than replaces `facts-common-attributes-2026-06`, the "
 "Forest Service FACTS Common Attributes collection in this catalogue: 737,013 of these records come "
 "from that same Forest Service source but carry a reduced set of attributes, so combining the two "
 "collections would count those Forest Service treatments twice.\n\n"
 "Four things decide whether a number taken from this dataset is meaningful.\n\n"
 "Adding up the acres column does not give treated ground. The same stand is thinned, piled, pile-burned "
 "and re-entered years later, and each is its own polygon with its own acres, so the acreage column counts "
 "that ground several times. Repeat treatment is real and worth measuring, but it is not additional area. "
 "For ground actually treated, count distinct H3 cells in the hex asset; for reported activity, sum the "
 "acres. Report the two separately and say which is which.\n\n"
 "Planned work is included. 240,404 treatments covering 50,596,043 acres are scheduled rather than done, "
 "against 1,249,074 completed treatments covering 121,205,444 acres. An unfiltered total overstates "
 "accomplished work by roughly 42 percent, so every tabulation needs to state its status filter.\n\n"
 "Dates need a sanity window. treatment_date runs from 1202-02-10 to 2926-10-03. 1,429,746 records fall "
 "between 1980 and the access date, 61,314 carry a future date and 12 fall before 1980. None have been "
 "removed; any time series should apply an explicit window and report how many records it discarded.\n\n"
 "The quality flags are worth reading. The error column marks the publisher's own findings, including "
 "65,107 records involved in duplicate pairs, 17,669 whose polygons were synthesized from a line or a "
 "point and therefore do not describe a measured footprint, and 815 where the recorded state disagrees "
 "with where the polygon falls. One such record, a 1.9-acre Virginia treatment mapped into the Atlantic "
 "off South America, is what stretches this collection's bounding box east to 51 degrees west.\n\n"
 "Source: paged from the publisher's live feature service on 2026-09-17, reconciling 1,491,072 records "
 "against the service's own count at both the start and end of the transfer. The service is live and is "
 "overwritten in place, so the staged copy is the provenance for this edition: "
 "s3://public-fire/raw/twig-treatment-index-2026-08.gpkg, 5,785,997,312 bytes, sha256 "
 "d0a4eb816db3217a6883a524f2e8996bc510a415377c8d0057695298b986cb11. The publisher last edited the "
 "service on 2026-09-02."
)

coll = {
 "type":"Collection","stac_version":"1.0.0","id":D,
 "stac_extensions":[
   "https://stac-extensions.github.io/table/v1.2.0/schema.json",
   "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
 ],
 "title":"TWIG Interagency Fuel Treatments, United States",
 "description":DESC,
 "license":"CC-BY-4.0",
 "keywords":["fuel treatment","wildfire","prescribed fire","forest management","FACTS","NFPORS","IFPRS","United States"],
 "providers":[
  {"name":"Southwest Ecological Restoration Institutes (SWERI), ReSHAPE","roles":["producer","licensor"],"url":"https://reshapewildfire.org/resources/twig-data-resources/"},
  {"name":"Boettiger Lab, UC Berkeley","roles":["processor","host"],"url":"https://s3-west.nrp-nautilus.io/public-fire/"},
 ],
 "sci:doi":"10.1038/s41597-025-05859-z",
 "sci:citation":("Call, A., Tomczyk, N., Withnall, K.A., Dappen, P., Heusinkveld, D., Mueller, S.E., Holloway, B., "
   "Shennan, K., Herring, J.A., Franko, A., Colavito, M.M., Kimple, A.D., Sanchez Meador, A.J., Stevens-Rumann, C.S. "
   "(2025). A new geodatabase of fuel treatments across federal lands in the USA. Scientific Data 12, 1485. "
   "https://doi.org/10.1038/s41597-025-05859-z. Treatment and Wildfire Interagency Geodatabase (TWIG) treatment "
   "index, accessed 2026-09-17 from the ReSHAPE feature service."),
 "extent":{
   "spatial":{"bbox":[
      [-164.66506,8.57298,144.86231,72.15331],
      [-164.66506,8.57298,-51.81414,72.15331],
      [144.66265,13.38437,144.86231,13.65356],
   ]},
   "temporal":{"interval":[["1980-01-01T00:00:00Z","2026-09-17T00:00:00Z"]]},
 },
 "links":[
  {"rel":"self","href":f"{B}/{D}/stac-collection.json","type":"application/json"},
  {"rel":"root","href":"https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json","type":"application/json"},
  {"rel":"parent","href":f"{B}/stac-collection.json","type":"application/json"},
  {"rel":"license","href":"https://creativecommons.org/licenses/by/4.0/","type":"text/html","title":"Creative Commons Attribution 4.0 International"},
  {"rel":"about","href":"https://reshapewildfire.org/resources/twig-data-resources/","type":"text/html","title":"TWIG Data Resources (documentation, metadata and licence)"},
  {"rel":"cite-as","href":"https://doi.org/10.1038/s41597-025-05859-z","type":"text/html","title":"Call et al. 2025, Scientific Data"},
  {"rel":"source","href":"https://gis.reshapewildfire.org/arcgis/rest/services/Hosted/Treatment_Index_View/FeatureServer/0","type":"text/html","title":"ReSHAPE Treatment Index feature service"},
 ],
 "assets":{
  f"{D}-parquet":{
    "href":f"{B}/{D}.parquet","type":"application/x-parquet",
    "title":"TWIG treatment index (GeoParquet)",
    "description":"One row per treatment polygon, 1,491,072 rows. The query target for attribute work and spatial filters.",
    "roles":["data"],"created":"2026-09-17T19:40:00Z",
    "table:primary_geometry":"geom",
    "table:columns":COLS+[GEOM],
  },
  f"{D}-pmtiles":{
    "href":f"{B}/{D}.pmtiles","type":"application/vnd.pmtiles",
    "title":"TWIG treatment index (PMTiles)",
    "description":"Vector tiles for web maps. The MapLibre source-layer is twig-treatment-index-2026-08.",
    "roles":["visual"],"created":"2026-09-17T20:00:00Z",
    "vector:layers":[D],
    "table:columns":[{k:v for k,v in c.items() if k in ("name","type","values")} for c in COLS],
  },
  f"{D}-hex":{
    "href":f"{B}/{D}/hex/h0=*/data_0.parquet","type":"application/x-parquet",
    "title":"TWIG treatment index (H3 hex)",
    "description":HEX_DESC,
    "roles":["data"],"created":"2026-09-17T19:55:00Z",
    "h3:native_resolution":10,"h3:parent_resolutions":[9,8,0],
    "table:columns":COLS+H3COLS,
  },
 },
}
with open("/tmp/twig/stac-collection.json","w") as f:
    json.dump(coll,f,indent=2,ensure_ascii=False)
print("wrote /tmp/twig/stac-collection.json")
