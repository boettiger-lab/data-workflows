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
                      col("_cng_fid", "Feature id.", "int64"),
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
    def test_wholly_grain_specific_flat_is_skipped_not_copied(self):
        # every sentence of the flat text is grain-specific -> nothing survives scrubbing
        # -> must NOT be copied verbatim; left for judgment.
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"),
                       col("X", "One row per feature on the flat GeoParquet, so SUM is "
                                "correct here.", "double")],
            hex_cols=[col("X", "Repeated on every hex cell; dedup by _cng_fid.", "double")],
        )
        rep = rc.reconcile(doc)
        self.assertIn("X", rep["skipped"])
        self.assertNotIn("X", rep["changed"])
        self.assertIn("X", rc.divergent_columns(doc))  # untouched -> still divergent

    def test_grain_specific_sentence_is_scrubbed_then_applied(self):
        # flat has a useful base sentence + a flat-grain-specific one; the tool keeps the
        # base (grain-neutral) and drops the false-on-hex sentence, then applies to all.
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"),
                       col("GIS_Acres", "GIS-calculated area in acres. Most reliable area "
                                        "measure. Safe to use directly on GeoParquet "
                                        "(one row per feature).", "double")],
            hex_cols=[col("GIS_Acres", "GIS-calculated area in acres. Repeated on every hex "
                                       "cell; never SUM on hex; dedup by _cng_fid.", "double"),
                      col("_cng_fid", "Feature id.", "int64")],
        )
        rep = rc.reconcile(doc)
        self.assertIn("GIS_Acres", rep["changed"])
        self.assertIn("GIS_Acres", rep.get("scrubbed", []))
        text = next(c for c in doc["assets"]["d-parquet"]["table:columns"]
                    if c["name"] == "GIS_Acres")["description"]
        self.assertEqual(text, "GIS-calculated area in acres. Most reliable area measure.")
        self.assertNotIn("one row per feature", text.lower())
        self.assertEqual(rc.divergent_columns(doc), {})
        # per-feature magnitude → dedup note relocated to hex asset
        self.assertTrue(rc.ASSET_NOTE.search(doc["assets"]["d-hex"]["description"]))

    def test_index_key_column_not_named_in_dedup_note(self):
        # _cng_fid is a key, not a magnitude: scrubbed/reconciled but never named "never SUM"
        doc = doc_with(
            flat_cols=[col("geom", "g", "geometry"),
                       col("_cng_fid", "Internal id. One row per site.", "int64")],
            hex_cols=[col("_cng_fid", "Internal id. Repeated on every hex row the site "
                                      "covers.", "int64")],
        )
        rep = rc.reconcile(doc)
        self.assertIn("_cng_fid", rep["changed"])
        self.assertEqual(rep["hex_notes_added"], [])  # key col not named in a SUM warning

    def test_raster_hex_categorical_gets_no_cng_fid_note(self):
        # A raster reduction hex has no _cng_fid; a categorical "do not SUM" must NOT be
        # mistaken for a per-feature dedup clause and must not spawn a _cng_fid note.
        doc = {"id": "r", "description": "",
               "assets": {
                   "r-hex": {"href": HEX_HREF, "type": PARQUET, "description": "",
                             "table:columns": [col("cls", "Class code. Do not SUM or AVG "
                                                    "(categorical).", "int64")]},
                   "r-hex-fractions": {"href": HEX_HREF.replace("hex", "hex-fractions"),
                                       "type": PARQUET, "description": "",
                                       "table:columns": [col("cls", "Class present in cell; "
                                                              "frac coverage.", "int64")]},
               }}
        overrides = {"r": {"columns": {"cls": "Class code. Categorical — do not SUM or AVG."}}}
        rep = rc.reconcile(doc, allow_no_flat=True, overrides=overrides)
        self.assertEqual(rep["hex_notes_added"], [])
        self.assertNotIn("_cng_fid", doc["assets"]["r-hex"]["description"])
        self.assertEqual(rc.divergent_columns(doc), {})

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
