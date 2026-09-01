#!/usr/bin/env python3
"""Regression tests for the fill-code rule in scripts/lint-stac-categorical.py.

Motivated by data-workflows #628: `landfire-2024-vcc` shipped its three fill codes as
renderable entries in `classification:classes`. A consumer builds its TiTiler colormap
straight from that list, so `-1111` painted solid grey and `32767` solid white across
~6% of CONUS — 8-37% of every painted pixel on a z4 tile — and no downstream config
could suppress it. Only `-9999` was harmless, because it equalled the band `nodata` and
was masked before the colormap ran.

The defect is invisible to every structural check: the values are inside the COG
min/max, the entries are well-formed, and the legend renders. It is caught only by a
rule that knows a fill code is not a class.

Stdlib `unittest` only, no network — `lint()` reads a file path, so each case writes its
document to a temp file.

Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import tempfile
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "lint-stac-categorical.py"
_spec = importlib.util.spec_from_file_location("lint_stac_categorical", _SRC)
lint_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_mod)


def collection(classes, nodata=-9999):
    return {
        "type": "Collection",
        "id": "test-collection",
        "assets": {
            "test-cog": {
                "href": "https://s3-west.nrp-nautilus.io/public-x/test/test-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "raster:bands": [{"name": "test", "data_type": "int16",
                                  "nodata": nodata, "classification:classes": classes}],
            }
        },
    }


def cls(value, name, color="808080"):
    return {"value": value, "name": name, "color_hint": color,
            "description": f"{name} (test fixture)."}


def lint(doc):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(doc, fh)
        path = fh.name
    try:
        return lint_mod.lint(path)
    finally:
        pathlib.Path(path).unlink()


# The eleven real VCC classes, which must always survive the rule untouched.
VCC_REAL = [
    cls(1, "Vegetation Condition Class I.A", "1A9641"),
    cls(2, "Vegetation Condition Class I.B", "A6D96A"),
    cls(3, "Vegetation Condition Class II.A", "FFFFBF"),
    cls(4, "Vegetation Condition Class II.B", "FDAE61"),
    cls(5, "Vegetation Condition Class III.A", "D7191C"),
    cls(6, "Vegetation Condition Class III.B", "A50026"),
    cls(111, "Water", "0000FF"),
    cls(112, "Snow/Ice", "E1E1E1"),
    cls(120, "Developed", "8400A8"),
    cls(132, "Barren", "B2B2B2"),
    cls(180, "Agriculture", "DF73FF"),
]


class FillCodesAreNotClasses(unittest.TestCase):
    def test_real_classes_alone_pass(self):
        self.assertEqual(lint(collection(VCC_REAL)), [])

    def test_nodata_declared_as_a_class_is_flagged(self):
        errs = lint(collection(VCC_REAL + [cls(-9999, "Fill-NoData", "FFFFFF")]))
        self.assertEqual(len(errs), 1)
        self.assertIn("band's own nodata", errs[0])
        self.assertIn("-9999", errs[0])

    def test_fill_that_is_not_the_nodata_is_flagged(self):
        """The #628 defect proper: these paint, because nothing masks them."""
        errs = lint(collection(VCC_REAL + [cls(-1111, "Fill-Not Mapped", "6F6F6F"),
                                           cls(32767, "Fill - NoData (band sentinel)", "FFFFFF")]))
        self.assertEqual(len(errs), 2)
        self.assertTrue(all("fill/no-data sentinel" in e for e in errs), errs)
        self.assertIn("-1111", errs[0])
        self.assertIn("32767", errs[1])

    def test_nodata_wins_over_the_name_heuristic(self):
        """One entry, one finding — a fill-named nodata is not reported twice."""
        errs = lint(collection([cls(250, "NoData", "FFFFFF")] + VCC_REAL, nodata=250))
        self.assertEqual(len(errs), 1)
        self.assertIn("band's own nodata", errs[0])

    def test_float_nodata_matches_an_int_class_value(self):
        """STAC carries nodata as int or float; -9999.0 must still match value -9999."""
        errs = lint(collection(VCC_REAL + [cls(-9999, "Fill-NoData", "FFFFFF")], nodata=-9999.0))
        self.assertEqual(len(errs), 1)
        self.assertIn("band's own nodata", errs[0])

    def test_missing_nodata_still_catches_fill_by_name(self):
        doc = collection(VCC_REAL + [cls(32767, "Background / Not Mapped", "FFFFFF")])
        del doc["assets"]["test-cog"]["raster:bands"][0]["nodata"]
        errs = lint(doc)
        self.assertEqual(len(errs), 1)
        self.assertIn("fill/no-data sentinel", errs[0])

    def test_real_class_names_are_not_mistaken_for_fill(self):
        """Precision guard: these are genuine published classes, not sentinels."""
        for name in ("Unclassified", "Barren or Sparsely Vegetated", "Sparse Vegetation",
                     "Open Water", "Snow/Ice", "Non-burnable", "Undifferentiated Forest"):
            with self.subTest(name=name):
                self.assertFalse(lint_mod.is_fill_name(name), name)

    def test_fill_names_are_recognized(self):
        for name in ("Fill-NoData", "Fill - NoData (band sentinel)", "Fill-Not Mapped",
                     "NoData", "No Data", "Background / Not Mapped", "Unmapped"):
            with self.subTest(name=name):
                self.assertTrue(lint_mod.is_fill_name(name), name)


class FractionalHexMayCarryTheNodataCode(unittest.TestCase):
    """The COG list is a RENDER legend, so the band nodata is deliberately absent from
    it. A fractional-coverage hex still carries that code as a real class — "what share
    of this cell is nodata" is data, not a render concern. The hex⊆COG cross-check must
    not push fill back into the legend to satisfy itself (nlcd, cgls-lc100).
    """

    @staticmethod
    def with_fraction_hex(hex_values, nodata=250):
        doc = collection([cls(11, "Open Water", "466B9F"),
                          cls(41, "Deciduous Forest", "68AB5F")], nodata=nodata)
        doc["assets"]["test-hex-fractions"] = {
            "href": "https://s3-west.nrp-nautilus.io/public-x/test/hex/h0=*/data_0.parquet",
            "type": "application/x-parquet",
            "table:columns": [
                {"name": "test", "type": "uint8",
                 "description": "Land-cover class code. Values: 11=Open Water, "
                                "41=Deciduous Forest, 250=NoData.",
                 "values": hex_values},
            ],
        }
        return doc

    def test_hex_may_carry_the_band_nodata(self):
        self.assertEqual(lint(self.with_fraction_hex([11, 41, 250])), [])

    def test_a_code_that_is_neither_a_class_nor_the_nodata_still_fails(self):
        errs = lint(self.with_fraction_hex([11, 41, 250, 99]))
        self.assertTrue(any("cross-check failed" in e and "[99]" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
