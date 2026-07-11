#!/usr/bin/env python3
"""Extract valid pixels from the CC0 Dryad economic rasters to point parquet (lon,lat,val)
for H3 binning in DuckDB. Run with /opt/venv/bin/python (rasterio). See ingest-recipe.md
for the production raster-workflow path; this is the fast POC route."""
import rasterio, numpy as np, pyarrow as pa, pyarrow.parquet as pq, os, sys
base = sys.argv[1] if len(sys.argv)>1 else 'inputs/inputs_for_publication'
layers = {
 'crop_current': 'cropland/oil_palm_split/totalproductionvaluecurrent_NoPalmOilRevR_nolabor_machinerycosts.tif',
 'palm_current': 'cropland/oil_palm_split/totalproductionvaluecurrent_OnlyPalmOilRevR_nolabor_machinerycosts.tif',
 'grazing':      'grazing/potential_meat_returns-t_per_ha_global_price_landshare_md5_d7cfbe4828d5b9a2e11ef1b6e2ccc174.tif',
}
for name,f in layers.items():
    with rasterio.open(os.path.join(base,f)) as ds:
        a=ds.read(1).astype('float64'); nd=ds.nodata; T=ds.transform
        rows,cols=np.where(np.isfinite(a) & (a!=0) & ((nd is None) | (a!=nd)))
        xs,ys=rasterio.transform.xy(T,rows,cols); val=a[rows,cols]
        keep=val>-9000   # drop -9999-class fill; keep moderate (real) negative net values
        pq.write_table(pa.table({'lon':np.asarray(xs)[keep],'lat':np.asarray(ys)[keep],'val':val[keep]}), f'econ_{name}.parquet')
        print(name, int(keep.sum()))
