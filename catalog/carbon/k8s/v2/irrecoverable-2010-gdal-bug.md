# Bug Report: gdal_translate fails on irrecoverable_c_total_2010.tif

**Date:** 2026-02-20  
**Source:** Zenodo record [https://zenodo.org/records/17645053](https://zenodo.org/records/17645053)  
**File:** `09_Irrecoverable_Carbon_Total_v1a_300m_2010.zip` (1.48 GB zip → `Irrecoverable_Carbon_Total_v1a_300m_2010.tif`, 2.3 GB unzipped)

## Minimal Reproduction

```bash
curl -L "https://zenodo.org/records/17645053/files/09_Irrecoverable_Carbon_Total_v1a_300m_2010.zip?download=1" -o test.zip
unzip test.zip
gdal_translate -b 1 Irrecoverable_Carbon_Total_v1a_300m_2010.tif out.tif
```

## Error Output

```
ERROR 1: Irrecoverable_Carbon_Total_v1a_300m_2010.tif:
  Failed to allocate memory for to read TIFF directory (0 elements of 20 bytes each)
ERROR 1: Irrecoverable_Carbon_Total_v1a_300m_2010.tif:
  TIFFReadDirectory:Failed to read directory at offset 2448179594
```

No output file is produced; the command exits non-zero.

## Key Observations

- Offset `2448179594` (~2.27 GB) is well within the 2.3 GB file — not a truncation issue.
- "0 elements of 20 bytes each" indicates the IFD directory entry count field reads as 0 or garbage at that offset.
- The error fires in libtiff's `TIFFReadDirectory` during IFD chain traversal, which happens at file open time.
- `-oo OVERVIEW_LEVEL=NONE` does not prevent the error — libtiff traverses the full IFD chain before GDAL's open options take effect.
- `gdal.PushErrorHandler('CPLQuietErrorHandler')` in Python also does not suppress it — the failure is at the libtiff level before GDAL error handling can intercept it.
- All four other irrecoverable-carbon year files (2018, 2022, 2023, 2024) convert without issue using the identical pipeline.
- The file contains multiple IFDs (main image + overview). The corrupt entry is in an overview IFD.
- The main raster band data is presumably intact; the file was in use by Conservation International when it was published.

## Question for GDAL Developers

Is there an open option, environment variable, or libtiff build flag that allows skipping or tolerating a corrupt overview IFD while still reading the main image band data? Or does this require a libtiff patch to make IFD traversal errors non-fatal?

## Current Status

This file is **skipped** in the v2 processing pipeline. The `irrecoverable-carbon-2010` dataset is not included in the S3 bucket or hex workflow outputs. All other 10 year/type combinations are processed normally.

If a workaround or Zenodo re-upload resolves the issue, re-run:
```bash
kubectl apply -f catalog/carbon/k8s/v2/individual-cog-jobs/carbon-v2-cog-irrec-2010.yaml
# then, after COG is in S3:
kubectl apply -f catalog/carbon/k8s/v2/irrecoverable-carbon-2010/configmap.yaml \
              -f catalog/carbon/k8s/v2/irrecoverable-carbon-2010/workflow.yaml
```
