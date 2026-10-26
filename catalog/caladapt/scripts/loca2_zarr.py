"""Chunk-aligned access to one LOCA2-Hybrid daily Zarr store on s3://cadcat (data-workflows #669).

A thin adapter over `cng_datasets.mdim.CubeSource`, which opens the store through GDAL's
multidimensional API and reads block-aligned slabs (one compressed chunk per read). This module
only adds what `loca2_exceedance.py` needs on top: path resolution from the cadcat catalogue, the
store's chunk grid, and a per-chunk read that is safe to call from several threads.

## Decisions that matter

  * **Paths come from the catalogue CSV, not from a template.** The bucket lowercases the model
    (`gfdl-esm4`); the CMIP6 casing 404s. `s3://cadcat/cae-zarr.csv` carries the real `path`.
  * **Nothing is read from the root `.zattrs`.** They are inherited parent-GCM attributes
    (`experiment_id = historical` on an ssp370 store). Model / experiment / member come from the
    catalogue row, the grid from the coordinate arrays, the calendar from `time`.
  * **One GDAL handle per thread.** GDAL dataset handles are not thread-safe, and the reducer
    fetches chunks concurrently, so each worker thread opens its own `CubeSource`.
"""
from __future__ import annotations

import csv
import io
import threading
import urllib.request
from dataclasses import dataclass, field

import numpy as np
from osgeo import gdal

from cng_datasets.mdim.reader import CubeSource

CATALOG_URL = "https://cadcat.s3.us-west-2.amazonaws.com/cae-zarr.csv"
VARIABLE = "tasmax"

gdal.SetConfigOption("AWS_NO_SIGN_REQUEST", "YES")
gdal.SetConfigOption("AWS_REGION", "us-west-2")


def store_path(model: str, experiment: str, member: str, table: str = "day",
               variable: str = VARIABLE, grid: str = "d03") -> str:
    """The `s3://` path of one LOCA2 store, looked up in the cadcat catalogue."""
    with urllib.request.urlopen(CATALOG_URL, timeout=60) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))
    hits = [row["path"] for row in rows
            if row["activity_id"] == "LOCA2" and row["source_id"] == model
            and row["experiment_id"] == experiment and row["member_id"] == member
            and row["table_id"] == table and row["variable_id"] == variable
            and row["grid_label"] == grid]
    if len(hits) != 1:
        raise ValueError(f"expected one catalogue row for {model}/{experiment}/{member}/"
                         f"{table}/{variable}/{grid}, found {len(hits)}")
    return hits[0]


def _gdal_name(s3_path: str) -> str:
    return 'ZARR:"/vsis3/' + s3_path.removeprefix("s3://").rstrip("/") + '"'


@dataclass
class Store:
    base: str
    shape: tuple[int, int, int]
    chunks: tuple[int, int, int]
    dates: np.ndarray            # datetime64[D], one per time step
    lat: np.ndarray
    lon: np.ndarray
    _local: threading.local = field(default_factory=threading.local, repr=False)

    def _cube(self) -> CubeSource:
        cube = getattr(self._local, "cube", None)
        if cube is None:
            cube = self._local.cube = CubeSource([_gdal_name(self.base)], [VARIABLE])
        return cube

    def spatial_tiles(self) -> list[tuple[int, int, int, int, int, int]]:
        """(yc, xc, y0, y1, x0, x1) for every spatial chunk of the grid."""
        _, ny, nx = self.shape
        _, cy, cx = self.chunks
        return [(yc, xc, y0, min(y0 + cy, ny), x0, min(x0 + cx, nx))
                for yc, y0 in enumerate(range(0, ny, cy))
                for xc, x0 in enumerate(range(0, nx, cx))]

    def read_chunk(self, tc: int, yc: int, xc: int) -> np.ndarray:
        """One storage chunk as float32 (t, y, x) Kelvin, NaN where the store has no data."""
        nt, ny, nx = self.shape
        ct, cy, cx = self.chunks
        t0, y0, x0 = tc * ct, yc * cy, xc * cx
        block = self._cube().read(VARIABLE, t0, min(t0 + ct, nt),
                                  y0, min(y0 + cy, ny), x0, min(x0 + cx, nx))
        return block.astype(np.float32)


def open_store(model: str, experiment: str, member: str = "r1i1p1f1") -> Store:
    base = store_path(model, experiment, member)
    cube = CubeSource([_gdal_name(base)], [VARIABLE])
    if cube.axis != {"time": 0, "lat": 1, "lon": 2}:
        raise ValueError(f"unexpected storage axis order {cube.axis}")
    if cube.time.dates is None:
        raise ValueError(f"calendar {cube.time.calendar!r} has no datetime64 representation")
    store = Store(
        base=base,
        shape=(len(cube.time.dates), len(cube.lat), len(cube.lon)),
        chunks=tuple(int(b) for b in cube.block),
        dates=cube.time.dates.astype("datetime64[D]"),
        lat=cube.lat, lon=cube.lon,
    )
    store._local.cube = cube
    return store
