"""Marine mammal species richness from IUCN range maps (#1045), on the pattern of
marine_richness.py (#807).

Counts, for every H3 resolution-5 cell, the distinct marine mammals whose range covers
the cell (marine_mammal_sr), and the subset assessed VU, EN or CR (marine_mammal_thr_sr).
Marine mammals: cetaceans, pinnipeds and sirenians whose IUCN systems include Marine,
plus the sea otter, marine otter and polar bear. The hippo, Arctic fox and river otters
are left out, although their systems include Marine. Range filters follow IUCN's richness
products: presence 1-2 (extant, probably extant), origin 1-2 (native,
reintroduced), seasonal 1-3 (resident, breeding, non-breeding).

Writes, under OUT (a local directory):
  hex/marine_mammal_sr/h0=*/data_0.parquet, hex/marine_mammal_thr_sr/h0=*/data_0.parquet
  Marine_Mammal_SR_2025_4326.tif, Marine_Mammal_THR_SR_2025_4326.tif  (COGs on the grid of the
  existing IUCN richness COGs, sampled at pixel centres from the h5 counts)
"""
import os
import sys

import duckdb
import numpy as np
from osgeo import gdal

OUT = sys.argv[1]
RANGES = "s3://public-iucn/iucn-ranges-2025/hex/h0=*/data_0.parquet"
TAXA = "s3://public-iucn/taxonomy/iucn-taxonomy.parquet"
# Grid of the existing cog/richness/*_4326.tif layers, so the new COGs align pixel for pixel.
NX, NY = 3609, 1804
X0, Y0 = -180.0, 89.977389135884778
DX, DY = 0.099750623441397, -0.099753644950529

os.makedirs(f"{OUT}/hex", exist_ok=True)
con = duckdb.connect()
con.execute(f"SET memory_limit='12GB'; SET temp_directory='{OUT}/tmp'; SET preserve_insertion_order=false")
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL h3 FROM community; LOAD h3")
con.execute(f"""CREATE SECRET (TYPE S3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
  SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["AWS_S3_ENDPOINT"]}',
  URL_STYLE 'path', USE_SSL false)""")

con.execute(f"""CREATE TABLE marine AS
  SELECT sis_taxon_id AS id, latest_category_code IN ('VU','EN','CR') AS thr
  FROM read_parquet('{TAXA}')
  WHERE upper(class) = 'MAMMALIA' AND systems ILIKE '%marine%'
    AND ((upper("order") = 'ARTIODACTYLA' AND upper(family) <> 'HIPPOPOTAMIDAE')
         OR upper("order") = 'SIRENIA'
         OR upper(family) IN ('PHOCIDAE', 'OTARIIDAE', 'ODOBENIDAE')
         OR scientific_name IN ('Enhydra lutris', 'Lontra felina', 'Ursus maritimus'))""")
con.execute(f"""CREATE TABLE counts AS
  WITH p AS (
    SELECT DISTINCT r.id_no, r.h5
    FROM read_parquet('{RANGES}', hive_partitioning=true) r
    SEMI JOIN marine m ON m.id = r.id_no
    WHERE r.presence IN (1,2) AND r.origin IN (1,2) AND r.seasonal IN (1,2,3))
  SELECT p.h5, count(*)::INTEGER AS marine_mammal_sr,
         (count(*) FILTER (WHERE m.thr))::INTEGER AS marine_mammal_thr_sr
  FROM p JOIN marine m ON m.id = p.id_no GROUP BY p.h5""")
print(con.execute("""SELECT count(*) cells, max(marine_mammal_sr), max(marine_mammal_thr_sr),
  count(*) FILTER (WHERE marine_mammal_thr_sr > 0) thr_cells FROM counts""").fetchall(), flush=True)
print("species counted:", con.execute(f"""SELECT count(DISTINCT id_no), count(DISTINCT id_no) FILTER (WHERE m.thr)
  FROM read_parquet('{RANGES}', hive_partitioning=true) r JOIN marine m ON m.id = r.id_no
  WHERE r.presence IN (1,2) AND r.origin IN (1,2) AND r.seasonal IN (1,2,3)""").fetchall(), flush=True)

for col in ["marine_mammal_sr", "marine_mammal_thr_sr"]:
    con.execute(f"""COPY (
      SELECT {col}, h5,
             h3_cell_to_parent(h5, 4)::UBIGINT AS h4,
             h3_cell_to_parent(h5, 3)::UBIGINT AS h3,
             h3_cell_to_parent(h5, 0)::UBIGINT AS h0
      FROM counts WHERE {col} > 0 ORDER BY h0, h5)
      TO '{OUT}/hex/{col}' (FORMAT parquet, PARTITION_BY (h0), FILENAME_PATTERN 'data_{{i}}',
                            COMPRESSION zstd, WRITE_PARTITION_COLUMNS true, OVERWRITE_OR_IGNORE)""")

# Rasterise: each pixel centre takes the count of the h5 cell that contains it.
con.execute(f"""CREATE TABLE px AS
  SELECT y, x, h3_latlng_to_cell({Y0} + (y + 0.5) * ({DY}), {X0} + (x + 0.5) * {DX}, 5)::UBIGINT AS h5
  FROM range({NY}) t(y), range({NX}) s(x)""")
for col, name in [("marine_mammal_sr", "Marine_Mammal_SR_2025"), ("marine_mammal_thr_sr", "Marine_Mammal_THR_SR_2025")]:
    v = con.execute(f"""SELECT coalesce(c.{col}, 0)::UINTEGER FROM px LEFT JOIN counts c USING (h5)
                        ORDER BY y, x""").fetchnumpy()
    arr = np.asarray(list(v.values())[0], dtype=np.uint32).reshape(NY, NX)
    tmp = f"{OUT}/{name}_tmp.tif"
    ds = gdal.GetDriverByName("GTiff").Create(tmp, NX, NY, 1, gdal.GDT_UInt32)
    ds.SetGeoTransform((X0, DX, 0, Y0, 0, DY))
    ds.SetProjection("EPSG:4326")
    b = ds.GetRasterBand(1)
    b.SetNoDataValue(0)
    b.WriteArray(arr)
    ds = None
    gdal.Translate(f"{OUT}/{name}_4326.tif", tmp, format="COG",
                   creationOptions=["COMPRESS=DEFLATE", "BLOCKSIZE=512", "OVERVIEWS=AUTO"])
    os.remove(tmp)
    print(name, "pixels > 0:", int((arr > 0).sum()), "max:", int(arr.max()), flush=True)
