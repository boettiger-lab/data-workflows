# PAD-US 4.1 Lookup Tables

Non-spatial reference tables from the PAD-US 4.1 geodatabase, providing code definitions and labels for categorical fields in the main datasets.

**Location:** `s3://public-padus/padus-4-1/lookup/*.parquet`

**Public URL:** `https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/`

## Access

All lookup tables are publicly accessible as Parquet files:

```python
import duckdb

# Example: Read Public_Access lookup table
df = duckdb.sql("""
    SELECT * FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/Public_Access.parquet')
""").df()
```

## Tables

### Public_Access (4 rows)

Defines public access restrictions for protected areas.

| Code | Description |
|------|-------------|
| OA | Open Access |
| RA | Restricted Access |
| UK | Unknown |
| XA | Closed |

**Referenced by:** `Pub_Access` field in main datasets

---

### Category (7 rows)

Primary classification category for protected areas.

| Code | Description |
|------|-------------|
| Designation | Designation |
| Easement | Easement |
| Fee | Fee |
| Marine | Marine Area |
| Other | Other |
| Proclamation | Approved, Proclamation or Extent Boundary |
| Unknown | Unknown |

**Referenced by:** `Category` field in main datasets

---

### Designation_Type (63 rows)

Detailed designation classifications for federal, state, local, and private lands.

<details>
<summary>Show all 63 designation types</summary>

| Code | Description |
|------|-------------|
| ACC | Access Area |
| ACEC | Area of Critical Environmental Concern |
| AGRE | Agricultural Easement |
| CONE | Conservation Easement |
| FACY | Facility |
| FORE | Forest Stewardship Easement |
| FOTH | Federal Other or Unknown |
| HCA | Historic or Cultural Area |
| HCAE | Historic or Cultural Easement |
| IRA | Inventoried Roadless Area |
| LCA | Local Conservation Area |
| LHCA | Local Historic or Cultural Area |
| LOTH | Local Other or Unknown |
| LP | Local Park |
| LREC | Local Recreation Area |
| LRMA | Local Resource Management Area |
| MIL | Military Land |
| MIT | Mitigation Land or Bank |
| MPA | Marine Protected Area |
| NCA | Conservation Area |
| ND | Not Designated |
| NF | National Forest |
| NG | National Grassland |
| NLS | National Lakeshore or Seashore |
| NM | National Monument |
| NP | National Park |
| NRA | National Recreation Area |
| NSBV | National Scenic, Botanical or Volcanic Area |
| NT | National Scenic or Historic Trail |
| NWR | National Wildlife Refuge |
| OCS | Outer Continental Shelf Area |
| OTHE | Other Easement |
| PAGR | Private Agricultural |
| PCON | Private Conservation |
| PFOR | Private Forest Stewardship |
| PHCA | Private Historic or Cultural |
| POTH | Private Other or Unknown |
| PPRK | Private Park |
| PRAN | Private Ranch |
| PREC | Private Recreation or Education |
| PROC | Approved or Proclamation Boundary |
| PUB | National Public Lands |
| RANE | Ranch Easement |
| REA | Research or Educational Area |
| REC | Recreation Management Area |
| RECE | Recreation or Education Easement |
| RMA | Resource Management Area |
| RNA | Research Natural Area |
| SCA | State Conservation Area |
| SDA | Special Designation Area |
| SHCA | State Historic or Cultural Area |
| SOTH | State Other or Unknown |
| SP | State Park |
| SREC | State Recreation Area |
| SRMA | State Resource Management Area |
| SW | State Wilderness |
| TRIBL | Native American Land Area |
| UNK | Unknown |
| UNKE | Unknown Easement |
| WA | Wilderness Area |
| WPA | Watershed Protection Area |
| WSA | Wilderness Study Area |
| WSR | Wild and Scenic River |

</details>

**Referenced by:** `Desig_Type` field in main datasets

---

### GAP_Status (4 rows)

GAP Analysis Program biodiversity management status codes.

| Code | Description |
|------|-------------|
| 1 | managed for biodiversity - disturbance events proceed or are mimicked |
| 2 | managed for biodiversity - disturbance events suppressed |
| 3 | managed for multiple uses - subject to extractive (e.g. mining or logging) or OHV use |
| 4 | no known mandate for biodiversity protection |

**Referenced by:** `GAP_Sts` field in main datasets

---

### IUCN_Category (10 rows)

International Union for Conservation of Nature protected area categories.

| Code | Description |
|------|-------------|
| Ia | Strict nature reserves |
| Ib | Wilderness areas |
| II | National park |
| III | Natural monument or feature |
| IV | Habitat / species management |
| V | Protected landscape / seascape |
| VI | Protected area with sustainable use of natural resources |
| N/R | Not Reported |
| Unassigned | Unassigned |
| Other Conservation Area | Other Conservation Area |

**Referenced by:** `IUCN_Cat` field in main datasets

**Reference:** [IUCN Protected Area Categories](https://www.iucn.org/theme/protected-areas/about/protected-area-categories)

---

### Agency_Name (44 rows)

Specific managing agency names for protected areas.

<details>
<summary>Show all 44 agencies</summary>

| Code | Description | Old_Code |
|------|-------------|----------|
| ARS | Agricultural Research Service | 0155 |
| AS | American Samoa Government | 1002 |
| BIA | Bureau of Indian Affairs | 0160 |
| BLM | Bureau of Land Management | 0110 |
| BOEM | Bureau of Ocean Energy Management | 0115 |
| BPA | Bonneville Power Administration | |
| CITY | City Land | 0510 |
| CNTY | County Land | 0520 |
| DESG | Designation | |
| DOD | Department of Defense | 0135 |
| DOE | Department of Energy | 0140 |
| FM | Federated States of Micronesia Government | 1006 |
| FWS | U.S. Fish and Wildlife Service | 0125 |
| GU | Guam Government | 1003 |
| JNT | Joint | 0800 |
| MH | Marshall Islands Government | 1007 |
| MP | Mariana Islands Government | 1004 |
| NGO | Non-Governmental Organization | |
| NOAA | National Oceanic and Atmospheric Administration | 0165 |
| NPS | National Park Service | 0145 |
| NRCS | Natural Resources Conservation Service | 0150 |
| OTHF | Other or Unknown Federal Land | 0170 |
| OTHR | Other | 0810 |
| OTHS | Other or Unknown State Land | 0395 |
| PR | Puerto Rico Government | 1005 |
| PVT | Private | 0710 |
| PW | Palau Government | 1008 |
| REG | Regional Agency Land | 0410 |
| RWD | Regional Water Districts | 0420 |
| SDC | State Department of Conservation | 0315 |
| SDNR | State Department of Natural Resources | 0340 |
| SDOL | State Department of Land | 0350 |
| SFW | State Fish and Wildlife | 0330 |
| SLB | State Land Board | 0320 |
| SPR | State Park and Recreation | 0310 |
| TRIB | American Indian Lands | 0220 |
| TVA | Tennessee Valley Authority | 0100 |
| UM | U.S. Minor Outlying Islands Government | 1009 |
| UNK | Unknown | 0910 |
| UNKL | Other or Unknown Local Government | |
| USACE | Army Corps of Engineers | |
| USBR | Bureau of Reclamation | 0120 |
| USFS | Forest Service | 0130 |
| VI | U.S. Virgin Islands Government | 1001 |

</details>

**Referenced by:** `Mang_Name` field in main datasets

---

### Agency_Type (11 rows)

Broad agency type classifications.

| Code | Description |
|------|-------------|
| DESG | Designation |
| DIST | Regional Agency Special District |
| FED | Federal |
| JNT | Joint |
| LOC | Local Government |
| NGO | Non-Governmental Organization |
| PVT | Private |
| STAT | State |
| TERR | Territorial |
| TRIB | American Indian Lands |
| UNK | Unknown |

**Referenced by:** `Mang_Type` field in main datasets

---

### State_Name (61 rows)

US states, territories, and associated jurisdictions.

<details>
<summary>Show all 61 states/territories</summary>

| Code | Name | FIPS Code |
|------|------|-----------|
| AK | Alaska | 02 |
| AL | Alabama | 01 |
| AR | Arkansas | 05 |
| AS | American Samoa | 60 |
| AZ | Arizona | 04 |
| CA | California | 06 |
| CO | Colorado | 08 |
| CT | Connecticut | 09 |
| DC | District of Columbia | 11 |
| DE | Delaware | 10 |
| FL | Florida | 12 |
| FM | Federated States of Micronesia | 64 |
| GA | Georgia | 13 |
| GU | Guam | 66 |
| HI | Hawaii | 15 |
| IA | Iowa | 19 |
| ID | Idaho | 16 |
| IL | Illinois | 17 |
| IN | Indiana | 18 |
| KS | Kansas | 20 |
| KY | Kentucky | 21 |
| LA | Louisiana | 22 |
| MA | Massachusetts | 25 |
| MD | Maryland | 24 |
| ME | Maine | 23 |
| MH | Marshall Islands | 68 |
| MI | Michigan | 26 |
| MN | Minnesota | 27 |
| MO | Missouri | 29 |
| MP | Mariana Islands | 65 |
| MS | Mississippi | 28 |
| MT | Montana | 30 |
| NC | North Carolina | 37 |
| ND | North Dakota | 38 |
| NE | Nebraska | 31 |
| NH | New Hampshire | 33 |
| NJ | New Jersey | 34 |
| NM | New Mexico | 35 |
| NV | Nevada | 32 |
| NY | New York | 36 |
| OH | Ohio | 39 |
| OK | Oklahoma | 40 |
| OR | Oregon | 41 |
| PA | Pennsylvania | 42 |
| PR | Puerto Rico | 72 |
| PW | Palau | 70 |
| RI | Rhode Island | 44 |
| SC | South Carolina | 45 |
| SD | South Dakota | 46 |
| TN | Tennessee | 47 |
| TX | Texas | 48 |
| UM | U.S. Minor Outlying Islands | 74 |
| UT | Utah | 49 |
| VA | Virginia | 51 |
| VI | U.S. Virgin Islands | 78 |
| VT | Vermont | 50 |
| WA | Washington | 53 |
| WI | Wisconsin | 55 |
| WV | West Virginia | 54 |
| WY | Wyoming | 56 |

</details>

**Referenced by:** `State_Nm` field in main datasets

---

## Usage Example

Join lookup tables with main dataset for human-readable labels:

```python
import duckdb

con = duckdb.connect()

# Query with lookup joins
result = con.sql("""
    SELECT 
        p.Unit_Nm,
        dt.Dom as Designation_Type,
        pa.Dom as Public_Access,
        gs.Dom as GAP_Status,
        an.Dom as Managing_Agency,
        st.Dom as State
    FROM read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/combined.parquet') p
    LEFT JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/Designation_Type.parquet') dt
        ON p.Desig_Type = dt.Code
    LEFT JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/Public_Access.parquet') pa
        ON p.Pub_Access = pa.Code
    LEFT JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/GAP_Status.parquet') gs
        ON p.GAP_Sts = gs.Code
    LEFT JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/Agency_Name.parquet') an
        ON p.Mang_Name = an.Code
    LEFT JOIN read_parquet('https://s3-west.nrp-nautilus.io/public-padus/padus-4-1/lookup/State_Name.parquet') st
        ON p.State_Nm = st.Code
    WHERE p.GAP_Sts = '1'
    LIMIT 10
""").df()
```

## File Details

| Table | Rows | Size | Columns |
|-------|------|------|---------|
| Public_Access | 4 | 384 B | Code, Dom |
| Category | 7 | 575 B | Code, Dom |
| Designation_Type | 63 | 1,230 B | Code, Dom |
| GAP_Status | 4 | 704 B | Code, Dom |
| IUCN_Category | 10 | 722 B | CODE, DOM |
| Agency_Name | 44 | 1,330 B | Code, Dom, Old_Code |
| Agency_Type | 11 | 564 B | Code, Dom |
| State_Name | 61 | 1,203 B | Code, Dom, St_FIPS |

**Total:** 204 rows across 8 tables

## Citation

U.S. Geological Survey (USGS) Gap Analysis Project (GAP). 2024. Protected Areas Database of the United States (PAD-US) 4.1: U.S. Geological Survey data release, https://doi.org/10.5066/P96WBCHS.
