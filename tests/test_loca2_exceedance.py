#!/usr/bin/env python3
"""Tests for catalog/caladapt/scripts/loca2_exceedance.py (data-workflows #669).

The reduction's whole correctness claim is that a 0.5 degC histogram, reverse-cumulative-summed,
reproduces *exactly* the count of days with `tasmax >= tau` that a brute-force scan would give.
That claim is cheap to state and easy to get subtly wrong -- an off-by-one in the bin index, a
`>` / `>=` slip, NaN leaking into a bin, or the open top bin swallowing the wrong side. So the
tests compare against brute force on random data rather than against hand-picked expectations.

The bin-edge case is the one that matters: a day landing exactly on 30.0 degC must count toward
the 30.0 threshold and not toward 30.5. Float data almost never lands exactly on an edge, which
is precisely why a bug there would survive every realistic spot-check.

Stdlib `unittest` + numpy, no network.

Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "catalog" / "caladapt" / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("loca2_exceedance", SCRIPTS / "loca2_exceedance.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["loca2_exceedance"] = mod
spec.loader.exec_module(mod)

KELVIN = mod.KELVIN
N_BINS = mod.N_BINS
THRESHOLDS = mod.THRESHOLDS


def reduce_block(kelvin_block, years):
    """Run _accumulate over a (t, y, x) Kelvin block as a single 1x1-tile period."""
    nt, ny, nx = kelvin_block.shape
    a = {
        "i0": 0, "i1": nt, "years": np.unique(years),
        "hist": np.zeros((N_BINS, ny, nx), dtype=np.int32),
        "amax": np.full((np.unique(years).size, ny, nx), np.nan, dtype=np.float32),
        "nvalid": np.zeros((ny, nx), dtype=np.int32),
    }
    mod._accumulate(kelvin_block, 0, a, years, 0, ny, 0, nx, time_block=7)
    return a


def exceedance(hist):
    """days >= tau_k, for every k -- the reverse cumulative sum the product publishes."""
    return np.cumsum(hist[::-1], axis=0)[::-1]


class TestExceedance(unittest.TestCase):
    def test_matches_bruteforce_on_random_data(self):
        rng = np.random.default_rng(669)
        celsius = rng.uniform(-10.0, 65.0, size=(40, 3, 4)).astype(np.float32)
        years = np.repeat([2040, 2041, 2042, 2043], 10)
        a = reduce_block((celsius + KELVIN).astype(np.float32), years)
        got = exceedance(a["hist"])
        for k, tau in enumerate(THRESHOLDS):
            want = (celsius >= tau).sum(axis=0)
            np.testing.assert_array_equal(
                got[k], want, err_msg=f"exceedance mismatch at tau={tau}"
            )

    def test_exact_bin_edges_count_toward_their_own_threshold(self):
        # One day at exactly each threshold. Day at 30.0 must satisfy >=30.0 and fail >=30.5.
        celsius = THRESHOLDS.reshape(-1, 1, 1).astype(np.float32)
        years = np.full(celsius.shape[0], 2040)
        got = exceedance(reduce_block((celsius + KELVIN).astype(np.float32), years)["hist"])
        for k, tau in enumerate(THRESHOLDS):
            self.assertEqual(int(got[k, 0, 0]), int((THRESHOLDS >= tau).sum()), f"tau={tau}")

    def test_curve_is_monotonically_non_increasing(self):
        rng = np.random.default_rng(1)
        celsius = rng.normal(28.0, 9.0, size=(200, 5, 5)).astype(np.float32)
        years = np.repeat(np.arange(2070, 2080), 20)
        got = exceedance(reduce_block((celsius + KELVIN).astype(np.float32), years)["hist"])
        self.assertTrue(np.all(np.diff(got, axis=0) <= 0))

    def test_open_top_bin_holds_everything_above_60(self):
        celsius = np.array([59.9, 60.0, 61.0, 120.0], dtype=np.float32).reshape(-1, 1, 1)
        years = np.full(4, 2040)
        got = exceedance(reduce_block((celsius + KELVIN).astype(np.float32), years)["hist"])
        self.assertEqual(int(got[-1, 0, 0]), 3)          # >= 60.0
        self.assertEqual(int(got[-2, 0, 0]), 4)          # >= 59.5

    def test_values_below_the_grid_are_dropped_not_folded_into_bin_zero(self):
        celsius = np.array([-40.0, 0.0, 19.9, 20.0], dtype=np.float32).reshape(-1, 1, 1)
        years = np.full(4, 2040)
        a = reduce_block((celsius + KELVIN).astype(np.float32), years)
        self.assertEqual(int(exceedance(a["hist"])[0, 0, 0]), 1)   # only the 20.0 day
        self.assertEqual(int(a["nvalid"][0, 0]), 4)                # but all four are real days

    def test_nan_is_excluded_from_histogram_annual_max_and_valid_count(self):
        celsius = np.array([np.nan, 35.0, np.nan, 45.0], dtype=np.float32).reshape(-1, 1, 1)
        years = np.array([2040, 2040, 2041, 2041])
        a = reduce_block((celsius + KELVIN).astype(np.float32), years)
        self.assertEqual(int(a["hist"].sum()), 2)
        self.assertEqual(int(a["nvalid"][0, 0]), 2)
        np.testing.assert_allclose(a["amax"][:, 0, 0], [35.0, 45.0], atol=1e-4)

    def test_all_nan_pixel_stays_nan_and_reports_no_valid_days(self):
        celsius = np.full((5, 1, 1), np.nan, dtype=np.float32)
        a = reduce_block(celsius, np.full(5, 2040))
        self.assertEqual(int(a["nvalid"][0, 0]), 0)
        self.assertEqual(int(a["hist"].sum()), 0)
        self.assertTrue(np.isnan(a["amax"][0, 0, 0]))

    def test_annual_max_is_per_year_not_per_period(self):
        celsius = np.array([10.0, 50.0, 20.0, 30.0], dtype=np.float32).reshape(-1, 1, 1)
        years = np.array([2040, 2040, 2041, 2041])
        a = reduce_block((celsius + KELVIN).astype(np.float32), years)
        np.testing.assert_allclose(a["amax"][:, 0, 0], [50.0, 30.0], atol=1e-4)

    def test_time_block_size_does_not_change_the_result(self):
        rng = np.random.default_rng(7)
        kelvin = (rng.uniform(0.0, 60.0, size=(31, 2, 2)).astype(np.float32) + KELVIN)
        years = np.repeat([2040, 2041], [15, 16])
        ref = None
        for tb in (1, 3, 7, 64):
            a = {
                "i0": 0, "i1": 31, "years": np.array([2040, 2041]),
                "hist": np.zeros((N_BINS, 2, 2), dtype=np.int32),
                "amax": np.full((2, 2, 2), np.nan, dtype=np.float32),
                "nvalid": np.zeros((2, 2), dtype=np.int32),
            }
            mod._accumulate(kelvin, 0, a, years, 0, 2, 0, 2, time_block=tb)
            if ref is None:
                ref = a
            else:
                np.testing.assert_array_equal(a["hist"], ref["hist"])
                np.testing.assert_allclose(a["amax"], ref["amax"], atol=0, rtol=0)

    def test_threshold_grid_is_the_specified_one(self):
        self.assertEqual(N_BINS, 81)
        self.assertAlmostEqual(float(THRESHOLDS[0]), 20.0)
        self.assertAlmostEqual(float(THRESHOLDS[-1]), 60.0)
        self.assertAlmostEqual(float(THRESHOLDS[1] - THRESHOLDS[0]), 0.5)


if __name__ == "__main__":
    unittest.main()
