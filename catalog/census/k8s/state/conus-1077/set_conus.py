"""#1077: document the `conus` column on the LIVE census-2024 state collection.

Run after census-2024-state-hex-conus.yaml has flipped the hex. Edits in place and
asserts every passage it touches, so a drifted collection fails instead of half-editing.

    python3 set_conus.py stac-collection.json
"""
import json
import sys

path = sys.argv[1]
c = json.load(open(path))

desc = ("True for the contiguous United States: the 48 states that border one another and "
        "the District of Columbia (49 rows of 56). False for Alaska, Hawaii, Puerto Rico, Guam, "
        "the US Virgin Islands, American Samoa and the Northern Mariana Islands. Filter "
        "`WHERE conus` instead of listing state codes. On the hex asset only.")

top = c["table:columns"]
names = [x["name"] for x in top]
assert "conus" not in names
top.insert(names.index("h8"), {"name": "conus", "type": "boolean", "description": desc})

for col in top:
    if col["name"] == "STUSPS":
        old = ("Contiguous United States (48 states and DC): "
               "`STUSPS NOT IN ('AK','HI','PR','GU','VI','AS','MP','UM')`.")
        assert old in col["description"], col["description"]
        col["description"] = col["description"].replace(
            old, "For the contiguous United States (48 states and DC) use the hex asset's "
                 "`conus` column, or `STUSPS NOT IN ('AK','HI','PR','GU','VI','AS','MP','UM')`.")

hexa = c["assets"]["state-hex"]
hc = [x["name"] for x in hexa["table:columns"]]
assert "conus" not in hc and hc[-1] == "h0"
hexa["table:columns"].insert(len(hc) - 1, {"name": "conus", "type": "boolean"})
hexa["description"] += ("\n\n`conus` marks the contiguous United States (48 states and DC): "
                        "`WHERE conus` selects it.")

json.dump(c, open(path, "w"), indent=2, ensure_ascii=False)
print("ok")
