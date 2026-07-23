#!/usr/bin/env python3
"""Stage one UDOGM sub-layer from its ArcGIS REST FeatureServer to a GeoJSON (issue #480).

Paginates the layer (`resultOffset`, `outSR=4326`, `f=geojson`), subsets each feature's
properties to the documented column contract, derives an integer `year` from the best
per-layer date field (null where absent), and writes a single GeoJSON to `out_path`.
Then a count assertion fails loudly if the service under-delivered vs the verified counts
(2026-07-23). The convert job rclone-localizes this GeoJSON and runs cng-convert-to-parquet.

Usage:  udogm_stage.py <sub-layer> <out_path>
        <sub-layer> in {wells, mineral-mines, coal-permits, oil-gas-fields}
"""
import datetime as _dt
import json
import sys
import urllib.parse
import urllib.request

# Per sub-layer: REST layer base (no /query), fields to keep, year derivation, expected count.
# year kinds: "epochms" (Esri Date, ms since epoch -> calendar year), "yearstr" (4-char
# year string -> int), None (no reliable date -> year is always null).
LAYERS = {
    "wells": {
        "base": "https://gis.trustlands.utah.gov/mapping/rest/services/"
                "Energy_Wells_DOGM/FeatureServer/4",
        "keep": ["api", "wellname", "operator", "fieldname", "county",
                 "leasetype", "wellstatus", "welltype", "worktype", "unitname"],
        "year_kind": "epochms",
        "year_fields": ["origcompld", "eventdate"],  # first populated wins
        "expect": 40344,
        "min_ok": 39000,
        "page": 2000,
    },
    "mineral-mines": {
        "base": "https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/"
                "Minerals_Permits_View_Layer/FeatureServer/0",
        "keep": ["Permit", "Status", "Mine_Name", "Mineral_Type", "Company",
                 "Mine_Status", "County", "Surface_Owner", "app_acr", "Bond_Amount"],
        "year_kind": "epochms",
        "year_fields": ["approved"],
        "expect": 1504,
        "min_ok": 1450,
        "page": 1000,
    },
    "coal-permits": {
        "base": "https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/"
                "Coalpermit/FeatureServer/0",
        "keep": ["permit_no", "status", "company", "mine_name", "County",
                 "acres", "TotalPermitArea", "TotalDisturbedArea"],
        "year_kind": None,
        "year_fields": [],
        "expect": 32,
        "min_ok": 30,
        "page": 500,
    },
    "oil-gas-fields": {
        "base": "https://services.arcgis.com/ZzrwjTRez6FJiOq4/arcgis/rest/services/"
                "Oil_and_Gas_Fields/FeatureServer/0",
        "keep": ["FIELDNUM", "FIELDNAME", "STATUS", "COUNTY", "PROD_FORM_",
                 "DISC_WELL", "COMMENTS"],
        "year_kind": "yearstr",
        "year_fields": ["DATE"],
        "expect": 153,
        "min_ok": 150,
        "page": 500,
    },
}


def _fetch(url):
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)


def _derive_year(props, cfg):
    kind = cfg["year_kind"]
    if kind is None:
        return None
    for f in cfg["year_fields"]:
        v = props.get(f)
        if v in (None, "", 0):
            continue
        try:
            if kind == "epochms":
                # Esri dates are ms since Unix epoch (UTC). Guard against absurd values.
                y = _dt.datetime.utcfromtimestamp(int(v) / 1000.0).year
                if 1850 <= y <= 2100:
                    return y
            elif kind == "yearstr":
                y = int(str(v)[:4])
                if 1850 <= y <= 2100:
                    return y
        except (ValueError, TypeError, OSError, OverflowError):
            continue
    return None


def main():
    sub = sys.argv[1]
    out = sys.argv[2]
    cfg = LAYERS[sub]
    base = cfg["base"].rstrip("/")
    page = cfg["page"]
    keep = cfg["keep"]

    feats, offset = [], 0
    while True:
        q = {
            "where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page,
            "returnGeometry": "true",
        }
        url = f"{base}/query?" + urllib.parse.urlencode(q)
        d = _fetch(url)
        batch = d.get("features", [])
        exceeded = (d.get("properties", {}) or {}).get("exceededTransferLimit") \
            or d.get("exceededTransferLimit")
        for feat in batch:
            src = feat.get("properties", {}) or {}
            # Source strings are fixed-width space-padded (Forklift ETL); strip and
            # collapse empty-after-strip to null so categoricals/filters are clean.
            out_props = {}
            for k in keep:
                v = src.get(k)
                if isinstance(v, str):
                    v = v.strip() or None
                out_props[k] = v
            out_props["year"] = _derive_year(src, cfg)
            feat["properties"] = out_props
        feats.extend(batch)
        print(f"  offset {offset}: +{len(batch)} (total {len(feats)})", file=sys.stderr)
        if not batch:
            break
        if len(batch) < page and not exceeded:
            break
        offset += len(batch)

    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
          "features": feats}
    with open(out, "w") as fh:
        json.dump(fc, fh)

    n_year = sum(1 for f in feats if f["properties"].get("year") is not None)
    print(f"WROTE {len(feats)} features -> {out}  ({n_year} with year)", file=sys.stderr)
    assert len(feats) >= cfg["min_ok"], \
        f"{sub}: expected ~{cfg['expect']} features, got {len(feats)}"


if __name__ == "__main__":
    main()
