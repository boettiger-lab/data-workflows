#!/usr/bin/env python3
"""Tests for catalog/caladapt/scripts/loca2_assemble.py (data-workflows #669).

Covers the numpy core: per-model exceedance from a histogram, the ensemble across models, the
completeness and land-mask checks, and centre-to-pixel lookup. The H3 and parquet write runs
in-cluster only.

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

spec = importlib.util.spec_from_file_location("loca2_assemble", SCRIPTS / "loca2_assemble.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["loca2_assemble"] = mod
spec.loader.exec_module(mod)

THRESHOLDS = (20.0 + 0.5 * np.arange(81)).astype(np.float32)


def member(hist, nvalid, n_days=10957, n_years=30, name="m"):
    ny, nx = nvalid.shape
    return {
        "hist": hist.astype(np.int32), "thresholds": THRESHOLDS, "nvalid": nvalid.astype(np.int32),
        "n_days": np.int32(n_days), "years": np.arange(n_years),
        "mean_annual_max": np.full((ny, nx), 30.0, np.float32),
        "max_annual": np.full((ny, nx), 40.0, np.float32),
        "lat": np.array([30.0, 30.03125]), "lon": np.array([-120.0, -119.96875, -119.9375]),
        "file": name,
    }


class TestAssemble(unittest.TestCase):
    def test_exceedance_is_days_per_year_at_or_above(self):
        hist = np.zeros((81, 1, 1), np.int32)
        hist[0], hist[20], hist[80] = 30, 60, 90           # 20.0, 30.0, >=60.0 degC bins
        c = mod.exceedance(hist, 30)[:, 0, 0]
        self.assertEqual(c[0], 6.0)                         # (30+60+90)/30
        self.assertEqual(c[20], 5.0)                        # 30.0 counts toward tau=30.0
        self.assertEqual(c[21], 3.0)                        # but not toward 30.5
        self.assertEqual(c[80], 3.0)

    def test_ensemble_mean_min_max(self):
        nv = np.full((2, 3), 10957)
        hists = []
        for scale in (1, 2, 3):
            h = np.zeros((81, 2, 3), np.int32)
            h[10] = 30 * scale
            hists.append(member(h, nv, name=str(scale)))
        land, mean, mn, mx, amean, amax, n = mod.reduce_group(hists)
        self.assertTrue(land.all())
        self.assertEqual(n, 3)
        np.testing.assert_allclose(mean[10], 2.0)
        np.testing.assert_allclose(mn[10], 1.0)
        np.testing.assert_allclose(mx[10], 3.0)
        np.testing.assert_allclose(mx[11], 0.0)

    def test_ocean_pixel_is_not_land(self):
        nv = np.full((2, 3), 10957)
        nv[0, 0] = 0
        land = mod.reduce_group([member(np.zeros((81, 2, 3)), nv)])[0]
        self.assertFalse(land[0, 0])
        self.assertEqual(land.sum(), 5)

    def test_partial_pixel_fails(self):
        nv = np.full((2, 3), 10957)
        nv[1, 2] = 100
        with self.assertRaises(AssertionError):
            mod.reduce_group([member(np.zeros((81, 2, 3)), nv)])

    def test_land_mask_must_agree_across_models(self):
        nv1 = np.full((2, 3), 10957)
        nv2 = nv1.copy()
        nv2[0, 1] = 0
        z = np.zeros((81, 2, 3))
        with self.assertRaises(AssertionError):
            mod.reduce_group([member(z, nv1, name="a"), member(z, nv2, name="b")])

    def test_pixel_index_contains_centre(self):
        lat = 30.0 + 0.03125 * np.arange(4)
        lon = -120.0 + 0.03125 * np.arange(5)
        iy, ix = mod.pixel_index(np.array([30.0, 30.015, 30.016, 29.9, 30.09]),
                                 np.array([-120.0, -119.985, -119.9, -120.0, -119.875]), lat, lon)
        self.assertEqual(iy.tolist(), [0, 0, 1, -1, 3])
        self.assertEqual(ix.tolist(), [0, 0, 3, -1, 4])


if __name__ == "__main__":
    unittest.main()
