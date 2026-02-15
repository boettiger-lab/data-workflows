# IUCN Range Maps

Raw polygon range map data from the IUCN Red List.

## Location

**S3 Bucket:** `nrp:public-iucn/raw/rangemaps/`  
**Public URL:** `https://s3-west.nrp-nautilus.io/public-iucn/raw/rangemaps/`

## Data Source

- **Source:** [IUCN Red List Spatial Data Download](https://www.iucnredlist.org/resources/spatial-data-download)
- **Birds:** [BirdLife International Data Zone](http://datazone.birdlife.org/species/spcdownload)
- **Date Downloaded:** 2026-01-23

## Files

| File | Size | MD5 |
|------|------|-----|
| BOTW.fgb | 7.5 GB | — |
| BOTW.parquet | 1.5 GB | — |
| species.zip | 3.9 GB | `7d369fe0364870e7df3a96797191cf26` |
| PLANTS.zip | 3.2 GB | `5de21cbce516155eb1c2c326b0ca62f5` |
| AMPHIBIANS.zip | 1.7 GB | `b6029be49dd9477f8f9b13b51893fd0a` |
| REPTILES.zip | 1.4 GB | `37e356873a4e99a983c56894c4e8a501` |
| MAMMALS.zip | 1.2 GB | `bb857ad66b3a9ed04ff9f92909b361f6` |

## Workflow

1. Download files from IUCN Red List website (requires registration)
2. Upload to NRP storage:

```bash
# Upload zip files from Downloads
rclone copy ~/Downloads/ nrp:public-iucn/raw/rangemaps/ --include "*.zip" -v

# Upload Birds of the World (from minio staging)
rclone copy minio:shared-iucn/BOTW.fgb nrp:public-iucn/raw/rangemaps/ -v
rclone copy minio:shared-iucn/BOTW.parquet nrp:public-iucn/raw/rangemaps/ -v
```

## File Formats

- **ZIP archives** contain ESRI Shapefiles or File Geodatabases (.gdb)
- **FlatGeoBuf (.fgb)** is a cloud-optimized vector format
- **Parquet** is columnar storage for efficient queries

## Citation

IUCN. (2025). The IUCN Red List of Threatened Species. Version 2025-1. https://www.iucnredlist.org

BirdLife International. (2024). Bird species distribution maps of the world. Version 2024.1. http://datazone.birdlife.org
