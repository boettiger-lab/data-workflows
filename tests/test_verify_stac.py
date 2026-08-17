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
import re
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
        self.assertEqual(f[0].severity, vs.HARD)  # promoted from ADVISORY in #532
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


class ScriptedMCP:
    """Replays canned rows keyed by a substring of the SQL (first match wins), so a check
    that issues several different queries gets a different answer for each. Raises on an
    unmatched query, so a test that forgets to script one fails loudly."""

    def __init__(self, responses):
        self.responses = list(responses)  # [(substr, rows), ...]
        self.sql = []

    def query(self, sql):
        self.sql.append(sql)
        for substr, rows in self.responses:
            if substr in sql:
                return rows
        raise AssertionError(f"unscripted query: {sql}")


class TruncationGuard(unittest.TestCase):
    """The MCP caps output at a 50-row markdown preview; consuming it as complete is how
    check_declared_schema_matches_data fabricated ~110 'absent' columns (#509). The client
    must refuse a truncated preview rather than silently return a partial row set."""

    @staticmethod
    def _result(text):
        return {"content": [{"type": "text", "text": text}]}

    def test_truncated_preview_raises(self):
        text = ("| name |\n|:--|\n| a |\n| b |\n\n"
                "⚠️ Showing the first 50 rows only — this is a preview, not the full result.")
        with self.assertRaises(vs.MCPError):
            vs._rows_from_tool_result(self._result(text))

    def test_full_result_parses(self):
        text = "| name | nf |\n|:--|--:|\n| a | 2 |\n| b | 2 |"
        self.assertEqual(vs._rows_from_tool_result(self._result(text)),
                         [{"name": "a", "nf": "2"}, {"name": "b", "nf": "2"}])


# --- #534: declared STAC schema vs actual parquet schema (per file) ---------

def _schema_doc(declared, href=HEX_HREF):
    return {"assets": {"d-hex": {"href": href, "type": PARQUET,
                                 "table:columns": [{"name": n} for n in declared]}}}


def _present(name_nf):
    """Expand a {name: files_present} map into synthetic parquet_schema rows
    (name, file_name, type). The total file count is COUNT(DISTINCT file_name), so the
    scenario must include a column present in every file (the common case)."""
    rows = []
    for name, nf in name_nf.items():
        for i in range(nf):
            rows.append((name, f"f{i}", "INT"))
    return rows


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "duckdb not installed")
class DeclaredSchemaMatch(unittest.TestCase):
    """The declared-vs-present set difference is computed IN SQL (so the MCP's 50-row
    preview cap can't drop wide-schema columns and fabricate 'absent' findings, #509).
    These run that real SQL against a synthetic parquet_schema relation."""

    def _run(self, name_nf, declared, href=HEX_HREF, raw_rows=None):
        import duckdb
        rows = raw_rows if raw_rows is not None else _present(name_nf)
        vals = ", ".join(
            "('%s','%s',%s)" % (n, f, "NULL" if t is None else "'%s'" % t)
            for (n, f, t) in rows)
        repl = "(SELECT * FROM (VALUES %s) _s(name, file_name, type))" % vals

        class Exec:
            def query(self, sql):
                con = duckdb.connect()
                sql2 = re.sub(r"parquet_schema\('[^']*'\)", lambda m: repl, sql)
                cur = con.execute(sql2)
                names = [d[0] for d in cur.description]
                return [dict(zip(names, r)) for r in cur.fetchall()]

        return vs.check_declared_schema_matches_data(_schema_doc(declared, href), Exec())

    def test_clean_reports_nothing(self):
        # h0 is a path partition key (from /h0=*/), so it is legitimately skipped.
        f = self._run({"_cng_fid": 2, "rfb": 2}, ["_cng_fid", "rfb", "h0"])
        self.assertEqual(f, [])

    def test_declared_absent_everywhere_is_hard(self):
        f = self._run({"_cng_fid": 2}, ["_cng_fid", "ghost"])
        self.assertEqual([x.code for x in f], ["declared-column-absent"])
        self.assertEqual(f[0].severity, vs.HARD)
        self.assertIn("ghost", f[0].message)

    def test_heterogeneous_hole_is_hard_and_counts_files(self):
        # THE #520 case: _cng_fid present in only some files.
        f = self._run({"_cng_fid": 99, "rfb": 121}, ["_cng_fid", "rfb"])
        self.assertEqual([x.code for x in f], ["declared-column-heterogeneous"])
        self.assertEqual(f[0].severity, vs.HARD)
        self.assertIn("22 of 121", f[0].message)

    def test_undocumented_extra_is_advisory(self):
        f = self._run({"_cng_fid": 2, "surprise": 2}, ["_cng_fid"])
        self.assertEqual([x.code for x in f], ["undocumented-column"])
        self.assertEqual(f[0].severity, vs.ADVISORY)
        self.assertIn("surprise", f[0].message)

    def test_partition_key_absent_from_footer_is_not_flagged(self):
        # Mutation guard: a partition key lives in the PATH, not the footer. Declaring h0
        # while parquet_schema shows no h0 must NOT read as an absent column.
        f = self._run({"_cng_fid": 2}, ["_cng_fid", "h0"])
        self.assertEqual(f, [])

    def test_geometry_column_is_skipped(self):
        # geometry may be writer-named differently; skip it both directions.
        f = self._run({"_cng_fid": 1}, ["_cng_fid", "geom"], href="https://x/d.parquet")
        self.assertEqual(f, [])

    def test_nested_list_column_is_present_not_absent(self):
        # A top-level LIST column (`country_codes VARCHAR[]`) is a parquet GROUP node with
        # physical type NULL; its only leaf is the internal `element`. Declaring it must NOT
        # read as absent (data-workflows#509: iucn-taxonomy, Overture names/sources).
        raw = [("_cng_fid", "f0", "INT"),
               ("country_codes", "f0", None),   # LIST group node
               ("list", "f0", None), ("element", "f0", "BYTE_ARRAY")]
        f = self._run({}, ["_cng_fid", "country_codes"], raw_rows=raw)
        self.assertEqual(f, [])

    def test_multilevel_partition_key_not_flagged(self):
        # Two-level hive partition Z=*/h0=*: both keys are path-supplied, so declaring `h0`
        # must not read as absent (the consecutive partitions share a slash, #509).
        self.assertEqual(
            vs._partition_keys("https://x/glwd/class-area-hex/Z=*/h0=*/data_0.parquet"),
            {"z", "h0"})
        raw = [("area_ha", "f0", "INT")]   # file stores neither Z nor h0
        f = self._run({}, ["area_ha", "h0"], raw_rows=raw,
                      href="https://x/glwd/class-area-hex/Z=*/h0=*/data_0.parquet")
        self.assertEqual(f, [])

    def test_wide_schema_is_not_truncated(self):
        # #509 regression: 160 present+declared columns must all read present. A row-parsed
        # 50-row preview would fabricate ~110 'absent' findings here.
        wide = {f"col{i}": 1 for i in range(160)}
        f = self._run(wide, [f"col{i}" for i in range(160)], href="https://x/d.parquet")
        self.assertEqual(f, [])


# --- #535: a vector hex must hold every feature of its flat GeoParquet -------

FLAT_HREF = "https://s3-west.nrp-nautilus.io/public-x/d/d.parquet"


def _cov_doc(hex_cols=("_cng_fid", "h10", "h0"), with_flat=True, **hex_kw):
    assets = {"d-hex": hex_asset(list(hex_cols), **hex_kw)}
    if with_flat:
        assets["d-parquet"] = {"href": FLAT_HREF, "type": PARQUET,
            "table:columns": [{"name": "_cng_fid"}, {"name": "geom", "type": "geometry"}]}
    return {"assets": assets}


def _cov_mcp(flat_n, hex_d, hex_nulls=0):
    return ScriptedMCP([
        ("COUNT(*) AS n FROM read_parquet", [{"n": flat_n}]),
        ("COUNT(DISTINCT _cng_fid) AS d", [{"d": hex_d, "nulls": hex_nulls}]),
    ])


class HexHoldsAllFeatures(unittest.TestCase):
    def test_equal_counts_report_nothing(self):
        self.assertEqual(
            vs.check_hex_holds_all_features(_cov_doc(), _cov_mcp(105, 105)), [])

    def test_short_hex_is_hard(self):
        # THE #520 case: hex holds 104 of 105.
        f = vs.check_hex_holds_all_features(_cov_doc(), _cov_mcp(105, 104))
        self.assertEqual([x.code for x in f], ["hex-missing-features"])
        self.assertEqual(f[0].severity, vs.HARD)
        self.assertIn("104 of 105", f[0].message)

    def test_raster_hex_without_cng_fid_is_skipped_not_queried(self):
        doc = _cov_doc(hex_cols=("h8", "h0"), with_flat=False)
        mcp = _cov_mcp(1, 1)
        self.assertEqual(vs.check_hex_holds_all_features(doc, mcp), [])
        self.assertEqual(mcp.sql, [], "must not query a raster-derived hex")

    def test_null_key_is_advisory_not_hard(self):
        f = vs.check_hex_holds_all_features(_cov_doc(), _cov_mcp(105, 90, hex_nulls=15))
        self.assertEqual([x.code for x in f], ["hex-coverage-unverifiable"])
        self.assertEqual(f[0].severity, vs.ADVISORY)

    def test_documented_shortfall_is_accepted(self):
        doc = _cov_doc(description="Two features are smaller than one cell and polyfill "
                                   "to zero cells, so are absent from the hex.")
        self.assertEqual(vs.check_hex_holds_all_features(doc, _cov_mcp(105, 103)), [])

    def test_extra_features_is_hard(self):
        f = vs.check_hex_holds_all_features(_cov_doc(), _cov_mcp(105, 106))
        self.assertEqual([x.code for x in f], ["hex-extra-features"])
        self.assertEqual(f[0].severity, vs.HARD)

    def test_multilayer_pairs_by_stem_not_any_two(self):
        # rfb short, vme complete: only rfb must be flagged, and rfb's hex must be compared
        # to rfb's flat (by stem), never to vme's.
        rfb_hex = "https://s3-west.nrp-nautilus.io/public-x/rfmo/rfb/hex/h0=*/data_0.parquet"
        vme_hex = "https://s3-west.nrp-nautilus.io/public-x/rfmo/vme/hex/h0=*/data_0.parquet"
        flat = lambda p: {"href": f"https://s3-west.nrp-nautilus.io/public-x/rfmo/{p}.parquet",
                          "type": PARQUET,
                          "table:columns": [{"name": "_cng_fid"}, {"name": "geom", "type": "geometry"}]}
        doc = {"assets": {
            "rfb-hex": hex_asset(["_cng_fid", "h8", "h0"], href=rfb_hex),
            "vme-hex": hex_asset(["_cng_fid", "h8", "h0"], href=vme_hex),
            "rfb-parquet": flat("rfb"), "vme-parquet": flat("vme"),
        }}
        mcp = ScriptedMCP([
            ("read_parquet('s3://public-x/rfmo/rfb.parquet')", [{"n": 105}]),
            ("read_parquet('s3://public-x/rfmo/vme.parquet')", [{"n": 50}]),
            ("rfb/hex/h0=*/data_0.parquet')", [{"d": 104, "nulls": 0}]),
            ("vme/hex/h0=*/data_0.parquet')", [{"d": 50, "nulls": 0}]),
        ])
        f = vs.check_hex_holds_all_features(doc, mcp)
        self.assertEqual([x.code for x in f], ["hex-missing-features"])
        self.assertIn("rfb-hex", f[0].message)
        self.assertIn("104 of 105", f[0].message)


class ValuesMatchDistinctArtifactTokens(unittest.TestCase):
    """A declared null/nan/none is a real category, not a missing-value artifact (#511).

    The filter that drops pandas/str(None) leakage from the ingested DISTINCT set must not
    fire on a token the schema itself declares — otherwise a genuine, populated category
    (WDPA NO_TAKE='None', 1,545 rows) is both hidden and reported as declared-but-absent.
    The decision is made in Python before the query, so assert on the generated SQL."""

    def _sql_for(self, values):
        asset = {"href": "https://s3-west.nrp-nautilus.io/public-x/d.parquet",
                 "type": PARQUET,
                 "table:columns": [{"name": "NO_TAKE", "type": "string",
                                    "values": values}]}
        doc = {"assets": {"d-parquet": asset}}
        mcp = StubMCP(rows=[])
        vs.check_values_match_distinct(doc, mcp)
        self.assertEqual(len(mcp.sql), 1)
        return mcp.sql[0]

    def test_undeclared_tokens_are_filtered(self):
        sql = self._sql_for(["All", "Part"]).lower()
        self.assertIn("not in ('null', 'nan', 'none')", sql)

    def test_declared_none_is_kept_on_ingested_side(self):
        sql = self._sql_for(["All", "Part", "None"]).lower()
        # 'none' must drop out of the exclusion so the ingested 'None' survives to match.
        self.assertIn("not in ('null', 'nan')", sql)
        self.assertNotIn("'none'", sql.split(") t(v)")[0].split("declared")[0])

    def test_all_artifact_tokens_declared_removes_exclusion(self):
        sql = self._sql_for(["Null", "NaN", "None", "Real"]).lower()
        # nothing left to exclude → no NOT IN artifact clause at all
        self.assertNotIn("not in ('null'", sql)
        self.assertNotIn("not in ('nan'", sql)
        self.assertNotIn("not in ('none'", sql)


class HexFidMatchesFlat(unittest.TestCase):
    """#549: a vector hex must carry the SAME _cng_fid numbering as its flat GeoParquet.
    Presence (#369) and cardinality (#535) both pass a renumbered hex; this joins on
    _cng_fid and asserts a shared witness attribute agrees. The query returns a single
    aggregate row, so a stub replaying that row exercises the finding logic."""

    def _doc(self, witness=True):
        flat_cols = [{"name": "_cng_fid", "type": "int64"}, {"name": "geom", "type": "geometry"}]
        hex_cols = ["_cng_fid", "h0"]
        if witness:
            flat_cols.insert(1, {"name": "GEOID", "type": "string"})
            hex_cols.insert(1, "GEOID")
        return {"assets": {
            "d-parquet": {"href": "https://s3-west.nrp-nautilus.io/public-x/d.parquet",
                          "type": PARQUET, "table:columns": flat_cols},
            "d-hex": hex_asset(hex_cols)}}

    def test_mismatch_is_hard(self):
        f = vs.check_hex_fid_matches_flat(self._doc(), StubMCP(rows=[{"n_join": 56, "mism": 56, "fdist": 56}]))
        self.assertEqual([x.code for x in f], ["hex-fid-mismatch"])
        self.assertEqual(f[0].severity, vs.HARD)

    def test_full_agreement_is_clean(self):
        f = vs.check_hex_fid_matches_flat(self._doc(), StubMCP(rows=[{"n_join": 56, "mism": 0, "fdist": 56}]))
        self.assertEqual(f, [])

    def test_constant_witness_is_advisory_not_hard(self):
        # fdist<=1: the witness can't distinguish a permutation, so never a false HARD.
        f = vs.check_hex_fid_matches_flat(self._doc(), StubMCP(rows=[{"n_join": 56, "mism": 56, "fdist": 1}]))
        self.assertEqual([x.code for x in f], ["hex-fid-identity-unverifiable"])
        self.assertEqual(f[0].severity, vs.ADVISORY)

    def test_no_shared_witness_is_advisory_and_unqueried(self):
        mcp = StubMCP(rows=[{"n_join": 1, "mism": 1, "fdist": 1}])
        f = vs.check_hex_fid_matches_flat(self._doc(witness=False), mcp)
        self.assertEqual([x.code for x in f], ["hex-fid-identity-unverifiable"])
        self.assertEqual(mcp.sql, [], "no witness → must not query")


if __name__ == "__main__":
    unittest.main()
