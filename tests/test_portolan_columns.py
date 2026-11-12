#!/usr/bin/env python3
"""Tests for scripts/portolan-columns.py (glen#441). Stdlib unittest, no network.

Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "portolan-columns.py"
_spec = importlib.util.spec_from_file_location("portolan_columns", _SRC)
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

PARQUET = "application/vnd.apache.parquet"
BASE = "https://s3-west.nrp-nautilus.io/public-x/"


def col(name, type_, desc=None, **kw):
    c = {"name": name, "type": type_}
    if desc:
        c["description"] = desc
    c.update(kw)
    return c


def doc():
    return {
        "links": [{"rel": "self", "href": BASE + "d/stac-collection.json"}],
        "assets": {
            # listed out of order on purpose: the flat parquet must still lead
            "d-pmtiles": {"href": BASE + "d.pmtiles", "type": "application/vnd.pmtiles",
                          "title": "Tiles", "vector:layers": ["d"],
                          "table:columns": [col("name", "String"), col("_cng_fid", "Number")]},
            "d-hex": {"href": BASE + "d/hex/h0=*/data_0.parquet", "type": PARQUET,
                      "table:columns": [col("_cng_fid", "int64", "feature id"),
                                        col("name", "string", "site name"),
                                        col("h8", "uint64", "H3 res 8")]},
            "d-parquet": {"href": BASE + "d.parquet", "type": PARQUET,
                          "table:columns": [col("_cng_fid", "int64", "feature id"),
                                            col("name", "string", "site name",
                                                values=[{"value": "x"}]),
                                            col("geometry", "binary", "WKB")]},
        },
    }


class Dictionary(unittest.TestCase):
    def test_union_in_flat_hex_pmtiles_order_with_parquet_types(self):
        d, conflicts, _ = pc.build_dictionary(doc())
        self.assertEqual(conflicts, [])
        self.assertEqual([(c["name"], c["type"]) for c in d],
                         [("_cng_fid", "int64"), ("name", "string"),
                          ("geometry", "binary"), ("h8", "uint64")])
        self.assertEqual(d[1]["values"], [{"value": "x"}])
        self.assertEqual(d[3]["description"], "H3 res 8")

    def test_divergent_description_is_a_conflict(self):
        x = doc()
        x["assets"]["d-hex"]["table:columns"][1]["description"] = "other"
        _, conflicts, _ = pc.build_dictionary(x)
        self.assertEqual(len(conflicts), 1)
        self.assertIn("`name`", conflicts[0])

    def test_type_spelling_is_not_a_conflict(self):
        x = doc()
        x["assets"]["d-hex"]["table:columns"][0]["type"] = "integer"
        _, conflicts, _ = pc.build_dictionary(x)
        self.assertEqual(conflicts, [])


class MergeValues(unittest.TestCase):
    def two_lists(self):
        x = doc()
        x["assets"]["d-hex"]["table:columns"][1]["values"] = [{"value": "x"}, {"value": "y"}]
        return x

    def test_differing_values_refused_by_default(self):
        _, conflicts, _ = pc.build_dictionary(self.two_lists())
        self.assertEqual(len(conflicts), 1)

    def test_merge_values_unions_in_order(self):
        d, conflicts, merged = pc.build_dictionary(self.two_lists(), merge_values=True)
        self.assertEqual(conflicts, [])
        self.assertEqual(d[1]["values"], [{"value": "x"}, {"value": "y"}])
        self.assertIn("`name`", merged[0])

    def test_note_extends_the_description(self):
        new, notes, conflicts = pc.migrate_columns(self.two_lists(), True,
                                                   {"name": "y appears on the hex only."})
        self.assertEqual(conflicts, [])
        col = next(c for c in new["table:columns"] if c["name"] == "name")
        self.assertEqual(col["description"], "site name. y appears on the hex only.")


class NotesAddValues(unittest.TestCase):
    def test_add_values_and_note(self):
        new, notes, _ = pc.migrate_columns(doc(), True, {"name": {"add_values": [{"value": "z"}],
                                                                  "note": "z on old rows."}})
        col = next(c for c in new["table:columns"] if c["name"] == "name")
        self.assertEqual(col["values"], [{"value": "x"}, {"value": "z"}])
        self.assertTrue(col["description"].endswith("z on old rows."))


class Migrate(unittest.TestCase):
    def test_lists_keep_names_and_types_only(self):
        new, _, _ = pc.migrate_columns(doc())
        hex_cols = new["assets"]["d-hex"]["table:columns"]
        self.assertEqual(hex_cols[0], {"name": "_cng_fid", "type": "int64"})
        self.assertEqual(new["assets"]["d-pmtiles"]["table:columns"][0],
                         {"name": "name", "type": "String"})

    def test_list_matching_the_dictionary_is_dropped(self):
        x = doc()
        del x["assets"]["d-hex"], x["assets"]["d-pmtiles"]
        new, notes, _ = pc.migrate_columns(x)
        self.assertNotIn("table:columns", new["assets"]["d-parquet"])
        self.assertEqual(len(new["table:columns"]), 3)

    def test_input_is_not_mutated(self):
        x = doc()
        pc.migrate_columns(x)
        self.assertNotIn("table:columns", x)
        self.assertIn("description", x["assets"]["d-hex"]["table:columns"][0])


class Links(unittest.TestCase):
    def test_link_added_once_with_layers(self):
        x = doc()
        pc.add_pmtiles_links(x)
        pc.add_pmtiles_links(x)
        links = [l for l in x["links"] if l["rel"] == "pmtiles"]
        self.assertEqual(links, [{"rel": "pmtiles", "href": BASE + "d.pmtiles",
                                  "type": "application/vnd.pmtiles", "title": "Tiles",
                                  "pmtiles:layers": ["d"]}])
        self.assertIn("d-pmtiles", x["assets"])  # the asset stays


if __name__ == "__main__":
    unittest.main()
