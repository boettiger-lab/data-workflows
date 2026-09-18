#!/usr/bin/env python3
"""Post-build verification for the public-rap collections (#666, #667, #607).

Checks the three things that every structural gate missed when these layers were first
published. Each defect passed schema validation, row-count checks, partition-name checks and
verify-stac.py, so the checks here deliberately compare against the SOURCE, not against the
collection's own metadata.

  1. band count      -- the COG must report exactly one band (#666 defect 1)
  2. h0 partitions   -- the measured set must equal the product's target set (#666 defect 2,
                        #607); note CONUS products take 6 and rangeland-s2 takes 4
  3. value provenance-- the hex must match the SOURCE BAND it claims, sampled over independent
                        windows (#666 defect 3). This is the only check that catches a
                        wrong-band build: AFG and PFG share the 0-100 percent domain, so a
                        range check cannot.

                        It must read the band out of the ORIGINAL multi-band raw, not out of
                        the extracted single-band COG. Comparing the hex to its own COG only
                        proves the hex step was faithful -- it passes just as happily when
                        gdal_translate pulled the wrong band, which is the defect being
                        guarded. `raw`/`source_band` below name what the collection claims,
                        and the competing band is measured alongside so the separation is
                        visible rather than assumed (review of #670).

Usage:  ./verify-rap-build.py [collection ...]      (default: all four)
"""
import json, sys, datetime, urllib.parse, urllib.request, pathlib, importlib.util

# Reuse the MCP client from scripts/verify-stac.py. Loaded by path because the hyphen in the
# filename makes it unimportable by name.
# catalog/rap/k8s/rap-bands/ -> repo root is parents[4], not [3].
_path = pathlib.Path(__file__).resolve().parents[4] / "scripts" / "verify-stac.py"
_spec = importlib.util.spec_from_file_location("verify_stac", _path)
_vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vs)
MCPClient = _vs.MCPClient

BASE = "https://s3-west.nrp-nautilus.io/public-rap"
TITILER = "https://titiler.nrp-nautilus.io"

# --h0-index -> h0 cell.  CONUS = all six; rangeland-s2 = the four western ones.
H0 = {12: 576812596024311807, 14: 577692205326532607, 20: 577164439745200127,
      50: 577199624117288959, 71: 577762574070710271, 78: 577234808489377791}
CONUS = {H0[i] for i in (12, 14, 20, 50, 71, 78)}
WEST  = {H0[i] for i in (12, 20, 50, 71)}

# Windows chosen so the candidate bands differ sharply. Kansas separates band 1 from band 2,
# which the Nevada window alone cannot.
WINDOWS = [("Kansas prairie", -100.0, -99.0, 38.0, 39.0),
           ("Great Basin NV", -117.0, -116.0, 40.0, 41.0)]

# The 6-band RAP Vegetation Cover v3 stack both CONUS collections are cut from.
RAW6 = f"{BASE}/raw/vegetation-cover-v3-2025.tif"
# Band order (upstream README): 1 annual forb & grass, 2 bare ground, 3 litter,
# 4 perennial forb & grass, 5 shrub, 6 tree.
RIVAL = {1: 4, 4: 1}   # the band a mis-extraction would most plausibly have taken instead

SPECS = {
    "rap-afg-cover": dict(col="afg", partitions=CONUS, source_band=1, raw=RAW6,
                          source=f"{BASE}/rap-afg-cover-cog.tif"),
    "rap-pfg-cover": dict(col="pfg", partitions=CONUS, source_band=4, raw=RAW6,
                          source=f"{BASE}/rap-pfg-cover-cog.tif"),
    # rangeland-s2 publishes arte and iag as separate single-band products, so the mosaic IS
    # the source band -- there is no multi-band stack to pick wrongly from.
    "rap-arte":      dict(col="arte", partitions=WEST, source_band=1, raw=None,
                          source=f"{BASE}/rap-arte-cog.tif"),
    "rap-iag":       dict(col="iag", partitions=WEST, source_band=1, raw=None,
                          source=f"{BASE}/rap-iag-cog.tif"),
}

def cog_info(url):
    probe = f"{url}?cachebust={int(datetime.datetime.now().timestamp())}"
    q = urllib.parse.quote(probe, safe="")
    with urllib.request.urlopen(f"{TITILER}/cog/info?url={q}", timeout=180) as r:
        return json.load(r)

def cog_window_mean(url, w, e, s, n, bidx=1):
    """Mean of band `bidx` over a lon/lat box, from the COG at `url`."""
    feat = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon",
            "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}
    # max_size=1024 returns HTTP 500 from this TiTiler; 512 is ample for a 1-degree window.
    # The cachebust parameter avoids TiTiler's per-URL cache, which survives object overwrites.
    probe = f"{url}?cachebust={int(datetime.datetime.now().timestamp())}"
    q = urllib.parse.quote(probe, safe="")
    req = urllib.request.Request(
        f"{TITILER}/cog/statistics?url={q}&max_size=512&bidx={bidx}",
        data=json.dumps(feat).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    st = d.get("properties", d).get("statistics", d)
    # With bidx=N TiTiler returns the single requested band, keyed "b1" on some versions and
    # "bN" on others. Take the only entry rather than guessing the key.
    return next(iter(st.values()))["mean"]

def main(names):
    mcp = MCPClient()
    failures = []
    for name in names:
        spec = SPECS[name]
        col = spec["col"]
        # The MCP reads s3:// paths; the https:// form silently matches nothing.
        href = f"s3://public-rap/{name}/hex/h0=*/data_0.parquet"
        print(f"\n=== {name} ===")

        info = cog_info(spec["source"])
        ok = info["count"] == 1
        print(f"  [{'ok' if ok else 'FAIL'}] COG band count = {info['count']} (expect 1)")
        if not ok:
            failures.append(f"{name}: COG has {info['count']} bands")
        print(f"        bounds {[round(b,3) for b in info['bounds']]}")

        rows = mcp.query(f"SELECT DISTINCT h0 FROM read_parquet('{href}', hive_partitioning=true)")
        got = {int(r["h0"]) for r in rows}
        ok = got == spec["partitions"]
        print(f"  [{'ok' if ok else 'FAIL'}] h0 partitions = {len(got)} (expect {len(spec['partitions'])})")
        if not ok:
            missing = spec["partitions"] - got
            extra = got - spec["partitions"]
            failures.append(f"{name}: partitions missing={sorted(missing)} unexpected={sorted(extra)}")

        for label, w, e, s, n in WINDOWS:
            hx = mcp.query(
                f"SELECT count(*) AS n, avg({col}) AS mean FROM read_parquet('{href}', hive_partitioning=true) "
                f"WHERE h3_cell_to_lng(h10) BETWEEN {w} AND {e} "
                f"AND h3_cell_to_lat(h10) BETWEEN {s} AND {n}")
            if not hx:
                print(f"  [FAIL] {label}: hex query returned no rows")
                failures.append(f"{name}: {label} hex query returned nothing")
                continue
            hmean, hn = hx[0].get("mean"), int(hx[0]["n"])
            if not hn:
                print(f"  [skip] {label}: no hex cells (outside this product's extent)")
                continue
            hmean = float(hmean)
            # Compare against the ORIGINAL band the collection claims. Falling back to the
            # extracted COG (raw=None) only proves hex-vs-COG fidelity, so say which one ran.
            band = spec["source_band"]
            if spec["raw"]:
                ref, ref_label = spec["raw"], f"raw band {band}"
            else:
                ref, ref_label = spec["source"], "COG band 1"
            cmean = cog_window_mean(ref, w, e, s, n, bidx=band if spec["raw"] else 1)
            rel = abs(hmean - cmean) / max(cmean, 1e-9)
            ok = rel < 0.05
            print(f"  [{'ok' if ok else 'FAIL'}] {label}: hex {hmean:.3f} vs {ref_label} "
                  f"{cmean:.3f} ({rel*100:.1f}% apart, {hn:,} cells)")
            if not ok:
                failures.append(f"{name}: {label} hex {hmean:.3f} != {ref_label} {cmean:.3f}")

            # Separation check: if the rival band is indistinguishable here, a pass proves
            # nothing about which band was extracted. Report that rather than banking the pass.
            if spec["raw"] and band in RIVAL:
                rmean = cog_window_mean(spec["raw"], w, e, s, n, bidx=RIVAL[band])
                sep = abs(rmean - cmean) / max(cmean, 1e-9)
                if sep < 0.05:
                    print(f"        [warn] band {RIVAL[band]} reads {rmean:.3f} here, within "
                          f"{sep*100:.1f}% of band {band} -- this window cannot tell them apart")
                    failures.append(
                        f"{name}: {label} cannot discriminate band {band} from {RIVAL[band]}")
                else:
                    print(f"        band {RIVAL[band]} would read {rmean:.3f} "
                          f"({sep*100:.0f}% away) -- the window discriminates")

    print("\n" + ("FAILURES:\n  " + "\n  ".join(failures) if failures else "All checks passed."))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(SPECS)))
