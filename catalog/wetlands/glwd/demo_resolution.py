#!/usr/bin/env python3
"""
Demo: H3 resolution detection and user override behavior.

This script demonstrates how the raster processor handles resolution detection
and provides informative messages when users override the detected resolution.
"""

import tempfile
import os
import numpy as np
from osgeo import gdal, osr


def create_test_raster(pixel_size_deg, width=10, height=10):
    """Create a test raster with specified pixel size."""
    temp_dir = tempfile.mkdtemp()
    raster_path = os.path.join(temp_dir, 'test.tif')
    
    xmin, ymin = -122.0, 37.0
    
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(raster_path, width, height, 1, gdal.GDT_Int16)
    ds.SetGeoTransform([xmin, pixel_size_deg, 0, ymin + height * pixel_size_deg, 0, -pixel_size_deg])
    
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    
    data = np.arange(width * height, dtype=np.int16).reshape(height, width)
    band = ds.GetRasterBand(1)
    band.WriteArray(data)
    band.FlushCache()
    
    ds = None
    return raster_path


def demo_resolution_messages():
    """Demonstrate resolution detection and override messages."""
    from cng_datasets.raster import RasterProcessor, detect_optimal_h3_resolution
    
    print("=" * 70)
    print("H3 Resolution Detection & Override Demo")
    print("=" * 70)
    
    # Create test rasters with different resolutions
    test_cases = [
        ("Very high-res (1m pixels)", 1/111000),      # ~1m
        ("High-res (30m pixels)", 30/111000),         # ~30m
        ("Medium-res (250m pixels)", 250/111000),     # ~250m
        ("Coarse (1km pixels)", 0.01),                # ~1.1km
        ("Very coarse (10km pixels)", 0.1),           # ~11km
    ]
    
    for name, pixel_size in test_cases:
        print(f"\n{'─' * 70}")
        print(f"Test Case: {name}")
        print(f"{'─' * 70}")
        
        raster_path = create_test_raster(pixel_size)
        
        try:
            # 1. Show auto-detection
            print("\n1️⃣  Auto-detection:")
            detected = detect_optimal_h3_resolution(raster_path, verbose=True)
            
            # 2. Use detected resolution
            print("\n2️⃣  Using detected resolution:")
            processor = RasterProcessor(
                input_path=raster_path,
                h3_resolution=detected,  # Match detected
            )
            
            # 3. Override with finer resolution
            if detected < 15:
                print(f"\n3️⃣  Override with finer resolution (h{detected + 2}):")
                processor = RasterProcessor(
                    input_path=raster_path,
                    h3_resolution=detected + 2,  # Finer
                )
            
            # 4. Override with coarser resolution
            if detected > 0:
                print(f"\n4️⃣  Override with coarser resolution (h{max(0, detected - 2)}):")
                processor = RasterProcessor(
                    input_path=raster_path,
                    h3_resolution=max(0, detected - 2),  # Coarser
                )
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(os.path.dirname(raster_path), ignore_errors=True)
    
    print("\n" + "=" * 70)
    print("✓ Demo complete!")
    print("=" * 70)
    print("\nKey takeaways:")
    print("  • Auto-detection uses raster pixel size to recommend H3 resolution")
    print("  • User can always override the detected resolution")
    print("  • Helpful messages explain the tradeoff (more cells vs more aggregation)")
    print("  • No errors when user chooses different resolution")


if __name__ == "__main__":
    demo_resolution_messages()
