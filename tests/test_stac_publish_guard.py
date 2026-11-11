#!/usr/bin/env python3
"""Tests for scripts/stac-publish-guard.py. Stdlib unittest, no network.

Run: python3 -m unittest discover -s tests -v
"""
import copy
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "stac-publish-guard.py"
_spec = importlib.util.spec_from_file_location("stac_publish_guard", _SRC)
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

BASE = "https://s3-west.nrp-nautilus.io/public-x/d/"
TILES = {"href": BASE + "d.pmtiles", "type": "application/vnd.pmtiles"}
PARQUET = {"href": BASE + "d.parquet", "type": "application/vnd.apache.parquet"}


def live():
    return {
        "type": "Collection",
        "links": [{"rel": "self", "href": BASE + "stac-collection.json"},
                  {"rel": "pmtiles", "href": "./d.pmtiles", "type": "application/vnd.pmtiles"}],
        "stac_extensions": ["https://stac-extensions.github.io/render/v2.0.0/schema.json"],
        "table:columns": [{"name": "a", "type": "string", "description": "A"}],
        "renders": {"d-cog": {"assets": ["d-cog"]}},
        "assets": {"d-pmtiles": dict(TILES), "d-parquet": dict(PARQUET),
                   "style-d": {"href": BASE + "styles/d.json", "roles": ["style", "default"],
                               "type": "application/vnd.mapbox.style+json"}},
    }


def new_from(doc):
    """What a stale publish job would upload: the live doc minus everything added since."""
    n = copy.deepcopy(doc)
    n["links"] = [l for l in n["links"] if l["rel"] != "pmtiles"]
    n.pop("renders"); n["stac_extensions"] = []
    n["assets"].pop("style-d")
    return n


class Keeps(unittest.TestCase):
    def test_keeps_styles_renders_extension_and_links(self):
        new = new_from(live())
        kept, refused = g.guard(new, live(), set())
        self.assertEqual(refused, [])
        self.assertIn("style-d", new["assets"])
        self.assertIn("d-cog", new["renders"])
        self.assertTrue(any("/render/" in e for e in new["stac_extensions"]))
        self.assertEqual([l["href"] for l in new["links"] if l["rel"] == "pmtiles"], ["./d.pmtiles"])
        self.assertEqual(len(kept), 3)

    def test_link_not_kept_when_the_pmtiles_asset_is_gone(self):
        new = new_from(live())
        del new["assets"]["d-pmtiles"]
        g.guard(new, live(), set())
        self.assertFalse(any(l["rel"] == "pmtiles" for l in new["links"]))

    def test_identical_file_changes_nothing(self):
        new = live()
        kept, refused = g.guard(new, live(), set())
        self.assertEqual((kept, refused), ([], []))
        self.assertEqual(new, live())


class Fallbacks(unittest.TestCase):
    STYLE = "application/vnd.mapbox.style+json"

    def live_with_fallback(self):
        d = live()
        del d["assets"]["style-d"]
        d["assets"]["style-fallback-d"] = {"href": BASE + "styles/fallback-d.json",
                                           "roles": ["style", "default"], "type": self.STYLE}
        return d

    def test_real_style_retires_fallback(self):
        new = new_from(live())
        new["assets"]["style-d"] = {"href": BASE + "styles/d.json", "type": self.STYLE,
                                    "roles": ["style", "default"]}
        g.guard(new, self.live_with_fallback(), set())
        self.assertNotIn("style-fallback-d", new["assets"])

    def test_fallback_kept_when_new_has_no_style(self):
        new = new_from(live())
        g.guard(new, self.live_with_fallback(), set())
        self.assertEqual(new["assets"]["style-fallback-d"]["roles"], ["style", "default"])

    def test_kept_style_loses_default_when_new_has_one(self):
        new = new_from(live())
        new["assets"]["style-d-by-x"] = {"href": BASE + "styles/x.json", "type": self.STYLE,
                                         "roles": ["style", "default"]}
        g.guard(new, live(), set())
        self.assertEqual(new["assets"]["style-d"]["roles"], ["style"])

    def test_default_for_another_file_is_kept(self):
        lv = live()
        lv["assets"]["e-pmtiles"] = {"href": BASE + "e.pmtiles", "type": "application/vnd.pmtiles"}
        lv["assets"]["style-e"] = {"href": BASE + "styles/e.json", "type": self.STYLE,
                                   "roles": ["style", "default"]}
        new = new_from(lv)
        new["assets"].pop("style-e")
        new["assets"]["style-d-by-x"] = {"href": BASE + "styles/x.json", "type": self.STYLE,
                                         "roles": ["style", "default"]}
        g.guard(new, lv, set())
        self.assertEqual(new["assets"]["style-e"]["roles"], ["style", "default"])
        self.assertEqual(new["assets"]["style-d"]["roles"], ["style"])

    def test_live_render_for_an_asset_new_renders_is_dropped(self):
        new = new_from(live())
        new["renders"] = {"other-key": {"assets": ["d-cog"]}}
        g.guard(new, live(), set())
        self.assertEqual(list(new["renders"]), ["other-key"])


class Refuses(unittest.TestCase):
    def test_dropping_the_column_dictionary_is_refused_and_file_untouched(self):
        new = new_from(live()); new.pop("table:columns")
        before = copy.deepcopy(new)
        _, refused = g.guard(new, live(), set())
        self.assertEqual(len(refused), 1)
        self.assertTrue(refused[0].startswith("columns"))
        self.assertEqual(new, before)

    def test_reverting_an_asset_key_rename_is_refused(self):
        new = new_from(live())
        new["assets"]["kaiparowits-d-pmtiles"] = new["assets"].pop("d-pmtiles")
        _, refused = g.guard(new, live(), set())
        self.assertEqual(len(refused), 1)
        self.assertTrue(refused[0].startswith("keys"))

    def test_allow_lets_a_deliberate_change_through(self):
        new = new_from(live()); new.pop("table:columns")
        new["assets"]["other-pmtiles"] = new["assets"].pop("d-pmtiles")
        _, refused = g.guard(new, live(), {"columns", "keys"})
        self.assertEqual(refused, [])

    def test_a_new_asset_is_not_a_rename(self):
        new = new_from(live())
        new["assets"]["d-hex"] = {"href": BASE + "d/hex/h0=*/data_0.parquet"}
        _, refused = g.guard(new, live(), set())
        self.assertEqual(refused, [])


class Cli(unittest.TestCase):
    def run_cli(self, new, live_doc, env=None):
        with tempfile.TemporaryDirectory() as d:
            n, l = os.path.join(d, "new.json"), os.path.join(d, "live.json")
            json.dump(new, open(n, "w"))
            if live_doc is None:
                open(l, "w").close()  # what `: > live.json` leaves for a new collection
            else:
                json.dump(live_doc, open(l, "w"))
            r = subprocess.run([sys.executable, str(_SRC), n, l], capture_output=True, text=True,
                               env={**os.environ, **(env or {})})
            return r.returncode, json.load(open(n))

    def test_new_collection_passes(self):
        code, out = self.run_cli(new_from(live()), None)
        self.assertEqual(code, 0)

    def test_refusal_exits_3(self):
        new = new_from(live()); new.pop("table:columns")
        code, _ = self.run_cli(new, live())
        self.assertEqual(code, 3)

    def test_env_allow(self):
        new = new_from(live()); new.pop("table:columns")
        code, _ = self.run_cli(new, live(), {"STAC_GUARD_ALLOW": "columns"})
        self.assertEqual(code, 0)

    def test_keeps_are_written_back(self):
        code, out = self.run_cli(new_from(live()), live())
        self.assertEqual(code, 0)
        self.assertIn("style-d", out["assets"])


if __name__ == "__main__":
    unittest.main()


_CHK = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check-stac-publish-guard.py"
_cspec = importlib.util.spec_from_file_location("check_stac_publish_guard", _CHK)
chk = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(chk)


class CheckScript(unittest.TestCase):
    def test_shell_upload_without_guard_is_flagged(self):
        self.assertTrue(chk.is_unguarded_writer(
            "rclone copyto /tmp/s.json nrp:public-x/d/stac-collection.json\n"))

    def test_python_upload_without_guard_is_flagged(self):
        self.assertTrue(chk.is_unguarded_writer(
            "K='nrp:public-x/d/stac-collection.json'\n"
            "subprocess.check_call(['rclone', 'copyto', '/tmp/o.json', K])\n"))

    def test_guarded_or_declared_passes(self):
        up = "rclone copyto /tmp/s.json nrp:public-x/d/stac-collection.json\n"
        self.assertFalse(chk.is_unguarded_writer("curl .../stac-publish-guard.py\n" + up))
        self.assertFalse(chk.is_unguarded_writer(
            "# STAC-PUBLISH-GUARD: not needed: reads the live collection and edits it\n" + up))

    def test_download_only_is_not_a_writer(self):
        self.assertFalse(chk.is_unguarded_writer(
            "rclone copyto nrp:public-x/d/data.parquet /tmp/d.parquet\n# stac-collection.json\n"))

    def test_upload_of_other_files_without_a_collection_is_not_a_writer(self):
        self.assertFalse(chk.is_unguarded_writer("rclone copyto /tmp/d.parquet nrp:public-x/d.parquet\n"))
