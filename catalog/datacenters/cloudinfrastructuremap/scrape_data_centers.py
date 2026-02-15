import requests
import csv
import json
from pathlib import Path

# URL of the data source
DATA_URL = "https://www.cloudinfrastructuremap.com/api/service/all.js"
OUTPUT_FILE = "data_centers.csv"

def fetch_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def process_data_centers(data):
    rows = []
    
    # Process cloud_regions
    for location in data.get("cloud_regions", []):
        metro = location.get("metro_area", "")
        country = location.get("country", "")
        lat = location.get("latitude", "")
        lon = location.get("longitude", "")
        
        for provider in location.get("cloud_service_providers", []):
            rows.append({
                "provider": provider.get("name", ""),
                "region_name": provider.get("cloud_region_name", ""),
                "type": "Cloud Region",
                "metro": metro,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "zones": provider.get("zones", "")
            })
            
    # Process local_zones
    for location in data.get("local_zones", []):
        metro = location.get("metro_area", "")
        country = location.get("country", "")
        lat = location.get("latitude", "")
        lon = location.get("longitude", "")
        
        for provider in location.get("cloud_service_providers", []):
            rows.append({
                "provider": provider.get("name", ""),
                "region_name": provider.get("cloud_region_name", ""),
                "type": "Local Zone",
                "metro": metro,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "zones": provider.get("zones", "")
            })

    # Process on_ramps (optional, keeping consistent with request for "data centers")
    # Some users might handle on-ramps differently, but usually they are points of presence (PoPs).
    # Including them for completeness.
    for location in data.get("on_ramps", []):
        metro = location.get("metro_area", "")
        country = location.get("country", "")
        lat = location.get("latitude", "")
        lon = location.get("longitude", "")
        
        for provider in location.get("cloud_service_providers", []):
            rows.append({
                "provider": provider.get("name", ""),
                "region_name": provider.get("cloud_region_name", ""),
                "type": "On Ramp",
                "metro": metro,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "zones": provider.get("zones", "")
            })
            
    return rows

def save_to_csv(rows, filename):
    if not rows:
        print("No data to save.")
        return

    fieldnames = ["provider", "region_name", "type", "metro", "country", "latitude", "longitude", "zones"]
    
    try:
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Successfully saved {len(rows)} data centers to {filename}")
    except IOError as e:
        print(f"Error saving CSV: {e}")

def main():
    print(f"Fetching data from {DATA_URL}...")
    data = fetch_data(DATA_URL)
    
    if data:
        print("Processing data...")
        rows = process_data_centers(data)
        save_to_csv(rows, OUTPUT_FILE)

if __name__ == "__main__":
    main()
