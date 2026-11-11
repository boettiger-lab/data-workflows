"""Tests for scripts/thumbnail.py. Stdlib unittest, no network or browser."""

import importlib.util
import pathlib
import unittest
import urllib.parse

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "thumbnail.py"
_spec = importlib.util.spec_from_file_location("thumbnail", _SRC)
th = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(th)

BASE = "https://s3-west.nrp-nautilus.io/public-x/d/stac-collection.json"


class Choice(unittest.TestCase):
    def test_first_default_style_by_key(self):
        doc = {"assets": {"style-b": {"href": "b.json", "roles": ["style", "default"]},
                          "style-a": {"href": "a.json", "roles": ["style", "default"]},
                          "style-0": {"href": "0.json", "roles": ["style"]}}}
        self.assertEqual(th.default_style(doc)[0], "style-a")

    def test_cog_render_skips_non_tiff_assets(self):
        doc = {"renders": {"r": {"assets": ["frames", "c"]}},
               "assets": {"frames": {"href": "f.json", "type": "application/json"},
                          "c": {"href": "c.tif", "type": "image/tiff; application=geotiff"}}}
        self.assertEqual(th.cog_render(doc)[2]["href"], "c.tif")

    def test_newest_year_of_a_series(self):
        tif = lambda y: {"href": f"{y}.tif"}
        doc = {"renders": {"x-cog-1985": {"assets": ["a"]}, "x-cog-2025": {"assets": ["b"]}},
               "assets": {"a": tif(1985), "b": tif(2025)}}
        self.assertEqual(th.cog_render(doc)[0], "x-cog-2025")


class CogPreview(unittest.TestCase):
    def query(self, render, asset):
        url = th.cog_preview_url(BASE, render, asset, 256)
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    def test_render_fields_and_unscale(self):
        q = self.query({"rescale": [[-2, 32]], "colormap_name": "rdylbu_r", "nodata": -32768},
                       {"href": "sst.tif", "raster:bands": [{"scale": 0.01}]})
        self.assertEqual(q["url"], ["https://s3-west.nrp-nautilus.io/public-x/d/sst.tif"])
        self.assertEqual(q["rescale"], ["-2,32"])
        self.assertEqual(q["unscale"], ["true"])
        self.assertEqual(q["nodata"], ["-32768"])

    def test_unscaled_band_and_categorical_colormap(self):
        q = self.query({"colormap": {"0": "#c8fafa"}}, {"href": "baa.tif"})
        self.assertNotIn("unscale", q)
        self.assertEqual(q["colormap"], ['{"0": "#c8fafa"}'])


class Style(unittest.TestCase):
    def test_sources_absolute_symbols_dropped_background_added(self):
        style = {"version": 8, "glyphs": "x/{fontstack}", "sources": {
                     "data": {"type": "vector", "url": "pmtiles://../d.pmtiles"}},
                 "layers": [{"id": "f", "type": "fill", "source": "data"},
                            {"id": "l", "type": "symbol", "source": "data"}]}
        s = th.style_for_thumbnail(style, "https://h/public-x/d/styles/d.json")
        self.assertEqual(s["sources"]["data"]["url"], "pmtiles://https://h/public-x/d/d.pmtiles")
        self.assertEqual([l["type"] for l in s["layers"]], ["background", "fill"])
        self.assertNotIn("glyphs", s)


class Bbox(unittest.TestCase):
    def test_clamped_and_3d(self):
        self.assertEqual(th.bbox({"extent": {"spatial": {"bbox": [[-200, -90, 0, -10, 90, 0]]}}}),
                         [-180, -85, -10, 85])

    def test_unusable_bbox_draws_the_world(self):
        self.assertEqual(th.bbox({"extent": {"spatial": {"bbox": [list("Final")]}}}),
                         [-180, -85, 180, 85])

    def test_flat_bbox_is_tolerated(self):
        self.assertEqual(th.bbox({"extent": {"spatial": {"bbox": [-124, 32, -114, 42]}}}),
                         [-124, 32, -114, 42])

    def test_antimeridian_shows_full_width(self):
        self.assertEqual(th.bbox({"extent": {"spatial": {"bbox": [[170, -20, -170, 10]]}}}),
                         [-180, -20, 180, 10])


if __name__ == "__main__":
    unittest.main()
