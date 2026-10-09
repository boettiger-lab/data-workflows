#!/usr/bin/env python3
"""Generate the six #627 hex workflows and fuse them into TWO Armada job sets.

    python3 gen_armada.py --out-dir /tmp/wrc-2-armada

Produces:
    armada-wrc-2-627-hex.yaml     one job set, every chunk of all six layers
    armada-wrc-2-627-merge.yaml   one job set, the six merge jobs
    per-layer/                    the raw generator output, kept as evidence

WHY FUSED. `armadactl` re-authenticates on every invocation: it caches through go-keyring, which
needs a D-Bus Secret Service, and this image has no `dbus-launch`. The device code Authentik
issues expires in **60 seconds**, so every separate submit costs a human a timed approval. One job
set can carry thousands of jobs, so fusing six layers into one submit turns seven approvals into
two. Armada job sets have exactly one queue and one jobSetId, and all six layers share the queue
(`geo-workflows`), so the fusion is legitimate rather than a trick.

WHY SUB-h0 CHUNKING. At chunk-resolution 0 every surviving h0 enumerates all 282,475,249 res-10
children whatever its data content, which is what pinned #592 at ~133 GiB and ~5 h per slice
regardless of size. `--chunk-resolution 2` divides that by 49 and `--window-reads` (automatic
above resolution 0) reads only the chunk's window instead of localizing a 26 GB COG. Measured on
a 13-chunk smoke test before this was trusted: 5,764,801 cells enumerated, ~3 s per 100k-cell
exact_extract batch, 8Gi ample against a measured-peak estimate of 0.6 GiB.

MEMORY IS THE LEVER, NOT CPU. The armada-pipeline skill measured a 32Gi/8-core job set as
2 scheduled and 4,231 "does not fit on any node". Armada carries no quota, so concurrency is
decided entirely by how many pods of this shape the cluster can hold. 2 cores / 8Gi fits nearly
anywhere; the generator's 32Gi default would throttle the queue against itself.

The h0 lists come from h0-selection.json (see h0_select.py) -- each layer's own valid-pixel
footprint, never a neighbouring layer's populated set.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BUCKET = "public-fire"
QUEUE = "geo-workflows"

THEMES = {"bp": "bp", "cfl": "cfl", "exposure": "exposure"}
DOMAINS = ["conus", "ak"]

# Kept identical across layers so one queue-report reading applies to every chunk.
HEX_MEMORY = "8Gi"
HEX_CPU = "2"
HEX_STORAGE = "16Gi"
CHUNK_RESOLUTION = 2


def generate(ds: str, column: str, h0: list, out_dir: str) -> str:
    cmd = [
        "cng-datasets", "raster-workflow",
        "--dataset", ds,
        "--source-url", f"s3://{BUCKET}/{ds}-cog.tif",
        "--bucket", BUCKET,
        "--h3-resolution", "10",
        "--parent-resolutions", "9,8,0",
        "--value-column", column,
        "--hex-resampling", "mean",
        "--nodata", "-9999",
        "--h0-subset", ",".join(str(x) for x in h0),
        "--chunk-resolution", str(CHUNK_RESOLUTION),
        "--backend", "armada",
        "--namespace", QUEUE,
        "--hex-memory", HEX_MEMORY,
        "--hex-cpu", HEX_CPU,
        "--hex-storage", HEX_STORAGE,
        "--merge-storage", "50Gi",
        "--output-dir", out_dir,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FATAL: generation failed for {ds}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def load_jobset(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="/tmp/wrc-2-armada")
    ap.add_argument("--selection", default=os.path.join(HERE, "h0-selection.json"))
    a = ap.parse_args()

    with open(a.selection) as fh:
        sel = json.load(fh)["datasets"]

    per = os.path.join(a.out_dir, "per-layer")
    shutil.rmtree(a.out_dir, ignore_errors=True)
    os.makedirs(per, exist_ok=True)

    hex_jobs, merge_jobs, report = [], [], []
    for theme, column in THEMES.items():
        for domain in DOMAINS:
            ds = f"wrc-2-{theme}-{domain}"
            if ds not in sel:
                sys.exit(f"FATAL: no h0 selection for {ds}; run h0_select.py over all six COGs")
            h0 = sel[ds]["h0_indexes"]
            d = os.path.join(per, ds)
            generate(ds, column, h0, d)

            hx = load_jobset(os.path.join(d, f"armada-{ds}-hex.yaml"))
            mg = load_jobset(os.path.join(d, f"armada-{ds}-merge.yaml"))
            for js, name in ((hx, "hex"), (mg, "merge")):
                if js.get("queue") != QUEUE:
                    sys.exit(f"FATAL: {ds} {name} queue is {js.get('queue')!r}, expected {QUEUE!r}")
            hex_jobs.extend(hx["jobs"])
            merge_jobs.extend(mg["jobs"])
            report.append((ds, len(h0), len(hx["jobs"])))

    # Every chunk job must carry its own --chunk-index, and the merge gate must match the fan-out
    # it was generated from: a mismatch publishes a partial build as complete (#409).
    def script_of(job: dict) -> str:
        """The pod's shell script. The generator puts it in `command` for some steps and `args`
        for others, so read both -- checking only one silently passes every job."""
        c = job["podSpec"]["containers"][0]
        return " ".join((c.get("command") or []) + (c.get("args") or []))

    for ds, _, n in report:
        want = f"--expect-chunks {n}"
        hit = [j for j in merge_jobs if ds in script_of(j) and want in script_of(j)]
        if len(hit) != 1:
            sys.exit(f"FATAL: {ds} merge does not gate on {want} (matched {len(hit)})")
    # And every chunk job must carry a distinct --chunk-index within its own layer.
    seen_idx = {}
    for j in hex_jobs:
        sc = script_of(j)
        m = re.search(r"--output-parquet s3://[^/]+/(\S+?)/hex-chunks", sc)
        k = re.search(r"--chunk-index (\d+)", sc)
        if not (m and k):
            sys.exit("FATAL: a hex job has no dataset or no --chunk-index")
        seen_idx.setdefault(m.group(1), []).append(int(k.group(1)))
    for ds, idxs in seen_idx.items():
        if sorted(idxs) != list(range(len(idxs))):
            sys.exit(f"FATAL: {ds} chunk indexes are not 0..{len(idxs) - 1}")

    os.makedirs(a.out_dir, exist_ok=True)
    for name, jobs, sid in (("hex", hex_jobs, "wrc-2-627-hex"),
                            ("merge", merge_jobs, "wrc-2-627-merge")):
        path = os.path.join(a.out_dir, f"armada-wrc-2-627-{name}.yaml")
        with open(path, "w") as fh:
            yaml.safe_dump({"queue": QUEUE, "jobSetId": sid, "jobs": jobs}, fh,
                           default_flow_style=False, sort_keys=False, width=10000)
        print(f"wrote {path}  ({len(jobs)} jobs)")

    print("\n  layer                    h0   chunks")
    for ds, nh0, n in report:
        print(f"  {ds:<24} {nh0:>3}   {n:>5}")
    print(f"  {'TOTAL':<24} {'':>3}   {sum(n for _, _, n in report):>5}")
    print(f"\n  submit:  armadactl submit {a.out_dir}/armada-wrc-2-627-hex.yaml")
    print(f"  then:    armadactl submit {a.out_dir}/armada-wrc-2-627-merge.yaml")
    print("  monitor: https://armada-lookout.nrp-nautilus.io")
    return 0


if __name__ == "__main__":
    sys.exit(main())
