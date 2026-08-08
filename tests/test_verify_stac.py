#!/usr/bin/env python3
"""Regression tests for scripts/verify-stac.py.

Motivated by a near-miss: `check_hex_row_uniqueness` shipped keying each row on
`h3:native_resolution`, which reported **77,991,738 duplicate rows on WDPA against a true
count of 0** — WDPA caps its 1,297 largest features at h8, leaving h9 NULL on 37.5% of
rows, and `COUNT(DISTINCT)` drops NULL keys. Had that been trusted, the "fix" would have
rewritten a 208M-row asset for no reason. It was caught by eyeballing an implausible
number, which is not a control.

These checks are also unexercised by the STAC CI, which verifies published catalog
artifacts rather than the verifier itself.

Stdlib `unittest` only, no network: static checks take a plain `doc` dict, and the
data-backed check takes a stub MCP client. The DuckDB test is skipped when duckdb is
unavailable (the CI runner installs nothing), but runs locally and is the one that proves
NULL-safety against real rows rather than asserting on SQL text.

Run: python3 -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import unittest

_SRC = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "verify-stac.py"
_spec = importlib.util.spec_from_file_location("verify_stac", _SRC)
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)

HEX_HREF = "https://s3-west.nrp-nautilus.io/public-x/d/hex/h0=*/data_0.parquet"
PARQUET = "application/x-parquet"


def hex_asset(cols, href=HEX_HREF, **kw):
    a = {"href": href, "type": PARQUET,
         "table:columns": [{"name": c, "type": "uint64"} for c in cols]}
    a.update(kw)
    return a


class StubMCP:
    """Records the SQL it is asked for and replays canned rows."""

    def __init__(self, rows=None, raise_exc=None):
        self.rows, self.raise_exc, self.sql = rows or [], raise_exc, []

    def query(self, sql):
        self.sql.append(sql)
        if self.raise_exc:
            raise self.raise_exc
        return self.rows


class HexRowUniquenessSQL(unittest.TestCase):
    """The NULL-safety is in the generated SQL, so assert on the SQL itself."""

    def _sql_for(self, cols):
        doc = {"assets": {"d-hex": hex_asset(cols, **{"h3:native_resolution": 9})}}
        mcp = StubMCP(rows=[{"total": 10, "pairs": 10}])
        vs.check_hex_row_uniqueness(doc, mcp)
        self.assertEqual(len(mcp.sql), 1)
        return mcp.sql[0]

    def test_keys_on_coalesce_not_native_resolution(self):
        # THE regression: h9 is native but NULL on many rows; the key must fall back
        # through the coarser columns instead of keying on h9 alone.
        sql = self._sql_for(["_cng_fid", "h9", "h8", "h0"])
        self.assertIn("COALESCE(", sql)
        for h in ("h9", "h8", "h0"):
            self.assertIn(f'"{h}"::VARCHAR', sql)
        # a bare native-column key is exactly the bug — it must not appear
        self.assertNotIn('COUNT(DISTINCT ("h9"::VARCHAR', sql)

    def test_coalesce_order_is_finest_to_coarsest(self):
        sql = self._sql_for(["_cng_fid", "h0", "h8", "h10", "h9"])
        order = [sql.index(f'"{h}"::VARCHAR') for h in ("h10", "h9", "h8", "h0")]
        self.assertEqual(order, sorted(order),
                         "COALESCE must try the finest cell first, else a row's key is a "
                         "coarser cell and distinct children collapse together")

    def test_all_null_row_stays_countable(self):
        # Without a literal fallback the whole key is NULL and COUNT(DISTINCT) drops the
        # row, which is how the WDPA false positive arose in the first place.
        self.assertIn("'none'", self._sql_for(["_cng_fid", "h9", "h8", "h0"]))


class HexRowUniquenessBehaviour(unittest.TestCase):
    def _findings(self, cols, rows, **asset_kw):
        doc = {"assets": {"d-hex": hex_asset(cols, **asset_kw)}}
        return vs.check_hex_row_uniqueness(doc, StubMCP(rows=rows))

    def test_clean_asset_reports_nothing(self):
        self.assertEqual(self._findings(["_cng_fid", "h10", "h0"],
                                        [{"total": 100, "pairs": 100}]), [])

    def test_duplicates_are_hard(self):
        f = self._findings(["_cng_fid", "h10", "h0"], [{"total": 100, "pairs": 90}])
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].code, "hex-duplicate-feature-cell-rows")
        self.assertEqual(f[0].severity, vs.HARD)
        self.assertIn("10", f[0].message)

    def test_asset_without_cng_fid_is_skipped_not_queried(self):
        # raster reduce / per-cell aggregation: no (feature, cell) grain to check
        doc = {"assets": {"d-hex": hex_asset(["h10", "h0"])}}
        mcp = StubMCP(rows=[{"total": 100, "pairs": 1}])
        self.assertEqual(vs.check_hex_row_uniqueness(doc, mcp), [])
        self.assertEqual(mcp.sql, [], "must not query an asset it cannot judge")

    def test_mcp_failure_is_advisory_not_hard(self):
        f = self._findings(["_cng_fid", "h10", "h0"], None)
        doc = {"assets": {"d-hex": hex_asset(["_cng_fid", "h10", "h0"])}}
        f = vs.check_hex_row_uniqueness(doc, StubMCP(raise_exc=vs.MCPError("boom")))
        self.assertEqual([x.severity for x in f], [vs.ADVISORY])

    def test_documented_multirow_case_is_accepted(self):
        f = self._findings(
            ["_cng_fid", "h10", "h0"], [{"total": 100, "pairs": 90}],
            description="This asset intentionally holds multiple rows per feature.")
        self.assertEqual(f, [])


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "duckdb not installed")
class HexRowUniquenessAgainstRealRows(unittest.TestCase):
    """Execute the generated SQL against synthetic rows — proves NULL-safety for real,
    rather than trusting that the SQL text looks right."""

    def _run(self, rows_sql, cols):
        import duckdb
        captured = {}

        class Exec:
            def query(self, sql):
                con = duckdb.connect()
                con.execute(f"CREATE TABLE t AS {rows_sql}")
                # the check reads from read_parquet('...'); point it at our table instead
                sql = sql.replace(
                    f"read_parquet('s3://public-x/d/hex/h0=*/data_0.parquet')", "t")
                captured["sql"] = sql
                cur = con.execute(sql)
                names = [d[0] for d in cur.description]
                return [dict(zip(names, r)) for r in cur.fetchall()]

        doc = {"assets": {"d-hex": hex_asset(cols, **{"h3:native_resolution": 9})}}
        return vs.check_hex_row_uniqueness(doc, Exec())

    def test_null_native_column_is_not_a_duplicate(self):
        # The WDPA shape: 3 rows whose native h9 is NULL but whose h8 is populated and
        # distinct. Keying on h9 alone counts them as 2 duplicates; keying on the finest
        # non-NULL cell correctly finds none.
        rows = ("SELECT * FROM (VALUES "
                "(1::BIGINT, NULL::UBIGINT, 10::UBIGINT, 1::UBIGINT), "
                "(2, NULL, 11, 1), "
                "(3, NULL, 12, 1), "
                "(4, 900, 13, 1)) t(_cng_fid, h9, h8, h0)")
        self.assertEqual(self._run(rows, ["_cng_fid", "h9", "h8", "h0"]), [],
                         "NULL native cells must not read as duplicates (WDPA regression)")

    def test_real_duplicate_is_still_detected(self):
        rows = ("SELECT * FROM (VALUES "
                "(1::BIGINT, 900::UBIGINT, 10::UBIGINT, 1::UBIGINT), "
                "(1, 900, 10, 1), "
                "(2, 901, 10, 1)) t(_cng_fid, h9, h8, h0)")
        f = self._run(rows, ["_cng_fid", "h9", "h8", "h0"])
        self.assertEqual([x.code for x in f], ["hex-duplicate-feature-cell-rows"])


class ColumnDescriptionConsistency(unittest.TestCase):
    def test_divergent_text_is_flagged_and_names_the_winner(self):
        doc = {"assets": {
            "d-parquet": {"href": "https://x/d.parquet", "type": PARQUET,
                          "table:columns": [{"name": "h10", "description": "first text"}]},
            "d-hex": {"href": HEX_HREF, "type": PARQUET,
                      "table:columns": [{"name": "h10", "description": "second text"}]},
        }}
        f = vs.check_column_description_consistency(doc)
        self.assertEqual([x.code for x in f], ["column-description-divergent"])
        self.assertEqual(f[0].severity, vs.ADVISORY)
        self.assertIn("d-parquet", f[0].message)  # first-seen wins

    def test_identical_text_is_fine(self):
        col = {"name": "h10", "description": "same text"}
        doc = {"assets": {
            "a": {"href": "https://x/a.parquet", "type": PARQUET, "table:columns": [col]},
            "b": {"href": HEX_HREF, "type": PARQUET, "table:columns": [dict(col)]},
        }}
        self.assertEqual(vs.check_column_description_consistency(doc), [])

    def test_missing_description_is_not_disagreement(self):
        # a lean PMTiles asset omits prose by standard; omitting is not disagreeing
        doc = {"assets": {
            "d-parquet": {"href": "https://x/d.parquet", "type": PARQUET,
                          "table:columns": [{"name": "ACCESS_TYP", "description": "text"}]},
            "d-pmtiles": {"href": "https://x/d.pmtiles", "type": "application/vnd.pmtiles",
                          "table:columns": [{"name": "ACCESS_TYP", "values": ["a", "b"]}]},
        }}
        self.assertEqual(vs.check_column_description_consistency(doc), [])


class PerCellAggregationExemption(unittest.TestCase):
    """A per-cell aggregation has no feature dimension, so `_cng_fid` is meaningless on it
    — but a genuine vector hex missing its id must still fail."""

    def _doc(self, hex_cols):
        return {"assets": {
            "d-parquet": {"href": "https://x/d.parquet", "type": PARQUET, "table:columns": [
                {"name": "_cng_fid"}, {"name": "GEOID"}, {"name": "Acres"},
                {"name": "geom", "type": "geometry"}]},
            "d-hex-weights": hex_asset(hex_cols, href=(
                "https://s3-west.nrp-nautilus.io/public-x/d/hex-weights/h0=*/data_0.parquet")),
        }}

    def test_derived_percell_asset_is_exempt(self):
        f = vs.check_cng_fid(self._doc(["h10", "h9", "h8", "w1", "w2", "nland", "h0"]))
        self.assertEqual([x.code for x in f], [])

    def test_vector_hex_carrying_source_attrs_still_hard_fails(self):
        f = vs.check_cng_fid(self._doc(["h10", "h9", "GEOID", "Acres", "h0"]))
        self.assertEqual([x.code for x in f], ["cng-fid-missing"])
        self.assertEqual(f[0].severity, vs.HARD)


if __name__ == "__main__":
    unittest.main()
