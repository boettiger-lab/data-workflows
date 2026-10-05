"""#735 group A: PMTiles rebuilt from the final GeoParquet so tiles carry _cng_fid.

One entry per asset. Each keeps the live asset's layer name, zoom range and
field set (read from its current footer `generator_options` / `vector_layers`)
and adds _cng_fid. `select` maps tile field -> parquet expression. Output
`key` is the live href's object key; the build writes it under staging/735-fid/.
"""

DEFAULT = "--drop-densest-as-needed --extend-zooms-if-still-dropping"
SVI = "-z 12 --drop-densest-as-needed --extend-zooms-if-still-dropping"

def cols(*names):
    return {n: f'"{n}"' for n in names}

HYBAS = cols("HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
             "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER", "SORT")
# Overture: `names` (struct) and `sources` (list) flatten to names.common/.primary/.rules
# and a JSON `sources` in GeoJSONSeq, as in the original tiles.
OVERTURE = cols("id", "country", "version", "sources", "subtype", "class", "names",
                "is_land", "is_territorial", "admin_level", "division_id", "theme", "type", "name_en")

ASSETS = [
    *[dict(bucket="public-hydrobasins", key=f"level_{l}/hydrobasins_level_{l}.pmtiles",
           src=f"s3://public-hydrobasins/level_{l}.parquet", geom="geometry",
           layer=f"hydrobasins_level_{l}", flags=DEFAULT, select=HYBAS)
      for l in ("03", "04", "05", "06")],
    dict(bucket="public-overturemaps", key="2026-02-18.0/countries.pmtiles",
         src="s3://public-overturemaps/2026-02-18.0/countries.parquet", geom="geometry",
         layer="countries", flags=DEFAULT, select=OVERTURE),
    *[dict(bucket="public-overturemaps", key=f"2026-02-18.0/{n}.pmtiles",
           src=f"s3://public-overturemaps/2026-02-18.0/{n}.parquet", geom="geometry",
           layer=n, flags=DEFAULT, select={**OVERTURE, **cols("region")})
      for n in ("regions", "counties")],
    # SVI: deliberate 3-4 field subset; 2000/2010 county tiles renamed columns.
    dict(bucket="public-social-vulnerability", key="2000/SVI2000_US_county.pmtiles",
         src="s3://public-social-vulnerability/2000/SVI2000_US_county.parquet", geom="Shape",
         layer="svi", flags=SVI,
         select={"ST_ABBR": '"STATE_ABBR"', "COUNTY": '"COUNTY"', "FIPS": '"CNTY_FIPS"'}),
    dict(bucket="public-social-vulnerability", key="2000/SVI2000_US_tract.pmtiles",
         src="s3://public-social-vulnerability/2000/SVI2000_US_tract.parquet", geom="Shape",
         layer="svi", flags=SVI, select=cols("STATE_ABBR", "COUNTY", "FIPS")),
    dict(bucket="public-social-vulnerability", key="2010/SVI2010_US_county.pmtiles",
         src="s3://public-social-vulnerability/2010/SVI2010_US_county.parquet", geom="Shape",
         layer="svi", flags=SVI,
         select={"ST_ABBR": '"ST"', "COUNTY": '"LOCATION"', "FIPS": '"FIPS"'}),
    dict(bucket="public-social-vulnerability", key="2010/SVI2010_US_tract.pmtiles",
         src="s3://public-social-vulnerability/2010/SVI2010_US_tract.parquet", geom="Shape",
         layer="svi", flags=SVI, select=cols("STATE_ABBR", "COUNTY", "FIPS")),
    *[dict(bucket="public-social-vulnerability", key=f"2020/SVI2020_US_{t}.pmtiles",
           src=f"s3://public-social-vulnerability/2020/SVI2020_US_{t}.parquet", geom="Shape",
           layer="svi", flags=SVI, select=cols("ST_ABBR", "COUNTY", "FIPS"))
      for t in ("county", "tract")],
    *[dict(bucket="public-social-vulnerability", key=f"2022/SVI2022_US_{t}.pmtiles",
           src=f"s3://public-social-vulnerability/2022/SVI2022_US_{t}.parquet", geom="Shape",
           layer="svi", flags="-z 12", select=cols("ST_ABBR", "COUNTY", "FIPS", "RPL_THEMES"))
      for t in ("county", "tract")],
    dict(bucket="public-social-vulnerability", key="2022/SVI2022_TRIBAL_TRACTS.pmtiles",
         src="s3://public-social-vulnerability/2022/SVI2022_TRIBAL_TRACTS.parquet", geom="Shape",
         layer="svi", flags=SVI, select=cols("FIPS")),
    dict(bucket="public-ecoregion", key="ecoregion.pmtiles",
         src="s3://public-ecoregion/ecoregion.parquet", geom="SHAPE", layer="ecoregion", flags=DEFAULT,
         select=cols("OBJECTID", "ECO_NAME", "BIOME_NUM", "BIOME_NAME", "REALM", "ECO_BIOME_", "NNH",
                     "ECO_ID", "SHAPE_LENG", "NNH_NAME", "COLOR", "COLOR_BIO", "COLOR_NNH", "LICENSE",
                     "SHAPE_Length", "SHAPE_Area")),
    dict(bucket="public-high-seas", key="hydrothermal-vents.pmtiles",
         src="s3://public-high-seas/hydrothermal-vents.parquet", geom="geom",
         layer="hydrothermal-vents", flags=DEFAULT,
         select=cols("name", "name_alias", "activity", "max_temperature_c", "max_temperature_category",
                     "ocean", "region", "national_jurisdiction", "max_depth_m", "min_depth_m",
                     "tectonic_setting", "spreading_rate_mm_a")),
    # The old tiles also carried _ogr_geometry__bbox.* (a GDAL bbox-covering artifact); dropped.
    dict(bucket="public-high-seas", key="seafloor-geomorphology.pmtiles",
         src="s3://public-high-seas/seafloor-geomorphology.parquet", geom="geometry",
         layer="seafloor-geomorphology",
         flags="--drop-densest-as-needed --maximum-zoom 10 --simplification 10",
         select=cols("fid", "Geomorphic", "area_km2", "feature_type")),
    # Original tiles join the map-unit descriptions onto the polygons.
    dict(bucket="public-cgs", key="sierra-nevada-atlas/map-unit-polys.pmtiles",
         src="s3://public-cgs/sierra-nevada-atlas/map-unit-polys.parquet", geom="Shape",
         layer="map-unit-polys", flags=DEFAULT,
         join="s3://public-cgs/sierra-nevada-atlas/description-of-map-units.parquet",
         select={"MapUnit": 'p."MapUnit"', "IdentityConfidence": 'p."IdentityConfidence"',
                 "FullName": 'd."FullName"', "Age": 'd."Age"', "GeoMaterial": 'd."GeoMaterial"',
                 "Description": 'd."Description"'}),
]
