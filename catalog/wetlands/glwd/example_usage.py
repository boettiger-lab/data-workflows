#!/usr/bin/env python3
"""
Example: Processing a global raster dataset to H3-indexed parquet.

This example demonstrates the complete workflow for converting a raster
dataset to cloud-native formats:
1. Create a Cloud-Optimized GeoTIFF (COG) for visualization
2. Convert to H3-indexed parquet partitioned by h0 regions

The workflow is designed for global datasets that don't fit in memory,
processing each h0 region independently.
"""

import os
import sys

# Add package to path if running from repo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cng_datasets.raster import RasterProcessor, detect_optimal_h3_resolution


def example_local_processing():
    """Process a raster locally (small datasets or single h0 region)."""
    
    print("=" * 60)
    print("Example 1: Local Processing")
    print("=" * 60)
    
    # Input raster (can be local file or S3 URL)
    input_path = "wetlands.tif"
    
    # Detect optimal H3 resolution
    print(f"\nDetecting optimal H3 resolution for {input_path}...")
    h3_res = detect_optimal_h3_resolution(input_path)
    print(f"Recommended: h{h3_res}")
    
    # Create processor
    processor = RasterProcessor(
        input_path=input_path,
        output_cog_path="s3://my-bucket/wetlands-cog.tif",
        output_parquet_path="s3://my-bucket/wetlands/hex/",
        h3_resolution=h3_res,
        parent_resolutions=[h3_res - 1, 0],  # One level up + h0
        value_column="wetland_class",
        nodata_value=255,
        compression="zstd",
    )
    
    # Step 1: Create COG for visualization
    print("\nCreating Cloud-Optimized GeoTIFF...")
    cog_path = processor.create_cog()
    print(f"COG created: {cog_path}")
    
    # Step 2: Convert to H3 parquet
    print("\nProcessing specific h0 region (for testing)...")
    output_file = processor.process_h0_region(h0_index=42)
    print(f"H3 parquet created: {output_file}")
    
    print("\n✓ Local processing complete!")


def example_kubernetes_job():
    """Generate Kubernetes job for parallel processing."""
    
    print("\n" + "=" * 60)
    print("Example 2: Kubernetes Parallel Processing")
    print("=" * 60)
    
    from cng_datasets.k8s import K8sJobManager
    
    # Create job manager
    manager = K8sJobManager(
        namespace="datasets",
        image="ghcr.io/rocker-org/ml-spatial:latest"
    )
    
    # Generate indexed job (one completion per h0 region)
    job_spec = manager.generate_chunked_job(
        job_name="wetlands-h3",
        script_path="/workspace/datasets/wetlands/glwd/job.py",
        num_chunks=122,  # 122 h0 regions
        base_args=[
            "--input-url", "s3://source-bucket/wetlands.tif",
            "--output-url", "s3://output-bucket/wetlands/hex/",
            "--parent-resolutions", "8,0",
            "--value-column", "wetland_class",
            "--nodata", "255",
        ],
        cpu="4",
        memory="34Gi",
        parallelism=61,  # Process half concurrently
    )
    
    # Save job YAML
    output_path = "wetlands-k8s-job.yaml"
    manager.save_job_yaml(job_spec, output_path)
    
    print(f"\n✓ Kubernetes job saved: {output_path}")
    print("\nTo submit the job:")
    print(f"  kubectl apply -f {output_path}")
    print("\nTo monitor progress:")
    print("  kubectl get jobs wetlands-h3")
    print("  kubectl get pods -l k8s-app=wetlands-h3")


def example_cog_only():
    """Create COG without H3 conversion (visualization only)."""
    
    print("\n" + "=" * 60)
    print("Example 3: COG Creation Only")
    print("=" * 60)
    
    from cng_datasets.raster import create_cog
    
    # Simple COG creation
    print("\nCreating COG with custom settings...")
    cog_path = create_cog(
        input_path="high-res-imagery.tif",
        output_path="s3://my-bucket/imagery-cog.tif",
        compression="jpeg",  # Good for RGB imagery
        blocksize=256,
        overviews=True,
        resampling="cubic",  # Better for imagery
    )
    
    print(f"✓ COG created: {cog_path}")
    print("\nThis COG can be rendered in titiler:")
    print("  https://titiler.example.com/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=...")


def example_cli_usage():
    """Show command-line interface examples."""
    
    print("\n" + "=" * 60)
    print("Example 4: Command-Line Usage")
    print("=" * 60)
    
    examples = [
        {
            "name": "Auto-detect resolution and create both COG + H3",
            "cmd": """cng-datasets raster \\
  --input wetlands.tif \\
  --output-cog s3://bucket/wetlands-cog.tif \\
  --output-parquet s3://bucket/wetlands/hex/ \\
  --parent-resolutions "8,0" \\
  --value-column wetland_class \\
  --nodata 255"""
        },
        {
            "name": "Process specific h0 region (for K8s jobs)",
            "cmd": """cng-datasets raster \\
  --input s3://bucket/data.tif \\
  --output-parquet s3://bucket/data/hex/ \\
  --h0-index 42 \\
  --resolution 8"""
        },
        {
            "name": "Create COG only",
            "cmd": """cng-datasets raster \\
  --input imagery.tif \\
  --output-cog s3://bucket/imagery-cog.tif \\
  --compression jpeg \\
  --blocksize 256"""
        },
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}:")
        print(f"   {example['cmd']}")


def example_custom_workflow():
    """Custom workflow with intermediate steps."""
    
    print("\n" + "=" * 60)
    print("Example 5: Custom Workflow")
    print("=" * 60)
    
    # Initialize processor with custom settings
    processor = RasterProcessor(
        input_path="/vsis3/source-bucket/climate-data.tif",
        output_cog_path="s3://output-bucket/climate-cog.tif",
        output_parquet_path="s3://output-bucket/climate/hex/",
        h3_resolution=7,  # ~12km resolution for climate data
        parent_resolutions=[6, 5, 0],
        value_column="temperature",
        nodata_value=-9999,
    )
    
    # Step 1: Create COG
    print("\n1. Creating COG...")
    processor.create_cog(
        overviews=True,
        overview_resampling="average"  # Better for continuous data
    )
    
    # Step 2: Process a subset of h0 regions for testing
    print("\n2. Testing with a few h0 regions...")
    test_regions = [0, 1, 2]  # Americas
    for h0_idx in test_regions:
        output_file = processor.process_h0_region(h0_idx)
        if output_file:
            print(f"   ✓ Processed h0={h0_idx}: {output_file}")
        else:
            print(f"   ⚠ No data in h0={h0_idx}")
    
    # Step 3: Once validated, process all regions
    print("\n3. Ready to process all regions!")
    print("   Run: processor.process_all_h0_regions()")
    print("   Or submit Kubernetes job for parallel processing")


def main():
    """Run all examples."""
    
    print("\n" + "=" * 70)
    print(" Raster Processing Examples")
    print("=" * 70)
    
    print("\nThese examples demonstrate the raster processing capabilities")
    print("of the cng_datasets package.\n")
    
    # Note: Most examples are for demonstration and won't actually run
    # without the proper input files and S3 credentials
    
    try:
        # This one we can safely run
        example_cli_usage()
        
        # These would need actual data files
        print("\n\nNote: Other examples require input files and S3 credentials.")
        print("Run with appropriate data files for full functionality.")
        
        # Uncomment to run with actual data:
        # example_local_processing()
        # example_kubernetes_job()
        # example_cog_only()
        # example_custom_workflow()
        
    except Exception as e:
        print(f"\nExample failed (expected without data files): {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
