"""Tests for scripts/default-style.py. Stdlib unittest, no network (PMTiles and MCP mocked)."""

import argparse
import importlib.util
import pathlib
import unittest
from unittest import mock

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "default-style.py"
_spec = importlib.util.spec_from_file_location("default_style", _SRC)
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

BASE = "https://s3-west.nrp-nautilus.io/public-x/"
COLL = "public-x/d/stac-collection.json"


def doc():
    return {
        "type": "Collection", "id": "d",
        "links": [{"rel": "self", "href": BASE + "d/stac-collection.json"}],
        "table:columns": [
            {"name": "kind", "type": "string", "values": ["A", "B"],
             "description": "Kind of thing. Values: A=Alpha site, B=Beta site, C=Gamma site. "
                            "Null where unrecorded."},
        ],
        "assets": {
            "d-pmtiles": {"href": BASE + "d.pmtiles", "type": "application/vnd.pmtiles",
                          "title": "Things", "vector:layers": ["d"]},
            "d-parquet": {"href": BASE + "d.parquet", "type": "application/vnd.apache.parquet"},
            "style-fallback-d": {"href": BASE + "d/styles/fallback-d.json",
                                 "roles": ["style", "default"]},
            "style-d-old": {"href": BASE + "d/styles/d-old.json", "roles": ["style", "default"]},
        },
    }


META = {"d": {"layer": "d", "count": 10, "geometry": "Polygon", "attributeCount": 3,
              "attributes": [{"attribute": "kind", "type": "string", "count": 3},
                             {"attribute": "n", "type": "number", "min": 0, "max": 100},
                             {"attribute": "pop", "type": "number", "min": 1, "max": 900}]}}


def args(**kw):
    base = dict(column=None, kind=None, single_colour=None, label=None, why=None, palette=None,
                reverse=False, colors=None, labels=None, breaks=None, unit=None, nodata=None,
                color=None, max_classes=10, tooltip=None)
    base.update(kw)
    return argparse.Namespace(**base)


class FakeMCP:
    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def query(self, sql):
        self.sql.append(sql)
        return self.rows


def build(a, rows=()):
    fake = FakeMCP(list(rows))
    with mock.patch.object(ds, "pmtiles_meta", return_value=META), \
            mock.patch.object(ds, "mcp", return_value=fake):
        new, fname, sty, _ = ds.build(doc(), COLL, "d-pmtiles", a)
    return new, fname, sty, fake


class Labels(unittest.TestCase):
    def test_codes_and_undeclared_code(self):
        col = doc()["table:columns"][0]
        self.assertEqual(ds.code_labels(col, ["C"]),
                         {"A": "Alpha site", "B": "Beta site", "C": "Gamma site"})

    def test_breaks_keep_fewest_digits_that_stay_distinct(self):
        self.assertEqual(ds.nice_breaks([2002, 2010, 2019, 2021, 2023], 1900, 2025),
                         [2002, 2010, 2019, 2021, 2023])
        self.assertEqual(ds.nice_breaks([12.3, 48.9], 0, 100), [10, 50])

    def test_break_at_the_maximum_is_dropped(self):
        self.assertEqual(ds.nice_breaks([30, 100], 0, 100), [30])


class Categorical(unittest.TestCase):
    def test_classes_labels_and_other(self):
        rows = [{"v": "A", "n": "5", "k": "3"}, {"v": "B", "n": "3", "k": "3"},
                {"v": "C", "n": "2", "k": "3"}]
        new, fname, sty, _ = build(args(column="kind", kind="categorical", max_classes=2), rows)
        legend = sty["metadata"]["glen:legend"]
        self.assertEqual([c["label"] for c in legend["classes"]], ["Alpha site", "Beta site", "Other"])
        color = sty["layers"][0]["paint"]["fill-color"]
        self.assertEqual(color[0], "case")
        self.assertEqual(color[-1][-1], ds.OTHER)
        self.assertEqual(fname, "d-kind.json")
        self.assertEqual(sty["sources"]["data"]["url"], "pmtiles://../../d.pmtiles")

    def test_explicit_colours_set_order_and_drop_absent_classes(self):
        rows = [{"v": "A", "n": "5", "k": "2"}, {"v": "B", "n": "3", "k": "2"}]
        _, _, sty, _ = build(args(column="kind", kind="categorical",
                                  colors='{"B": "#111111", "Z": "#222222", "A": "#333333"}'), rows)
        self.assertEqual([c["color"] for c in sty["metadata"]["glen:legend"]["classes"]],
                         ["#111111", "#333333"])

    def test_nodata_sentinel_is_not_a_class(self):
        rows = [{"v": "", "n": "9", "k": "3"}, {"v": "A", "n": "5", "k": "3"},
                {"v": "B", "n": "3", "k": "3"}]
        _, _, sty, _ = build(args(column="kind", kind="categorical", nodata=[""]), rows)
        self.assertEqual(len(sty["metadata"]["glen:legend"]["classes"]), 2)
        self.assertIn([["==", ["to-string", ["get", "kind"]], ""], ds.NO_DATA][0],
                      sty["layers"][0]["paint"]["fill-color"])


class Continuous(unittest.TestCase):
    def test_quantile_classes_with_no_data_guard(self):
        row = {f"q{i}": str(v) for i, v in enumerate([10, 20, 30, 40, 50])}
        row.update(lo="0", hi="100")
        _, _, sty, fake = build(args(column="n", kind="continuous", unit="%"), [row])
        color = sty["layers"][0]["paint"]["fill-color"]
        self.assertEqual(color[1], ["==", ["typeof", ["get", "n"]], "number"])
        self.assertEqual(color[2][0], "step")
        labels = [c["label"] for c in sty["metadata"]["glen:legend"]["classes"]]
        self.assertEqual(labels[0], "under 10 %")
        self.assertEqual(labels[-1], "No data")
        self.assertIn("quantile_cont", fake.sql[0])

    def test_ratio_of_two_columns(self):
        row = {f"q{i}": str(v) for i, v in enumerate([.1, .2, .3, .4, .5])}
        row.update(lo="0", hi="1")
        _, fname, sty, fake = build(args(column="n/pop", kind="continuous"), [row])
        self.assertIn("NULLIF", fake.sql[0])
        self.assertEqual(fname, "d-n-per-pop.json")
        self.assertEqual(sty["layers"][0]["paint"]["fill-color"][2][1][0], "/")


class Defaults(unittest.TestCase):
    def test_new_style_is_the_files_only_default(self):
        rows = [{"v": "A", "n": "5", "k": "1"}]
        new, _, _, _ = build(args(column="kind", kind="categorical"), rows)
        a = new["assets"]
        self.assertNotIn("style-fallback-d", a)
        self.assertEqual(a["style-d-kind"]["roles"], ["style", "default"])
        self.assertEqual(a["style-d-old"]["roles"], ["style"])
        self.assertEqual(a["style-d-kind"]["href"], BASE + "d/styles/d-kind.json")

    def test_defaults_of_files_sharing_a_prefix_are_kept(self):
        d = doc()
        d["assets"]["d-2016"] = {"href": BASE + "d-2016.pmtiles", "type": "application/vnd.pmtiles"}
        d["assets"]["style-d-2016"] = {"href": BASE + "d/styles/d-2016.json",
                                       "roles": ["style", "default"]}
        with mock.patch.object(ds, "pmtiles_meta", return_value=META), \
                mock.patch.object(ds, "mcp", return_value=FakeMCP([{"v": "A", "n": "1", "k": "1"}])):
            new, _, _, _ = ds.build(d, COLL, "d-pmtiles", args(column="kind", kind="categorical"))
        self.assertEqual(new["assets"]["style-d-2016"]["roles"], ["style", "default"])
        self.assertEqual(new["assets"]["style-d-old"]["roles"], ["style"])

    def test_single_colour_records_its_reason(self):
        new, fname, sty, _ = build(args(single_colour="Outline only; no attributes.",
                                        color="#123456"))
        self.assertEqual(sty["layers"][0]["paint"]["fill-color"], "#123456")
        self.assertEqual(sty["metadata"]["glen:single_colour_reason"], "Outline only; no attributes.")
        self.assertEqual(new["assets"]["style-d"]["description"], "Outline only; no attributes.")
        self.assertEqual(fname, "d.json")

    def test_unknown_column_is_refused(self):
        with self.assertRaises(SystemExit):
            build(args(column="missing", kind="categorical"))


if __name__ == "__main__":
    unittest.main()
