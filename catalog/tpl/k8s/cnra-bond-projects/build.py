"""CNRA bond accountability (#866): ABCRS map features joined to the per-proposition project lists.

Join path. The map service keys features by ProjectNo_FK (an internal project id); the Prop 1/1E/68/84
spreadsheets key projects by 'Project Ref Num' and do not carry ProjectNo_FK. The project detail page
/Project/Details/{ProjectNo_FK} shows the ref num, so the crawl (crawl_details.py) is the crosswalk.
Prop 4's CSV carries ProjectNo_FK directly (ProjectID).

Output grain: one row per (map feature x funding record). A project with several map features, or
several funding rows (Prop x program), appears on several rows; funding records with no map feature
are kept with a null geometry; map features with no published project page are kept with null
attributes. Prop 1E's Details workbook is empty upstream, so its attributes come from the detail page.
"""
import csv, datetime, glob, json, re, sys
import duckdb, openpyxl
R, OUT, OUT_METRICS = "/tmp/raw/", sys.argv[1], sys.argv[2]
def snake(s): return re.sub(r"_+", "_", re.sub(r"[^0-9a-z]+", "_", str(s).strip().lower())).strip("_")
def clean(v):
    if isinstance(v, str):
        v = v.replace("\t", "").strip()
        return v or None
    return v
def num(v):
    v = clean(v)
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    v = v.replace("$", "").replace(",", "")
    try: return float(v)
    except ValueError: return None
def day(v):
    v = clean(v)
    if v is None: return None
    if isinstance(v, datetime.datetime): return v.date()
    if isinstance(v, datetime.date): return v
    for fmt in ("%d %b %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(v, fmt).date()
        except ValueError: pass
    return None
def sheet(path):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True); hdr = [str(h).strip() for h in next(rows)]
    return [dict(zip(hdr, r)) for r in rows if any(x is not None for x in r)]

# ---- funding records ------------------------------------------------------------------------
DET = {"Title": "title", "Description": "description", "Implemented By": "implemented_by", "Objective": "objective",
       "Project Types": "project_types", "Project Status": "project_status", "On Time": "on_time",
       "Within Scope": "within_scope", "Within Budget": "within_budget", "Associated Counties": "associated_counties",
       "Chapter": "chapter", "Bond Program Code Section": "bond_program_code_section", "Program": "program"}
DET_NUM = {"Total Cost": "total_cost", "Federal Contribution": "federal_contribution", "Local Contribution": "local_contribution",
           "Private Contribution": "private_contribution", "Other State Contribution": "other_state_contribution", "Prop Funds": "prop_funds"}
DET_DATE = {"Est/Act Comp": "est_act_completion", "Final Payment": "final_payment"}
DAC = {"Project Benefits a Disadvantaged Community (or SDAC)": "benefits_dac_or_sdac",
       "Located In Severely Disadvantaged Community": "located_in_sdac", "Located in Disadvantaged Community": "located_in_dac"}
recs = []  # funding records
for p in ("1", "68", "84"):
    rows = sheet(f"{R}Prop_{p}_Details.xlsx")
    for i, r in enumerate(rows, start=2):  # spreadsheet row number
        d = {"prop": p, "project_ref_num": clean(str(r["Project Ref Num"])), "attribute_source": f"Prop_{p}_Details.xlsx",
             "funding_record_id": f"P{p}-row{i}"}
        d.update({v: clean(r.get(k)) for k, v in DET.items()})
        d.update({v: num(r.get(k)) for k, v in DET_NUM.items()})
        d.update({v: day(r.get(k)) for k, v in DET_DATE.items()})
        d.update({v: clean(r.get(k)) for k, v in DAC.items() if k in r})
        recs.append(d)
    print(f"Prop {p} details rows: {len(rows)}")
assert len(sheet(f"{R}Prop_1E_Details.xlsx")) <= 2, "Prop 1E details now populated upstream: add it to the loop above"
P4 = list(csv.DictReader(open(f"{R}prop_4_project_list.csv", encoding="utf-8-sig", newline="")))
print("Prop 4 rows:", len(P4))
for i, r in enumerate(P4, start=2):
    d = {"prop": "4", "funding_record_id": f"P4-row{i}", "project_ref_num": clean(r["ProjectRefNumber"]), "project_no": int(r["ProjectID"]),
         "attribute_source": "prop_4_project_list.csv",
         "title": clean(r["ProjectTitle"]), "description": clean(r["ProjectDescription"]), "objective": clean(r["ProjectObjective"]),
         "project_status": clean(r["ProjectStatus"]), "associated_counties": clean(r["Counties"]), "program": clean(r["FundingProgram"]),
         "total_cost": num(r["TotalProjectAmount"]), "prop_funds": num(r["ProgramAmountAwarded"]),
         "federal_contribution": num(r["FederalContribution"]), "local_contribution": num(r["LocalContribution"]),
         "private_contribution": num(r["PrivateContribution"]), "other_state_contribution": num(r["OtherStateContribution"]),
         "est_act_completion": day(r["EstimatedCompletion"]),
         "agency_org": clean(r["AgencyOrg"]), "applicant_org": clean(r["ApplicantOrg"]), "recipient_org": clean(r["RecipientOrg"]),
         "program_contribution_date": day(r["ProgramContributionDate"]), "federal_contribution_date": day(r["FederalContributionDate"]),
         "local_contribution_date": day(r["LocalContributionDate"]), "private_contribution_date": day(r["PrivateContributionDate"]),
         "other_state_contribution_date": day(r["OtherStateContributionDate"]),
         "disadvantaged_comm": clean(r["DisadvantagedComm"]), "severely_disadvantaged_comm": clean(r["SeverelyDisadvantagedComm"]),
         "vulnerable_population": clean(r["VulnerablePopulation"]), "point_collection": clean(r["PointCollection"]),
         "funding_id": clean(r["FundingID"]), "program_allocation_pl2id": clean(r["ProgramAllocation_PL2ID"])}
    recs.append(d)

# ---- crosswalk + detail-page attributes -----------------------------------------------------
pages = {}
for f in glob.glob(f"{R}detail-pages/part-*.jsonl"):
    for line in open(f):
        j = json.loads(line); pages[j["ProjectNo_FK"]] = j
ok = {k: v for k, v in pages.items() if v["status"] == 200}
print(f"detail pages: {len(pages)} ids, {len(ok)} with a page, {len(pages) - len(ok)} not found (404)")
ref2fk = {}
for fk, j in ok.items(): ref2fk.setdefault(clean(j["Reference Number"]), set()).add(fk)
assert all(len(v) == 1 for v in ref2fk.values()), "ref num maps to several ProjectNo_FK"
ref2fk = {k: next(iter(v)) for k, v in ref2fk.items()}
for d in recs:
    if d.get("project_no") is None: d["project_no"] = ref2fk.get(d["project_ref_num"])
# Prop 1E (empty Details upstream): prop from Prop_1E_Spatial/Metrics, attributes from the detail page
refs1e = {clean(str(r["Project Ref Num"])) for f in ("Spatial", "Metrics") for r in sheet(f"{R}Prop_1E_{f}.xlsx")}
PG = {"title": "title", "Description": "description", "Implemented By": "implemented_by", "Objective": "objective",
      "Project Types": "project_types", "Project Status": "project_status", "On Time?": "on_time", "Within Scope?": "within_scope",
      "Within Budget?": "within_budget", "Associated Counties": "associated_counties"}
def from_page(fk, prop):
    j = ok[fk]
    d = {"prop": prop, "project_ref_num": clean(j["Reference Number"]), "project_no": fk, "attribute_source": "project detail page",
         "funding_record_id": f"page-{fk}"}
    d.update({v: clean(j.get(k)) for k, v in PG.items()})
    d["total_cost"] = num(j.get("Total Cost"))
    d["est_act_completion"] = day(j.get("Estimated/Actual Project Work Completion"))
    d["final_payment"] = day(j.get("Final Payment (GO Bond only)"))
    if j.get("Located In Severely Disadvantaged Community") is not None: d["located_in_sdac"] = clean(j["Located In Severely Disadvantaged Community"])
    return d
n1e = 0
for ref in sorted(refs1e):
    if ref in ref2fk: recs.append(from_page(ref2fk[ref], "1E")); n1e += 1
    else: recs.append({"prop": "1E", "project_ref_num": ref, "attribute_source": "Prop_1E_Spatial.xlsx", "funding_record_id": f"P1E-{ref}"})
print("Prop 1E projects:", len(refs1e), "with a detail page:", n1e)
covered = {d["project_no"] for d in recs if d.get("project_no") is not None}
extra = 0
for fk in sorted(set(ok) - covered):  # has a page, but its ref num is in no download
    recs.append(from_page(fk, None)); extra += 1
print("projects with a detail page but in no download file (prop unknown):", extra)

# ---- administering agency and recipient --------------------------------------------------
# The first four digits of a Project Ref Num are the state organization code of the department
# holding the bond appropriation. CNRA's own Prop 4 list gives AgencyOrg beside the ref num, which
# fixes the code -> agency mapping for 19 codes; the remaining four never occur in Prop 4 and are
# named from their program titles (e.g. 3480 '... Planning Grants - DOC').
ORG = {"0540": "CNRA", "0650": "LCI", "3125": "CTC", "3340": "CCC", "3360": "CEC", "3540": "CAL FIRE", "3600": "CDFW",
       "3640": "WCB", "3760": "SCC", "3790": "Parks", "3825": "RMC", "3835": "BHUWC", "3845": "SDRC", "3850": "CVMC",
       "3855": "SNC", "3860": "DWR", "3861": "DWR", "3940": "SWRCB", "8570": "CDFA",
       "3480": "DOC", "3810": "SMMC", "3875": "SSJDC", "4265": "CDPH"}
FROM_P4 = {k for k in ORG if k not in ("3480", "3810", "3875", "4265")}
p4map = {}
for d in recs:
    if d["prop"] == "4" and d.get("project_ref_num") and d.get("agency_org"):
        p4map.setdefault(d["project_ref_num"][:4], set()).add(d["agency_org"])
for k, v in p4map.items():
    assert v == {ORG[k]}, f"org code {k}: Prop 4 says {v}, table says {ORG.get(k)}"
assert FROM_P4 <= set(p4map), f"codes no longer in Prop 4: {FROM_P4 - set(p4map)}"
unk = set()
for d in recs:
    ref = d.get("project_ref_num") or ""
    code = ref[:4]
    if d["prop"] == "4" and d.get("agency_org"):
        d["administering_agency"], d["administering_agency_basis"] = d["agency_org"], "Prop 4 AgencyOrg"
    elif code in ORG:
        d["administering_agency"] = ORG[code]
        d["administering_agency_basis"] = ("org code " + code + (" (named by Prop 4 AgencyOrg)" if code in FROM_P4 else " (named from program titles)"))
    elif ref: unk.add(code)
    d["recipient"] = d.get("recipient_org") or d.get("implemented_by")
print("ref-num prefixes with no agency:", sorted(unk))

# ---- map features ---------------------------------------------------------------------------
feats = []
for lyr, name in [("point", "abcrs-points"), ("line", "abcrs-lines"), ("polygon", "abcrs-polygons")]:
    for f in json.load(open(f"{R}{name}.geojson"))["features"]:
        a = f["properties"]
        ts = lambda v: None if v is None else datetime.datetime.fromtimestamp(v / 1000, datetime.timezone.utc).replace(tzinfo=None)
        feats.append({"project_no": a["ProjectNo_FK"], "map_layer": lyr, "map_objectid": a["OBJECTID"],
                      "map_label": clean(a.get("MapLabel")), "map_description": clean(a.get("Description")),
                      "map_online_url": clean(a.get("OnlineURL")), "map_mapping_method_id": a.get("MappingMethodID"),
                      "map_x": a.get("XCoord", a.get("CentroidX")), "map_y": a.get("YCoord", a.get("CentroidY")),
                      "map_created": ts(a.get("CreateDateTime")), "map_updated": ts(a.get("UpdateDateTime")),
                      "map_created_by": clean(a.get("CreateUserName")), "map_updated_by": clean(a.get("UpdateUserName")),
                      "geojson": json.dumps(f["geometry"])})
print("map features:", len(feats))
by_fk = {}
for d in recs:
    if d.get("project_no") is not None: by_fk.setdefault(d["project_no"], []).append(d)
nfeat = {}
for f in feats: nfeat[f["project_no"]] = nfeat.get(f["project_no"], 0) + 1
out = []
for f in feats:
    for d in by_fk.get(f["project_no"], [None]):
        out.append({**(d or {"project_no": f["project_no"], "attribute_source": None}), **f, "map_feature_count": nfeat[f["project_no"]]})
mapped = {f["project_no"] for f in feats}
for d in recs:
    if d.get("project_no") not in mapped: out.append({**d, "geojson": None, "map_feature_count": 0})
cols = ["funding_record_id", "prop", "project_ref_num", "project_no", "map_feature_count", "title", "description", "objective", "implemented_by", "agency_org",
        "applicant_org", "recipient_org", "recipient", "administering_agency", "administering_agency_basis", "program", "chapter", "bond_program_code_section", "project_types", "project_status",
        "prop_funds", "total_cost", "federal_contribution", "local_contribution", "private_contribution", "other_state_contribution",
        "program_contribution_date", "federal_contribution_date", "local_contribution_date", "private_contribution_date",
        "other_state_contribution_date", "est_act_completion", "final_payment", "on_time", "within_scope", "within_budget",
        "associated_counties", "benefits_dac_or_sdac", "located_in_sdac", "located_in_dac", "disadvantaged_comm",
        "severely_disadvantaged_comm", "vulnerable_population", "funding_id", "program_allocation_pl2id", "point_collection",
        "attribute_source", "map_layer", "map_objectid", "map_label", "map_description", "map_online_url", "map_mapping_method_id",
        "map_x", "map_y", "map_created", "map_updated", "map_created_by", "map_updated_by"]
TY = {c: "DOUBLE" for c in DET_NUM.values()} | {c: "DATE" for c in ["program_contribution_date", "federal_contribution_date",
      "local_contribution_date", "private_contribution_date", "other_state_contribution_date", "est_act_completion", "final_payment"]} \
     | {"project_no": "BIGINT", "map_objectid": "BIGINT", "map_mapping_method_id": "BIGINT", "map_x": "DOUBLE", "map_feature_count": "BIGINT", "map_y": "DOUBLE",
        "map_created": "TIMESTAMP", "map_updated": "TIMESTAMP"}
con = duckdb.connect(); con.execute("INSTALL spatial; LOAD spatial;")
con.execute("CREATE TABLE t (" + ", ".join(f"{c} {TY.get(c, 'VARCHAR')}" for c in cols) + ", geojson VARCHAR)")
con.executemany(f"INSERT INTO t VALUES ({','.join(['?'] * (len(cols) + 1))})",
                [[(str(r.get(c)) if TY.get(c, "VARCHAR") == "VARCHAR" and r.get(c) is not None else r.get(c)) for c in cols] + [r.get("geojson")] for r in out])
con.execute(f"COPY (SELECT * EXCLUDE geojson, ST_GeomFromGeoJSON(geojson) AS geom FROM t ORDER BY prop, project_ref_num, map_layer, map_objectid) "
            f"TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 2000)")
q = lambda s: print(con.sql(s.replace("OUT", f"'{OUT}'")))
q("SELECT count(*) nrows, count(geom) with_geom, count(DISTINCT project_no) projects, count(DISTINCT map_objectid || map_layer) features FROM OUT")
q("SELECT prop, count(*) nrows, count(geom) with_geom, count(DISTINCT project_ref_num) refs, count(DISTINCT CASE WHEN geom IS NOT NULL THEN project_ref_num END) refs_mapped FROM OUT GROUP BY 1 ORDER BY 1")
q("SELECT map_layer, count(*) nrows, count(DISTINCT map_layer||map_objectid) feats, count(*) FILTER (WHERE attribute_source IS NULL) no_attrs FROM OUT GROUP BY 1 ORDER BY 1")
q("SELECT prop, count(DISTINCT funding_record_id) recs, round(sum(prop_funds)/1e6,1) prop_funds_m FROM (SELECT DISTINCT funding_record_id, prop, prop_funds FROM OUT) GROUP BY 1 ORDER BY 1")
q("SELECT round(sum(prop_funds / greatest(map_feature_count,1))/1e6,1) split_sum_m, round((SELECT sum(prop_funds) FROM (SELECT DISTINCT funding_record_id, prop_funds FROM OUT))/1e6,1) dedup_sum_m FROM OUT")
q("SELECT administering_agency, count(DISTINCT funding_record_id) recs, round(sum(prop_funds)/1e6,1) m FROM (SELECT DISTINCT funding_record_id, administering_agency, prop_funds FROM OUT) GROUP BY 1 ORDER BY 3 DESC NULLS LAST")
q("SELECT count(*) FILTER (WHERE funding_record_id IS NULL AND attribute_source IS NOT NULL) missing_ids FROM OUT")
q("SELECT ST_GeometryType(geom) gt, count(*) n, count(*) FILTER (WHERE NOT ST_IsValid(geom)) invalid FROM OUT GROUP BY 1")
q("SELECT min(ST_XMin(geom)), max(ST_XMax(geom)), min(ST_YMin(geom)), max(ST_YMax(geom)) FROM OUT")
# ---- companion metrics table ---------------------------------------------------------------
m = []
for p in ("1", "1E", "68", "84"):
    for r in sheet(f"{R}Prop_{p}_Metrics.xlsx"):
        ref = clean(str(r["Project Ref Num"]))
        m.append((p, ref, ref2fk.get(ref), clean(r["Title"]), clean(r["Metric"]), clean(r["Topic"]), num(r["Quantity"]), clean(r["Unit"])))
con.execute("CREATE TABLE m (prop VARCHAR, project_ref_num VARCHAR, project_no BIGINT, title VARCHAR, metric VARCHAR, topic VARCHAR, quantity DOUBLE, unit VARCHAR)")
con.executemany("INSERT INTO m VALUES (?,?,?,?,?,?,?,?)", m)
con.execute(f"COPY (SELECT * FROM m ORDER BY prop, project_ref_num) TO '{OUT_METRICS}' (FORMAT PARQUET, COMPRESSION ZSTD)")
print(con.sql("SELECT prop, count(*) n, count(project_no) keyed FROM m GROUP BY 1 ORDER BY 1"))
