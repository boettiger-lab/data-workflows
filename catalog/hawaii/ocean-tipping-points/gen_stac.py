#!/usr/bin/env python3
"""Write the STAC collections for the Ocean Tipping Points layers in public-hawaii (#851).

Usage: gen_stac.py <otp-meta.json> <stage-json-dir> <stats.json> <out_dir>

otp-meta.json   per layer: PacIOOS metadata title, abstract and Use Limitation text
stage-json-dir  the <layer>.tif.json sidecars the stage job wrote (URL, access time, sha256, grid, stats)
stats.json      per short name, measured from the published objects: hex rows, hex created,
                cog created
Writes <out_dir>/stac-collection.json (the ocean-tipping-points collection) and
<out_dir>/<short>/stac-collection.json for each layer.
"""
import json
import os
import sys

B = "public-hawaii"
S3 = f"https://s3-west.nrp-nautilus.io/{B}"
P = "ocean-tipping-points"
ROOT = "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json"
META = "https://www.pacioos.hawaii.edu/metadata"
OTP = "https://www.pacioos.hawaii.edu/projects/oceantippingpoints/"
DOI = "10.1371/journal.pone.0189792"
CITE = ("Wedding LM, Lecky J, Gove JM, Walecka HR, Donovan MK, Williams GJ, Jouffray J-B, Crowder LB, "
        "Erickson A, Falinski K, Friedlander AM, Kappel CV, Kittinger JN, McCoy K, Norström A, Nyström M, "
        "Oleson KLL, Stamoulis KA, White C, Selkoe KA (2018) Advancing the integration of spatial data to map "
        "human and natural drivers on coral reefs. PLOS ONE 13(3): e0189792.")

FRAC = ("fraction of a year", "1")
CHL = ("milligrams per cubic metre", "mg m-3")
PAR = ("moles of photons per square metre per day", "mol m-2 day-1")
DEGC = ("degrees Celsius", "degC")
KW = ("kilowatts per metre of wave crest", "kW m-1")
KGHA = ("kilograms of reef fish per hectare per year", "kg ha-1 yr-1")
PRES = ("1 for presence and 0 for no recorded presence", "1")

# short -> (title, years, units, kind); kind is stat, presence or index
L = {
    "chlor_anom_freq": ("Chlorophyll-a anomaly frequency in the Main Hawaiian Islands", "2002-2013", FRAC, "stat"),
    "chlor_anom_max": ("Chlorophyll-a maximum anomaly in the Main Hawaiian Islands", "2002-2013", CHL, "stat"),
    "chlor_avg": ("Long-term mean chlorophyll-a in the Main Hawaiian Islands", "2002-2013", CHL, "stat"),
    "chlor_clim_max": ("Chlorophyll-a maximum monthly climatology in the Main Hawaiian Islands", "2002-2013", CHL, "stat"),
    "chlor_std": ("Chlorophyll-a variability in the Main Hawaiian Islands", "2002-2013", CHL, "stat"),
    "coastal_mod": ("Coastal habitat modification in the Main Hawaiian Islands", None, PRES, "presence"),
    "fishing": ("Total reef fish catch in the Main Hawaiian Islands", "2003-2013", KGHA, "stat"),
    "fishing_com": ("Commercial reef fish catch in the Main Hawaiian Islands", "2003-2013", KGHA, "stat"),
    "fishing_com_line": ("Commercial line fishing catch in the Main Hawaiian Islands", "2003-2013", KGHA, "stat"),
    "fishing_com_net": ("Commercial net fishing catch in the Main Hawaiian Islands", "2003-2013", KGHA, "stat"),
    "fishing_com_spear": ("Commercial spear fishing catch in the Main Hawaiian Islands", "2003-2013", KGHA, "stat"),
    "fishing_rec": ("Non-commercial reef fish catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_boat": ("Non-commercial boat-based fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_boat_line": ("Non-commercial boat-based line fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_boat_net": ("Non-commercial boat-based net fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_boat_spear": ("Non-commercial boat-based spear fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_shore": ("Non-commercial shore-based fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_shore_line": ("Non-commercial shore-based line fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_shore_net": ("Non-commercial shore-based net fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "fishing_rec_shore_spear": ("Non-commercial shore-based spear fishing catch in the Main Hawaiian Islands", "2004-2013", KGHA, "stat"),
    "invasive_algae": ("Observed invasive algae in the Main Hawaiian Islands", "2000-2013", PRES, "presence"),
    "invasive_fish": ("Observed invasive reef fish in the Main Hawaiian Islands", "2000-2013", PRES, "presence"),
    "nearshore_dev": ("Nearshore new development impact in the Main Hawaiian Islands", "2005-2011",
                      ("a unitless index from 0 to 1", "1"), "index"),
    "nearshore_sediment": ("Sediment export to nearshore waters of the Main Hawaiian Islands", None,
                           ("tons of sediment per hectare per year", "t ha-1 yr-1"), "stat"),
    "osds_effluent": ("Cesspool and septic effluent in the Main Hawaiian Islands", None,
                      ("gallons per day per square kilometre", "gal day-1 km-2"), "stat"),
    "osds_nitrogen": ("Cesspool and septic nitrogen flux in the Main Hawaiian Islands", None,
                      ("grams of nitrogen per day per square kilometre", "g day-1 km-2"), "stat"),
    "osds_phosphorus": ("Cesspool and septic phosphorus flux in the Main Hawaiian Islands", None,
                        ("grams of phosphorus per day per square kilometre", "g day-1 km-2"), "stat"),
    "par_anom_freq": ("Light anomaly frequency in the Main Hawaiian Islands", "2002-2013", FRAC, "stat"),
    "par_anom_max": ("Light maximum anomaly in the Main Hawaiian Islands", "2002-2013", PAR, "stat"),
    "par_avg": ("Long-term mean light in the Main Hawaiian Islands", "2002-2013", PAR, "stat"),
    "par_clim_max": ("Light maximum monthly climatology in the Main Hawaiian Islands", "2002-2013", PAR, "stat"),
    "par_std": ("Light variability in the Main Hawaiian Islands", "2002-2013", PAR, "stat"),
    "sst_anom_freq": ("Sea surface temperature anomaly frequency in the Main Hawaiian Islands", "2000-2013", FRAC, "stat"),
    "sst_anom_max": ("Sea surface temperature maximum anomaly in the Main Hawaiian Islands", "2000-2013", DEGC, "stat"),
    "sst_avg": ("Long-term mean sea surface temperature in the Main Hawaiian Islands", "2000-2013", DEGC, "stat"),
    "sst_clim_max": ("Sea surface temperature maximum monthly climatology in the Main Hawaiian Islands", "1985-2013", DEGC, "stat"),
    "sst_dhw_max": ("Maximum degree heating weeks in the Main Hawaiian Islands", "2000-2013",
                    ("degree Celsius weeks", "degC week"), "stat"),
    "sst_std": ("Sea surface temperature variability in the Main Hawaiian Islands", "2000-2013", DEGC, "stat"),
    "wave_anom_freq": ("Wave power anomaly frequency in the Main Hawaiian Islands", "2000-2013", FRAC, "stat"),
    "wave_anom_max": ("Wave power maximum anomaly in the Main Hawaiian Islands", "2000-2013", KW, "stat"),
    "wave_avg": ("Long-term mean wave power in the Main Hawaiian Islands", "2000-2013", KW, "stat"),
    "wave_clim_max": ("Wave power maximum monthly climatology in the Main Hawaiian Islands", "1979-2013", KW, "stat"),
    "wave_std": ("Wave power variability in the Main Hawaiian Islands", "2000-2013", KW, "stat"),
}

TERMS = (
    "PacIOOS distributes the Ocean Tipping Points layers under these terms: the data may be used and "
    "redistributed for free but are not intended for legal use, since they may contain inaccuracies. Credit the "
    "Ocean Tipping Points project as a source, and cite Wedding et al. (2018), PLOS ONE 13(3): e0189792. The "
    "project also asks users to contact it before applying the data to project work, so that the principal "
    "investigator, Carrie Kappel at NCEAS (kappel@nceas.ucsb.edu), can track uses and avoid duplicated efforts."
)


def link(rel, href, title=None, typ="application/json"):
    d = {"rel": rel, "href": href, "type": typ}
    if title:
        d["title"] = title
    return d


def leaf(short, meta, stage, st):
    title, years, (units, sym), kind = L[short]
    layer = f"hi_otp_all_{short}"
    native = 10 if stage["geotransform"][1] < 0.002 else 9
    px = "100 m" if native == 10 else "500 m"
    area = "about 0.015 square kilometres" if native == 10 else "about 0.1 square kilometres"
    x0, dx, _, y1, _, dy = stage["geotransform"]
    bbox = [x0, y1 + stage["height"] * dy, x0 + stage["width"] * dx, y1]
    nd = stage["nodata"]
    nd = int(nd) if nd == int(nd) else nd
    if years:
        a, b = years.split("-")
        interval = [f"{a}-01-01T00:00:00Z", f"{b}-12-31T00:00:00Z"]
        when = f"The layer summarises {a} to {b}."
    else:
        interval = [None, None]
        when = "PacIOOS gives no time period for this layer."
    hcol = f"h{native}"

    if kind == "presence":
        col = (f"Recorded presence in the cell: 1 where present and 0 where not recorded, as the mean of the "
               f"{px} source pixels the cell overlaps. A cell that straddles a presence boundary holds a value "
               "between 0 and 1, the share of the cell in presence pixels.")
        how = "These are presence-only data: 0 means no presence was recorded, not that absence was confirmed."
    elif kind == "index":
        col = (f"Index from 0 to 1, as the mean of the {px} source pixels the cell overlaps. Higher values mean "
               "more new development nearby.")
        how = "The index is relative, so compare values within this layer rather than reading them as amounts."
    else:
        col = f"Value in {units}, as the mean of the {px} source pixels the cell overlaps."
        how = ("Values are rates per area or long-term statistics, so do not sum them across cells. To summarise "
               "a region, take an area-weighted mean, because H3 cells are not equal-area.")

    desc = (
        f"{meta['abstract']}\n\n"
        f"This is one of the 43 Ocean Tipping Points layers for the Main Hawaiian Islands (Wedding et al. 2018). "
        f"{when} Values are in {units}. The layer covers coastal waters around the Main Hawaiian Islands on a "
        f"{px} grid; cells outside the project's area of interest are empty.\n\n"
        f"The H3 hexagon table is the layer for queries and joins, at resolution {native} with h8 and h0 parents. "
        f"A Cloud-Optimized GeoTIFF of the source grid is published for map display and pixel-level work.\n\n"
        f"Source: PacIOOS GeoServer coverage {layer}, metadata at {META}/{layer}.html. The full grid was requested "
        f"through WCS at its native pixel size on {stage['accessed'][:10]}. The GeoTIFF as delivered is staged at "
        f"s3://{B}/raw/{P}/{layer}.tif ({stage['bytes']} bytes, SHA-256 {stage['sha256']}), next to a .json file "
        "recording the request URL and access time. PacIOOS does not publish an edition label for these layers.\n\n"
        f"{TERMS}"
    )
    hex_desc = (
        f"H3 hexagon table of {title[0].lower() + title[1:]} at resolution {native} ({area} per cell), one row per "
        f"cell, partitioned by h0. Each cell holds the mean of the {px} source pixels it overlaps. Cells with no "
        f"source data are absent. {how}\n\n"
        "```sql\n"
        f"-- the cells around Kāneʻohe Bay, Oʻahu\n"
        f"SELECT {hcol}, h8, {short}\n"
        f"FROM read_parquet('s3://{B}/{P}/{short}/hex/h0=*/data_0.parquet')\n"
        f"WHERE h3_cell_to_lat({hcol}) BETWEEN 21.24 AND 21.73\n"
        f"  AND h3_cell_to_lng({hcol}) BETWEEN -158.30 AND -157.63;\n"
        "```"
    )
    cols = [
        {"name": short, "type": "double", "description": col},
        {"name": hcol, "type": "uint64",
         "description": f"H3 cell index at resolution {native}, the native resolution of this table; one row per cell."},
        {"name": "h8", "type": "uint64",
         "description": "H3 cell index at resolution 8, the catalog's common join key."},
        {"name": "h0", "type": "uint64",
         "description": "H3 cell index at resolution 0, used as the partition key for hive-partitioned reads."},
    ]
    if native == 9:
        cols[2]["description"] = "H3 cell index at resolution 8, parent of h9; the catalog's common join key."
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/raster/v1.1.0/schema.json",
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "id": f"{P}-{short}",
        "title": title,
        "description": desc,
        "license": "other",
        "keywords": ["Ocean Tipping Points", "Hawaii", "Main Hawaiian Islands", "coral reefs", "PacIOOS", "H3"],
        "providers": [
            {"name": "Ocean Tipping Points project", "roles": ["producer"], "url": OTP},
            {"name": "Pacific Islands Ocean Observing System (PacIOOS)", "roles": ["host", "licensor"],
             "url": "https://www.pacioos.hawaii.edu/"},
            {"name": "Boettiger Lab, UC Berkeley", "roles": ["processor", "host"],
             "url": "https://boettiger-lab.github.io"},
        ],
        "sci:doi": DOI,
        "sci:citation": (f"{CITE} Layer {layer}, distributed by PacIOOS; accessed through its GeoServer WCS on "
                         f"{stage['accessed'][:10]}."),
        "created": st["cog_created"],
        "updated": st["hex_created"],
        "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [interval]}},
        "links": [
            link("self", f"{S3}/{P}/{short}/stac-collection.json"),
            link("root", ROOT),
            link("parent", f"{S3}/{P}/stac-collection.json"),
            link("license", f"{META}/{layer}.html", "PacIOOS metadata record with the Use Limitation terms",
                 "text/html"),
            link("about", f"{META}/{layer}.html", "PacIOOS metadata record", "text/html"),
            link("cite-as", f"https://doi.org/{DOI}", "Wedding et al. 2018", "text/html"),
            link("describedby", f"{S3}/{P}/README.md", None, "text/markdown"),
        ],
        "assets": {
            f"{short}-hex": {
                "href": f"{S3}/{P}/{short}/hex/h0=*/data_0.parquet",
                "type": "application/x-parquet",
                "roles": ["data"],
                "title": f"{title} in H3 hexagons at resolution {native}",
                "description": hex_desc,
                "created": st["hex_created"],
                "h3:native_resolution": native,
                "h3:parent_resolutions": [8, 0],
                "table:columns": cols,
            },
            f"{short}-cog": {
                "href": f"{S3}/{P}/{short}-cog.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "roles": ["data", "visual"],
                "title": f"{title} on the {px} source grid",
                "description": (f"Cloud-Optimized GeoTIFF of the source grid in WGS84, with the pixel values PacIOOS "
                                f"serves. Units are {units}. Pixels with value {nd} are empty."),
                "created": st["cog_created"],
                "raster:bands": [{
                    "name": short, "data_type": stage["dtype"].lower(), "nodata": nd, "unit": sym,
                    "statistics": {"minimum": stage["min"], "maximum": stage["max"], "mean": stage["mean"],
                                   "valid_percent": round(stage["valid_percent"], 2)},
                }],
            },
        },
    }


def parent(kids):
    starts = [k["extent"]["temporal"]["interval"][0][0] for k in kids if k["extent"]["temporal"]["interval"][0][0]]
    ends = [k["extent"]["temporal"]["interval"][0][1] for k in kids if k["extent"]["temporal"]["interval"][0][1]]
    bb = [k["extent"]["spatial"]["bbox"][0] for k in kids]
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "stac_extensions": ["https://stac-extensions.github.io/scientific/v1.0.0/schema.json"],
        "id": P,
        "title": "Ocean Tipping Points stressor layers for the Main Hawaiian Islands",
        "description": (
            "The 43 gridded layers of human and natural drivers on Hawaiian coral reefs that the Ocean Tipping "
            "Points project mapped for the coastal waters of the Main Hawaiian Islands (Wedding et al. 2018). They "
            "cover reef fish catch by sector and gear, sediment export, nearshore development, coastal habitat "
            "modification, cesspool and septic effluent and nutrient flux, invasive algae and fish, and long-term "
            "statistics of chlorophyll-a, light, sea surface temperature and wave power. Fishing, sediment and "
            "development layers are on a 100 m grid and hexed at H3 resolution 10; the rest are on a 500 m grid and "
            "hexed at resolution 9. Every layer carries h8 and h0, so layers can be joined to each other and to the "
            "rest of the catalog at resolution 8.\n\n"
            "Each child collection has an H3 hexagon table and a Cloud-Optimized GeoTIFF of the source grid. "
            "PacIOOS hosts the layers; they were requested through its GeoServer WCS at their native pixel size.\n\n"
            f"{TERMS}"
        ),
        "license": "other",
        "sci:doi": DOI,
        "sci:citation": CITE,
        "extent": {
            "spatial": {"bbox": [[min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb),
                                  max(b[3] for b in bb)]]},
            "temporal": {"interval": [[min(starts), max(ends)]]},
        },
        "links": [
            link("self", f"{S3}/{P}/stac-collection.json"),
            link("root", ROOT),
            link("parent", f"{S3}/stac-collection.json"),
            link("license", f"{META}/hi_otp_all_sst_avg.html",
                 "PacIOOS metadata record with the Use Limitation terms shared by every layer", "text/html"),
            link("about", OTP, "Ocean Tipping Points at PacIOOS", "text/html"),
            link("cite-as", f"https://doi.org/{DOI}", "Wedding et al. 2018", "text/html"),
            link("describedby", f"{S3}/{P}/README.md", None, "text/markdown"),
        ] + [link("child", f"{S3}/{P}/{k['id'][len(P) + 1:]}/stac-collection.json", k["title"]) for k in kids],
    }


def main():
    meta = json.load(open(sys.argv[1]))
    sdir, stats, out = sys.argv[2], json.load(open(sys.argv[3])), sys.argv[4]
    kids = []
    for short in L:
        layer = f"hi_otp_all_{short}"
        c = leaf(short, meta[layer], json.load(open(f"{sdir}/{layer}.tif.json")), stats[short])
        kids.append(c)
        os.makedirs(f"{out}/{short}", exist_ok=True)
        json.dump(c, open(f"{out}/{short}/stac-collection.json", "w"), indent=2, ensure_ascii=False)
    json.dump(parent(kids), open(f"{out}/stac-collection.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
