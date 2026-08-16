#!/usr/bin/env python3
"""Tests for scripts/reconcile-column-descriptions.py (data-workflows#532).

Stdlib unittest only, no network — the tool's transform takes a plain doc dict.
Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "reconcile-column-descriptions.py"
_spec = importlib.util.spec_from_file_location("reconcile_cd", _SRC)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

PARQUET = "application/x-parquet"
FLAT_HREF = "https://s3-west.nrp-nautilus.io/public-x/d.parquet"
HEX_HREF = "https://s3-west.nrp-nautilus.io/public-x/d/hex/h0=*/data_0.parquet"


def doc_with(flat_cols, hex_cols, hex_desc="", coll_desc=""):
    return {
        "id": "d", "description": coll_desc,
        "assets": {
            "d-parquet": {"href": FLAT_HREF, "type": PARQUET, "table:columns": flat_cols},
            "d-hex": {"href": HEX_HREF, "type": PARQUET, "description": hex_desc,
                      "table:columns": hex_cols},
        },
    }


def col(name, desc, type="string"):
    return {"name": name, "type": type, "description": desc}


class CanonicalFromFlat(unittest.TestCase):
    def test_hex_column_gets_flat_text_and_note_relocates(self):
        doc = doc_with(
            flat_cols=[col("geom", "geometry", "geometry"),
                       col("ALAND", "Land area in square meters.", "int64")],
            hex_cols=[col("ALAND", "Land area in square meters. Repeated on every hex row — "
                                   "never SUM(ALAND); dedup by _cng_fid.", "int64"),
                      col("h0", "H3 res 0.", "int64")],
        )
        rep = rc.reconcile(doc)
        self.assertEqual(rep["status"], "ok")
        self.assertIn("ALAND", rep["changed"])
        # hex column now equals the flat text (fold-safe)
        hex_aland = next(c for c in doc["assets"]["d-hex"]["table:columns"]
                         if c["name"] == "ALAND")
        self.assertEqual(hex_aland["description"], "Land area in square meters.")
        # dedup note relocated to the hex ASSET description
        self.assertTrue(rc.ASSET_NOTE.search(doc["assets"]["d-hex"]["description"]))
        self.assertIn("ALAND", doc["assets"]["d-hex"]["description"])
        # no divergence remains
        self.assertEqual(rc.divergent_columns(doc), {})

    def test_no_note_added_when_hex_asset_already_has_one(self):
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"),
                       col("AREA", "Area km2.", "double")],
            hex_cols=[col("AREA", "Area km2. dedup by _cng_fid; never sum.", "double")],
            hex_desc="These per-feature totals are repeated on every cell; dedup first.",
        )
        before = doc["assets"]["d-hex"]["description"]
        rep = rc.reconcile(doc)
        self.assertIn("AREA", rep["changed"])
        self.assertEqual(rep["hex_notes_added"], [])
        self.assertEqual(doc["assets"]["d-hex"]["description"], before)


class SafetyGuards(unittest.TestCase):
    def test_flat_specific_text_is_skipped_not_copied(self):
        # flat text makes a claim false on hex -> must NOT be copied verbatim
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"),
                       col("RCRD_ACRS", "Recorded acreage. One row per case on the flat "
                                        "GeoParquet, so SUM is correct here.", "double")],
            hex_cols=[col("RCRD_ACRS", "Recorded acreage. Repeated on every hex cell; "
                                       "dedup by _cng_fid.", "double")],
        )
        rep = rc.reconcile(doc)
        self.assertIn("RCRD_ACRS", rep["skipped"])
        self.assertNotIn("RCRD_ACRS", rep["changed"])
        # untouched -> still divergent (left for judgment)
        self.assertIn("RCRD_ACRS", rc.divergent_columns(doc))

    def test_no_flat_asset_is_judgment(self):
        doc = {"id": "r", "description": "",
               "assets": {
                   "r-hex": {"href": HEX_HREF, "type": PARQUET,
                             "table:columns": [col("v", "text A", "double")]},
                   "r-hex-fractions": {"href": HEX_HREF.replace("hex", "hex-fractions"),
                                       "type": PARQUET,
                                       "table:columns": [col("v", "text B", "double")]},
               }}
        rep = rc.reconcile(doc)
        self.assertEqual(rep["status"], "judgment")
        self.assertIn("v", rep["skipped"])

    def test_already_clean_is_noop(self):
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"), col("X", "same", "int64")],
            hex_cols=[col("X", "same", "int64")],
        )
        rep = rc.reconcile(doc)
        self.assertEqual(rep["status"], "already-clean")
        self.assertEqual(rep["changed"], [])


if __name__ == "__main__":
    unittest.main()
