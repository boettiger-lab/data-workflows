"""Build one #735 PMTiles asset (ASSETS[JOB_COMPLETION_INDEX]) to staging/735-fid/."""
import gzip, json, os, struct, subprocess, sys
import duckdb
from assets import ASSETS

a = ASSETS[int(os.environ.get("ASSET_INDEX", os.environ["JOB_COMPLETION_INDEX"]))]
print("=== asset:", a["bucket"], a["key"], flush=True)
work = "/tmp/work"
os.makedirs(f"{work}/duckdb", exist_ok=True)
subset, jsonl, out = f"{work}/subset.parquet", f"{work}/subset.geojsonl", f"{work}/out.pmtiles"

c = duckdb.connect()
c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
# cap below the pod limit; the default is 80% of *host* RAM -> OOMKilled
c.execute(f"SET memory_limit='{os.environ.get('DUCKDB_MEMORY', '10GB')}'; SET threads=4; "
          f"SET preserve_insertion_order=false; SET temp_directory='{work}/duckdb'")
c.execute("CREATE SECRET nrp (TYPE S3, ENDPOINT 'rook-ceph-rgw-nautiluss3.rook', URL_STYLE 'path', "
          "USE_SSL false, KEY_ID ?, SECRET ?)",
          [os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"]])

src = f"read_parquet('{a['src']}')"
gtype = dict(c.execute(f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {src})").fetchall())[a["geom"]]
if "join" in a:
    frm, p = f"{src} p LEFT JOIN read_parquet('{a['join']}') d USING (MapUnit)", "p."
else:
    frm, p = src, ""
geom = f'{p}"{a["geom"]}"'
geom = geom if gtype.startswith("GEOMETRY") else f"ST_GeomFromWKB({geom})"
sel = ", ".join([f"{p}_cng_fid"] + [f'{e} AS "{n}"' for n, e in a["select"].items()] + [f"{geom} AS geometry"])
c.execute(f"COPY (SELECT {sel} FROM {frm}) TO '{subset}' (FORMAT PARQUET, COMPRESSION ZSTD)")
n, nd = c.execute(f"SELECT COUNT(*), COUNT(DISTINCT _cng_fid) FROM read_parquet('{subset}')").fetchone()
n_src = c.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
print(f"rows={n} distinct_fid={nd} src_rows={n_src}", flush=True)
assert n == nd == n_src, "row count / _cng_fid uniqueness mismatch"
c.close()

def run(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)

run(f"ogr2ogr -wrapdateline -datelineoffset 15 -f GeoJSONSeq {jsonl} {subset}")
os.remove(subset)
# must be a power of 2 (felt/tippecanoe#216); match the pod CPU limit, not the host
threads = 1 << (int(os.environ.get("TILE_THREADS", os.cpu_count() or 1)).bit_length() - 1)
run(f"TIPPECANOE_MAX_THREADS={threads} tippecanoe -o {out} -l {a['layer']} {a['flags']} --force {jsonl}")
os.remove(jsonl)

# Footer check: _cng_fid plus every requested field must be in the tiles.
with open(out, "rb") as f:
    h = f.read(127)
    mo, ml = struct.unpack_from("<QQ", h, 24)
    f.seek(mo); m = f.read(ml)
md = json.loads(gzip.decompress(m) if h[97] == 2 else m)
fields = {k for l in md["vector_layers"] for k in l.get("fields", {})}
layers = [l["id"] for l in md["vector_layers"]]
print("layers", layers, "zoom", h[100], h[101], "fields", sorted(fields), flush=True)
want = {"_cng_fid", *a["select"]}
missing = {w for w in want if w not in fields and not any(f.startswith(w + ".") for f in fields)}
assert layers == [a["layer"]] and not missing, f"footer check failed: layers={layers} missing={missing}"

run(f"rclone copyto {out} nrp:{a['bucket']}/staging/735-fid/{a['key']} -v")
print("=== done:", a["key"])
