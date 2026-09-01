#!/usr/bin/env python3
"""Patch the generated ship-density hex jobs (issue #641).

Two fixes the generator does not make for us:

1. Retry policy. The generator emits `backoffLimit: 0`, which AGENTS.md forbids for indexed
   hex jobs: a preempted pod then never gets retried elsewhere and a partial run can be
   published as if complete. Replace with `backoffLimitPerIndex` + `maxFailedIndexes` so a
   partial run surfaces as Failed.

2. Output path. `--dataset ship-density/<layer>` flattens to `ship-density-<layer>/hex/` in
   the generated `--output-parquet`. Issue #641 specifies the hierarchical
   `ship-density/<layer>/hex/`, which is what the STAC collection at
   `ship-density/stac-collection.json` and its asset globs assume.

Idempotent: safe to re-run.
"""
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).parent
LAYERS = ["leisure", "oil-gas", "fishing", "passenger", "commercial", "global"]

changed = []
for layer in LAYERS:
    path = BASE / layer / f"ship-density-{layer}-hex.yaml"
    if not path.exists():
        sys.exit(f"missing: {path}")
    text = original = path.read_text()

    # 1. retry policy
    text = text.replace(
        "  backoffLimit: 0\n",
        "  backoffLimitPerIndex: 2\n  maxFailedIndexes: 122\n",
    )

    # 2. hierarchical output path
    text = text.replace(
        f"s3://public-high-seas/ship-density-{layer}/hex/",
        f"s3://public-high-seas/ship-density/{layer}/hex/",
    )

    if text != original:
        path.write_text(text)
        changed.append(layer)

    # verify post-conditions
    assert "backoffLimit: 0" not in text, f"{layer}: backoffLimit 0 still present"
    assert "backoffLimitPerIndex: 2" in text, f"{layer}: missing backoffLimitPerIndex"
    assert "maxFailedIndexes: 122" in text, f"{layer}: missing maxFailedIndexes"
    assert f"ship-density-{layer}/hex/" not in text, f"{layer}: flattened path remains"
    out = re.search(r"--output-parquet (\S+)", text)
    assert out and out.group(1) == f"s3://public-high-seas/ship-density/{layer}/hex/", \
        f"{layer}: unexpected output path {out.group(1) if out else None}"

print("patched:", ", ".join(changed) if changed else "(none, already current)")
print("verified all 6 hex jobs: backoffLimitPerIndex=2, maxFailedIndexes=122,"
      " output s3://public-high-seas/ship-density/<layer>/hex/")
