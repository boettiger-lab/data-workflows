#!/usr/bin/env python3
"""
verify-stac.py — one verifier for the whole STAC-correctness check suite.

Promotes every written STAC rule in AGENTS.md from "an agent remembered it" to an
enforced gate. Runs three tiers of checks against a published STAC collection:

  HARD      — a real defect; exits non-zero. Blocks merge / publish.
  ADVISORY  — informational; printed but never affects exit code (keeps the gate
              precise — see the categorical recall gap below).

Static checks (no data; just the STAC JSON):
  - license present + a recognized SPDX id, or other/various/proprietary WITH a
    license link — EXCEPT a meta-collection (has child links) may use various/other
    with no link, since the licenses live on (and are gated per) its children
  - nav links: self/root/parent present + well-formed; child (if any) well-formed
  - extent.temporal.interval present, each endpoint RFC 3339 (or null for an open
    end), start not after end — pystac parses these eagerly, so a malformed value
    makes the whole collection unloadable for every MCP consumer
  - asset keys follow {last-segment}-{format}; no generic keys
    (pmtiles/geoparquet/hex/parquet/cog/h3-parquet)
  - hex asset href uses the hive glob  …/hex/h0=*/data_0.parquet  (not a bare dir)
  - hex asset declares h3:native_resolution + h3:parent_resolutions (incl 0)
  - vector:layers on every PMTiles asset
  - table:columns on each parquet asset (NOT collection-level); geometry column
    included on the geoparquet asset, excluded on the hex asset
  - universal `_cng_fid` on vector assets (#369): HARD for a flat GeoParquet-with-
    geometry or a vector hex lacking it; raster-derived hex (no vector source in the
    collection) is exempt; a non-spatial table is ADVISORY (see the advisory list)
  - per-feature-duplication warning on aggregatable hex columns (area/length/
    count/amount/…)
  - categorical raster COG classification:classes completeness  [reuses lint-stac-categorical]
  - point datasets: a processing-resolution note in description/processing:notes
  - categorical column completeness (values + inline CODE=Name)  [reuses lint-stac-categorical]
  - PMTiles tile-accurate table:columns                          [reuses lint-stac-pmtiles-fields]

Data-backed checks (delegated to the duckdb-geo MCP server, --no-data to skip):
  - every coded column's `values` array == the ingested DISTINCT set (automates the
    #114/#294 lesson; column-projected, never decodes the geometry chunk)
  - HARD: hex asset with an undocumented NULL finest-parent column (a coarser column
    is fully populated) — joining on it silently drops the largest features (#309 §2)
  - ADVISORY: polygon/point asset where a candidate feature-id column has rows ≫
    DISTINCT — possible per-feature row duplication (#309 §1; FP-prone, so advisory)
  - HARD: an inline hex-area formula in any column description / prose field — both the
    nominal-constant recipe (`… × cell_area_at_resolution_N`, a global average that ran
    the ca-30x30 CA extent ~6% low) and an inlined exact `h3_cell_area()` call; the
    area method belongs in the h3-guide, not baked into STAC where it goes stale (#389)

Advisory passes (never block):
  - recall: candidate string-categorical columns with a low DISTINCT count and no
    `values` array — catches the recall gap that missed PAD-US IUCN_Cat / Pub_Access
  - non-spatial parquet table with no `_cng_fid` — may be a feature fact table that
    should carry it, or a legit lookup/crosswalk/scores table (#369; human judgment)

Usage:
    scripts/verify-stac.py <collection-url-or-path> [...]
    scripts/verify-stac.py --bucket public-census --dataset census-2024/tract
    scripts/verify-stac.py --no-data <url>            # static + advisory only
    scripts/verify-stac.py --strict <url>             # promote chosen advisories to hard

Exit 0 = no HARD findings. Exit 1 = one or more HARD findings.

The heavy data check POSTs SQL to the public duckdb-geo MCP endpoint
(https://duckdb-mcp.nrp-nautilus.io/mcp, no auth), so it is not bound by GitHub
runner resources or the slow public S3 endpoint. Set MCP_ENDPOINT to override and
MCP_AUTH_TOKEN for a bearer token if the endpoint is ever locked down.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Severities & finding model
# ---------------------------------------------------------------------------

HARD = "HARD"
ADVISORY = "ADVISORY"


class Finding:
    __slots__ = ("severity", "code", "message")

    def __init__(self, severity: str, code: str, message: str):
        self.severity = severity
        self.code = code
        self.message = message

    def render(self, collection_id: str) -> str:
        tag = "ADVISORY" if self.severity == ADVISORY else "HARD"
        return f"[{tag}][{self.code}] [{collection_id}] {self.message}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

NRP = "https://s3-west.nrp-nautilus.io"
SCRIPT_DIR = Path(__file__).resolve().parent


def load_doc(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as r:
            return json.load(r)
    return json.loads(Path(source).read_text())


# Buckets that hold pipeline infrastructure / the root catalog, never a dataset.
INFRA_BUCKETS = {"public-grids", "public-data", "public-output", "public-test",
                 "public-requests"}


def targets_from_yaml(text: str) -> set[tuple[str, str]]:
    """Extract (bucket, dataset) collection targets from a generated workflow YAML.

    The cng-datasets manifests reference each dataset by its S3 paths — e.g.
    s3://public-census/census-2024/tract.parquet, …/tract/hex, …/tract/chunks —
    which all collapse to the dataset 'census-2024/tract'. We never see the STAC URL
    in-repo (STAC lives only on S3), so the S3 path is the signal.
    """
    targets = set()
    for bucket, rest in re.findall(r"s3://(public-[a-z0-9-]+)/([^\s'\"]+)", text):
        if bucket in INFRA_BUCKETS:
            continue
        rest = rest.strip("/")
        # Skip raw/staging inputs — never a dataset collection. `raw` may be a
        # top-level prefix (public-census/raw/…) OR nested under a domain prefix
        # (public-rivers/american-rivers/raw/<ds>-src.parquet, the staging layout
        # used when re-converting an existing GeoParquet), so exclude `raw` as ANY
        # path segment, not just the leading one.
        if not rest or "raw" in rest.split("/"):
            continue  # bucket-level / raw inputs aren't a dataset collection
        if re.search(r"\.(tif|tiff)$", rest, re.I):
            continue  # a COG raster (`<name>-cog.tif`, `…-cog-4326.tif`, …) is an asset
                      # of a collection, not a collection itself; the collection is
                      # derived from the dataset's hex/parquet path elsewhere in the YAML
        rest = re.sub(r"\.(parquet|pmtiles|gpkg|geojson)$", "", rest)
        for marker in ("/hex/", "/hex", "/chunks/", "/chunks", "/temp_versions"):
            i = rest.find(marker)
            if i >= 0:
                rest = rest[:i]
                break
        rest = rest.strip("/")
        if rest and rest != "raw":
            targets.add((bucket, rest))
    return targets


def derive_url(bucket: str, dataset: str) -> str:
    """Collection URL from --bucket/--dataset, per the catalog's self-link convention:
    https://s3-west.nrp-nautilus.io/<bucket>/<dataset>/stac-collection.json
    A dataset of '' (bucket-level collection) → …/<bucket>/stac-collection.json.
    """
    bucket = bucket.strip("/")
    dataset = (dataset or "").strip("/")
    path = f"{bucket}/{dataset}" if dataset else bucket
    return f"{NRP}/{path}/stac-collection.json"


def _collection_exists(url: str) -> bool:
    """True if a STAC doc loads at url (used to fall back to a bucket-level collection)."""
    try:
        load_doc(url)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Reuse the two existing standalone linters (filenames have dashes → import by path)
# ---------------------------------------------------------------------------

def _load_sibling(modname: str, filename: str):
    path = SCRIPT_DIR / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_categorical = _load_sibling("lint_stac_categorical", "lint-stac-categorical.py")
_pmtiles = _load_sibling("lint_stac_pmtiles_fields", "lint-stac-pmtiles-fields.py")


# ---------------------------------------------------------------------------
# SPDX
# ---------------------------------------------------------------------------

# Curated set of SPDX ids that actually appear (or plausibly will) in this catalog,
# plus the sanctioned non-SPDX escape hatches. An id outside this set that still
# matches the SPDX shape is ADVISORY, not HARD — we don't want to block on an
# obscure-but-valid id we haven't enumerated.
KNOWN_SPDX = {
    "CC0-1.0", "CC-BY-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0",
    "CC-BY-SA-3.0", "CC-BY-SA-4.0", "CC-BY-NC-3.0", "CC-BY-NC-4.0",
    "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-4.0", "CC-BY-ND-4.0", "CC-BY-NC-ND-4.0",
    "CDLA-Permissive-1.0", "CDLA-Permissive-2.0", "CDLA-Sharing-1.0",
    "ODbL-1.0", "ODC-By-1.0", "PDDL-1.0",
    "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "GPL-3.0-only",
    "OGL-UK-3.0",
}
# Sanctioned non-SPDX values (AGENTS.md): escape hatches + US federal works.
NON_SPDX_OK = {"other", "various", "proprietary", "public-domain"}
# These REQUIRE an accompanying license link.
NEED_LICENSE_LINK = {"other", "various", "proprietary"}
SPDX_SHAPE = re.compile(r"^[A-Za-z0-9.+-]+$")

GENERIC_ASSET_KEYS = {"pmtiles", "geoparquet", "hex", "parquet", "cog", "h3-parquet", "h3"}

# Name tokens that mark a hex column as a per-feature magnitude — a value that is
# wrong to SUM across the duplicated (feature, cell) rows. Matched against *name*
# tokens only (never the description: e.g. PAD-US descriptions all contain
# "protected area", which would match everything), and only when the column type
# is numeric (a per-feature total is never a string/struct).
AGGREGATABLE_TOKENS = {
    "acre", "acres", "area", "areas", "length", "perimeter", "perim",
    "population", "pop", "count", "counts", "amount", "funding", "fund",
    "hectare", "hectares", "person", "persons", "dollar", "dollars", "cost",
    "mile", "miles", "sum", "total", "aland", "awater",
}
SAFE_HEX_COLS = {"h0", "h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "h9",
                 "h10", "h11", "h12", "_cng_fid", "bbox"}
GEOM_COLS = {"geometry", "geom", "shape", "the_geom", "wkb_geometry"}  # compared lowercased


def _is_numeric_type(t: str) -> bool:
    return t.lower().startswith(("int", "uint", "float", "double", "decimal", "number"))


def _name_tokens(name: str) -> set[str]:
    """Split a column name on underscores and camelCase boundaries; lowercase."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return {t.lower() for t in re.split(r"[_\W]+", spaced) if t}


def _is_geom_col(name: str) -> bool:
    return name.lower() in GEOM_COLS


def is_parquet(asset: dict) -> bool:
    return "parquet" in asset.get("type", "")


_H0_PARTITION = re.compile(r"/h0=\*/")


def is_hex_asset(key: str, asset: dict) -> bool:
    """A hive-partitioned H3 asset. The `h0=*` partition glob is the substantive signal:
    partition-dir names vary across the catalog (hex, hex-fractions, hex-max, hex-mean,
    hex-weights, taxonomy, p80-hex), and keying only off `/hex/` or a `-hex` key suffix
    silently skipped the h3-resolution / glob / hex-dup checks on every variant name and
    mis-flagged them as flat GeoParquet missing a geometry column."""
    href = asset.get("href", "")
    return ("/hex/" in href or key.endswith("-hex") or key == "hex"
            or bool(_H0_PARTITION.search(href)))


def is_pmtiles(asset: dict) -> bool:
    return "pmtiles" in asset.get("type", "")


def is_cog(asset: dict) -> bool:
    t = asset.get("type", "")
    return "tiff" in t or "geotiff" in t or bool(asset.get("raster:bands"))


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------

def check_license(doc: dict) -> list[Finding]:
    out = []
    lic = doc.get("license")
    links = doc.get("links", [])
    has_license_link = any(l.get("rel") == "license" for l in links)

    if not lic:
        out.append(Finding(HARD, "license-missing",
                            "collection has no top-level `license` — set the upstream "
                            "SPDX id (or other/various/proprietary/public-domain)."))
        return out

    if lic in NON_SPDX_OK:
        if lic in NEED_LICENSE_LINK and not has_license_link:
            # A meta-collection (one that has child links) may declare 'various' or
            # 'other' WITHOUT its own license link: the real licenses live on the
            # child collections — each verified individually — and downstream gating
            # (source.coop redistribution excludes, per-dataset decisions) keys on
            # those per-child licenses, not the parent. A single parent-level link
            # would be misleading for genuinely mixed children. 'proprietary' is NOT
            # exempted (it asserts specific restrictive terms, not "see children"),
            # and a LEAF collection (no children) still needs the link — that catches
            # the lazy-'various'-default case.
            is_meta = lic in {"various", "other"} and any(
                l.get("rel") == "child" for l in links)
            if not is_meta:
                out.append(Finding(HARD, "license-link-missing",
                                    f"license is '{lic}' but there is no "
                                    f"{{'rel':'license'}} link to the canonical terms URL "
                                    f"(exempt only for a meta-collection with child links, "
                                    f"whose per-child licenses govern; this is a leaf)."))
        return out

    if lic in KNOWN_SPDX:
        return out

    if SPDX_SHAPE.match(lic):
        out.append(Finding(ADVISORY, "license-unknown-spdx",
                            f"license '{lic}' is not in the verifier's known-SPDX set — "
                            f"confirm it is a valid SPDX identifier (verifier set is "
                            f"curated, not exhaustive)."))
    else:
        out.append(Finding(HARD, "license-invalid",
                            f"license '{lic}' is neither a recognized SPDX id nor one of "
                            f"{sorted(NON_SPDX_OK)} — do not guess; verify upstream terms."))
    return out


def check_nav_links(doc: dict) -> list[Finding]:
    out = []
    links = doc.get("links", [])
    by_rel = {}
    for l in links:
        by_rel.setdefault(l.get("rel"), []).append(l)

    for rel in ("self", "root", "parent"):
        got = by_rel.get(rel)
        if not got:
            out.append(Finding(HARD, f"nav-{rel}-missing",
                                f"missing required navigation link rel='{rel}'."))
            continue
        href = got[0].get("href", "")
        if not href.startswith(("http://", "https://")):
            out.append(Finding(HARD, f"nav-{rel}-malformed",
                                f"rel='{rel}' link href is not an absolute URL: {href!r}."))

    # root should point at the canonical root catalog
    root = by_rel.get("root")
    if root and "public-data/stac/catalog.json" not in root[0].get("href", ""):
        out.append(Finding(ADVISORY, "nav-root-noncanonical",
                            f"rel='root' is {root[0].get('href')!r}; canonical root is "
                            f"{NRP}/public-data/stac/catalog.json."))

    # child is optional (leaf collections have none) but must be well-formed if present
    for c in by_rel.get("child", []):
        if not c.get("href", "").startswith(("http://", "https://")):
            out.append(Finding(HARD, "nav-child-malformed",
                                f"a rel='child' link href is not an absolute URL: "
                                f"{c.get('href')!r}."))
        if c.get("rel") == "item":
            out.append(Finding(HARD, "nav-child-is-item",
                                "sub-collections must use rel='child', not 'item' "
                                "(item is for STAC Items/features)."))
    return out


# --- temporal extent: RFC 3339, or the collection is unloadable ------------
# STAC requires every `extent.temporal.interval` endpoint to be an RFC 3339
# date-time (or null for an open end). pystac parses these EAGERLY when it loads
# a collection, via dateutil.isoparse -- so a malformed endpoint is not a
# cosmetic defect, it makes the entire collection fail to load for every MCP
# consumer, silently. That is exactly how the seven BLM MLRS mineral collections
# went missing from the served catalog (mcp-data-server side: pystac raised
# "ValueError: Unused components in ISO string" and skipped the child).
#
# NOTE ON THE IMPLEMENTATION: do NOT reach for datetime.fromisoformat() here.
# On Python 3.11+ it is lenient enough to ACCEPT the very string that broke us --
# fromisoformat("1974-03-01T00:00:00.000000T00:00:00Z") returns a datetime rather
# than raising, so a fromisoformat-based gate would have passed these seven
# collections too. dateutil.isoparse (what the consumer actually uses) rejects
# it, but this verifier is deliberately stdlib-only -- CI runs it on a bare
# setup-python with no pip install step -- so match RFC 3339 explicitly instead.
# The pattern is stricter than either parser: it also requires a timezone
# designator and rejects a bare date, both of which STAC mandates.
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def check_temporal_extent(doc: dict) -> list[Finding]:
    out = []
    extent = doc.get("extent")
    if not isinstance(extent, dict):
        return [Finding(HARD, "temporal-extent-missing",
                        "collection has no `extent` object.")]
    temporal = extent.get("temporal")
    if not isinstance(temporal, dict) or not isinstance(temporal.get("interval"), list) \
            or not temporal["interval"]:
        return [Finding(HARD, "temporal-extent-missing",
                        "collection has no `extent.temporal.interval` "
                        "(STAC requires one, with null for an open end).")]

    for pair in temporal["interval"]:
        if not isinstance(pair, list) or len(pair) != 2:
            out.append(Finding(HARD, "temporal-interval-malformed",
                                f"`extent.temporal.interval` entry is not a "
                                f"[start, end] pair: {pair!r}."))
            continue
        parsed = []
        for v in pair:
            if v is None:          # legitimate open start/end
                parsed.append(None)
                continue
            if not isinstance(v, str) or not RFC3339.match(v):
                out.append(Finding(HARD, "temporal-not-rfc3339",
                                    f"temporal extent endpoint {v!r} is not an "
                                    f"RFC 3339 date-time (expected e.g. "
                                    f"'1920-05-15T00:00:00Z'). pystac refuses to "
                                    f"load a collection with this value, so the "
                                    f"dataset disappears from the served catalog."))
                parsed.append(None)
                continue
            # Safe only because RFC3339 already gated the format above: compare as
            # real instants so a mixed 'Z' / '+05:00' pair can't compare backwards
            # the way a lexical string compare would.
            parsed.append(datetime.fromisoformat(v.replace("Z", "+00:00")))
        lo, hi = parsed
        if lo and hi and lo > hi:
            out.append(Finding(HARD, "temporal-interval-reversed",
                                f"temporal extent starts after it ends: "
                                f"{pair[0]} > {pair[1]}."))
    return out


def check_asset_keys(doc: dict) -> list[Finding]:
    out = []
    for key in doc.get("assets", {}):
        if key in GENERIC_ASSET_KEYS:
            out.append(Finding(HARD, "asset-key-generic",
                                f"asset key '{key}' is a generic format name — use "
                                f"'{{last-segment}}-{{format}}' (e.g. 'tract-{key}') so keys "
                                f"don't collide across collections."))
    return out


def check_hex_assets(doc: dict) -> list[Finding]:
    out = []
    for key, asset in doc.get("assets", {}).items():
        if not (is_parquet(asset) and is_hex_asset(key, asset)):
            continue
        href = asset.get("href", "")
        # hive glob, not a bare directory. Any partition-dir name is valid
        # (hex, hex-max, hex-mean, p80-hex, …) — the requirement is the
        # h0=* partition glob + a filename, which is what rejects a bare dir.
        if not re.search(r"/h0=\*/[^/]+\.parquet$", href):
            out.append(Finding(HARD, "hex-href-not-glob",
                                f"asset '{key}' hex href must be the hive glob "
                                f"…/h0=*/data_0.parquet (not a bare directory), got {href!r}."))
        # h3 resolutions declared
        native = asset.get("h3:native_resolution")
        parents = asset.get("h3:parent_resolutions")
        if native is None:
            out.append(Finding(HARD, "hex-no-native-res",
                                f"asset '{key}' missing 'h3:native_resolution'."))
        if parents is None:
            out.append(Finding(HARD, "hex-no-parent-res",
                                f"asset '{key}' missing 'h3:parent_resolutions'."))
        elif 0 not in parents:
            out.append(Finding(HARD, "hex-parent-res-no-0",
                                f"asset '{key}' h3:parent_resolutions {parents} must "
                                f"include 0 (the partition key)."))
    return out


def check_vector_layers(doc: dict) -> list[Finding]:
    out = []
    for key, asset in doc.get("assets", {}).items():
        if is_pmtiles(asset) and not asset.get("vector:layers"):
            out.append(Finding(HARD, "pmtiles-no-vector-layers",
                                f"PMTiles asset '{key}' missing 'vector:layers' "
                                f"(the MapLibre source-layer id)."))
    return out


def check_table_columns_placement(doc: dict) -> list[Finding]:
    out = []
    if "table:columns" in doc:
        out.append(Finding(HARD, "table-columns-collection-level",
                            "`table:columns` is at the collection level — it must live on "
                            "each parquet asset, not the collection."))
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset):
            continue
        cols = asset.get("table:columns")
        if not cols:
            out.append(Finding(HARD, "parquet-no-table-columns",
                                f"parquet asset '{key}' has no 'table:columns'."))
            continue
        has_geom = any(_is_geom_col(c.get("name", "")) for c in cols)
        is_hex = is_hex_asset(key, asset)
        if is_hex and has_geom:
            out.append(Finding(HARD, "hex-has-geom-column",
                                f"hex asset '{key}' lists a geometry column in "
                                f"table:columns — hex parquet has no geometry; remove it."))
        if not is_hex and not has_geom:
            out.append(Finding(ADVISORY, "geoparquet-no-geom-column",
                                f"geoparquet asset '{key}' table:columns lists no geometry "
                                f"column ({sorted(GEOM_COLS)}); confirm it isn't a hex asset."))
    return out


def check_column_description_consistency(doc: dict) -> list[Finding]:
    """One text per column NAME per collection — the mcp-data-server#303 fold.

    `get_stac_details` folds per-column descriptions across every asset in the collection
    and **first-seen wins**, so a column documented two ways loses one version silently.
    That is not merely redundant text: whichever asset happens to be listed first decides
    what every consumer reads about that column on *all* assets.

    Two ways this bites, both observed on ca30x30-conserved-areas-terrestrial-2025
    (data-workflows#512):

      * A hex-only clause appended to a column that also exists on the flat GeoParquet
        ("…repeated on every hex cell — dedup by _cng_fid first") is dropped, because the
        flat is listed first. Eight duplication warnings were invisible this way. Such a
        note belongs in the hex asset's own `description`, which is always rendered.
      * A newly added asset that words a shared column differently loses to the older
        asset — and the older text may be *false* for the new asset. Here the surviving
        h10 text said "one row per (feature, h10) pair", true for the hex asset and wrong
        for the per-cell hex-weights assets.

    ADVISORY rather than HARD for now: pre-gate collections have not been swept yet
    (data-workflows#509), so a hard failure would block unrelated PRs. Promote to HARD
    once the catalog is fold-clean. Columns with no description (a lean PMTiles asset,
    per the PMTiles standard) are skipped — omitting text is not disagreeing about it.
    """
    out = []
    seen: dict[str, tuple[str, str]] = {}
    clashes: dict[str, set[str]] = {}
    for key, asset in doc.get("assets", {}).items():
        for col in asset.get("table:columns", []):
            name, text = col.get("name", ""), col.get("description", "")
            if not name or not text:
                continue
            if name in seen and seen[name][1] != text:
                clashes.setdefault(name, {seen[name][0]}).add(key)
            seen.setdefault(name, (key, text))
    for name, assets in sorted(clashes.items()):
        winner = seen[name][0]
        out.append(Finding(ADVISORY, "column-description-divergent",
            f"column '{name}' is documented differently on {sorted(assets)} — the #303 fold "
            f"keeps the first-seen text (from '{winner}') and silently drops the others. Use "
            f"one text everywhere; put asset-specific notes in that asset's `description`."))
    return out


def check_hex_dup_warning(doc: dict) -> list[Finding]:
    """Any aggregatable per-feature column on a hex asset must warn that it is repeated
    per (feature, cell) and give a dedup recipe."""
    out = []
    # Aggregation guidance may live at the hex ASSET-description level (or the
    # collection description) rather than per-column. That is in fact the location
    # the mcp-data-server renderer preserves: get_stac_details dedups per-column
    # descriptions across assets (mcp-data-server#303), so a per-column note on the
    # hex that differs from the flat's description is silently dropped from what the
    # LLM sees — while the per-asset `description` line is always rendered. So a note
    # on the hex asset (or collection) description satisfies this check. Per-column
    # notes are still accepted (legacy datasets) — this only ADDS the asset-level path.
    ASSET_NOTE = re.compile(
        r"repeated (on|for|across) (every|the)|never (use )?sum|do not sum|don't sum|"
        r"not safe to sum|per[- ]?feature|count\(distinct|select distinct|dedup|"
        r"deduplicat|multiply by .*cell area|sum is the .*total|area-weighted|reducer",
        re.I)
    coll_desc = doc.get("description", "") or ""
    for key, asset in doc.get("assets", {}).items():
        if not (is_parquet(asset) and is_hex_asset(key, asset)):
            continue
        # Asset-level (or collection-level) aggregation note → requirement satisfied
        # for the whole asset (this is what the renderer surfaces).
        if ASSET_NOTE.search(asset.get("description", "") or "") or ASSET_NOTE.search(coll_desc):
            continue
        for col in asset.get("table:columns", []):
            name = col.get("name", "")
            if name in SAFE_HEX_COLS or _is_geom_col(name):
                continue
            # Per-feature totals are numeric; a string/struct column is never one.
            if not _is_numeric_type(col.get("type", "")):
                continue
            if not (_name_tokens(name) & AGGREGATABLE_TOKENS):
                continue
            desc = col.get("description", "")
            warns = bool(re.search(
                r"repeated (on|for) every|never (use )?sum|do not sum|don't sum|"
                r"per[- ]?\(?feature|count\(distinct|row_number|select distinct|"
                r"deduplicat|dedup", desc, re.I))
            if not warns:
                out.append(Finding(HARD, "hex-dup-warning-missing",
                                    f"hex asset '{key}' column '{name}' looks like a "
                                    f"per-feature total but its description has no "
                                    f"duplication warning / dedup recipe (one hex row = one "
                                    f"(feature, cell) pair — SUM over hex double-counts)."))
    return out


def check_point_note(doc: dict) -> list[Finding]:
    """If this is a point dataset, it must document the processing resolution."""
    out = []
    gtype = (doc.get("properties", {}) or {}).get("geometry_type", "")
    text = " ".join([
        doc.get("description", ""),
        json.dumps(doc.get("properties", {}).get("processing:notes", "")),
        doc.get("properties", {}).get("processing:notes", "") if isinstance(
            doc.get("properties", {}).get("processing:notes"), str) else "",
    ]).lower()
    is_pointish = "point" in gtype.lower() or "point observation" in text or "each point" in text
    if not is_pointish:
        return out
    mentions_res = bool(re.search(r"h3 resolution\s*\d+|resolution\s*\d+|→\s*one h3|one h3 cell", text))
    if not mentions_res:
        out.append(Finding(ADVISORY, "point-no-resolution-note",
                            "looks like a point dataset but description/processing:notes "
                            "do not state the H3 processing resolution (each point → one "
                            "cell at res N)."))
    return out


# --- #389 — no inline hex-area formula in published STAC -------------------
# The area-from-hex recipe is generic guidance that lives in
# `mcp-data-server/h3-guide.md` (which the geo-agent reads). Any copy baked into a
# column description or prose field goes stale and becomes actively harmful:
#   * the NOMINAL-CONSTANT form (`… × cell_area_at_resolution_N`) is a global average
#     that undercounted the ca-30x30 California extent ~6% (mcp-data-server#294 / #389);
#   * even the EXACT `h3_cell_area(...)` form must not be inlined — a duplicated copy
#     drifts out of sync with the h3-guide (maintainer's final #389 resolution: the
#     recipe is REMOVED from STAC, not merely corrected).
# So the guard HARD-flags either formula anywhere in the doc. A hex column that is a
# per-feature total should just be flagged "repeated / never SUM on hex / dedup by
# <key>" and defer the area method to the h3-guide.
_AREA_FORMULA_PATTERNS = [
    ("area-recipe-nominal-constant", re.compile(r"cell_area_at_resolution", re.I),
     "the nominal per-resolution constant (a global average — undercounts real cell "
     "area by well over ±5% with latitude; ca-30x30 CA extent was ~6% low, #389)"),
    ("area-recipe-inlined", re.compile(r"h3_cell_area\s*\(", re.I),
     "an inline h3_cell_area() formula (even the exact recipe must not be baked into "
     "STAC — it drifts out of sync with the h3-guide; #389)"),
]


def _iter_strings(obj, path="$"):
    """Yield (json-path, string) for every string leaf in the STAC doc."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, f"{path}[{i}]")


def check_inline_area_formula(doc: dict) -> list[Finding]:
    """HARD-flag any inline hex-area formula in a column description or prose field.

    The area-from-hex method is generic guidance sourced from the h3-guide; a copy in
    published STAC goes stale (see #389). Covers both the nominal-constant recipe and
    an inlined exact `h3_cell_area()` call, wherever they appear in the document.
    """
    out = []
    for path, text in _iter_strings(doc):
        for code, rx, why in _AREA_FORMULA_PATTERNS:
            if rx.search(text):
                out.append(Finding(HARD, code,
                                   f"inline hex-area formula at {path}: {why}. "
                                   f"Remove it — flag the column as a per-feature total "
                                   f"(repeated per hex cell, never SUM on hex, dedup by "
                                   f"key) and defer the area method to mcp-data-server/"
                                   f"h3-guide.md; do not inline the formula."))
    return out




def _asset_has_geom(asset: dict) -> bool:
    return any(_is_geom_col(c.get("name", "")) for c in asset.get("table:columns", []))


def _is_hex_like(key: str, asset: dict) -> bool:
    """A hive-partitioned H3 reduction. `is_hex_asset` only matches the …/hex/ path or a
    `-hex` key suffix; broaden here to ANY `h0=*` partition glob so raster reductions
    published under a variant partition dir — …/hex-max/h0=*/, …/hex-fractions/h0=*/,
    …/taxonomy/h0=*/ (plant-richness, cwhr13, gbif) — are recognised as hexes (hence
    exempted for a raster collection) rather than mistaken for flat non-spatial tables.
    A single-file `…-index.parquet` with only an h0 column is NOT partitioned, so it
    stays a table (correctly advisory)."""
    return is_hex_asset(key, asset) or bool(_H0_PARTITION.search(asset.get("href", "")))


def _collection_has_vector_source(doc: dict) -> bool:
    """True if the collection carries a geometry-bearing feature source — a flat
    GeoParquet with a geometry column, or a PMTiles asset. This (not COG-presence) is
    the robust signal for a *vector* collection: a raster reduce to H3 has neither, even
    when it ships no COG in the same collection (the richness / cwhr / gbif hexes)."""
    for key, asset in doc.get("assets", {}).items():
        if is_pmtiles(asset):
            return True
        if is_parquet(asset) and not is_hex_asset(key, asset) and _asset_has_geom(asset):
            return True
    return False


def _flat_vector_attrs(doc: dict) -> set[str]:
    """Lowercased attribute names documented on the collection's flat vector asset(s),
    excluding H3 indexes, bbox and geometry."""
    out = set()
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset) or is_hex_asset(key, asset):
            continue
        if not _asset_has_geom(asset):
            continue
        for col in asset.get("table:columns", []):
            name = col.get("name", "").lower()
            if name in SAFE_HEX_COLS or _is_geom_col(name):
                continue
            out.add(name)
    return out


def _is_percell_aggregation(doc: dict, asset: dict) -> bool:
    """True for a hex asset that is a per-CELL aggregation — one row per cell — derived
    from the collection's own features, rather than a per-(feature, cell) conversion.

    A cng-datasets vector hex always carries the source feature attributes forward, so it
    necessarily shares attribute names with the flat GeoParquet. A derived aggregation
    shares NONE: every non-index column is newly computed (data-workflows#506
    `…-hex-weights`: h-indexes + w1…w4 + n_units). Such an asset has collapsed the
    feature dimension away, so there is no per-feature identity left to carry and
    `_cng_fid` is as meaningless on it as on a raster reduce — where a row-unique id would
    in fact be actively misleading, since `COUNT(DISTINCT _cng_fid)` would then equal the
    cell count rather than a feature count.

    Deliberately a positive schema test rather than an opt-out flag: a genuine
    `_cng_fid`-missing defect still carries its source attributes and so still HARD-fails.
    """
    flat = _flat_vector_attrs(doc)
    if not flat:
        return False
    attrs = {c.get("name", "").lower() for c in asset.get("table:columns", [])}
    attrs = {c for c in attrs if c not in SAFE_HEX_COLS and not _is_geom_col(c)}
    return bool(attrs) and not (attrs & flat)


def check_cng_fid(doc: dict) -> list[Finding]:
    """Enforce the universal `_cng_fid` contract (#369).

    cng-datasets `convert_to_parquet` synthesizes `_cng_fid` on every conversion —
    always, additive, row-unique — so it is meant to be present on *every* vector
    parquet asset, flat GeoParquet and hex alike. A single uniform key then works for
    dedup / COUNT(DISTINCT) across all datasets, instead of per-dataset id discovery
    (the over-count failures behind #309 / open-llm-proxy#68). Source ids (`ramsarid`,
    `tpl_id`, `GEOID`) may accompany `_cng_fid` for cross-collection joins, but they do
    not replace it.

    The catalog holds three kinds of `_cng_fid`-free parquet, only one of which is a
    defect, so the severity is scoped to the issue's exact wording — a *vector asset
    (polygon/point/line, flat or hex)*:

      HARD — a vector feature conversion that is missing its id:
        - flat GeoParquet WITH a geometry column, or
        - a vector hex (a hex asset in a collection that has a geometry-bearing / PMTiles
          source). This is a `convert_to_parquet` product; `_cng_fid` must be there.

      exempt (silent) — raster-derived hex: a raster reduce into H3, not a feature
        conversion, so it correctly has no per-feature id. Detected as a hex asset whose
        collection has NO vector source (COG-independent — covers carbon/ghs-pop which
        ship a COG *and* richness/cwhr/gbif which do not).

      exempt (silent) — per-cell aggregation of a VECTOR collection's own features
        (#506 `…-hex-weights`): one row per cell, not per (feature, cell). The feature
        dimension is aggregated away, so `_cng_fid` has nothing to identify. Detected by
        `_is_percell_aggregation`: it shares no attribute column with the collection's
        flat GeoParquet, whereas a real conversion always carries its source attributes.

      ADVISORY — a non-spatial parquet table (no geometry, not a vector hex): could be a
        fact table that SHOULD carry `_cng_fid` (tpl `…-funding`, keyed by tpl_id) or a
        legitimate lookup / crosswalk / coefficient / long-form scores table that never
        went through `convert_to_parquet` (nci `predicts-crosswalk`, barred-owl `scores`,
        `taxa-list`). Only a human can tell those apart, so surface it — don't block CI.

    Non-parquet assets (COG, PMTiles, readme) are never checked. Assets with no
    `table:columns` are skipped — `parquet-no-table-columns` already HARD-flags those.

    Schema-level check on the asset's documented `table:columns` (which must mirror the
    real schema); the named offenders omit `_cng_fid` there because the data lacks it.
    """
    out = []
    has_vector_source = _collection_has_vector_source(doc)
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset):
            continue
        cols = asset.get("table:columns", [])
        if not cols:
            continue  # parquet-no-table-columns already HARD-flags a missing schema
        if "_cng_fid" in {c.get("name", "").lower() for c in cols}:
            continue
        hex_ = _is_hex_like(key, asset)
        common = ("cng-datasets synthesizes '_cng_fid' as the universal per-feature id "
                  "on every vector asset (flat + hex); reprocess through cng-datasets so "
                  "one key works for dedup / COUNT(DISTINCT) across datasets. A source id "
                  "(ramsarid, tpl_id, GEOID) may accompany _cng_fid but does not replace it.")
        if hex_:
            if not has_vector_source:
                continue  # raster-derived hex → no per-feature id by design
            if _is_percell_aggregation(doc, asset):
                continue  # per-cell aggregation → feature dimension collapsed by design
            out.append(Finding(HARD, "cng-fid-missing",
                f"vector hex asset '{key}' does not document '_cng_fid'. " + common))
        elif _asset_has_geom(asset):
            out.append(Finding(HARD, "cng-fid-missing",
                f"vector flat GeoParquet asset '{key}' does not document '_cng_fid'. "
                + common))
        else:
            out.append(Finding(ADVISORY, "cng-fid-missing-nonspatial",
                f"non-spatial parquet asset '{key}' has no '_cng_fid'. If it is a feature "
                f"fact table (e.g. per-record funding keyed to a site), it should carry "
                f"_cng_fid — reprocess through cng-datasets. If it is a lookup / crosswalk "
                f"/ coefficient / long-form table, this is expected; leave it."))
    return out


def run_sibling_linter(mod, doc_source: str, code: str) -> list[Finding]:
    """Wrap an existing linter's `lint()` (returns list[str]) as HARD findings."""
    if mod is None:
        return [Finding(ADVISORY, f"{code}-unavailable",
                        f"sibling linter for '{code}' not found next to verify-stac.py.")]
    try:
        errs = mod.lint(doc_source)
    except Exception as e:  # never let a linter crash abort the whole verify
        return [Finding(ADVISORY, f"{code}-error", f"sibling linter '{code}' raised: {e}")]
    # The sibling linters prefix each message with "[collection_id] " — strip it so
    # render() doesn't print the id twice.
    return [Finding(HARD, code, re.sub(r"^\[[^\]]+\]\s*", "", e)) for e in errs]


STATIC_CHECKS = [
    check_license,
    check_nav_links,
    check_temporal_extent,
    check_asset_keys,
    check_hex_assets,
    check_vector_layers,
    check_table_columns_placement,
    check_cng_fid,
    check_hex_dup_warning,
    check_column_description_consistency,
    check_point_note,
    check_inline_area_formula,
]


# ---------------------------------------------------------------------------
# MCP client (streamable HTTP, JSON-RPC 2.0, SSE-framed replies)
# ---------------------------------------------------------------------------

DEFAULT_MCP = os.environ.get("MCP_ENDPOINT", "https://duckdb-mcp.nrp-nautilus.io/mcp")


class MCPError(Exception):
    pass


class MCPClient:
    """Minimal client for the duckdb-geo MCP server's `query` tool. Stdlib only."""

    def __init__(self, endpoint: str = DEFAULT_MCP, token: str | None = None, timeout: int = 300):
        self.endpoint = endpoint
        self.token = token or os.environ.get("MCP_AUTH_TOKEN")
        self.timeout = timeout
        self.session_id = None

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    @staticmethod
    def _parse_sse(body: bytes) -> dict:
        """Pull the first JSON-RPC payload out of an SSE (or plain-JSON) body."""
        text = body.decode("utf-8", "replace")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        # Some servers reply with bare JSON
        text = text.strip()
        if text:
            return json.loads(text)
        raise MCPError("empty MCP response")

    def _post(self, payload: dict, capture_session: bool = False) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.endpoint, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            if capture_session:
                sid = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid
            return self._parse_sse(r.read())

    def initialize(self):
        resp = self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "verify-stac", "version": "0.1"},
            },
        }, capture_session=True)
        if "error" in resp:
            raise MCPError(f"initialize failed: {resp['error']}")
        # required follow-up notification (no response expected)
        try:
            note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
            req = urllib.request.Request(self.endpoint, data=note, headers=self._headers(), method="POST")
            urllib.request.urlopen(req, timeout=30).read()
        except Exception:
            pass  # some servers don't require / don't reply to this

    def query(self, sql: str) -> list[dict]:
        """Run SQL via the `query` tool; return rows as a list of dicts (best-effort)."""
        resp = self._post({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "query", "arguments": {"sql_query": sql}},
        })
        if "error" in resp:
            raise MCPError(f"query error: {resp['error']}")
        result = resp.get("result", {})
        # MCP tool result: {"content": [{"type":"text","text": "..."}], "isError": bool}
        if result.get("isError"):
            txt = _first_text(result)
            raise MCPError(f"query tool reported error: {txt}")
        return _rows_from_tool_result(result)


def _first_text(result: dict) -> str:
    for block in result.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


def _rows_from_tool_result(result: dict):
    """The query tool returns a markdown table in a text block. We only need the
    single projected column's values, so parse the markdown table generically."""
    text = _first_text(result)
    # structuredContent is preferred if the server provides it
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and isinstance(sc.get("rows"), list):
        return sc["rows"]
    return _parse_markdown_table(text)


def _parse_markdown_table(text: str) -> list[dict]:
    rows, header, seen_sep = [], None, False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if header is not None and seen_sep:
                break  # table ended
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if re.fullmatch(r"[:\-\s|]+", line):  # separator row
            seen_sep = True
            continue
        rows.append(dict(zip(header, cells)))
    return rows


# ---------------------------------------------------------------------------
# Data-backed check: values arrays == ingested DISTINCT
# ---------------------------------------------------------------------------

def _coded_columns(doc: dict):
    """Yield (asset_key, s3_path, column_name, declared_values) for every parquet
    asset column that declares a `values` array. Prefer the geoparquet asset over
    the hex asset when both carry the same column (smaller, no dup rows)."""
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset):
            continue
        href = asset.get("href", "")
        s3 = _to_s3(href)
        if not s3:
            continue
        for col in asset.get("table:columns", []):
            vals = col.get("values")
            if vals:
                yield key, s3, col.get("name", ""), vals


def _to_s3(href: str) -> str | None:
    """Map a public https NRP href to an s3:// path the MCP can read internally."""
    m = re.match(r"https?://s3-west\.nrp-nautilus\.io/(.+)$", href)
    if m:
        return "s3://" + m.group(1)
    if href.startswith("s3://"):
        return href
    return None


def _sql_str_tuples(values) -> str:
    """Render declared values as DuckDB VALUES rows of escaped string literals."""
    rows = []
    for v in values:
        s = str(v).replace("'", "''")
        rows.append(f"('{s}')")
    return ", ".join(rows)


def check_values_match_distinct(doc: dict, mcp: MCPClient) -> list[Finding]:
    """Compare each declared `values` array to the ingested DISTINCT set. The diff is
    computed *in SQL* (not by parsing a DISTINCT row-list) because the MCP query tool
    truncates large markdown tables — a parsed list would silently drop the tail and
    fabricate findings. Pushing the set-difference into DuckDB returns only the
    discrepancies, so the result is tiny and truncation-proof."""
    out = []
    seen = set()  # one (s3_path, column) may appear on multiple assets
    for asset_key, s3, col, declared in _coded_columns(doc):
        if not col or not declared or (s3, col) in seen:
            continue
        seen.add((s3, col))
        decl_rows = _sql_str_tuples(declared)
        # Normalize a trailing ".0" so an integer class code stored as a float
        # (the cng-datasets raster `mode` reducer emits the value column as DOUBLE,
        # so code 11 reads back as "11.0") compares equal to the int declared in the
        # `values` array ("11"). Genuine string codes ('FED', 'STAT') and real
        # fractional codes ('11.5') are left untouched.
        norm = lambda e: f"regexp_replace(CAST({e} AS VARCHAR), '\\.0+$', '')"
        # Treat missing-value artifacts as absence, like NULL: an empty/whitespace string
        # and the literal conversion tokens 'null'/'nan'/'none' (pandas/str(None) leakage,
        # case-insensitive) are not real category codes. Requiring them in a `values`
        # array pollutes the schema and breaks the self-describing fold — so exclude them
        # from the ingested DISTINCT set, the same way SQL NULL is already excluded.
        # Real "unknown" categories (UNK, Unknown, N/A) are intentional codes and stay.
        sql = (
            f'WITH ingested AS (SELECT DISTINCT {norm(chr(34)+col+chr(34))} AS v '
            f"  FROM read_parquet('{s3}') WHERE \"{col}\" IS NOT NULL "
            f"    AND trim(CAST(\"{col}\" AS VARCHAR)) <> '' "
            f"    AND lower(trim(CAST(\"{col}\" AS VARCHAR))) NOT IN ('null','nan','none')), "
            f"declared AS (SELECT {norm('v')} AS v FROM (VALUES {decl_rows}) t(v)) "
            f"SELECT 'missing' AS kind, v FROM ingested WHERE v NOT IN (SELECT v FROM declared) "
            f"UNION ALL "
            f"SELECT 'extra' AS kind, v FROM declared WHERE v NOT IN (SELECT v FROM ingested) "
            f"ORDER BY kind, v"
        )
        try:
            rows = mcp.query(sql)
        except MCPError as e:
            out.append(Finding(ADVISORY, "data-query-failed",
                               f"asset '{asset_key}' column '{col}': could not verify "
                               f"DISTINCT against data ({e})."))
            continue
        missing = sorted(str(r.get("v")) for r in rows if r.get("kind") == "missing")
        extra = sorted(str(r.get("v")) for r in rows if r.get("kind") == "extra")
        if missing:
            out.append(Finding(HARD, "values-incomplete",
                               f"asset '{asset_key}' column '{col}': ingested values "
                               f"{missing[:25]} are NOT in the declared `values` array — "
                               f"the code→name map is incomplete or wrong (#114/#294 class)."))
        if extra:
            out.append(Finding(ADVISORY, "values-extra",
                               f"asset '{asset_key}' column '{col}': declared values "
                               f"{extra[:25]} never appear in the data (stale or superset — "
                               f"acceptable if intentional)."))
    return out


# ---------------------------------------------------------------------------
# Advisory recall pass — candidate categoricals that declare no `values`
# ---------------------------------------------------------------------------

# Columns we already know are NOT categorical even at low cardinality.
RECALL_SKIP_NAME = re.compile(
    r"^(h\d+|_cng_fid|bbox|geometry|geom|shape)$|"
    r"fp$|fips|geoid|^st$|iso3?$|_id$|objectid|guid|uuid|"
    r"name|date|dt$|src$|source|_acres?$|area|length", re.I)
RECALL_MAX_DISTINCT = 40


def recall_pass(doc: dict, mcp: MCPClient) -> list[Finding]:
    out = []
    seen = set()
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset):
            continue
        s3 = _to_s3(asset.get("href", ""))
        if not s3:
            continue
        # Collect this asset's candidate columns, then probe them all in ONE scan.
        candidates = []
        for col in asset.get("table:columns", []):
            name = col.get("name", "")
            ctype = col.get("type", "")
            if not name or col.get("values") or name in SAFE_HEX_COLS or _is_geom_col(name):
                continue
            if RECALL_SKIP_NAME.search(name):
                continue
            # only string/short-int columns are plausible enums
            if not (ctype.startswith(("string", "varchar", "utf8")) or ctype in ("int16", "uint8", "int8")):
                continue
            if (s3, name) in seen:
                continue
            seen.add((s3, name))
            candidates.append(name)
        if not candidates:
            continue
        # One pass over the parquet instead of one scan per column, and
        # approx_count_distinct (HyperLogLog: single pass, constant memory) instead of
        # exact COUNT(DISTINCT) — the latter builds a full hash set and, on billion-row
        # datasets with a high-cardinality column (e.g. GBIF `species` ~1.4M distinct),
        # blows the query timeout. This is an ADVISORY cardinality nudge (is it ≤ N
        # distinct?), so HLL's ~2% error near the threshold is immaterial: a genuine
        # small categorical still reads small, a high-cardinality column still reads huge.
        cols_sql = ", ".join(
            f'approx_count_distinct("{n}") AS "{n}"' for n in candidates)
        sql = f"SELECT {cols_sql} FROM read_parquet('{s3}')"
        try:
            rows = mcp.query(sql)
            row = rows[0] if rows else {}
        except (MCPError, ValueError, KeyError, IndexError):
            continue
        for name in candidates:
            try:
                n = int(row[name])
            except (KeyError, ValueError, TypeError):
                continue
            if 2 <= n <= RECALL_MAX_DISTINCT:
                out.append(Finding(ADVISORY, "recall-candidate-categorical",
                                   f"asset '{key}' column '{name}' has ~{n} distinct values "
                                   f"and no `values` array — possible undocumented "
                                   f"categorical (recall-gap check)."))
    return out


# ---------------------------------------------------------------------------
# #309 §2 — NULL finest-parent-cell on very large features (HARD, clean signal)
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^h(\d{1,2})$")
_NULL_JOIN_NOTE = re.compile(
    r"null.{0,40}(parent|finest|coarse|join)|join.{0,40}(coarse|parent|null)|"
    r"h3_cell_to_parent|largest features.{0,40}null", re.I)


_MULTIROW_NOTE = re.compile(
    r"multiple rows per \(?feature|more than one row per \(?feature|"
    r"duplicate \(feature, cell\) rows are expected|per \(feature, cell, part\)", re.I)


def check_hex_row_uniqueness(doc: dict, mcp: MCPClient) -> list[Finding]:
    """One hex row must be one (feature, cell) pair — data-workflows#509.

    The vector polyfill used to emit one row per (feature, cell, geometry PART), so any
    MultiPolygon whose parts shared a cell produced byte-identical duplicate rows. Fixed
    upstream 2026-07-12 (boettiger-lab/datasets#150 / PR #158, Pass 2 writes
    `SELECT DISTINCT *`), but every vector hex built before that date still carries the
    duplication, and nothing caught it: `COUNT(DISTINCT _cng_fid)` is unaffected, so the
    documented dedup key does not rescue a consumer, and `audit-feature-dup.py` audits
    UPSTREAM (axis-2) duplication rather than build artifacts. Confirmed live on
    ca30x30-conserved-areas-terrestrial-2025 (70,806 dup rows, up to 221 copies of one
    unit on a single cell) and padus-4-1/fee (160,293).

    HARD, because the asset's own contract ("one row per (feature, hN) pair") is false and
    every `COUNT(*)` / per-cell `SUM` over it is inflated. A genuine multi-row-per-
    (feature, cell) case does not exist by construction; if one is ever legitimate,
    document it in the asset description and this check will accept it.
    """
    out = []
    coll_desc = doc.get("description", "") or ""
    for key, asset in doc.get("assets", {}).items():
        if not (is_parquet(asset) and is_hex_asset(key, asset)):
            continue
        s3 = _to_s3(asset.get("href", ""))
        if not s3:
            continue
        cols = {c.get("name", "") for c in asset.get("table:columns", [])}
        if "_cng_fid" not in cols:
            continue  # raster reduce / per-cell aggregation — no (feature, cell) grain
        # Key each row on its FINEST NON-NULL cell, not on h3:native_resolution.
        # A build that caps very large features at a coarser resolution leaves the native
        # column NULL for them (WDPA: h9 is NULL for its 1,297 biggest features, h8 is
        # complete). COUNT(DISTINCT) drops NULL keys, so keying on the native column alone
        # reports every NULL-native row as a duplicate — on WDPA that is a 77,991,738-row
        # false positive against a true count of 0. H3 ids encode their resolution, so
        # they are unique across resolutions and COALESCE is safe. The trailing literal
        # keeps an all-NULL row countable rather than silently dropped.
        hcols = sorted((c for c in cols if _HEX_RE.match(c)),
                       key=lambda n: int(_HEX_RE.match(n).group(1)), reverse=True)
        if not hcols:
            continue
        cell = "COALESCE(" + ", ".join(f'"{h}"::VARCHAR' for h in hcols) + ", 'none')"
        try:
            rows = mcp.query(
                f"SELECT COUNT(*) AS total, COUNT(DISTINCT ({cell} || '-' || "
                f"_cng_fid::VARCHAR)) AS pairs FROM read_parquet('{s3}')")
            total, pairs = int(rows[0]["total"]), int(rows[0]["pairs"])
        except (MCPError, ValueError, KeyError, IndexError) as e:
            out.append(Finding(ADVISORY, "hex-row-uniqueness-check-failed",
                               f"asset '{key}': could not check (feature, cell) "
                               f"uniqueness ({e})."))
            continue
        if total and pairs < total:
            desc = (asset.get("description", "") or "") + " " + coll_desc
            if _MULTIROW_NOTE.search(desc):
                continue
            dup = total - pairs
            out.append(Finding(HARD, "hex-duplicate-feature-cell-rows",
                f"asset '{key}': {dup:,} rows ({100.0*dup/total:.3f}%) are duplicate "
                f"(finest-cell, _cng_fid) pairs — one hex row must be one (feature, cell) "
                f"pair, so COUNT(*) and any per-cell SUM over this asset are inflated. "
                f"Almost certainly a vector hex built before the 2026-07-12 polyfill fix "
                f"(boettiger-lab/datasets#150); remediate with a SELECT DISTINCT * rewrite "
                f"or re-hex. See data-workflows#509."))
    return out


def check_null_hex_index(doc: dict, mcp: MCPClient) -> list[Finding]:
    """A hex column with NULLs where a coarser column is fully populated means joining
    at that resolution silently drops the very large features that have no finer cell
    (WDPA: ~38% of rows have NULL h9 while h8/h0 are complete). HARD unless the asset
    or collection description documents the NULL-parent / join-at-coarsest caveat."""
    out = []
    coll_desc = doc.get("description", "") or ""
    for key, asset in doc.get("assets", {}).items():
        if not (is_parquet(asset) and is_hex_asset(key, asset)):
            continue
        s3 = _to_s3(asset.get("href", ""))
        if not s3:
            continue
        hcols = sorted((c.get("name") for c in asset.get("table:columns", [])
                        if _HEX_RE.match(c.get("name", ""))),
                       key=lambda n: int(_HEX_RE.match(n).group(1)))
        if len(hcols) < 2:
            continue
        sel = ", ".join(f'COUNT("{h}") AS {h}' for h in hcols)
        try:
            rows = mcp.query(f"SELECT COUNT(*) AS total, {sel} FROM read_parquet('{s3}')")
            r = rows[0]
            total = int(r["total"])
            nn = {h: int(r[h]) for h in hcols}
        except (MCPError, ValueError, KeyError, IndexError) as e:
            out.append(Finding(ADVISORY, "null-hex-check-failed",
                               f"asset '{key}': could not check hex-index NULLs ({e})."))
            continue
        if not total:
            continue
        # finest = highest resolution; flag if it has NULLs a coarser col doesn't
        finest = hcols[-1]
        coarsest_full = next((h for h in hcols if nn[h] == total), None)
        if nn[finest] < total and coarsest_full and coarsest_full != finest:
            desc = (asset.get("description", "") or "") + " " + coll_desc
            if not _NULL_JOIN_NOTE.search(desc):
                pct = 100.0 * (total - nn[finest]) / total
                out.append(Finding(HARD, "hex-null-parent-undocumented",
                    f"asset '{key}': column '{finest}' is NULL for {pct:.0f}% of rows "
                    f"while '{coarsest_full}' is fully populated — joining on '{finest}' "
                    f"silently drops the largest features. Document in the description: "
                    f"join at the coarsest shared resolution (or via h3_cell_to_parent), "
                    f"not '{finest}'."))
    return out


# ---------------------------------------------------------------------------
# #309 §1 — per-feature row duplication on polygon assets (ADVISORY, FP-prone)
# ---------------------------------------------------------------------------

# A column that *should* be one-row-per-feature. Row-unique keys (_cng_fid, OGC_FID)
# are excluded — they never repeat, so they carry no duplication signal.
_FEATURE_ID_RE = re.compile(r"(?i).+(id|gid|uid)$")
_ROWUNIQUE = {"_cng_fid", "ogc_fid", "objectid", "fid", "gid", "uid"}
# Not feature ids — provenance/source/metadata keys that repeat by design (e.g. WDPA
# METADATAID = the source dataset, 314 distinct over 307k rows). Excluded to cut the FP.
_NOT_FEATURE_ID = re.compile(r"(?i)(metadata|source|src|provider|dataset|batch|import)")
_DEDUP_NOTE = re.compile(r"distinct|dedup|one row per|multiple rows|repeat", re.I)


def check_polygon_row_dup(doc: dict, mcp: MCPClient) -> list[Finding]:
    """Surface non-hex (polygon/point) assets where a candidate feature-id column has
    many fewer DISTINCT values than rows — i.e. the file may repeat features (ramsar:
    8,347 rows / 2,551 ramsarid). ADVISORY only: the naive rows>distinct signal
    over-flags (#309 found 4 of 5 were false positives — the column was a label not a
    key, had a high NULL fraction, or the dup rows were genuinely distinct multiparts),
    so this names the candidate + the discriminators to check rather than asserting a
    defect. Skipped when the description already documents a dedup recipe."""
    out = []
    for key, asset in doc.get("assets", {}).items():
        if not is_parquet(asset) or is_hex_asset(key, asset):
            continue
        s3 = _to_s3(asset.get("href", ""))
        if not s3:
            continue
        if _DEDUP_NOTE.search(asset.get("description", "") or ""):
            continue
        cands = [c.get("name") for c in asset.get("table:columns", [])
                 if c.get("name") and _FEATURE_ID_RE.match(c["name"])
                 and c["name"].lower() not in _ROWUNIQUE and not _is_geom_col(c["name"])
                 and not _NOT_FEATURE_ID.search(c["name"])]
        if not cands:
            continue
        sel = ", ".join(f'COUNT(DISTINCT "{c}") AS d_{i}, COUNT("{c}") AS n_{i}'
                        for i, c in enumerate(cands))
        try:
            rows = mcp.query(f"SELECT COUNT(*) AS total, {sel} FROM read_parquet('{s3}')")
            r = rows[0]
            total = int(r["total"])
        except (MCPError, ValueError, KeyError, IndexError):
            continue
        if total < 2:
            continue
        for i, c in enumerate(cands):
            try:
                distinct = int(r[f"d_{i}"]); nonnull = int(r[f"n_{i}"])
            except (ValueError, KeyError):
                continue
            # need a meaningful repeat AND mostly-populated to be worth surfacing
            if distinct and nonnull >= 0.5 * total and total >= 1.2 * distinct:
                out.append(Finding(ADVISORY, "polygon-row-dup-candidate",
                    f"asset '{key}': COUNT(*)={total:,} but COUNT(DISTINCT \"{c}\")="
                    f"{distinct:,} (null frac {1 - nonnull/total:.0%}). Possible per-feature "
                    f"row duplication on '{c}'. Run `scripts/audit-feature-dup.py "
                    f"--key {c}` to classify REPEATED vs VARIES and confirm before "
                    f"documenting ('{c}' may be a label/provenance key, not the feature "
                    f"id — this signal over-flags), then record the verdict on the asset."))
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def verify(source: str, do_data: bool = True, do_recall: bool = True,
           mcp: MCPClient | None = None) -> tuple[str, list[Finding]]:
    try:
        doc = load_doc(source)
    except Exception as e:
        return source, [Finding(HARD, "load-error", f"could not load STAC: {e}")]

    collection_id = doc.get("id", source)
    findings: list[Finding] = []
    for check in STATIC_CHECKS:
        findings.extend(check(doc))

    # Reuse the two standalone linters (these fetch/parse the doc themselves).
    findings.extend(run_sibling_linter(_categorical, source, "categorical"))
    findings.extend(run_sibling_linter(_pmtiles, source, "pmtiles-fields"))

    if do_data or do_recall:
        client = mcp
        if client is None:
            client = MCPClient()
            try:
                client.initialize()
            except Exception as e:
                findings.append(Finding(ADVISORY, "mcp-unavailable",
                                        f"data checks skipped — MCP not reachable: {e}"))
                client = None
        if client is not None:
            if do_data:
                findings.extend(check_values_match_distinct(doc, client))
                findings.extend(check_null_hex_index(doc, client))      # #309 §2 (hard)
                findings.extend(check_hex_row_uniqueness(doc, client))  # #509 (hard)
                findings.extend(check_polygon_row_dup(doc, client))     # #309 §1 (advisory)
            if do_recall:
                findings.extend(recall_pass(doc, client))

    return collection_id, findings


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="*",
                   help="STAC collection URL(s) or local path(s).")
    p.add_argument("--bucket", help="Bucket (with --dataset) to derive the collection URL.")
    p.add_argument("--dataset", default="",
                   help="Dataset path under the bucket (e.g. census-2024/tract). "
                        "Empty = bucket-level collection.")
    p.add_argument("--yaml", nargs="*", default=[],
                   help="Generated workflow YAML file(s); derive collection target(s) "
                        "from their s3:// paths (used by CI on changed catalog/** files).")
    p.add_argument("--no-data", action="store_true",
                   help="Skip the MCP-backed DISTINCT check (static + recall only).")
    p.add_argument("--no-recall", action="store_true",
                   help="Skip the advisory recall pass.")
    p.add_argument("--strict", action="store_true",
                   help="Promote the geoparquet-no-geom and unknown-SPDX advisories to hard.")
    args = p.parse_args()

    sources = list(args.sources)
    if args.bucket:
        sources.append(derive_url(args.bucket, args.dataset))
    if args.yaml:
        targets = set()
        for path in args.yaml:
            try:
                targets |= targets_from_yaml(Path(path).read_text())
            except OSError as e:
                print(f"[warn] could not read {path}: {e}", file=sys.stderr)
        for bucket, dataset in sorted(targets):
            url = derive_url(bucket, dataset)
            # Bucket-level collections: many datasets can share ONE collection at the
            # bucket root (e.g. public-carbon, public-nci-frontiers) instead of a
            # per-dataset stac-collection.json. If the per-dataset STAC 404s but a
            # bucket-level one exists, verify that instead. De-dup (below) then collapses
            # all the bucket's datasets to the single bucket-level collection. If NEITHER
            # exists (recipe not run yet at PR-open), keep the per-dataset URL so the
            # load-error RED still fires (the intended pre-publish state).
            if not _collection_exists(url) and _collection_exists(derive_url(bucket, "")):
                url = derive_url(bucket, "")
            sources.append(url)
        if not targets:
            print("No dataset collection targets derived from the given YAML(s) — "
                  "nothing to verify.", file=sys.stderr)
    if not sources:
        # --yaml with no derivable targets is a clean no-op (e.g. a sync/infra PR).
        if args.yaml:
            sys.exit(0)
        p.error("provide a collection URL/path, --bucket [--dataset], or --yaml FILE.")
    # de-dup while preserving order
    sources = list(dict.fromkeys(sources))

    total_hard = 0
    for src in sources:
        collection_id, findings = verify(
            src, do_data=not args.no_data, do_recall=not args.no_recall)
        if args.strict:
            for f in findings:
                if f.code in ("geoparquet-no-geom-column", "license-unknown-spdx"):
                    f.severity = HARD
        hard = [f for f in findings if f.severity == HARD]
        adv = [f for f in findings if f.severity == ADVISORY]
        print(f"\n=== {collection_id} ({src}) ===", file=sys.stderr)
        for f in hard:
            print(f.render(collection_id), file=sys.stderr)
        for f in adv:
            print(f.render(collection_id), file=sys.stderr)
        if not findings:
            print("  ✓ all checks passed", file=sys.stderr)
        else:
            print(f"  {len(hard)} hard, {len(adv)} advisory", file=sys.stderr)
        total_hard += len(hard)

    if total_hard:
        print(f"\nFAIL: {total_hard} hard finding(s) across {len(sources)} collection(s).",
              file=sys.stderr)
        sys.exit(1)
    print(f"\nPASS: no hard findings across {len(sources)} collection(s).", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
