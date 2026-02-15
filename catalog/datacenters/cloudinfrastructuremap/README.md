# Data Center Locations Dataset

This directory contains a dataset of global data center locations, including Cloud Regions, Local Zones, and On-Ramps.

## Source Data

The data is sourced from [Cloud Infrastructure Map](https://www.cloudinfrastructuremap.com/).
Specifically, it is fetched from their public API endpoint:
`https://www.cloudinfrastructuremap.com/api/service/all.js`

## Contents

- **`data_centers.csv`**: The primary dataset in CSV format.
  - Columns: `provider`, `region_name`, `type`, `metro`, `country`, `latitude`, `longitude`, `zones`.
- **`data_centers.geojson`**: The same dataset in GeoJSON format (FeatureCollection of Points).
- **`scrape_data_centers.py`**: Python script to fetch the latest data from the source and save it as CSV.
- **`create_geojson.py`**: Python script to convert the CSV file into GeoJSON format.

## Process

1.  **Scraping**: The `scrape_data_centers.py` script fetches the JSON data directly from the source website. It parses the nested structure (Regions/Zones/On-Ramps) and extracts the provider details and pre-defined coordinates.
2.  **Conversion**: The `create_geojson.py` script reads the generated CSV and converts each row into a GeoJSON Feature Point, preserving all attributes as properties.

## Usage

To update the dataset:

1.  **Install dependencies**:
    ```bash
    pip install requests
    ```

2.  **Run the scraper**:
    ```bash
    python3 scrape_data_centers.py
    ```
    This will update `data_centers.csv`.

3.  **Generate GeoJSON**:
    ```bash
    python3 create_geojson.py
    ```
    This will update `data_centers.geojson`.
