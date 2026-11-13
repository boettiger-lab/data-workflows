"""Tests for scripts/to-catalog.py."""
import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "to-catalog.py"
_spec = importlib.util.spec_from_file_location("to_catalog", _SRC)
tc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tc)


class ToCatalog(unittest.TestCase):
    def test_group_node(self):
        d = {"type": "Collection", "id": "g", "license": "various", "extent": {}, "keywords": ["k"],
             "stac_extensions": ["https://stac-extensions.github.io/table/v1.2.0/schema.json",
                                 "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
             "sci:citation": "c", "links": [{"rel": "child", "href": "./a/stac-collection.json"}],
             "assets": {"README": {"href": "https://h/b/README.md"}}}
        c = tc.to_catalog(d)
        self.assertEqual(c["type"], "Catalog")
        self.assertNotIn("license", c); self.assertNotIn("extent", c); self.assertNotIn("assets", c)
        self.assertEqual(c["sci:citation"], "c")
        self.assertEqual(len(c["stac_extensions"]), 1)
        self.assertIn({"rel": "describedby", "href": "https://h/b/README.md", "type": "text/markdown",
                       "title": "README"}, c["links"])

    def test_refuses_data_assets(self):
        with self.assertRaises(SystemExit):
            tc.to_catalog({"id": "m", "assets": {"d": {"href": "d.parquet"}}})


if __name__ == "__main__":
    unittest.main()
