"""Per-cell daily-tmax exceedance histograms from one LOCA2-Hybrid store (data-workflows #669).

Reduces one `(model, experiment)` Zarr store to, for each requested period, a per-source-pixel
histogram of daily maximum temperature in 0.5 degC bins, plus the per-year maximum. Those two
arrays are the complete input to the published product: the exceedance curve is the reverse
cumulative sum of the histogram, and the annual-max field is the companion table.

## The published quantity is "days with tasmax >= tau", and that is a correctness decision

Bin `j` holds days whose tmax falls in `[tau_j, tau_j + 0.5)`, with the last bin holding
`[60.0, inf)`. Reverse-cumulative-summing that histogram gives, exactly,

    exceed[k] = sum_{j >= k} hist[j] = count of days with tmax >= tau_k

with **no** approximation, because every day in bin `j` satisfies `tmax >= tau_k` for all `k <= j`
and fails it for all `k > j`. Had the product been defined as strictly `> tau`, a day landing
exactly on a bin edge would be miscounted, and binning could not answer the question exactly.
So the `>=` convention is not a stylistic choice — it is what makes a binned summary an exact
answer rather than an approximate one. It must be stated in the STAC.

## Other decisions, all of which change the numbers

  * **Kelvin -> Celsius** is applied here (`- 273.15`); the source is Kelvin (`tasmax/.zattrs`).
  * **NaN is ocean.** LOCA2-Hybrid is a land downscaling; ocean pixels are `NaN` (the store's
    declared `fill_value`). NaN days are counted in neither the histogram nor the annual max, and
    `n_valid` records how many real days each pixel had, so "0 days above 20 degC" (a cold
    mountain pixel) stays distinguishable from "no data" (ocean) downstream.
  * **Leap days are real days.** The calendar is `proleptic_gregorian` and the series is
    contiguous, so a 30-year window is 10,957 or 10,958 days, not 30*365. The denominator for
    `days_mean` is the number of **years** in the window; the numerator counts every actual day.
    `n_days` is written out so the assembly step can assert this rather than assume it.
  * **Time is subset to the requested windows.** Only the chunks overlapping a window are
    fetched; reading whole stores would transfer ~4x more for no gain.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import sys
import time
import warnings

import numpy as np

from loca2_zarr import open_store

T_MIN, T_MAX, T_STEP = 20.0, 60.0, 0.5
N_BINS = int(round((T_MAX - T_MIN) / T_STEP)) + 1  # 81: 20.0, 20.5, ... 60.0
THRESHOLDS = (T_MIN + T_STEP * np.arange(N_BINS)).astype(np.float32)
KELVIN = 273.15


def parse_period(s: str) -> tuple[int, int]:
    a, b = s.split("-")
    return int(a), int(b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="CMIP6-cased model id, e.g. GFDL-ESM4")
    ap.add_argument("--experiment", required=True, help="historical | ssp245 | ssp370 | ssp585")
    ap.add_argument("--member", default="r1i1p1f1")
    ap.add_argument("--period", action="append", required=True, help="YYYY-YYYY inclusive (repeat)")
    ap.add_argument("--out-prefix", required=True, help="local path prefix for the .npz outputs")
    ap.add_argument("--workers", type=int, default=6, help="concurrent chunk fetches")
    ap.add_argument("--time-block", type=int, default=512, help="days per histogram pass")
    ap.add_argument("--max-tiles", type=int, default=0, help="preflight only: stop after N tiles")
    args = ap.parse_args()

    t_start = time.time()
    store = open_store(args.model, args.experiment, args.member)
    nt, ny, nx = store.shape
    ct = store.chunks[0]
    years_of = store.dates.astype("datetime64[Y]").astype(int) + 1970
    print(f"store {store.base}", flush=True)
    print(f"  shape={store.shape} chunks={store.chunks} "
          f"dates {store.dates[0]}..{store.dates[-1]}", flush=True)

    # The series must be contiguous daily for the year bookkeeping below to be sound.
    gaps = np.unique(np.diff(store.dates).astype("timedelta64[D]").astype(int))
    assert gaps.tolist() == [1], f"non-contiguous daily series: day-steps {gaps.tolist()}"

    periods = [parse_period(p) for p in args.period]
    acc = {}
    for y0, y1 in periods:
        sel = np.flatnonzero((years_of >= y0) & (years_of <= y1))
        if sel.size == 0:
            print(f"  !! period {y0}-{y1} not covered by this store; skipping", flush=True)
            continue
        assert sel[-1] - sel[0] + 1 == sel.size, "period indices not contiguous"
        yrs = np.arange(y0, y1 + 1)
        acc[(y0, y1)] = {
            "i0": int(sel[0]),
            "i1": int(sel[-1]) + 1,
            "years": yrs,
            "hist": np.zeros((N_BINS, ny, nx), dtype=np.int32),
            "amax": np.full((yrs.size, ny, nx), np.nan, dtype=np.float32),
            "nvalid": np.zeros((ny, nx), dtype=np.int32),
        }
        print(f"  period {y0}-{y1}: idx {sel[0]}..{sel[-1]} "
              f"({sel.size} days, {yrs.size} years)", flush=True)
    if not acc:
        print("no requested period is present in this store", file=sys.stderr)
        return 2

    # Only the time chunks overlapping some requested window are ever fetched.
    wanted_tc = sorted({tc for a in acc.values()
                        for tc in range(a["i0"] // ct, (a["i1"] - 1) // ct + 1)})
    tiles = store.spatial_tiles()
    if args.max_tiles:
        tiles = tiles[: args.max_tiles]
    print(f"  fetching {len(wanted_tc)} time-chunks x {len(tiles)} spatial tiles "
          f"= {len(wanted_tc) * len(tiles)} chunk reads", flush=True)

    nbytes = 0
    for n_tile, (yc, xc, y0g, y1g, x0g, x1g) in enumerate(tiles, 1):
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(store.read_chunk, tc, yc, xc): tc for tc in wanted_tc}
            for fut in cf.as_completed(futs):
                tc = futs[fut]
                block = fut.result()               # (t, y, x) float32 Kelvin
                nbytes += block.nbytes
                g0 = tc * ct                       # global time index of block[0]
                for key, a in acc.items():
                    s = max(a["i0"], g0) - g0
                    e = min(a["i1"], g0 + block.shape[0]) - g0
                    if e <= s:
                        continue
                    _accumulate(block[s:e], g0 + s, a, years_of,
                                y0g, y1g, x0g, x1g, args.time_block)
        print(f"  tile {n_tile}/{len(tiles)} (y {y0g}:{y1g}, x {x0g}:{x1g}) "
              f"done, {nbytes / 1e9:.1f} GB decoded, {time.time() - t_start:.0f}s", flush=True)

    for (y0, y1), a in acc.items():
        out = f"{args.out_prefix}_{y0}-{y1}.npz"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mean_amax = np.nanmean(a["amax"], axis=0).astype(np.float32)
            max_amax = np.nanmax(a["amax"], axis=0).astype(np.float32)
        np.savez_compressed(
            out,
            hist=a["hist"], thresholds=THRESHOLDS, nvalid=a["nvalid"],
            mean_annual_max=mean_amax, max_annual=max_amax,
            years=a["years"], n_days=np.int32(a["i1"] - a["i0"]),
            lat=store.lat, lon=store.lon,
            model=np.str_(args.model), experiment=np.str_(args.experiment),
            member=np.str_(args.member),
        )
        land = int(np.sum(a["nvalid"] > 0))
        print(f"wrote {out}  land_pixels={land}  n_days={a['i1'] - a['i0']}  "
              f"hist_total={int(a['hist'].sum())}", flush=True)
    print(f"COMPLETE in {time.time() - t_start:.0f}s, {nbytes / 1e9:.1f} GB decoded", flush=True)
    return 0


def _accumulate(block, gstart, a, years_of, y0g, y1g, x0g, x1g, time_block):
    """Fold one (t, y, x) Kelvin block into the period's histogram, annual max and valid count."""
    nt_b, ny_b, nx_b = block.shape
    S = ny_b * nx_b
    hist_view = a["hist"][:, y0g:y1g, x0g:x1g]
    yrs = a["years"]

    for s in range(0, nt_b, time_block):
        e = min(s + time_block, nt_b)
        c = block[s:e].astype(np.float32) - KELVIN
        valid = np.isfinite(c)

        # bin index: j = floor((c - 20) / 0.5), with j<0 dropped and j>=80 folded into the open
        # top bin [60, inf). +1 shifts the drop bucket to 0 so bincount can hold it.
        b = np.floor((c - T_MIN) * (1.0 / T_STEP))
        np.copyto(b, -1.0, where=~valid)
        bi = b.astype(np.int32)
        np.clip(bi, -1, N_BINS - 1, out=bi)

        flat = bi.reshape(e - s, S)
        comb = np.arange(S, dtype=np.int64)[None, :] * (N_BINS + 1) + (flat + 1)
        counts = np.bincount(comb.ravel(), minlength=S * (N_BINS + 1))
        counts = counts.reshape(S, N_BINS + 1)
        hist_view += counts[:, 1:].T.reshape(N_BINS, ny_b, nx_b).astype(np.int32)

        a["nvalid"][y0g:y1g, x0g:x1g] += valid.sum(axis=0, dtype=np.int32)

        # Annual max. Days are contiguous in time, so each year is a contiguous run.
        yr_block = years_of[gstart + s: gstart + e]
        for yr in np.unique(yr_block):
            m = np.flatnonzero(yr_block == yr)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                part = np.nanmax(c[m[0]: m[-1] + 1], axis=0)
            k = int(np.flatnonzero(yrs == yr)[0])
            cur = a["amax"][k, y0g:y1g, x0g:x1g]
            np.fmax(cur, part, out=cur)


if __name__ == "__main__":
    raise SystemExit(main())
