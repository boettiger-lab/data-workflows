import argparse
import os
import sys
import psutil
import time
from osgeo import gdal
import ibis
from cng.utils import *  # noqa
from cng.h3 import *  # noqa
from ibis import _


def main():
  parser = argparse.ArgumentParser(description="Process IUCN richness tile for a given hex index i")
  parser.add_argument("--i", type=int, required=True, help="Hex index i to process (matches column i in h0-valid.parquet)")
  parser.add_argument("--zoom", type=int, default=8, help="H3 resolution to aggregate to (default 8)")
  parser.add_argument("--input-url", required=True, help="Input raster URL")
  parser.add_argument("--output-url", required=True, help="Output parquet location")
  parser.add_argument("--layer-name", required=True, help="Layer name for column naming")
  parser.add_argument("--profile", action="store_true", help="Enable memory and runtime profiling")
  args = parser.parse_args()

  i = args.i
  zoom = args.zoom

  try:
    gdal.DontUseExceptions()
    install_h3()
    con = ibis.duckdb.connect(extensions=["spatial", "h3"])
    print("Connected to DuckDB", flush=True)

    # internal endpoint on NRP does not use ssl.
    set_secrets(
      con,
      key=os.getenv("AWS_ACCESS_KEY_ID"),
      secret=os.getenv("AWS_SECRET_ACCESS_KEY"),
      endpoint=os.getenv("AWS_S3_ENDPOINT"),
      use_ssl="FALSE",
    )
    print("AWS secrets configured", flush=True)

    print(f"Input URL: {args.input_url}", flush=True)
    print(f"Output URL: {args.output_url}", flush=True)
    print(f"Layer name: {args.layer_name}", flush=True)

    import ibis.expr.datatypes as dt

    @ibis.udf.scalar.builtin
    def ST_GeomFromText(geom) -> dt.geometry:  # noqa: D401
      ...

    @ibis.udf.scalar.builtin
    def ST_MakeValid(geom) -> dt.geometry:  # noqa: D401
      ...

    df = con.read_parquet("s3://public-grids/hex/h0-valid.parquet")
    wkt = df.filter(_.i == i).geom.execute().set_crs("EPSG:4326").to_wkt()[0]
    h0 =  df.filter(_.i == i).h0.execute()[0]

    input_url = args.input_url
    output_url = args.output_url
    layer_name = args.layer_name

    if input_url.startswith("/vsis3/"):
      # keep as is, else allow override
      pass

    warp_result = gdal.Warp(
      "/tmp/iucn.xyz",
      input_url,
      dstSRS="EPSG:4326",
      cutlineWKT=wkt,
      cropToCutline=True,
    )
    
    if warp_result is None:
      print(f"ERROR: GDAL Warp failed for {input_url}", file=sys.stderr, flush=True)
      sys.exit(1)

    # compute h0 id for output path (from the polygon we just used)
    (
      con.read_csv(
        "/tmp/iucn.xyz",
        delim=" ",
        columns={"X": "FLOAT", "Y": "FLOAT", "Z": "INTEGER"},
        nullstr="nan"
      )
      .filter(_.Z.notnull())
      .filter(_.Z >= 0)  # Filter out any negative values
      .mutate(
        h0=h3_latlng_to_cell_string(_.Y, _.X, 0),  # base
        h_zoom=h3_latlng_to_cell_string(_.Y, _.X, zoom),
      )
      .select(_.Z, _.h_zoom, _.h0)
      .rename({f"h{zoom}": "h_zoom", layer_name: "Z"})
      .to_parquet(
        f"{output_url}/h0={h0}/data_0.parquet"
      )
    )
    print("Finished writing parquet", flush=True)

    if args.profile:
      process = psutil.Process(os.getpid())
      mem_info = process.memory_info()
      print(f"Maximum RAM used: {mem_info.rss / 1024**2:.2f} MiB", flush=True)
  
  except Exception as e:
    print(f"ERROR: Failed to process hex {i} for layer {args.layer_name}: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    main()
