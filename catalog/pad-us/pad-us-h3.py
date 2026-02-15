from cng.utils import *

duckdb_install_h3()

import ibis
from ibis import _
con = ibis.duckdb.connect(extensions = ["spatial", "h3"])

import streamlit as st
set_secrets(con, st.secrets["MINIO_KEY"], st.secrets["MINIO_SECRET"])

parquet = "https://minio.carlboettiger.info/public-biodiversity/pad-us-4/pad-us-4.parquet"
con.raw_sql(f"CREATE  OR REPLACE VIEW pad4 AS SELECT Unit_Nm, row_n, geom FROM '{parquet}'")

zoom = 10

con.sql(f'''
WITH t1 AS (
  SELECT Unit_Nm, row_n, ST_Dump(geom) AS geom 
  FROM pad4
) 
SELECT Unit_Nm, row_n,
       h3_polygon_wkt_to_cells_string(UNNEST(geom).geom, {zoom}) AS h{zoom}
FROM t1
''').to_parquet(f"s3://public-biodiversity/pad-us-4/pad-h3-z{zoom}.parquet")
