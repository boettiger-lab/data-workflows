"""Tests for scripts/fallback-styles.py (#881)."""

import importlib.util
import pathlib
import unittest
from unittest import mock

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fallback-styles.py"
_spec = importlib.util.spec_from_file_location("fallback_styles", _SRC)
fb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fb)

BASE = "https://s3-west.nrp-nautilus.io/public-x/"
COLL = "public-x/d/stac-collection.json"


def doc(**assets):
    return {"type": "Collection", "id": "d", "stac_extensions": [], "assets": assets}


TILES = {"href": BASE + "d.pmtiles", "type": "application/vnd.pmtiles", "vector:layers": ["d"]}


class Pmtiles(unittest.TestCase):
    def run_fb(self, d, types, targets=None):
        with mock.patch.object(fb, "pmtiles_layer_types", return_value=types):
            return fb.fallback(d, COLL, targets=targets or {})

    def test_one_colour_style_by_geometry(self):
        new, files, _ = self.run_fb(doc(**{"d-pmtiles": dict(TILES)}), {"d": "line"})
        a = new["assets"]["style-fallback-d"]
        self.assertEqual(a["roles"], ["style", "default"])
        self.assertEqual(a["href"], BASE + "d/styles/fallback-d.json")
        (fname, sty), = files
        self.assertEqual(sty["layers"][0]["type"], "line")
        self.assertEqual(sty["layers"][0]["source-layer"], "d")
        self.assertEqual(sty["sources"]["data"]["url"], "pmtiles://../../d.pmtiles")

    def test_existing_default_style_is_left_alone(self):
        d = doc(**{"d-pmtiles": dict(TILES),
                   "style-d": {"href": BASE + "s.json", "roles": ["style", "default"]}})
        new, files, _ = self.run_fb(d, {"d": "fill"}, {"style-d": {TILES["href"]}})
        self.assertIsNone(new)
        self.assertEqual(files, [])

    def test_generic_default_covers_every_file(self):
        d = doc(**{"d-pmtiles": dict(TILES),
                   "style-d": {"href": BASE + "s.json", "roles": ["style", "default"]}})
        new, _, _ = self.run_fb(d, {"d": "fill"}, {"style-d": None})
        self.assertIsNone(new)

    def test_each_file_gets_its_own_default(self):
        other = dict(TILES, href=BASE + "e.pmtiles", **{"vector:layers": ["e"]})
        d = doc(**{"d-pmtiles": dict(TILES), "e-pmtiles": other,
                   "style-d": {"href": BASE + "s.json", "roles": ["style", "default"]}})
        new, files, _ = self.run_fb(d, {"e": "fill"}, {"style-d": {TILES["href"]}})
        self.assertEqual(new["assets"]["style-fallback-e"]["roles"], ["style", "default"])
        self.assertEqual(len(files), 1)

    def test_existing_style_for_a_file_is_promoted(self):
        d = doc(**{"d-pmtiles": dict(TILES),
                   "style-d": {"href": BASE + "s.json", "roles": ["style"]}})
        new, files, notes = self.run_fb(d, {"d": "fill"}, {"style-d": {TILES["href"]}})
        self.assertEqual(new["assets"]["style-d"]["roles"], ["style", "default"])
        self.assertEqual(files, [])

    def test_unknown_geometry_is_skipped(self):
        new, _, notes = self.run_fb(doc(**{"d-pmtiles": dict(TILES)}), {})
        self.assertIsNone(new)
        self.assertIn("no geometry type", notes[0])


class Renders(unittest.TestCase):
    def cog(self, band):
        return {"href": BASE + "d-cog.tif", "type": "image/tiff; application=geotiff",
                "raster:bands": [band]}

    def test_classes_become_a_colormap(self):
        band = {"nodata": 255, "classification:classes": [
            {"value": 0, "name": "a", "color_hint": "EDEDD6"},
            {"value": 1, "name": "b", "color_hint": "0070FF"}]}
        new, _, _ = fb.fallback(doc(**{"d-cog": self.cog(band)}), COLL)
        r = new["renders"]["d"]
        self.assertEqual(r["colormap"], {"0": "#EDEDD6", "1": "#0070FF"})
        self.assertEqual((r["nodata"], r["resampling"]), (255, "nearest"))
        self.assertIn(fb.apps.RENDER_EXT, new["stac_extensions"])

    def test_statistics_become_a_viridis_stretch(self):
        band = {"nodata": -9999, "statistics": {"minimum": 0.0, "maximum": 4.2}}
        new, _, _ = fb.fallback(doc(**{"d-cog": self.cog(band)}), COLL)
        r = new["renders"]["d"]
        self.assertEqual((r["colormap_name"], r["rescale"]), ("viridis", [[0.0, 4.2]]))

    def test_nodata_only_is_skipped(self):
        new, _, notes = fb.fallback(doc(**{"d-cog": self.cog({"nodata": 0})}), COLL)
        self.assertIsNone(new)
        self.assertIn("no render", notes[0])

    def test_already_rendered_cog_is_left_alone(self):
        d = doc(**{"d-cog": self.cog({"statistics": {"minimum": 0, "maximum": 1}})})
        d["renders"] = {"x": {"assets": ["d-cog"]}}
        new, _, _ = fb.fallback(d, COLL)
        self.assertIsNone(new)

    def test_overview_stats_become_a_clipped_stretch(self):
        a = self.cog({"nodata": -1})
        stats = {a["href"]: {"min": 0, "max": 100, "mean": 10, "std": 5}}
        new, _, notes = fb.fallback(doc(**{"d-cog": a}), COLL, stats)
        self.assertEqual(new["renders"]["d"]["rescale"], [[0, 20]])
        self.assertIn("overview statistics", notes[0])
        self.assertNotIn("statistics", new["assets"]["d-cog"]["raster:bands"][0])

    def test_load_stats_maps_vsis3_to_href_and_drops_errors(self):
        import tempfile, pathlib, json
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as t:
            t.write(json.dumps({"path": "/vsis3/public-x/d-cog.tif", "min": 0, "max": 1}))
            t.write(json.dumps({"path": "/vsis3/public-x/f.tif", "min": 0, "max": 1}) + "\n")
            t.write(json.dumps({"path": "/vsis3/public-x/e.tif", "error": "x"}) + "\nDONE\n")
        got = fb.load_stats(pathlib.Path(t.name))
        self.assertEqual(sorted(got), [BASE + "d-cog.tif", BASE + "f.tif"])


if __name__ == "__main__":
    unittest.main()
