"""Assemble per-model LOCA2 histograms into the published H3 tables (data-workflows #669, step 2).

Reads the `<model>_<experiment>_<y0>-<y1>.npz` files written by `loca2_exceedance.py` and writes
two h0-partitioned hex tables at H3 resolution 7 (parents 6 and 0):

  tasmax-exceedance   h7, scenario, period, threshold_c, days_mean, days_min, days_max, n_models
  tasmax-annual-max   h7, scenario, period, tmax_mean_annual_max_c, tmax_max_c, n_models

## Decisions that change the numbers

  * **days_X = days per year with tasmax >= threshold_c.** Per model, the reverse cumulative sum
    of the 0.5 degC histogram divided by the number of years in the period (30), so leap days
    count as days and the denominator is years, not 365. Exact for `>=`; see loca2_exceedance.py.
  * **Ensemble statistics are taken per threshold across models** (mean, min, max of the three
    per-model curves). Each is monotonically non-increasing because each input curve is; that is
    asserted, not assumed.
  * **Zero rows are suppressed:** a (cell, scenario, period, threshold) row is written only when
    at least one model has a day at or above the threshold. Curves are monotone, so the rows kept
    for a cell are always the contiguous low end of the threshold grid; a missing threshold means
    0 days. A cell that never reaches 20 degC has no exceedance rows but does appear in the
    annual-max table.
  * **Cells sample the pixel containing their centre.** The source pixel (1/32 deg, ~9.6 km2) is
    coarser than an h7 cell (~5.2 km2), so each h7 cell takes its pixel's values, as
    `cng_datasets.mdim` does for pixels coarser than cells. Cells whose pixel is ocean (no valid
    days) are dropped.
  * **A land pixel must be complete in every model.** n_valid is either 0 or the full day count;
    anything in between fails the build, because a partial pixel would bias the per-year rate.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import defaultdict

import numpy as np

H3_RES = 7
PARENTS = (6, 0)
NAME = re.compile(r"(?P<model>.+)_(?P<experiment>[^_]+)_(?P<y0>\d{4})-(?P<y1>\d{4})\.npz$")


def exceedance(hist: np.ndarray, n_years: int) -> np.ndarray:
    """Days per year with tmax >= tau_k, from a (k, ...) histogram."""
    return np.cumsum(hist[::-1], axis=0)[::-1].astype(np.float32) / np.float32(n_years)


def load_groups(in_dir: pathlib.Path) -> dict:
    """{(experiment, 'y0-y1'): [npz-dict, ...]} with one entry per model."""
    groups = defaultdict(list)
    for p in sorted(in_dir.glob("*.npz")):
        m = NAME.match(p.name)
        if not m:
            continue
        with np.load(p) as z:
            d = {k: z[k] for k in z.files}
        d["file"] = p.name
        groups[(m["experiment"], f"{m['y0']}-{m['y1']}")].append(d)
    return dict(groups)


def reduce_group(members: list[dict]):
    """Ensemble curves and annual-max fields for one (scenario, period).

    Returns (land mask (ny, nx), mean/min/max curves (k, ny, nx), mean annual max, overall max,
    n_models)."""
    ref = members[0]
    thresholds = ref["thresholds"]
    land = None
    curves, amax_mean, amax_max = [], [], []
    for d in members:
        assert np.array_equal(d["thresholds"], thresholds), d["file"]
        assert np.array_equal(d["lat"], ref["lat"]) and np.array_equal(d["lon"], ref["lon"]), d["file"]
        n_days, n_years = int(d["n_days"]), int(d["years"].size)
        nv = d["nvalid"]
        partial = (nv > 0) & (nv != n_days)
        assert not partial.any(), f"{d['file']}: {int(partial.sum())} pixels with partial days"
        this_land = nv == n_days
        land = this_land if land is None else land
        assert np.array_equal(land, this_land), f"{d['file']}: land mask differs between models"
        c = exceedance(d["hist"], n_years)
        assert np.all(np.diff(c, axis=0) <= 0), f"{d['file']}: exceedance curve not monotone"
        curves.append(c)
        amax_mean.append(d["mean_annual_max"])
        amax_max.append(d["max_annual"])
    stack = np.stack(curves)
    out = (land, stack.mean(axis=0), stack.min(axis=0), stack.max(axis=0),
           np.mean(amax_mean, axis=0).astype(np.float32),
           np.max(amax_max, axis=0).astype(np.float32), len(members))
    for arr in out[1:4]:
        assert np.all(np.diff(arr, axis=0) <= 1e-6), "ensemble curve not monotone"
    return out


def pixel_index(lat_c, lon_c, lat, lon):
    """(iy, ix) of the pixel containing each point on a regular ascending grid; -1 outside."""
    dy, dx = float(lat[1] - lat[0]), float(lon[1] - lon[0])
    assert np.allclose(np.diff(lat), dy) and np.allclose(np.diff(lon), dx), "grid is not regular"
    iy = np.rint((lat_c - lat[0]) / dy).astype(np.int64)
    ix = np.rint((lon_c - lon[0]) / dx).astype(np.int64)
    ok = (iy >= 0) & (iy < lat.size) & (ix >= 0) & (ix < lon.size)
    return np.where(ok, iy, -1), np.where(ok, ix, -1)


def h7_cells(con, lat, lon):
    """Every h7 cell whose centre falls on the source grid, with its centre."""
    dy, dx = float(lat[1] - lat[0]), float(lon[1] - lon[0])
    y0, y1 = lat[0] - dy, lat[-1] + dy
    x0, x1 = lon[0] - dx, lon[-1] + dx
    wkt = f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"
    return con.execute(f"""
        SELECT cell, h3_cell_to_lat(cell) AS lat, h3_cell_to_lng(cell) AS lon
        FROM (SELECT UNNEST(h3_polygon_wkt_to_cells('{wkt}', {H3_RES})) AS cell)
    """).fetchnumpy()


def main() -> int:
    import duckdb
    import pyarrow as pa

    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True, type=pathlib.Path)
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--expect-models", type=int, default=3)
    ap.add_argument("--row-group-size", type=int, default=100_000)
    args = ap.parse_args()

    groups = load_groups(args.in_dir)
    print(f"groups: { {k: [d['file'] for d in v] for k, v in groups.items()} }", flush=True)
    for k, v in groups.items():
        assert len(v) == args.expect_models, f"{k}: {len(v)} models, expected {args.expect_models}"

    con = duckdb.connect()
    con.execute("INSTALL h3 FROM community; LOAD h3;")
    first = next(iter(groups.values()))[0]
    lat, lon, thresholds = first["lat"], first["lon"], first["thresholds"]
    nx = lon.size

    cells = h7_cells(con, lat, lon)
    iy, ix = pixel_index(cells["lat"], cells["lon"], lat, lon)
    on_grid = iy >= 0
    cell_ids = cells["cell"].astype(np.uint64)[on_grid]
    cell_pix = (iy * nx + ix)[on_grid]
    print(f"h7 cells with centre on grid: {cell_ids.size}", flush=True)

    ex_parts, am_parts = [], []
    land_ref = None
    for (scenario, period), members in sorted(groups.items()):
        land, mean, mn, mx, amean, amax, n_models = reduce_group(members)
        land_ref = land if land_ref is None else land_ref
        assert np.array_equal(land, land_ref), f"{scenario} {period}: land mask differs"
        flat_land = land.ravel()
        keep_cell = flat_land[cell_pix]
        cid, pix = cell_ids[keep_cell], cell_pix[keep_cell]

        k = thresholds.size
        mean_f = mean.reshape(k, -1)[:, pix]
        mn_f = mn.reshape(k, -1)[:, pix]
        mx_f = mx.reshape(k, -1)[:, pix]
        ti, ci = np.nonzero(mx_f > 0)                  # zero suppression
        ex_parts.append(pa.table({
            "h7": cid[ci],
            "scenario": np.full(ci.size, scenario),
            "period": np.full(ci.size, period),
            "threshold_c": thresholds[ti].astype(np.float32),
            "days_mean": mean_f[ti, ci],
            "days_min": mn_f[ti, ci],
            "days_max": mx_f[ti, ci],
            "n_models": np.full(ci.size, n_models, dtype=np.uint8),
        }))
        am_parts.append(pa.table({
            "h7": cid,
            "scenario": np.full(cid.size, scenario),
            "period": np.full(cid.size, period),
            "tmax_mean_annual_max_c": amean.ravel()[pix],
            "tmax_max_c": amax.ravel()[pix],
            "n_models": np.full(cid.size, n_models, dtype=np.uint8),
        }))
        print(f"{scenario} {period}: land cells {cid.size}, exceedance rows {ci.size}", flush=True)

    ex = pa.concat_tables(ex_parts)
    am = pa.concat_tables(am_parts)
    con.register("ex", ex)
    con.register("am", am)
    parents = ", ".join(f"h3_cell_to_parent(h7, {r}) AS h{r}" for r in PARENTS)
    for name, rel, order in (
            ("tasmax-exceedance", "ex", "h7, scenario, period, threshold_c"),
            ("tasmax-annual-max", "am", "h7, scenario, period")):
        out = args.out_dir / name / "hex"
        out.mkdir(parents=True, exist_ok=True)
        con.execute(f"""
            COPY (SELECT *, {parents} FROM {rel} ORDER BY h0, {order})
            TO '{out}' (FORMAT parquet, PARTITION_BY (h0), FILENAME_PATTERN 'data_{{i}}',
                        COMPRESSION zstd, ROW_GROUP_SIZE {args.row_group_size},
                        OVERWRITE_OR_IGNORE)
        """)
        n = con.execute(f"SELECT count(*) FROM read_parquet('{out}/*/*.parquet')").fetchone()[0]
        parts = len(list(out.glob("h0=*")))
        print(f"wrote {name}: {n} rows in {parts} h0 partitions", flush=True)
    print("COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
