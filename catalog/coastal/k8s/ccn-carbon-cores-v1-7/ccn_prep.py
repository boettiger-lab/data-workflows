"""Coastal Carbon Data Library v1.7.0 (#793): cores with derived carbon stocks + companion tables.

Reads the staged CSVs in IN (a local directory), writes to OUT:
  ccn-cores.parquet            GeoParquet, one point per core with coordinates, every column of
                               CCN_cores.csv plus derived stocks (input to cng-datasets workflow)
  <table>.parquet              depthseries, sites, species, impacts, methods, study_citations

Derived stocks, for D in (30, 100) cm:
  stock_0_{D}cm_mgha  = sum(dry_bulk_density * f_c * overlap) over intervals clipped to [0, D],
                        scaled by D / covered, in Mg C/ha (1 g C/cm2 = 100 Mg C/ha).
                        Computed only where the union of usable intervals covers >= 90% of [0, D].
  cov_0_{D}cm         = that covered fraction (0-1) of [0, D].
  f_c is fraction_carbon where measured, else converted from fraction_organic_matter (LOI%):
    seagrass cores: Fourqurean et al. (2012), OC% = 0.40 * LOI% - 0.21 below 20% LOI,
                    0.43 * LOI% - 0.33 from 20%, floored at 0;
    all other cores: Craft et al. (1991), OC% = 0.40 * LOI% + 0.0025 * LOI%^2.
  Mangroves stay on Craft: the published mangrove equation (Kauffman et al. 2011, Palau,
  0.415 * LOI% + 2.89) overestimates CCN's paired mangrove samples below 20% LOI (#793).
  carbon_source_0_{D}cm = measured | organic_matter | mixed.
  Usable interval: depth_max > depth_min, 0 < dry_bulk_density <= 3, 0 <= f_c <= 1.
"""
import sys
from collections import defaultdict

import duckdb

IN, OUT = sys.argv[1], sys.argv[2]
DEPTHS = (30, 100)
con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial")


def csv(name):
    return f"read_csv('{IN}/CCN_{name}.csv', header=true, nullstr='NA', all_varchar=false, sample_size=-1)"


rows = con.execute(f"""SELECT d.core_id, d.study_id, depth_min::DOUBLE, depth_max::DOUBLE,
       dry_bulk_density::DOUBLE, fraction_carbon::DOUBLE, fraction_organic_matter::DOUBLE, c.habitat
       FROM {csv('depthseries')} d LEFT JOIN {csv('cores')} c USING (study_id, core_id)""").fetchall()


def om_to_c(loi, habitat):
    """Organic carbon fraction from LOI in percent."""
    if habitat == "seagrass":
        return max(0.40 * loi - 0.21 if loi < 20 else 0.43 * loi - 0.33, 0.0) / 100
    return (0.40 * loi + 0.0025 * loi * loi) / 100


def union_len(iv):
    total, end = 0.0, None
    for a, b in sorted(iv):
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


ivs = defaultdict(list)
for core, study, dmin, dmax, dbd, fc, om, habitat in rows:
    if dmin is None or dmax is None or dmax <= dmin or dbd is None or not (0 < dbd <= 3):
        continue
    if fc is not None:
        src = "measured"
    elif om is not None:
        fc, src = om_to_c(om * 100, habitat), "organic_matter"
    else:
        continue
    if not (0 <= fc <= 1):
        continue
    ivs[(study, core)].append((dmin, dmax, dbd * fc, src))

out = []
for key, iv in ivs.items():
    rec = list(key)
    for D in DEPTHS:
        clip = [(max(a, 0), min(b, D), dens, s) for a, b, dens, s in iv if min(b, D) > max(a, 0)]
        cov = union_len([(a, b) for a, b, _, _ in clip]) / D
        thick = sum(b - a for a, b, _, _ in clip)
        if cov >= 0.9 and thick > 0:
            # density-weighted mean over sampled thickness, times D: handles gaps and overlaps
            stock = sum(dens * (b - a) for a, b, dens, _ in clip) / thick * D * 100
            srcs = {s for *_, s in clip}
            src = srcs.pop() if len(srcs) == 1 else "mixed"
        else:
            stock, src = None, None
        rec += [stock, round(cov, 4), src]
    out.append(rec)

cols = ["study_id", "core_id"] + [f"{c}_0_{D}cm{u}" for D in DEPTHS
                                  for c, u in (("stock", "_mgha"), ("cov", ""), ("carbon_source", ""))]
con.execute("CREATE TABLE stocks (" + ", ".join(
    f"{c} {'VARCHAR' if c in ('study_id', 'core_id') or c.startswith('carbon_source') else 'DOUBLE'}"
    for c in cols) + ")")
con.executemany(f"INSERT INTO stocks VALUES ({', '.join('?' * len(cols))})", out)

con.execute(f"""COPY (
  SELECT c.*, s.* EXCLUDE (study_id, core_id),
         ST_Point(c.longitude::DOUBLE, c.latitude::DOUBLE) AS geometry
  FROM {csv('cores')} c LEFT JOIN stocks s USING (study_id, core_id)
  WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL
  ORDER BY c.study_id, c.core_id)
  TO '{OUT}/ccn-cores.parquet' (FORMAT parquet, COMPRESSION zstd)""")
for t in ["depthseries", "sites", "species", "impacts", "methods", "study_citations"]:
    con.execute(f"COPY (SELECT * FROM {csv(t)}) TO '{OUT}/{t}.parquet' (FORMAT parquet, COMPRESSION zstd)")

print(con.execute(f"""SELECT count(*) cores, count(stock_0_30cm_mgha) s30, count(stock_0_100cm_mgha) s100,
  median(stock_0_30cm_mgha), median(stock_0_100cm_mgha)
  FROM read_parquet('{OUT}/ccn-cores.parquet')""").fetchall())
print(con.execute(f"""SELECT habitat, count(*), count(stock_0_100cm_mgha), round(median(stock_0_100cm_mgha),1)
  FROM read_parquet('{OUT}/ccn-cores.parquet') GROUP BY 1 ORDER BY 2 DESC""").fetchall())
print(con.execute(f"""SELECT carbon_source_0_100cm, count(*) FROM read_parquet('{OUT}/ccn-cores.parquet')
  GROUP BY 1""").fetchall())
