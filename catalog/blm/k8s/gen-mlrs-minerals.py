#!/usr/bin/env python3
"""Generate the `stage-raw` scrape Jobs for the seven BLM National MLRS mineral
case-record layers (data-workflows #486).

The seven layers are the same scrape modulo (service name, layer id, feature count,
schema variant), so they are emitted from one template + the LAYERS table below rather
than hand-copied seven times (a gen-script-plus-committed-output pattern).

    python3 catalog/blm/k8s/gen-mlrs-minerals.py

writes `catalog/blm/k8s/<layer>/<layer>-stage-raw.yaml` for each layer. The five
pipeline jobs (setup-bucket / convert / pmtiles / hex / repartition) plus configmap and
workflow come from `cng-datasets workflow` instead — see the README-less convention of
the sibling BLM datasets; the generation command is recorded in each configmap.

Scope, column contract and the year-column design are recorded in issue #486.
"""

import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# --- schema variants ------------------------------------------------------------------
# Verified field-by-field against all seven live FeatureServers, 2026-07-24 (#486).
#
# Dropped from every layer and why:
#   QLTY                        despite the "Data Quality" alias this is NOT a quality
#                               code -- it is a multi-kilobyte free-text dump of the LLD
#                               geocoder's debug log (2000+ distinct values). Measured to
#                               inflate the scrape payload ~1.7x for zero analytical
#                               value. `SRC` is the useful geocoding-provenance field and
#                               is retained. (Same trap as #487/#488.)
#   Shape__Area / Shape__Length decimal-degree junk (the real area is RCRD_ACRS)
#   Shape                       when present, an empty VARCHAR whose NAME collides with
#                               cng-datasets' geometry-column auto-detection, which then
#                               aliases it as `geom` and crashes the hex step on
#                               ST_GeometryType(VARCHAR) (#451). Real geometry rides in
#                               the GeoJSON `geometry` and is untouched.
#   CSE_META, SF_ID, ID, OBJECTID   internal MLRS / Salesforce / GIS record keys

_COMMON = ("CSE_NR", "LEG_CSE_NR", "CSE_NAME", "CSE_TYPE_NR", "BLM_PROD",
           "CSE_DISP", "CMMDTY", "RCRD_ACRS", "ADMIN_STATE", "GEO_STATE",
           "PRDCNG", "SRC", "EFF_DT", "EXP_DT", "SALE_DT", "Created", "Modified")

# Both variants emit the same four year columns (eff_year, disp_year, case_year,
# case_year_src) even though `disp_year` can only ever be NULL on the energy variant.
# Uniform column lists across all seven collections mean the app's slider SQL is identical
# for every layer it toggles; one always-NULL int column is a cheap price.
VARIANTS = {
    # Energy variant: carries FRMTN (producing formation). No CSE_DISP_DT, no business
    # account group -- so `case_year` can only ever come from EFF_DT here.
    "energy": {
        "keep": _COMMON + ("FRMTN",),
        "dates": ("EFF_DT", "EXP_DT", "SALE_DT", "Created", "Modified"),
        "has_disp_dt": False,
    },
    # Leasable/salable variant: carries the case-disposition date and the business
    # account group (who holds the interest and what share). No FRMTN.
    "leasable": {
        "keep": _COMMON + ("CSE_DISP_DT", "CUST_NM_SEC", "PCT_INT_SEC", "INT_REL_SEC"),
        "dates": ("EFF_DT", "EXP_DT", "SALE_DT", "CSE_DISP_DT", "Created", "Modified"),
        "has_disp_dt": True,
    },
}

# --- the seven layers -----------------------------------------------------------------
# `layer` is the FeatureServer sublayer index. NOTE Coal Cases is 1, not 0 -- layer 0
# 404s on that service. `count` is the live polygon count verified 2026-07-24; the scrape
# asserts it received at least 98% of it so a truncated pull fails loudly instead of
# silently publishing a subset.
#
# Hex/repartition sizing is calibrated against the PUBLISHED sibling datasets rather than
# guessed: #451 oil-gas-leases ran 466,415 features / 651.9M RCRD_ACRS -> 1.90B hex rows
# (2.92 hex rows per recorded acre, the pessimistic end) and #487 locatable-operations ran
# 2,399 features -> 1.03M rows (0.62 rows/acre). The spread is how coarsely the LLD
# geocoder snaps to whole PLSS sections. Applying 2.92 rows/acre to each layer's live
# SUM(RCRD_ACRS) gives the row estimates in the `est_rows` field. All seven combined are
# ~415M hex rows -- under a quarter of oil-gas-leases alone -- and the largest single
# feature anywhere in this data family is ~818k cells, so:
#   * one shared hex tier (4 cpu / 32Gi / 10Gi eph -- the proven #451 config) for all seven;
#     only `chunk`/`completions` vary, always with >=20% capacity headroom over `count`
#     (if completions x chunk < count the TAIL FEATURES ARE SILENTLY DROPPED -- the worst
#     failure mode here, so headroom is not optional);
#   * NO rechunk-scratch PVC on any layer. Even oil-gas-agreements (~265M rows, ~26 GB
#     sorted spill, and the sort is per-h0 so the peak is a fraction of that) fits inside
#     the 50Gi ephemeral cap. #451 needed the PVC only because its largest single h0 was
#     ~660M rows -- more than this entire seven-layer set. If og-agreements does OOM or
#     trip "ephemeral local storage usage exceeds the total limit", the escalation is the
#     documented #451 recipe: mount rechunk-scratch with a per-job subPath, TMPDIR=/scratch,
#     `ln -s /scratch/hex /tmp/hex`, drop ephemeral to 20Gi and raise memory.
LAYERS = [
    dict(name="coal-cases", service="BLM_Natl_MLRS_Coal_Cases", layer=1,
         count=3857, variant="leasable", est_rows="~17M",
         chunk=500, completions=10, parallelism=10, maxfail=2, rp_mem="48Gi",
         desc="Coal leases, licenses, exploration licenses and logical mining units "
              "(leasable -- solid fuel)."),
    dict(name="geothermal-leases", service="BLM_Natl_MLRS_Geothermal_Leases", layer=0,
         count=7394, variant="energy", est_rows="~46M",
         chunk=500, completions=20, parallelism=20, maxfail=2, rp_mem="48Gi",
         desc="Geothermal leases and utilization sites (leasable -- energy)."),
    dict(name="oil-shale-leases", service="BLM_Natl_MLRS_Oil_Shale_Leases", layer=0,
         count=42, variant="leasable", est_rows="~0.2M",
         chunk=100, completions=2, parallelism=2, maxfail=1, rp_mem="16Gi",
         desc="Oil shale RD&D leases, preference-right leases and exploration licenses "
              "(leasable -- energy). The smallest MLRS layer."),
    dict(name="non-energy-leasables", service="BLM_Natl_MLRS_Non_Energy_Leasables",
         layer=0, count=7106, variant="leasable", est_rows="~30M",
         chunk=500, completions=20, parallelism=20, maxfail=2, rp_mem="48Gi",
         desc="Non-energy leasable minerals -- phosphate, sodium, potassium, sulfur, "
              "gilsonite, hardrock-on-acquired-lands and others."),
    dict(name="mineral-materials", service="BLM_Natl_MLRS_Mineral_Materials", layer=0,
         count=35670, variant="leasable", est_rows="~36M",
         chunk=1200, completions=40, parallelism=40, maxfail=5, rp_mem="48Gi",
         desc="Salable mineral materials -- sand, gravel, stone, fill -- sold or "
              "free-use permitted (community pits, common use areas, quarries)."),
    dict(name="oil-gas-agreements", service="BLM_Natl_MLRS_Oil_and_Gas_Agreements",
         layer=0, count=32787, variant="energy", est_rows="~265M",
         chunk=800, completions=50, parallelism=50, maxfail=5, rp_mem="96Gi",
         desc="Oil & gas administrative units -- unit agreements, communitization "
              "agreements, development contracts, gas storage and compensatory royalty."),
    dict(name="oil-gas-participating-areas",
         service="BLM_Natl_MLRS_Oil_and_Gas_Participating_Areas", layer=0,
         count=2562, variant="energy", est_rows="~21M",
         chunk=400, completions=10, parallelism=10, maxfail=2, rp_mem="48Gi",
         desc="Participating areas within oil & gas unit agreements -- the sub-areas "
              "committed to a producing formation."),
]

TEMPLATE = '''# GENERATED by catalog/blm/k8s/gen-mlrs-minerals.py -- do not edit by hand.
#
# Stage raw BLM National MLRS {title} from the ArcGIS FeatureServer to S3.
#
# {desc}
#
# Paginates the FeatureServer ({count:,} polygon features, maxRecordCount 2000) to a single
# GeoJSON. Robustness matches the sibling MLRS scrapes (#451 leases, #477 claims, #487
# locatable operations, #488 LUA): explicit User-Agent (gis.blm.gov 403s the default
# python-urllib UA), per-page retry with exponential backoff, stable OBJECTID ordering,
# and a terminal count assert. Output feeds `cng-datasets workflow` as an ordinary source.
#
# Schema: the MLRS **{variant} variant** (verified live 2026-07-24, issue #486).
# {variant_note}
# MLRS returns every date as epoch-MILLISECONDS even in GeoJSON output, so they are parsed
# to ISO YYYY-MM-DD here (via datetime+timedelta, which handles the pre-1970 negative-ms
# cases that utcfromtimestamp would reject).
#
# Year columns for the app's time slider (#486, confirmed at ingest):
#   eff_year       year of EFF_DT{eff_cov}
#   {disp_line}
#   case_year      COALESCE(eff_year, disp_year) -- the UNIFORM slider column across all
#                  seven mineral case-record datasets
#   case_year_src  'effective' | 'disposition' | null -- provenance for case_year, so a
#                  consumer can tell a case *start* year from a case *closure* year
#                  instead of silently mixing them
#
# Polygons are geocoded from Legal Land Descriptions via the PLSS, so some cases have no
# geometry: {nullgeom} of {count:,} ({nullgeom_pct}) as of 2026-07-24. Those rows are
# retained as attribute-only records in the GeoParquet; they are absent from PMTiles and
# from the hex (cng-datasets drops them at hex time). The scrape prints the live count --
# use it, not this comment, as the number documented in the STAC and README.{nullgeom_warn}
#
#   Source: https://gis.blm.gov/nlsdb/rest/services/HUB/{service}/FeatureServer/{layer}
#   Issue:  https://github.com/boettiger-lab/data-workflows/issues/486
apiVersion: batch/v1
kind: Job
metadata:
  name: {name}-stage-raw
  labels:
    k8s-app: {name}-stage-raw
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 3
  ttlSecondsAfterFinished: 10800
  template:
    metadata:
      labels:
        k8s-app: {name}-stage-raw
    spec:
      restartPolicy: Never
      activeDeadlineSeconds: 3600
      # Cluster DNS on some nodes intermittently fails to resolve external hosts
      # (gis.blm.gov). Append public resolvers as a fallback; cluster DNS is still tried
      # first so the internal rook-ceph-rgw-nautiluss3.rook rclone endpoint keeps resolving.
      dnsConfig:
        nameservers:
        - 8.8.8.8
        - 1.1.1.1
      containers:
      - name: stage-raw
        image: ghcr.io/boettiger-lab/datasets:latest
        imagePullPolicy: Always
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom:
            secretKeyRef:
              name: aws
              key: AWS_ACCESS_KEY_ID
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: aws
              key: AWS_SECRET_ACCESS_KEY
        volumeMounts:
        - name: rclone-config
          mountPath: /root/.config/rclone
          readOnly: true
        command:
        - bash
        - -c
        - |
          set -euo pipefail
          python3 - <<'PY'
          import json, time, urllib.parse, urllib.request, urllib.error
          from datetime import datetime, timedelta, timezone

          BASE = ("https://gis.blm.gov/nlsdb/rest/services/HUB/"
                  "{service}/FeatureServer/{layer}/query")
          PAGE = 2000
          EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)  # handles pre-1970 (negative ms)
          # gis.blm.gov 403s the default python-urllib User-Agent -- send an explicit one
          UA = {{"User-Agent": "data-workflows/1.0 (boettiger-lab; issue 486)"}}

          # Attributes to keep; everything else is internal GIS/MLRS junk (see the header
          # for the drop list and the reasoning). CSE_DISP is the disposition/status,
          # CMMDTY the commodity, RCRD_ACRS the case acres (a per-feature total -- dedup
          # by _cng_fid before any SUM on the hex).
          KEEP = ({keep})
          DATE_FIELDS = ({dates})

          def fetch_page(url, tries=6):
              # the FeatureServer intermittently returns 503/timeouts; retry each page with
              # exponential backoff so one transient blip does not lose the whole scrape.
              for attempt in range(1, tries + 1):
                  try:
                      req = urllib.request.Request(url, headers=UA)
                      with urllib.request.urlopen(req, timeout=180) as r:
                          return json.load(r)
                  except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                      if attempt == tries:
                          raise
                      wait = min(60, 2 ** attempt)
                      print(f"  retry {{attempt}}/{{tries}} after {{type(e).__name__}} ({{e}}); sleep {{wait}}s", flush=True)
                      time.sleep(wait)

          def ms_to_iso(v):
              if v is None:
                  return None
              return (EPOCH + timedelta(milliseconds=v)).strftime("%Y-%m-%d")

          def year_of(iso):
              # Extract the year, rejecting implausible ones. MLRS uses a year-3999
              # sentinel for "no known end" (mineral-materials ships 3999-12-12 and
              # 3999-01-01); left in place it makes case_year useless as a slider bound --
              # the range reads 1921..3999. The window is deliberately wide enough to keep
              # GENUINE future disposition dates, which do occur (2030-04-17, 2034-03-06),
              # and 2100 is a fixed bound so a regenerated manifest never drifts with the
              # clock. The raw EFF_DT / CSE_DISP_DT strings are retained verbatim, so
              # nothing is lost -- only the derived integer is withheld.
              if not iso:
                  return None
              y = int(iso[:4])
              return y if 1800 <= y <= 2100 else None

          def clean(feat):
              p = feat.get("properties") or {{}}
              out = {{k: p.get(k) for k in KEEP}}
              # Normalize strings with one rule: collapse every whitespace run to a single
              # space and map empty -> None. str.split() treats U+00A0 as whitespace, so
              # this also repairs the non-breaking spaces the MLRS export ships inside some
              # BLM_PROD values ('PHOSPHATE\\xa0COMPETITIVE\\xa0LEASE'), which would
              # otherwise break every literal WHERE comparison against that value.
              # Casing is deliberately NOT folded: the source's mixed forms ('Coal' vs
              # 'COAL, BITUMINOUS') are genuinely distinct codes, not case duplicates.
              for k, v in list(out.items()):
                  if isinstance(v, str):
                      out[k] = " ".join(v.split()) or None
              # ISO dates (MLRS epoch-ms -> YYYY-MM-DD)
              for d in DATE_FIELDS:
                  out[d] = ms_to_iso(p.get(d))
              # --- derived year columns (see header) ---
              out["eff_year"] = year_of(out.get("EFF_DT"))
{disp_derive}
              out["case_year"] = out["eff_year"]{case_year_fallback}
              out["case_year_src"] = ("effective" if out["eff_year"] is not None
{src_fallback}                                     else None)
              feat["properties"] = out
              return feat

          feats, offset = [], 0
          while True:
              q = {{
                  "where": "1=1",
                  # Request only the KEEP fields rather than "*". Measured on
                  # mineral-materials: 46,370 B vs 26,793 B per 50 rows -- a 1.73x payload
                  # reduction, essentially all of it the QLTY geocoder-debug blob we would
                  # discard anyway. A typo'd field name yields an ArcGIS 400, which is a
                  # desirable fail-fast; clean() still filters to KEEP as defense in depth.
                  "outFields": ",".join(KEEP),
                  "outSR": "4326",              # WGS84 lon/lat (source is NAD83 / WKID 4269)
                  "f": "geojson",
                  "resultOffset": offset,
                  "resultRecordCount": PAGE,
                  "orderByFields": "OBJECTID",  # stable pagination order
              }}
              url = BASE + "?" + urllib.parse.urlencode(q)
              fc = fetch_page(url)
              batch = fc.get("features", [])
              for feat in batch:
                  feats.append(clean(feat))
              print(f"offset {{offset}}: +{{len(batch)}} (total {{len(feats)}})", flush=True)
              more = fc.get("properties", {{}}).get("exceededTransferLimit") or fc.get("exceededTransferLimit")
              if len(batch) < PAGE and not more:
                  break
              if not batch:
                  break
              offset += len(batch)

          # sanity check: disposition set, states, year coverage, null-geometry count.
          # These print into the job log and are the source for the STAC `values` arrays
          # and the documented null-geometry count.
          disps = sorted({{(f["properties"].get("CSE_DISP") or "") for f in feats}})
          states = sorted({{(f["properties"].get("ADMIN_STATE") or "") for f in feats}})
          years = sorted({{y for f in feats if (y := f["properties"].get("case_year")) is not None}})
          nogeom = sum(1 for f in feats if not f.get("geometry"))
          n_eff = sum(1 for f in feats if f["properties"].get("eff_year") is not None)
          n_case = sum(1 for f in feats if f["properties"].get("case_year") is not None)
          print(f"CSE_DISP: {{disps}}", flush=True)
          print(f"distinct ADMIN_STATE: {{states}}", flush=True)
          print(f"case_year range: {{years[:1]}}..{{years[-1:]}}", flush=True)
          print(f"eff_year populated: {{n_eff}}/{{len(feats)}}; case_year populated: {{n_case}}/{{len(feats)}}", flush=True)
          print(f"null-geometry features: {{nogeom}}", flush=True)
          # count dates present in the source but rejected as implausible (the 3999 sentinel)
          sentinel = sum(1 for f in feats
                         for k, yk in (("EFF_DT", "eff_year"), ("CSE_DISP_DT", "disp_year"))
                         if f["properties"].get(k) and f["properties"].get(yk) is None)
          print(f"dates rejected as out-of-range (3999 sentinel etc.): {{sentinel}}", flush=True)

          out = {{"type": "FeatureCollection",
                 "crs": {{"type": "name", "properties": {{"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}}},
                 "features": feats}}
          with open("/tmp/{name}.geojson", "w") as f:
              json.dump(out, f)
          print(f"WROTE {{len(feats)}} features", flush=True)
          # fail loudly if the FeatureServer under-delivered vs the count verified 2026-07-24
          assert len(feats) >= {floor}, f"expected ~{count:,} features, got {{len(feats)}}"
          PY
          ls -la /tmp/{name}.geojson
          rclone copyto /tmp/{name}.geojson nrp:public-blm/raw/{name}.geojson --s3-no-check-bucket
          echo "staged raw -> s3://public-blm/raw/{name}.geojson"
        resources:
          requests:
            cpu: '2'
            memory: 8Gi
            ephemeral-storage: 10Gi
          limits:
            cpu: '2'
            memory: 8Gi
            ephemeral-storage: 10Gi
      volumes:
      - name: rclone-config
        secret:
          secretName: rclone-config
      priorityClassName: opportunistic
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: feature.node.kubernetes.io/pci-10de.present
                operator: NotIn
                values:
                - 'true'
'''

# Live EFF_DT / CSE_DISP_DT coverage, measured 2026-07-24. Purely documentary -- it goes
# into the generated header so the reason for the four-column year design is visible at
# the point of use.
COVERAGE = {
    "coal-cases": (32, 99), "geothermal-leases": (58, None),
    "oil-shale-leases": (23, 97), "non-energy-leasables": (30, 98),
    "mineral-materials": (5, 98), "oil-gas-agreements": (92, None),
    "oil-gas-participating-areas": (98, None),
}

# Cases whose Legal Land Description the PLSS geocoder could not place, measured live
# 2026-07-24 (`where=Shape__Area IS NULL`). These rows are kept in the GeoParquet as
# attribute-only records and are absent from PMTiles and hex. coal-cases at 25% is the
# headline caveat of this ingest and must reach the STAC description and README.
NULLGEOM = {
    "coal-cases": 971, "geothermal-leases": 195, "oil-shale-leases": 0,
    "non-energy-leasables": 212, "mineral-materials": 1393,
    "oil-gas-agreements": 443, "oil-gas-participating-areas": 17,
}

ENERGY_NOTE = (
    "Carries FRMTN (producing formation) -- retained, it is the field that makes an\n"
    "# O&G/geothermal case joinable to production data. Has NO CSE_DISP_DT and no business\n"
    "# account group, so case_year here can only come from EFF_DT.")
LEASABLE_NOTE = (
    "Carries CSE_DISP_DT (case disposition date) and the business account group\n"
    "# (CUST_NM_SEC / PCT_INT_SEC / INT_REL_SEC -- who holds the interest and what share).\n"
    "# Has no FRMTN. EFF_DT is sparse on this variant, which is why disp_year exists.")


def tup(names):
    """Render a python tuple literal, wrapped, for embedding in the heredoc."""
    lines, cur = [], "          "
    for n in names:
        piece = f'"{n}", '
        if len(cur) + len(piece) > 88:
            lines.append(cur.rstrip())
            cur = "                  "
        cur += piece
    lines.append(cur.rstrip().rstrip(","))
    return "\n".join(lines).strip()


def pipeline(spec):
    """Emit the five DAG jobs + configmap + workflow + rbac via `cng-datasets workflow`,
    then apply the two hand-tuning edits the generator cannot express as CLI flags."""
    import re
    import subprocess

    d = HERE / spec["name"]
    cmd = [
        "cng-datasets", "workflow",
        "--namespace", "geo-workflows",          # HARD BOUNDARY 3: never `biodiversity`
        "--dataset", spec["name"],
        "--source-url", f"s3://public-blm/raw/{spec['name']}.geojson",
        "--bucket", "public-blm",
        "--h3-resolution", "10",
        "--parent-resolutions", "9,8,0",         # -> h10 native + h9, h8 (universal join), h0
        "--hex-memory", "32Gi",
        "--max-completions", str(spec["completions"]),
        "--max-parallelism", str(spec["parallelism"]),
        "--repartition-memory", spec["rp_mem"],
        "--output-dir", str(d),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    cap = spec["completions"] * spec["chunk"]
    margin = 100.0 * (cap - spec["count"]) / spec["count"]
    assert cap >= spec["count"], (
        f"{spec['name']}: hex capacity {cap:,} < {spec['count']:,} features -- the tail "
        f"would be SILENTLY DROPPED")

    def patch(text, indent, where):
        """Apply the two hex tunings the CLI cannot express, at a given indent level.

        `indent` differs between the standalone hex Job (2 spaces) and the copy embedded
        in the ConfigMap (6). Both must be patched: the DAG applies the ConfigMap's copy,
        so patching only the standalone file would run an untuned hex job.
        """
        i = " " * indent
        # (1) chunk-size: the generator hardcodes 1000; set the per-layer value so that
        #     completions x chunk covers `count` with headroom (see the LAYERS comment).
        text, n = re.subn(r"--chunk-size \d+", f"--chunk-size {spec['chunk']}", text)
        assert n == 1, f"{where}: expected 1 --chunk-size, found {n}"
        # (2) failure policy: under `backoffLimit: 0` a preempted index leaves the Job
        #     neither Complete nor Failed, so it can publish a SUBSET of h0 partitions and
        #     look done (#409). Per-index retries fail a partial run loudly and let a
        #     healthy node pick the index up.
        note = (
            f"{i}# chunk-size {spec['chunk']} x {spec['completions']} completions = "
            f"{cap:,} capacity for {spec['count']:,} features\n"
            f"{i}# ({margin:.0f}% headroom for upstream drift). Estimated {spec['est_rows']} "
            f"hex rows at res 10,\n"
            f"{i}# calibrated from #451 (2.92 hex rows per recorded acre). Per-index retries,\n"
            f"{i}# NOT backoffLimit:0, so a partial run fails loudly instead of publishing a\n"
            f"{i}# subset of h0 partitions (#409).\n"
            f"{i}backoffLimitPerIndex: 2\n"
            f"{i}maxFailedIndexes: {spec['maxfail']}")
        text, n = re.subn(rf"{i}backoffLimit: 0", note, text)
        assert n == 1, f"{where}: expected 1 `backoffLimit: 0`, found {n}"
        return text

    def patch_pmtiles(text, where):
        """Raise the open-file limit before tippecanoe.

        tippecanoe shards through many temporary files; on nodes whose default soft
        RLIMIT_NOFILE is low it dies with `Too many open files` partway through the
        write, and the Job fails with no output. Observed here on
        oil-gas-participating-areas (2,562 features) even though the 42-feature layer
        succeeded, so it is a node-dependent limit, not a size threshold. The generator
        does not emit this; #451 carries the same line as a hand-edit. `|| true` because
        an unprivileged container may not be permitted to raise it, in which case we
        still want the attempt rather than a hard failure.
        """
        gen_flags = ("--drop-densest-as-needed --extend-zooms-if-still-dropping --force")
        # Use the flag set proven on this exact data family by #451/#477 instead of the
        # generator default. `--extend-zooms-if-still-dropping` with no -z cap lets
        # tippecanoe keep adding zoom levels, and the shard count grows with them until
        # it lands on a non-power-of-2 and trips the radix-sort assertion
        # "Internal error: N shards not a power of 2" (felt/tippecanoe#216) — observed
        # here as 745 shards on oil-gas-participating-areas. Pinning -z 13 bounds it.
        # These are parcel polygons; zoom 13 is ample.
        proven_flags = ("--coalesce-densest-as-needed --drop-densest-as-needed -z 13 --force")
        old = f"          tippecanoe -o /tmp/$DATASET.pmtiles -l $DATASET {gen_flags}"
        new = (f"          ulimit -n 65536 || true\n"
               f"          tippecanoe -o /tmp/$DATASET.pmtiles -l $DATASET {proven_flags}")
        if where == "configmap.yaml":       # embedded copy is indented 4 further
            old = "    " + old
            new = "    " + new.replace("\n          ", "\n              ")
        n = text.count(old)
        assert n == 1, f"{where}: expected 1 tippecanoe invocation, found {n}"
        return text.replace(old, new)

    hexf = d / f"{spec['name']}-hex.yaml"
    hexf.write_text(patch(hexf.read_text(), 2, hexf.name))
    pmf = d / f"{spec['name']}-pmtiles.yaml"
    pmf.write_text(patch_pmtiles(pmf.read_text(), pmf.name))
    cmf = d / "configmap.yaml"
    cmf.write_text(patch_pmtiles(patch(cmf.read_text(), 6, cmf.name), cmf.name))
    return cap, margin


def main():
    import sys
    do_pipeline = "--pipeline" in sys.argv
    for spec in LAYERS:
        v = VARIANTS[spec["variant"]]
        eff_cov, disp_cov = COVERAGE[spec["name"]]
        title = spec["name"].replace("-", " ").title()
        ng = NULLGEOM[spec["name"]]
        ng_pct = f"{100.0 * ng / spec['count']:.1f}%"
        # A quarter of coal cases have no geometry -- loud enough that it belongs in the
        # manifest header, not just the STAC.
        ng_warn = ("\n#\n#   *** HEADLINE CAVEAT: {} of cases here have NO geometry -- any "
                   "area, extent or\n#   *** overlap computed from the hex or PMTiles for this "
                   "layer silently omits a\n#   *** quarter of the cases. This must appear in "
                   "the STAC collection description,\n#   *** the hex asset description, and "
                   "the README.".format(ng_pct)
                   if ng / spec["count"] > 0.10 else "")

        if v["has_disp_dt"]:
            disp_line = (f"disp_year      year of CSE_DISP_DT ({disp_cov}% populated) -- "
                         f"the leasable/salable\n"
                         f"#                  variant only")
            disp_derive = '              out["disp_year"] = year_of(out.get("CSE_DISP_DT"))'
            case_year_fallback = ' if out["eff_year"] is not None else out["disp_year"]'
            src_fallback = ('                                     else "disposition" '
                            'if out["disp_year"] is not None\n')
        else:
            disp_line = ("disp_year      ALWAYS NULL here -- this service exposes no "
                         "CSE_DISP_DT. Emitted\n"
                         "#                  anyway so all seven collections share one column list")
            disp_derive = ('              # This service has no CSE_DISP_DT, so disp_year is '
                           'always NULL on this\n'
                           '              # layer. Emitted regardless to keep the column list '
                           'identical across all\n'
                           '              # seven mineral case-record datasets.\n'
                           '              out["disp_year"] = None')
            case_year_fallback = ""
            src_fallback = ""

        body = TEMPLATE.format(
            name=spec["name"], service=spec["service"], layer=spec["layer"],
            count=spec["count"], desc=spec["desc"], title=title,
            variant=spec["variant"],
            variant_note=ENERGY_NOTE if spec["variant"] == "energy" else LEASABLE_NOTE,
            eff_cov=f" ({eff_cov}% populated)",
            nullgeom=f"{ng:,}", nullgeom_pct=ng_pct, nullgeom_warn=ng_warn,
            disp_line=disp_line, disp_derive=disp_derive,
            case_year_fallback=case_year_fallback, src_fallback=src_fallback,
            keep=tup(v["keep"]), dates=tup(v["dates"]),
            floor=int(spec["count"] * 0.98),
        )
        d = HERE / spec["name"]
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"{spec['name']}-stage-raw.yaml"
        out.write_text(body)
        msg = (f"wrote {out.relative_to(HERE.parents[2])}  ({spec['count']:,} features, "
               f"{spec['variant']})")
        if do_pipeline:
            cap, margin = pipeline(spec)
            msg += (f"\n      + DAG: hex {spec['completions']}x{spec['chunk']}="
                    f"{cap:,} cap ({margin:.0f}% headroom), repartition {spec['rp_mem']}")
        print(msg)


if __name__ == "__main__":
    main()
