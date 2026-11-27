"""Column-description fixes for #1070, applied to a LIVE collection.

  set_columns.py <collection.json> <collection-id>

Rewrites the named columns wherever they are described: the collection's `table:columns`
dictionary, and any asset list that still carries its own description for the column, so the
text stays identical across assets. Everything else on the collection is left as it is.
Idempotent.

Each text below was written against measured values (2026-11-27, duckdb-geo):
- gfw-fishing-effort: 16 distinct `geartype` values; the live text listed 13.
- census-2025-sldu / -sldl: codes are always 3 characters; non-numeric codes by state as listed.
- irrecoverable-carbon: `carbon` is Mg C (tonnes); 1 Pg = 1 Gt = 1e9 t.
"""
import json
import sys

GEAR = {
    "dredge_fishing": "Dredge fishing vessels",
    "drifting_longlines": "Drifting longlines",
    "fishing": "Unclassified fishing (gear type uncertain)",
    "fixed_gear": "Fixed gear (subtype uncertain)",
    "other_purse_seines": "Other purse seiners",
    "other_seines": "Other seiners",
    "pole_and_line": "Pole and line",
    "pots_and_traps": "Pots and traps",
    "purse_seines": "Purse seiners (unclassified)",
    "seiners": "Seiners (unclassified)",
    "set_gillnets": "Set gillnets",
    "set_longlines": "Set longlines",
    "squid_jigger": "Squid jiggers",
    "trawlers": "Trawlers",
    "trollers": "Trollers",
    "tuna_purse_seines": "Tuna purse seiners",
}

SLD_COMMON = (
    "A three-character text code, unique within a state. Most states number their districts and "
    "zero-pad the number, so district 2 is '002', not '2' or '02'. {letters} 'ZZZ' marks the part "
    "of a state that lies in no district, mostly water. To pick one district, filter on the state "
    "as well, or use GEOID (state FIPS code followed by this code):\n\n"
    "```sql\n-- {example_label}\nWHERE STATEFP = '06' AND {col} = '002'\n```"
)

EDITS = {
    "gfw-fishing-effort": {
        "geartype": {
            "description": (
                "Gear type of the fishing vessel, as classified by Global Fishing Watch from its "
                "movement pattern. Values: "
                + ", ".join(f"{k}={v}" for k, v in GEAR.items())
                + ". By fishing hours, trawlers account for about half of the effort, followed by "
                "unclassified fishing and drifting longlines at about 14% each."
            ),
            "values": list(GEAR),
        },
    },
    "census-2025-sldu": {
        "SLDUST": {
            "description": "State legislative district (upper chamber) code. " + SLD_COMMON.format(
                letters=("A few states use letters instead: Alaska '00A' to '00T', Massachusetts "
                         "'D01' and up, and Vermont abbreviations of county names such as 'ADD' "
                         "and 'BEN'."),
                example_label="California Senate district 2", col="SLDUST"),
        },
    },
    "census-2025-sldl": {
        "SLDLST": {
            "description": "State legislative district (lower chamber) code. " + SLD_COMMON.format(
                letters=("Some states split a district into lettered seats, such as '01A' and "
                         "'01B' in Minnesota and Maryland, and Vermont uses codes such as 'A-1'."),
                example_label="California Assembly district 2", col="SLDLST"),
        },
    },
    "irrecoverable-carbon": {
        "carbon": {
            "append": (" A sum of this column is in tonnes of carbon: divide by 1e6 for megatonnes "
                       "(Mt C) and by 1e9 for gigatonnes (Gt C), which are the same as petagrams "
                       "(Pg C)."),
        },
    },
}

path, cid = sys.argv[1], sys.argv[2]
c = json.load(open(path))
assert c["id"] == cid, f"collection id {c['id']} != {cid}"
edits = EDITS[cid]
touched = 0
dictionary = c.get("table:columns", [])
lists = [dictionary] + [a.get("table:columns", []) for a in c.get("assets", {}).values()]
for cols in lists:
    for col in cols:
        e = edits.get(col["name"])
        if not e:
            continue
        if cols is not dictionary and "description" not in col:
            continue  # an asset list of name + type only inherits the dictionary text
        if "append" in e:
            if e["append"].strip() not in col.get("description", ""):
                col["description"] = col.get("description", "").rstrip() + e["append"]
        else:
            col["description"] = e["description"]
            if "values" in e:
                col["values"] = e["values"]
        touched += 1
missing = [n for n in edits if not any(col["name"] == n for cols in lists for col in cols)]
assert not missing, f"columns not found: {missing}"
json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print(f"{cid}: {touched} column entries set")
