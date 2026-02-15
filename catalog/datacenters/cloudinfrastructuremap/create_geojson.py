import csv
import json
from pathlib import Path

INPUT_FILE = "data_centers.csv"
OUTPUT_FILE = "data_centers.geojson"

def create_geojson_feature(row):
    try:
        lon = float(row['longitude'])
        lat = float(row['latitude'])
        
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": row
        }
    except ValueError:
        return None

def main():
    features = []
    
    try:
        with open(INPUT_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                feature = create_geojson_feature(row)
                if feature:
                    features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        with open(OUTPUT_FILE, mode='w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2)
            
        print(f"Successfully created {OUTPUT_FILE}")
        print(f"Total features: {len(features)}")
        
    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found.")

if __name__ == "__main__":
    main()
