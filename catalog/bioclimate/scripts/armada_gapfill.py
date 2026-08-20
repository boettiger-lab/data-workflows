"""Enumerate missing staged slices for a combination and emit an Armada job set to fill them.

Armada exposes no retry service on NRP (`armadactl get retry-policies` -> Unimplemented) and, per
the NRP docs, preempted jobs are not rescheduled. So **any** transient failure leaves a
permanently missing slice, and gap-fill is a required pipeline stage rather than an exception.

Measured failure rate: 1-4 slices per 3,780 (~0.1%), and the one reason readable from the event
stream was `Pod unexpectedly started up after delete was called` — a scheduler race, unrelated to
the job's resources. Failures are roughly uniform across variables, not concentrated in the dense
ones, so this is about retry semantics, not sizing.

⛔ Find gaps by ENUMERATING the expected set, never by counting. 3,779 of 3,780 reads as complete
at a glance, and a count cannot tell you which slice is absent.
"""
import argparse
import re
import sys
import urllib.parse
import urllib.request

VARS = ["bio1", "bio4", "bio5", "bio6", "bio12", "bio15", "bio17"]
MEMBERS = ["gfdl_esm4", "ipsl_cm6a_lr", "mpi_esm1_2_hr", "mri_esm2_0", "ukesm1_0_ll"]
BASE = "https://s3-west.nrp-nautilus.io/public-bioclimate"


def keys(prefix):
    tok, out = None, []
    while True:
        u = f"{BASE}?list-type=2&prefix={urllib.parse.quote(prefix)}&max-keys=1000"
        if tok:
            u += "&continuation-token=" + urllib.parse.quote(tok)
        x = urllib.request.urlopen(u, timeout=90).read().decode()
        out += re.findall(r"<Key>([^<]*)</Key>", x)
        m = re.search(r"<NextContinuationToken>([^<]*)</NextContinuationToken>", x)
        if not m:
            break
        tok = m.group(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combo", required=True, help="e.g. ssp126-2041-2070")
    ap.add_argument("--staging", default="staging")
    ap.add_argument("--reference", default="chelsa-2-1/ssp370-2041-2070/hex/",
                    help="a published hex whose h0 set defines the land partitions")
    ap.add_argument("--grid", default="s3://public-grids/hex/h0-valid.parquet")
    args = ap.parse_args()

    land_cells = sorted(set(re.findall(r"hex/h0=(\d+)/", "".join(keys(args.reference)))))
    if not land_cells:
        print(f"ERROR: no land h0 found under {args.reference}", file=sys.stderr)
        return 1

    got = set()
    for k in keys(f"{args.staging}/{args.combo}/"):
        m = re.search(rf"{re.escape(args.staging)}/{re.escape(args.combo)}/([^/]+)/h0=(\d+)/", k)
        if m:
            got.add((m.group(1), m.group(2)))

    expected = len(land_cells) * len(VARS) * len(MEMBERS)
    missing = [(v, m, h) for h in land_cells for v in VARS for m in MEMBERS
               if (f"{v}_{m}", h) not in got]

    print(f"{args.combo}: {expected - len(missing)}/{expected} staged, {len(missing)} missing")
    for v, m, h in missing:
        print(f"  MISSING {v}_{m} h0cell={h}")

    # Emit the h0 CELL ids; the caller maps them back to --h0-indexes for the generator.
    if missing:
        cells = sorted({h for _, _, h in missing})
        vars_ = sorted({v for v, _, _ in missing})
        print(f"\nGAPFILL_CELLS={','.join(cells)}")
        print(f"GAPFILL_VARS={','.join(vars_)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
