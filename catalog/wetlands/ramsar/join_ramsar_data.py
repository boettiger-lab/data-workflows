"""
Join Ramsar site data from multiple sources:
1. Start with ramsar_wetlands.parquet (existing polygons)
2. Join with site-details.parquet for additional metadata
3. For missing sites, try to match with WDPA using fuzzy matching
4. For remaining sites, use centroid coordinates
"""

import duckdb
import os
from datetime import datetime

def setup_duckdb():
    """Configure DuckDB with S3 and spatial extensions"""
    print("Connecting to DuckDB...")
    conn = duckdb.connect(database=':memory:')
    print("Installing extensions...")
    conn.execute("INSTALL httpfs;")
    conn.execute("LOAD httpfs;")
    conn.execute("INSTALL spatial;")
    conn.execute("LOAD spatial;")
    
    # Configure S3 credentials using DuckDB secret manager
    print("Configuring S3 credentials...")
    endpoint = os.environ.get('AWS_S3_ENDPOINT', 'minio.carlboettiger.info')
    use_ssl = 'false' if 'rook' in endpoint else 'true'
    
    conn.execute(f"""
        CREATE SECRET s3 (
            TYPE S3,
            KEY_ID '{os.environ.get("AWS_ACCESS_KEY_ID", "")}',
            SECRET '{os.environ.get("AWS_SECRET_ACCESS_KEY", "")}',
            ENDPOINT '{endpoint}',
            URL_STYLE 'path',
            USE_SSL {use_ssl}
        );
    """)
    print(f"DuckDB configured successfully (endpoint={endpoint}, use_ssl={use_ssl})")
    return conn

def main():
    print(f"Starting Ramsar data integration at {datetime.now()}")
    conn = setup_duckdb()
    
    # Define data sources
    ramsar_polygons = "s3://public-wetlands/ramsar/ramsar_wetlands.parquet"
    site_details = "s3://public-wetlands/ramsar/site-details.parquet"
    wdpa = "s3://public-wdpa/WDPA_Dec2025.parquet"
    centroids = "s3://public-wetlands/ramsar/raw/features_centroid_publishedPoint.parquet"
    
    print("\n=== Step 1: Join existing ramsar polygons with site details ===")
    conn.execute(f"""
        CREATE TABLE ramsar_with_details AS
        SELECT 
            rp.*,
            sd."Site name",
            sd.Region,
            sd.Country,
            sd.Territory,
            sd."Designation date",
            sd."Last publication date",
            sd."Area (ha)",
            sd."Annotated summary",
            sd.Criterion1, sd.Criterion2, sd.Criterion3, sd.Criterion4, sd.Criterion5,
            sd.Criterion6, sd.Criterion7, sd.Criterion8, sd.Criterion9,
            sd."Wetland Type",
            sd."Maximum elevation",
            sd."Minimum elevation",
            sd."Montreux listed",
            sd."Management plan implemented",
            sd."Management plan available",
            sd."Ecosystem services",
            sd.Threats,
            sd."large administrative region",
            sd."Global international legal designations",
            sd."Regional international legal designations",
            sd."National conservation designation"
        FROM '{ramsar_polygons}' rp
        LEFT JOIN '{site_details}' sd ON rp.ramsarid = sd.ramsarid;
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM ramsar_with_details").fetchone()
    print(f"Created {result[0]} records with existing polygons + site details")
    
    print("\n=== Step 2: Identify missing sites ===")
    conn.execute(f"""
        CREATE TABLE missing_sites AS
        SELECT *
        FROM '{site_details}'
        WHERE ramsarid NOT IN (
            SELECT DISTINCT ramsarid FROM '{ramsar_polygons}'
        );
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM missing_sites").fetchone()
    print(f"Found {result[0]} sites without polygon data")
    
    print("\n=== Step 3: Match missing sites with WDPA ===")
    # Strategy: Match on name similarity and country, considering area
    conn.execute(f"""
        CREATE TABLE wdpa_ramsar AS
        SELECT 
            w.NAME,
            w.DESIG,
            w.DESIG_ENG,
            w.ISO3,
            w.REP_AREA,
            w.GIS_AREA,
            w.SHAPE,
            w.STATUS_YR
        FROM '{wdpa}' w
        WHERE w.DESIG LIKE '%Ramsar%' OR w.DESIG_ENG LIKE '%Ramsar%';
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM wdpa_ramsar").fetchone()
    print(f"Found {result[0]} Ramsar sites in WDPA database")
    
    # Create a mapping table using fuzzy matching
    # Match on name similarity (case insensitive, trimmed)
    print("\n=== Step 3a: Performing fuzzy matching ===")
    conn.execute("""
        CREATE TABLE wdpa_matches AS
        SELECT 
            ms.ramsarid,
            ms."Site name" as ramsar_name,
            ms.Country as ramsar_country,
            ms."Area (ha)" as ramsar_area,
            wr.NAME as wdpa_name,
            wr.ISO3 as wdpa_iso3,
            wr.REP_AREA as wdpa_area,
            wr.SHAPE,
            -- Calculate similarity score
            CASE 
                WHEN LOWER(TRIM(ms."Site name")) = LOWER(TRIM(wr.NAME)) THEN 1.0
                WHEN LOWER(TRIM(wr.NAME)) LIKE '%' || LOWER(TRIM(ms."Site name")) || '%' THEN 0.8
                WHEN LOWER(TRIM(ms."Site name")) LIKE '%' || LOWER(TRIM(wr.NAME)) || '%' THEN 0.8
                ELSE 0.0
            END as name_match_score,
            -- Area similarity (within 10% = good match)
            CASE 
                WHEN ms."Area (ha)" IS NULL OR wr.REP_AREA IS NULL THEN 0.0
                WHEN ABS(ms."Area (ha)" - wr.REP_AREA) / GREATEST(ms."Area (ha)", wr.REP_AREA) < 0.1 THEN 1.0
                WHEN ABS(ms."Area (ha)" - wr.REP_AREA) / GREATEST(ms."Area (ha)", wr.REP_AREA) < 0.3 THEN 0.5
                ELSE 0.0
            END as area_match_score
        FROM missing_sites ms
        CROSS JOIN wdpa_ramsar wr
        WHERE (
            LOWER(TRIM(ms."Site name")) = LOWER(TRIM(wr.NAME))
            OR LOWER(TRIM(wr.NAME)) LIKE '%' || LOWER(TRIM(ms."Site name")) || '%'
            OR LOWER(TRIM(ms."Site name")) LIKE '%' || LOWER(TRIM(wr.NAME)) || '%'
        );
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM wdpa_matches").fetchone()
    print(f"Found {result[0]} potential WDPA matches")
    
    # Select best match for each ramsar site
    conn.execute("""
        CREATE TABLE best_wdpa_matches AS
        SELECT 
            ramsarid,
            ramsar_name,
            wdpa_name,
            SHAPE,
            name_match_score,
            area_match_score,
            (name_match_score + area_match_score) / 2 as total_score
        FROM wdpa_matches
        WHERE (ramsarid, (name_match_score + area_match_score) / 2) IN (
            SELECT ramsarid, MAX((name_match_score + area_match_score) / 2)
            FROM wdpa_matches
            GROUP BY ramsarid
        )
        AND (name_match_score + area_match_score) / 2 >= 0.4;  -- Minimum threshold
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM best_wdpa_matches").fetchone()
    print(f"Matched {result[0]} sites with WDPA (score >= 0.4)")
    
    # Show sample matches
    print("\nSample WDPA matches:")
    matches = conn.execute("""
        SELECT ramsar_name, wdpa_name, total_score
        FROM best_wdpa_matches
        ORDER BY total_score DESC
        LIMIT 5
    """).fetchall()
    for match in matches:
        print(f"  {match[0]} -> {match[1]} (score: {match[2]:.2f})")
    
    print("\n=== Step 4: Create records from WDPA matches ===")
    conn.execute("""
        CREATE TABLE wdpa_additions AS
        SELECT 
            ms.ramsarid,
            bw.SHAPE as geometry,
            ms."Site name",
            ms.Region,
            ms.Country,
            ms.Territory,
            ms."Designation date",
            ms."Last publication date",
            ms."Area (ha)",
            ms."Annotated summary",
            ms.Criterion1, ms.Criterion2, ms.Criterion3, ms.Criterion4, ms.Criterion5,
            ms.Criterion6, ms.Criterion7, ms.Criterion8, ms.Criterion9,
            ms."Wetland Type",
            ms."Maximum elevation",
            ms."Minimum elevation",
            ms."Montreux listed",
            ms."Management plan implemented",
            ms."Management plan available",
            ms."Ecosystem services",
            ms.Threats,
            ms."large administrative region",
            ms."Global international legal designations",
            ms."Regional international legal designations",
            ms."National conservation designation",
            'WDPA' as source
        FROM missing_sites ms
        JOIN best_wdpa_matches bw ON ms.ramsarid = bw.ramsarid;
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM wdpa_additions").fetchone()
    print(f"Created {result[0]} records from WDPA matches")
    
    print("\n=== Step 5: Handle remaining sites with centroids ===")
    # Sites still missing after WDPA matching
    conn.execute("""
        CREATE TABLE still_missing AS
        SELECT ramsarid
        FROM missing_sites
        WHERE ramsarid NOT IN (SELECT ramsarid FROM best_wdpa_matches);
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM still_missing").fetchone()
    print(f"Still missing {result[0]} sites after WDPA matching")
    
    # Load centroids and create point geometries
    print("Loading centroid data from parquet...")
    try:
        conn.execute(f"""
            CREATE TABLE centroids AS
            SELECT * FROM '{centroids}';
        """)
    except Exception as e:
        print(f"Warning: Could not load centroids due to encoding issue: {e}")
        print("Creating empty centroids table...")
        conn.execute("""
            CREATE TABLE centroids (
                v_idris INTEGER,
                ramsarid INTEGER,
                officialna VARCHAR,
                iso3 VARCHAR,
                country_en VARCHAR,
                area_off DOUBLE,
                geom BLOB
            );
        """)
    
    result = conn.execute("SELECT COUNT(*) FROM centroids").fetchone()
    print(f"Loaded {result[0]} centroid points")
    
    # Create point records
    conn.execute("""
        CREATE TABLE centroid_additions AS
        SELECT 
            ms.ramsarid,
            c.geometry as geometry,
            ms."Site name",
            ms.Region,
            ms.Country,
            ms.Territory,
            ms."Designation date",
            ms."Last publication date",
            ms."Area (ha)",
            ms."Annotated summary",
            ms.Criterion1, ms.Criterion2, ms.Criterion3, ms.Criterion4, ms.Criterion5,
            ms.Criterion6, ms.Criterion7, ms.Criterion8, ms.Criterion9,
            ms."Wetland Type",
            ms."Maximum elevation",
            ms."Minimum elevation",
            ms."Montreux listed",
            ms."Management plan implemented",
            ms."Management plan available",
            ms."Ecosystem services",
            ms.Threats,
            ms."large administrative region",
            ms."Global international legal designations",
            ms."Regional international legal designations",
            ms."National conservation designation",
            'centroid' as source
        FROM missing_sites ms
        JOIN still_missing sm ON ms.ramsarid = sm.ramsarid
        JOIN centroids c ON ms.ramsarid = c.ramsarid;
    """)
    
    result = conn.execute("SELECT COUNT(*) FROM centroid_additions").fetchone()
    print(f"Created {result[0]} records from centroids")
    
    print("\n=== Step 6: Combine all data sources ===")
    # Union all sources
    conn.execute("""
        CREATE TABLE ramsar_complete AS
        SELECT 
            ramsarid,
            geometry,
            "Site name",
            Region,
            Country,
            Territory,
            "Designation date",
            "Last publication date",
            "Area (ha)",
            "Annotated summary",
            Criterion1, Criterion2, Criterion3, Criterion4, Criterion5,
            Criterion6, Criterion7, Criterion8, Criterion9,
            "Wetland Type",
            "Maximum elevation",
            "Minimum elevation",
            "Montreux listed",
            "Management plan implemented",
            "Management plan available",
            "Ecosystem services",
            Threats,
            "large administrative region",
            "Global international legal designations",
            "Regional international legal designations",
            "National conservation designation",
            'original' as source
        FROM ramsar_with_details
        
        UNION ALL
        
        SELECT * FROM wdpa_additions
        
        UNION ALL
        
        SELECT * FROM centroid_additions;
    """)
    
    result = conn.execute("SELECT COUNT(*) as total FROM ramsar_complete").fetchone()
    print(f"\nTotal combined records: {result[0]}")
    
    # Summary statistics
    print("\n=== Summary by source ===")
    summary = conn.execute("""
        SELECT 
            source,
            COUNT(*) as count,
            COUNT(DISTINCT ramsarid) as unique_sites
        FROM ramsar_complete
        GROUP BY source
        ORDER BY count DESC;
    """).fetchall()
    
    for row in summary:
        print(f"  {row[0]}: {row[1]} records, {row[2]} unique sites")
    
    # Coverage check
    print("\n=== Coverage check ===")
    coverage = conn.execute(f"""
        SELECT 
            (SELECT COUNT(DISTINCT ramsarid) FROM ramsar_complete) as sites_with_geometry,
            (SELECT COUNT(*) FROM '{site_details}') as total_sites_in_details,
            ROUND(100.0 * (SELECT COUNT(DISTINCT ramsarid) FROM ramsar_complete) / 
                  (SELECT COUNT(*) FROM '{site_details}'), 2) as coverage_percent;
    """).fetchone()
    print(f"  Sites with geometry: {coverage[0]}")
    print(f"  Total sites in details: {coverage[1]}")
    print(f"  Coverage: {coverage[2]}%")
    
    print("\n=== Step 7: Export to parquet ===")
    output_path = "/tmp/ramsar_complete.parquet"
    conn.execute(f"""
        COPY ramsar_complete TO '{output_path}' (FORMAT PARQUET);
    """)
    print(f"Exported complete dataset to {output_path}")
    
    # Upload to S3
    print("Uploading to S3...")
    conn.execute("""
        COPY ramsar_complete TO 's3://public-wetlands/ramsar/ramsar_wetlands.parquet' (FORMAT PARQUET);
    """)
    print("Uploaded to s3://public-wetlands/ramsar/ramsar_wetlands.parquet")
    
    # Also create a summary report
    print("\n=== Creating summary report ===")
    conn.execute(f"""
        CREATE TABLE summary_report AS
        SELECT 
            'Total sites in site-details' as metric,
            COUNT(*)::VARCHAR as value
        FROM '{site_details}'
        
        UNION ALL
        
        SELECT 
            'Sites with original polygons',
            COUNT(DISTINCT ramsarid)::VARCHAR
        FROM ramsar_with_details
        
        UNION ALL
        
        SELECT 
            'Sites matched from WDPA',
            COUNT(DISTINCT ramsarid)::VARCHAR
        FROM wdpa_additions
        
        UNION ALL
        
        SELECT 
            'Sites with centroids only',
            COUNT(DISTINCT ramsarid)::VARCHAR
        FROM centroid_additions
        
        UNION ALL
        
        SELECT 
            'Total sites in final dataset',
            COUNT(DISTINCT ramsarid)::VARCHAR
        FROM ramsar_complete
        
        UNION ALL
        
        SELECT 
            'Total geometries in final dataset',
            COUNT(*)::VARCHAR
        FROM ramsar_complete;
    """)
    
    report_path = "/tmp/ramsar_summary.parquet"
    conn.execute(f"""
        COPY summary_report TO '{report_path}' (FORMAT PARQUET);
    """)
    print(f"Exported summary report to {report_path}")
    
    # Upload summary to S3
    conn.execute("""
        COPY summary_report TO 's3://public-wetlands/ramsar/ramsar_summary.parquet' (FORMAT PARQUET);
    """)
    print("Uploaded summary to s3://public-wetlands/ramsar/ramsar_summary.parquet")
    
    # Display final report
    print("\n" + "="*60)
    print("FINAL SUMMARY REPORT")
    print("="*60)
    report = conn.execute("SELECT * FROM summary_report").fetchall()
    for row in report:
        print(f"{row[0]:<40} {row[1]:>15}")
    print("="*60)
    
    conn.close()
    print(f"\nCompleted at {datetime.now()}")

if __name__ == "__main__":
    main()
