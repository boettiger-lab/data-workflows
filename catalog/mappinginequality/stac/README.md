# Mapping Inequality: Redlining in New Deal America

This dataset contains the "Home Owners' Loan Corporation" (HOLC) grades for neighborhoods in cities across the United States. These maps, created in the 1930s, were used to grade the "security" of real estate investments, leading to the practice known as redlining.

## Source

- **Project:** [Mapping Inequality: Redlining in New Deal America](https://dsl.richmond.edu/panorama/redlining/)
- **Authors:** Robert K. Nelson, Laedale Winling, Richard Marciano, Nathan Connolly, et al.
- **Institution:** Digital Scholarship Lab, University of Richmond
- **License:** [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/)

## Data Format

The dataset is available in the following formats:
- **GeoParquet:** `s3://public-mappinginequality/mappinginequality.parquet` (Full dataset)
- **PMTiles:** `s3://public-mappinginequality/mappinginequality.pmtiles` (For web mapping)
- **H3 Hexagons:** `s3://public-mappinginequality/hex/` (Partitioned by h0)

## Data Dictionary

| Column | Type | Description |
|--------|------|-------------|
| `fid` | BigInt | Unique Feature ID |
| `area_id` | Integer | ID of the specific polygon area |
| `city` | String | Name of the city |
| `state` | String | Two-letter state abbreviation |
| `city_survey` | Boolean | Whether the city was surveyed |
| `category` | String | HOLC Grade (A, B, C, D) - duplicates `grade` |
| `grade` | String | HOLC Grade (A="Best", B="Still Desirable", C="Definitely Declining", D="Hazardous") |
| `label` | String | Full label (e.g., "A1", "D4") |
| `residential` | Boolean | Classified as residential area |
| `commercial` | Boolean | Classified as commercial area |
| `industrial` | Boolean | Classified as industrial area |
| `fill` | String | Hex color code associated with the grade |

### HOLC Grades

The `grade` column contains the core classification:
- **A (Green):** "Best" - Upper-class, wealthy neighborhoods.
- **B (Blue):** "Still Desirable" - Sound working-class neighborhoods.
- **C (Yellow):** "Definitely Declining" - Neighborhoods with "infiltration" of lower-grade populations.
- **D (Red):** "Hazardous" - Neighborhoods with high populations of racial/ethnic minorities or "undesirable" features.

## Citation

Robert K. Nelson, Laedale Winling, Richard Marciano, Nathan Connolly, et al., "Mapping Inequality," American Panorama, ed. Robert K. Nelson and Edward L. Ayers, accessed [Date], https://dsl.richmond.edu/panorama/redlining/
