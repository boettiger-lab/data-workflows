"""#914: dam-removal tiles rebuilt so every point shows at every zoom (tippecanoe -r1).

The old build used tippecanoe's default point drop rate, so the overview zooms held a handful
of the 2,126 removals. Same layer name, zoom range (0-14) and fields; built by
catalog/pmtiles-fid/k8s/build.py from the published GeoParquet.
"""

ASSETS = [
    dict(bucket="public-rivers", key="american-rivers/dam-removal.pmtiles",
         src="s3://public-rivers/american-rivers/dam-removal.parquet", geom="geom",
         layer="dam-removal", flags="-r1 -Z0 -z14", select="*"),
]
