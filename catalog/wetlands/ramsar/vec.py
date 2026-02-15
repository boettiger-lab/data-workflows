import argparse

import ibis
from ibis import _
from cng.utils import set_secrets
from cng.h3 import * 
import os


def geom_to_cell(df, zoom=10, keep_cols=None):
    con = df.get_backend()
    
    # Default to keeping all columns except geom if not specified
    if keep_cols is None:
        keep_cols = [col for col in df.columns if col != 'geom']
    
    # Build column list for SELECT statements, quoting column names to handle spaces
    col_list = ', '.join([f'"{col}"' for col in keep_cols])
    
    # all types must be multi-polygons
    cases = ibis.cases(
        (df.geom.geometry_type() == 'POLYGON', ST_Multi(df.geom)),
        else_=df.geom,
    )
    
    df = df.mutate(geom=cases)
    sql = ibis.to_sql(df)
    
    expr = f'''
        WITH t1 AS (
            SELECT {col_list}, UNNEST(ST_Dump(ST_GeomFromWKB(geom))).geom AS geom 
            FROM ({sql})
        ) 
        SELECT *, h3_polygon_wkt_to_cells_string(geom, {zoom}) AS h3id FROM t1
    '''

    out = con.sql(expr)
    return out



def main():
    parser = argparse.ArgumentParser(description="Process Ramsar wetland polygons into H3 hexes")
    parser.add_argument("--i", type=int, default=0, help="Chunk index to process (0-based)")
    parser.add_argument("--zoom", type=int, default=9, help="H3 resolution to aggregate to (default 9)")
    parser.add_argument("--chunk-size", type=int, default=50, help="Number of rows per chunk")
    parser.add_argument("--input-url", default="s3://public-wetlands/ramsar/ramsar_wetlands.parquet", help="Input geoparquet file")
    parser.add_argument("--output-url", default="s3://public-wetlands/ramsar/chunks", help="Output geoparquet bucket")
    args = parser.parse_args()


    con = ibis.duckdb.connect(extensions=["spatial", "h3"])
    con.raw_sql("INSTALL h3 FROM community; LOAD h3;")
    con.raw_sql("SET http_retries=20")
    con.raw_sql("SET http_retry_wait_ms=5000")

    # Must use scoped secrets with different names for the different endpoints
    set_secrets(con)  # read/write using AWS env var credentials (nrp alias)


    SOURCE = args.input_url

    table = con.read_parquet(SOURCE)
    
    # Find the geometry column (could be 'geometry', 'SHAPE', 'geom', etc.)
    geom_col = None
    for col in table.columns:
        if col.upper() in ['SHAPE', 'GEOMETRY', 'GEOM']:
            geom_col = col
            break
    
    if geom_col is None:
        raise ValueError(f"No geometry column found. Available columns: {table.columns}")
    
    table = table.rename(geom=geom_col)
    
    # Get column names to keep (all except geom)
    keep_cols = [col for col in table.columns if col != 'geom']

    CHUNK_SIZE = args.chunk_size

    # Get total row count and calculate chunks
    total_rows = table.count().execute()
    num_chunks = (total_rows + CHUNK_SIZE - 1) // CHUNK_SIZE

    print(f"Total rows: {total_rows:,}")
    print(f"Chunk size: {CHUNK_SIZE:,}")
    print(f"Number of chunks: {num_chunks}")
    print(f"IMPORTANT: Ensure k8s job completions >= {num_chunks} to process all rows!")

    # Use provided chunk index; guard against out-of-range
    chunk_id = int(args.i)
    if chunk_id < 0 or chunk_id >= num_chunks:
        print(f"Index {chunk_id} out of range [0, {num_chunks - 1}]. Exiting successfully.")
        return
    offset = chunk_id * CHUNK_SIZE
    print(f"\nProcessing chunk {chunk_id + 1}/{num_chunks} (rows {offset:,} to {min(offset + CHUNK_SIZE, total_rows):,})")

    chunk = table.limit(CHUNK_SIZE, offset=offset)
    
    # Start with the base zoom level
    zoom = args.zoom
    result = (
        geom_to_cell(chunk, zoom=zoom, keep_cols=keep_cols)
        .drop('geom')  # very important to drop large geom before unnest!  
        .mutate(**{f'h{zoom}': _.h3id.unnest()})
        .drop('h3id')
    )
    
    # Add parent resolutions from zoom-1 down to 0
    for parent_res in range(zoom - 1, -1, -1):
        result = result.mutate(**{f'h{parent_res}': h3_cell_to_parent(result[f'h{zoom}'], parent_res)})

    output_file = f"{args.output_url}/chunk_{chunk_id:06d}.parquet"
    result.to_parquet(output_file)

    print(f"  ✓ Chunk {chunk_id} written to {output_file}")


if __name__ == "__main__":
    main()
