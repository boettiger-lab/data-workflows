"""#914 candidate tile builds, compared on overview thumbnails, features kept at zoom 4-6 and tile
size before any is swapped in. Each keeps the live tiles' layer, zoom range and field list; only
the thinning changes. Built by catalog/pmtiles-fid/k8s/build.py into staging/914-candidates/.

NHDPlus uses its own `visibilityfilter` (the smallest map scale at which USGS says a flowline
should show) mapped to a first zoom: 1:5M -> 0, 1:2M -> 4, 1:1M -> 5, 1:500k -> 6, 1:250k -> 7,
1:100k -> 8, 1:50k and 1:24k -> 9, unassigned (0) -> 10.
"""
import json

def cols(names):
    return {n: f'"{n}"' for n in names}

NHD_FILTER = json.dumps({"flowline": ["any", [">=", "$zoom", 10], ["all", [">=", "visibilityfilter", 5000000], [">=", "$zoom", 0]], ["all", [">=", "visibilityfilter", 2000000], [">=", "$zoom", 4]], ["all", [">=", "visibilityfilter", 1000000], [">=", "$zoom", 5]], ["all", [">=", "visibilityfilter", 500000], [">=", "$zoom", 6]], ["all", [">=", "visibilityfilter", 250000], [">=", "$zoom", 7]], ["all", [">=", "visibilityfilter", 100000], [">=", "$zoom", 8]], ["all", [">=", "visibilityfilter", 24000], [">=", "$zoom", 9]]]})

ASSETS = [
    dict(bucket="public-storms", key="ibtracs-v04r01/points.r1.pmtiles",
         src="s3://public-storms/ibtracs-v04r01/points.parquet", geom="geom", layer="points",
         flags="-r1 -z11 --drop-densest-as-needed --extend-zooms-if-still-dropping",
         select=cols(['BASIN', 'BOM_CI', 'BOM_EYE', 'BOM_GUST', 'BOM_GUSTP', 'BOM_LAT', 'BOM_LON', 'BOM_POCI', 'BOM_POS_FL', 'BOM_PRES', 'BOM_PRS_FL', 'BOM_R34_NE', 'BOM_R34_NW', 'BOM_R34_SE', 'BOM_R34_SW', 'BOM_R50_NE', 'BOM_R50_NW', 'BOM_R50_SE', 'BOM_R50_SW', 'BOM_R64_NE', 'BOM_R64_NW', 'BOM_R64_SE', 'BOM_R64_SW', 'BOM_RMW', 'BOM_ROCI', 'BOM_TNUM', 'BOM_TYPE', 'BOM_WIND', 'CMA_CAT', 'CMA_LAT', 'CMA_LON', 'CMA_PRES', 'CMA_WIND', 'DIST2LAND', 'DS8_LAT', 'DS8_LON', 'DS8_PRES', 'DS8_STAGE', 'DS8_WIND', 'HKO_CAT', 'HKO_LAT', 'HKO_LON', 'HKO_PRES', 'HKO_WIND', 'IFLAG', 'ISO_TIME', 'KMA_CAT', 'KMA_LAT', 'KMA_LON', 'KMA_PRES', 'KMA_R30_DR', 'KMA_R30_L', 'KMA_R30_S', 'KMA_R50_DR', 'KMA_R50_L', 'KMA_R50_S', 'KMA_WIND', 'LANDFALL', 'LAT', 'LON', 'MLC_CLASS', 'MLC_LAT', 'MLC_LON', 'MLC_PRES', 'MLC_WIND', 'NAD_CAT', 'NAD_LAT', 'NAD_LON', 'NAD_PRES', 'NAD_WIND', 'NAME', 'NATURE', 'NEU_CLASS', 'NEU_LAT', 'NEU_LON', 'NEU_PRES', 'NEU_WIND', 'NEW_CI', 'NEW_DP', 'NEW_GRADE', 'NEW_LAT', 'NEW_LON', 'NEW_POCI', 'NEW_PRES', 'NEW_WIND', 'NUMBER', 'OGC_FID', 'REU_CI', 'REU_GUSTP', 'REU_LAT', 'REU_LON', 'REU_PRES', 'REU_R34_NE', 'REU_R34_NW', 'REU_R34_SE', 'REU_R34_SW', 'REU_R50_NE', 'REU_R50_NW', 'REU_R50_SE', 'REU_R50_SW', 'REU_RMW', 'REU_TNUM', 'REU_TYPE', 'REU_WIND', 'SEASON', 'SID', 'STORM_DR', 'STORM_SPD', 'SUBBASIN', 'TD5_LAT', 'TD5_LON', 'TD5_PRES', 'TD5_ROCI', 'TD5_WIND', 'TD6_LAT', 'TD6_LON', 'TD6_STAGE', 'TD6_WIND', 'TOK_GRADE', 'TOK_LAND', 'TOK_LAT', 'TOK_LON', 'TOK_PRES', 'TOK_R30_DR', 'TOK_R30_L', 'TOK_R30_S', 'TOK_R50_DR', 'TOK_R50_L', 'TOK_R50_S', 'TOK_WIND', 'TRACK_TYPE', 'USA_AGENCY', 'USA_ATCFID', 'USA_EYE', 'USA_GUST', 'USA_LAT', 'USA_LON', 'USA_POCI', 'USA_PRES', 'USA_R34_NE', 'USA_R34_NW', 'USA_R34_SE', 'USA_R34_SW', 'USA_R50_NE', 'USA_R50_NW', 'USA_R50_SE', 'USA_R50_SW', 'USA_R64_NE', 'USA_R64_NW', 'USA_R64_SE', 'USA_R64_SW', 'USA_RECORD', 'USA_RMW', 'USA_ROCI', 'USA_SEAHGT', 'USA_SEA_NE', 'USA_SEA_NW', 'USA_SEA_SE', 'USA_SEA_SW', 'USA_SSHS', 'USA_STATUS', 'USA_WIND', 'WEL_LAT', 'WEL_LON', 'WEL_PRES', 'WEL_WIND', 'WMO_AGENCY', 'WMO_PRES', 'WMO_WIND', 'day', 'hour', 'min', 'month', 'year'])),
    dict(bucket="public-padus", key="padus-4-1/easement.coalesce.pmtiles",
         src="s3://public-padus/padus-4-1/easement.parquet", geom="SHAPE", layer="easement",
         flags="-z14 --coalesce-densest-as-needed --extend-zooms-if-still-dropping",
         select=cols(['Access_Dt', 'Access_Src', 'Agg_Src', 'Category', 'Comments', 'Date_Est', 'Des_Tp', 'Duration', 'EHoldTyp', 'EsmtHldr', 'GAPCdDt', 'GAPCdSrc', 'GAP_Sts', 'GIS_Acres', 'GIS_Src', 'IUCNCtDt', 'IUCNCtSrc', 'IUCN_Cat', 'Loc_Ds', 'Loc_Mang', 'Loc_Nm', 'Loc_Own', 'Mang_Name', 'Mang_Type', 'Own_Name', 'Own_Type', 'Pub_Access', 'SHAPE_Area', 'SHAPE_Length', 'Source_PAID', 'Src_Date', 'State_Nm', 'Term', 'Unit_Nm', 'WDPA_Cd'])),
    dict(bucket="public-padus", key="padus-4-1/easement.smallest.pmtiles",
         src="s3://public-padus/padus-4-1/easement.parquet", geom="SHAPE", layer="easement",
         flags="-z14 --drop-smallest-as-needed --extend-zooms-if-still-dropping",
         select=cols(['Access_Dt', 'Access_Src', 'Agg_Src', 'Category', 'Comments', 'Date_Est', 'Des_Tp', 'Duration', 'EHoldTyp', 'EsmtHldr', 'GAPCdDt', 'GAPCdSrc', 'GAP_Sts', 'GIS_Acres', 'GIS_Src', 'IUCNCtDt', 'IUCNCtSrc', 'IUCN_Cat', 'Loc_Ds', 'Loc_Mang', 'Loc_Nm', 'Loc_Own', 'Mang_Name', 'Mang_Type', 'Own_Name', 'Own_Type', 'Pub_Access', 'SHAPE_Area', 'SHAPE_Length', 'Source_PAID', 'Src_Date', 'State_Nm', 'Term', 'Unit_Nm', 'WDPA_Cd'])),
    dict(bucket="public-usgs-nhd", key="nhdplus-hr/flowline.visibility.pmtiles",
         src="s3://public-usgs-nhd/nhdplus-hr/flowline.parquet", geom="geom", layer="flowline",
         flags="-z10 --drop-densest-as-needed --simplification 10 -j '" + NHD_FILTER + "'",
         select=cols(['arbolatesu', 'areasqkm', 'divdasqkm', 'divergence', 'dnhydroseq', 'dnlevel', 'fcode', 'flowdir', 'ftype', 'gnis_id', 'gnis_name', 'hydroseq', 'innetwork', 'lengthkm', 'levelpathi', 'mainpath', 'maxelevsmo', 'minelevsmo', 'nhdplusid', 'pathlength', 'permanent_identifier', 'reachcode', 'slope', 'startflag', 'streamcalc', 'streamleve', 'streamorde', 'terminalfl', 'terminalpa', 'totdasqkm', 'uphydroseq', 'visibilityfilter', 'vpu_level', 'vpu_unit', 'vpu_vintage', 'vpuid'])),
]
