"""CCI 2026 annual report 'Project List' -> GeoParquet input for cng-datasets (#867).
Every column is kept; names are snake_cased (the mapping is printed and recorded in the STAC).
Geometry: the 'Lat Long' column, one or more 'lat,lon' pairs separated by ';', as MultiPoint.
Rows without parseable coordinates are kept with a null geometry."""
import collections, datetime, json, re, sys
import openpyxl, duckdb
SRC, OUT = sys.argv[1], sys.argv[2]
ws = openpyxl.load_workbook(SRC, read_only=True, data_only=True)["Project List"]
rows = ws.iter_rows(values_only=True)
hdr = list(next(rows))
def snake(s): return re.sub(r"_+", "_", re.sub(r"[^0-9a-z]+", "_", str(s).strip().lower())).strip("_")
names = [snake(h) for h in hdr]
assert len(set(names)) == len(names), collections.Counter(names).most_common(3)
print(json.dumps(dict(zip(names, [h.replace("\n", " ") for h in hdr]))))
data = [list(r) for r in rows if any(v is not None for v in r)]
print("rows:", len(data), flush=True)
LL = hdr.index("Lat Long"); NUM = re.compile(r"-?\d+(?:\.\d+)?")
geoms, stats, bad = [], collections.Counter(), []
for r in data:
    v = r[LL]
    if v is None or str(v).strip() == "": geoms.append(None); stats["empty"] += 1; continue
    pts = []
    for part in str(v).split(";"):
        f = NUM.findall(part)
        if len(f) != 2: continue
        la, lo = float(f[0]), float(f[1])
        if 32 <= lo <= 42.5 and -125 <= la <= -114: la, lo = lo, la; stats["swapped_pair"] += 1
        if 32 <= la <= 42.5 and -125 <= lo <= -114: pts.append((lo, la))
        else: stats["pair_outside_ca"] += 1; bad.append(part.strip())
    if pts:
        geoms.append("MULTIPOINT(" + ",".join(f"({x} {y})" for x, y in pts) + ")"); stats["geom"] += 1; stats["points"] += len(pts)
    else: geoms.append(None); stats["unparsed_or_outside"] += 1; bad.append(str(v)[:80])
print("geometry stats:", dict(stats)); print("examples dropped:", bad[:15])
# column typing: numeric only if every non-null value is a number; dates; else text
cols = list(zip(*data)); types = []
for n, c in zip(names, cols):
    vals = [v for v in c if v is not None and not (isinstance(v, str) and v.strip() == "")]
    if n == "census_tract": t = "TRACT"
    elif vals and all(isinstance(v, bool) for v in vals): t = "BOOLEAN"
    elif vals and all(isinstance(v, int) and not isinstance(v, bool) for v in vals): t = "BIGINT"
    elif vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals): t = "DOUBLE"
    elif vals and all(isinstance(v, (datetime.datetime, datetime.date)) for v in vals): t = "TIMESTAMP"
    else: t = "VARCHAR"
    types.append(t)
def conv(v, t):
    if v is None or (isinstance(v, str) and v.strip() == ""): return None
    if t == "TRACT": return str(int(v)).zfill(11) if isinstance(v, (int, float)) else str(v).strip()
    if t == "VARCHAR": return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else str(v)
    return v
print("types:", dict(collections.Counter(types)))
con = duckdb.connect(); con.execute("INSTALL spatial; LOAD spatial;")
ddl = ", ".join(f'"{n}" {"VARCHAR" if t == "TRACT" else t}' for n, t in zip(names, types))
con.execute(f"CREATE TABLE t ({ddl}, wkt VARCHAR)")
con.executemany(f"INSERT INTO t VALUES ({','.join(['?'] * (len(names) + 1))})",
                [[conv(v, t) for v, t in zip(r, types)] + [g] for r, g in zip(data, geoms)])
con.execute(f"COPY (SELECT * EXCLUDE wkt, ST_GeomFromText(wkt) AS geom FROM t) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 20000)")
print(con.sql(f"SELECT count(*) n, count(geom) with_geom, sum(total_program_ggrf_funding) ggrf, count(DISTINCT project_id_number) ids, min(reporting_cycle_name), max(reporting_cycle_name) FROM '{OUT}'"))
print(con.sql(f"SELECT agency_name, count(*) n, count(geom) g, round(sum(total_program_ggrf_funding)/1e6) ggrf_m FROM '{OUT}' GROUP BY 1 ORDER BY 4 DESC"))
