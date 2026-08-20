# 2001 Roadless Rule Rescission — Provenance Capture (2026)

Reference capture, not a spatial ingest. No H3, no bucket ingest. This directory holds the
agency's own documents and definitions for the 2026 proposal to rescind the 2001 Roadless Area
Conservation Rule, so that the `roadless` dataset set can *reproduce* the agency's numbers rather
than compute differently-defined ones.

Captured 2026-08-20. Closes #589. Unblocks #586, #587, #588.

## The document

**Federal Register `2026-16965` — "Special Areas; Roadless Area Conservation", Proposed Rule,
Forest Service (USDA).**

| Field | Value |
|---|---|
| Citation | **91 FR 53827** (pp. 53827–53832) |
| Publication date | 2026-08-20 (filed 2026-08-19 08:45 ET) |
| RIN | **0596-AD66** |
| Regulations.gov docket | **FS-2025-0001** |
| Regulations.gov document | **FS-2025-0001-223869** |
| Comments close | **2026-09-21** (portal accepts until 2026-09-22 03:59 UTC) |
| Action | Remove and reserve 36 CFR part 294, subpart B |
| Signed | Stephen Alexander Vaden, Deputy Secretary |
| Published URL | <https://www.federalregister.gov/documents/2026/08/20/2026-16965/special-areas-roadless-area-conservation> |

The public-inspection PDF **was captured while still live** (`docs/pi-2026-16965.pdf`,
20 typescript pages) — it rotates out now that the document has published, so the committed copy
is the only one. It agrees with the published version on every quantitative claim (11.3M, 18.2M,
28.3%, 45.5%, 4.8M, 9.8M, 5–10%); only pagination and hyphenation differ. See
[sources.tsv](sources.tsv) for checksums — `fetch-sources.sh` re-fetches and verifies the other 12
documents byte-for-byte.

Notice of intent: 90 FR 42179 (2025-08-29). 220,000+ comment letters on behalf of 625,000+
individuals and organizations were received in the 21-day NOI comment period.

## ⛔ The denominator: ~40.0M acres, not 44.7M and not 58.4M

**This is the single most load-bearing thing in this capture.** The DEIS computes almost every
percentage against the **potentially affected environment**, which is derived as:

| Step | Acres | Source |
|---|---:|---|
| IRAs subject to the 2001 Roadless Rule (excl. ID + CO) | 44,700,000 | DEIS Vol I p. 30 |
| − not on NFS lands (ownership change / vertical-integration slivers) | −400,000 | DEIS Vol I p. 30, fn. 9 |
| = on National Forest System lands | 44,300,000 | |
| − Congressionally designated wilderness | −1,300,000 | DEIS Vol I p. 30, fn. 14 |
| − Congressionally designated wilderness study areas | −2,800,000 | fn. 15 |
| − Wild segments of Wild & Scenic Rivers | −85,000 | fn. 16 |
| **= potentially affected environment** | **40,049,537** | **DEIS Vol I Table 12** |

Statutory designations are excluded because they carry "more restrictive and more permanent
mandates than the 2001 Roadless Rule", so change there is "not reasonably foreseeable."

`40,049,537` is the exact figure from Table 12 (NLCD pixel sum; the DEIS notes it "may differ
slightly" from the vector total). **Every tabulation in #586/#587/#588 must state which base it
uses**, and to reproduce an agency percentage it must use this one — the four-way distinction is
now `58.4M all-IRA` / `44.7M rule-affected` / `44.3M rule-affected on NFS` / `40.0M potentially
affected`. See #594.

Alternative 3 (modified rule) has its own smaller base: the ~40.0M minus 17.9M removed by the
roaded/WUI criteria, leaving ~27.3M under continued prohibition (the DEIS also refers to "13
million acres" remaining under 2001-rule management).

## The three headline claims — agency definitions

All three are **press-release claims attributed to Chief Tom Schultz**, not preamble text. The FR
preamble contains none of them; the DEIS supplies the methods. Verbatim release wording:

> "More than 40% of inventoried roadless areas, primarily in the West, have high or very high
> wildfire hazard potential. And only 5% of those areas have received hazardous fuels reduction
> treatments since 2014. At the same time, more than a quarter of these lands—11.3 million
> acres—are already near existing roads."

### 1. ">40% high or very high wildfire hazard potential" → #586

| Question | Agency answer |
|---|---|
| Which WHP edition? | **Dillon, G.K. 2023. *Wildfire Hazard Potential for the United States (270-m), version 2023*. 4th Edition.** (DEIS Vol I references; also cites Dillon et al. 2014) |
| Classes counted | **high + very high** (classified WHP, not continuous) |
| Denominator | total acres of the potentially affected environment — **not** forested acres |
| Non-burnable pixels | **in** the denominator (no exclusion is described) |
| Alaska | **excluded — WHP is "Not Available" for Alaska** (DEIS Table 22) |

Agency result (DEIS Vol I Table 22): **11,479,564 acres** high or very high WHP.

- **41.8%** of the potentially affected environment **excluding Alaska**
- **28.7%** of the potentially affected environment **including Alaska**

So ">40%" is the **excluding-Alaska** figure. Including Alaska the same numerator is 28.7%. The
release's "primarily in the West" gestures at this but does not state that ~12.2M Alaska acres are
dropped from the denominator for lack of WHP coverage. **Reproducing this claim requires dropping
Alaska; reporting it as a share of all rule-affected IRAs does not.**

Regional range: 5.4% (Eastern) to 59.9% (Pacific Southwest). Product page:
<https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential>

Companion indicators in the same table, same denominator convention (all/excl-AK):

| Indicator | Acres | % of PAE | % excl. AK |
|---|---:|---:|---:|
| High or very high WHP | 11,479,564 | 28.7 | 41.8 |
| High-priority firesheds (Wildfire Crisis Strategy) | 7,236,418 | 18.1 | 26.3 |
| Community Wildfire Risk Reduction Zones (CWRRZ) | 5,919,512 | 14.8 | 20.7 |
| HFRA Wildland-Urban Interface | 9,785,271 | 24.4 | 35.4 |

CWRRZ = 1.5-mile buffer around building clusters (USDA FS 2022a); nearly all CWRRZ overlap in the
PAE is in the transition zone. HFRA WUI = at-risk community boundaries + 1.5-mile buffer (unless
modified by a Community Wildfire Protection Plan) + evacuation-route areas. Note the FR preamble
quotes the WUI overlap as "9.8 million acres (or 24 percent)" — the *including-Alaska* base.

### 2. "only 5% received hazardous fuels reduction treatments since 2014" → #587 / FACTS

| Question | Agency answer |
|---|---|
| Source | **FACTS** (Forest Activity Tracking System) — "Forest Service management activity reporting" |
| Status | **completed**, not planned ("has been completed on about 5 percent") |
| Period | **fiscal years 2014–2024** — FY, not CY, and 11 fiscal years, which the DEIS calls "the most recent decade" |
| Denominator | potentially affected IRA area (~40.0M) |
| Activity codes | **NOT DISCLOSED — still unresolved** |
| Footprint vs. summed records | **NOT DISCLOSED — still unresolved** |

DEIS Vol I p. 94: *"Forest Service management activity reporting (Forest Activity Tracking System,
or FACTS database) indicates that hazardous fuels reduction has been completed on about 5 percent
of the potentially affected IRA area over the most recent decade (fiscal years 2014-2024)."*

FACTS appears exactly **once** in DEIS Volume I. No activity-code list, no treatment-category
crosswalk, and no statement of whether overlapping records were dissolved to a footprint or summed
is published anywhere in the DEIS, the Economic Analysis, or the preamble.

Partial disaggregation is given (DEIS Vol I p. 96), as **shares of reported activities**, not of
area: mechanical rearrangement **11%**, mechanical removal **6%**. Elsewhere the DEIS notes
"a total of 1.8 million acres of hazardous fuels" and that "an additional 25 percent of the
hazardous fuels reduction was from prescribed burning activities."

**Consequence for #587:** the 5% is reproducible only up to activity-code choice. Any
reconstruction must publish its own code list and state the footprint-vs-summed decision, and
should report sensitivity across plausible code sets rather than a single number. The agency also
cites Healey (2020), which reached the opposite conclusion — that the 2001 Rule "did not
meaningfully constrain hazardous fuel treatment activities" — using similar agency data.

### 3. "11.3 million acres already near existing roads" → #588

**"Near" = within 0.5 miles, either side, of an existing road.**

| Question | Agency answer |
|---|---|
| Buffer | **0.5 miles**, measured either side of the road line |
| Road layer | **NFS roads from the Natural Resource Manager (NRM) database, September 2025 snapshot**, plus "other authorized public roads" (DEIS Vol I fn. 10, fn. 20) |
| NFS-only? | **No** — NFS roads *and* other authorized public roads |
| Denominator | potentially affected environment (~40.0M) |

Agency result: **11.3 million acres = 28.3%** of the potentially affected environment
(DEIS Vol I p. 41; FR preamble 91 FR 53829).

⚠️ **The Economic Analysis reports a different number for the same buffer.** Against the full
44.7M base (IRAs outside ID/CO, no wilderness deduction) it gives **13.3 million acres (30.8%)**
within 0.5 miles of a road, and 22.3 million acres (51.5%) within 1 mile, with ~17,000 miles of
road inside those IRAs. So:

| Base | Within 0.5 mi | Share | Implied base |
|---|---:|---:|---|
| Potentially affected environment (DEIS) | 11.3M | 28.3% | 39.9M |
| IRAs outside ID/CO (Economic Analysis) | 13.3M | 30.8% | 43.2M |

Both are "more than a quarter", so the release's phrasing is not wrong either way — but a
reproduction must pick a base, and the 11.3M figure is the wilderness-excluded one. The ~2.0M-acre
gap is roughly the wilderness/WSA/wild-river deduction, which is a useful cross-check on #588.

The Forest Service has **no national database of temporary roads** (fn. 20); temporary roads are
tracked locally only.

## 36 CFR 294 subpart B — read [36-cfr-294-subpart-b-2001.md](36-cfr-294-subpart-b-2001.md) first

⛔ **The CFR's printed text of §§ 294.10–294.18 is the 2005 State Petitions Rule, not the 2001
Roadless Rule.** Pulling "the current text of 36 CFR 294 subpart B" from eCFR returns the wrong
regulation. The 2001 text — the version legally in effect — must be read from 66 FR 3244. The
verbatim §294.12(b) and §294.13(b)(1) text, and the numbering trap, are in that file.

Short version of what those sections say, for the "the rule blocked the work" claim:
**§294.13(b)(1)(ii) already permits cutting small-diameter timber "to maintain or restore the
characteristics of ecosystem composition and structure, such as to reduce the risk of
uncharacteristic wildfire effects"**, and the DEIS concedes the rule "does not prohibit and has not
entirely prevented hazardous fuels reduction in IRAs" and that "there are no prohibitions on the
use of prescribed fire." The agency's argument is about *frequency and friction* — §294.13(b) says
use of the exceptions "is expected to be infrequent" — not about prohibition.

## Does the DEIS project timber volume or road miles under the action alternative?

**Timber volume: yes. Road miles: no.**

| | Alternative 2 (proposed action) | Alternative 3 (modified rule) |
|---|---|---|
| Operable acres where plans allow harvest | 4.8M (16% of forested area in PAE) | 4.3M |
| Added sawtimber, likely operable | 106,000–254,000 ccf/yr | 112,000–264,000 ccf/yr |
| Added sawtimber, likely operable but complex | 147,000–303,000 ccf/yr | 106,000–237,000 ccf/yr |
| **Total added sawtimber** | **253,000–557,000 ccf/yr** | **219,000–501,000 ccf/yr** |
| As % of national NFS sawtimber harvest (5.5M ccf/yr) | **5–10%** | **4–9%** |
| Plan-allowed road construction area | 18.2M acres (45.5% of PAE) | 14.2M acres (~52% of alt-3 PAE) |

Revenue (FR preamble): $5.2–11.4M/yr to Treasury and Forest Service, $4.6–10.6M/yr to industry.
Recreation benefit loss: ~$6.1M/yr. Total additional impacts "could exceed $100 million"; the rule
is economically significant under E.O. 12866 § 3(f)(1).

**No projection of new road miles is published** — only *acres where road construction would
become plan-allowed*. Combined with the absence of a national temporary-road database, the DEIS
gives no miles figure to audit under either action alternative.

⚠️ **The "16 percent of forested areas" denominator does not reconcile.** 4.8M ÷ 0.16 ⇒ ~30.0M
forested acres, but the DEIS reports forested area within the PAE three other ways:

| Source | Forested acres |
|---|---:|
| NLCD forest classes (Table 12) | 20,928,700 |
| Narrative, "about 21 million acres (52 percent)", FIA-based | ~21,000,000 |
| FIA forest type groups (Table 13), conifers + hardwoods | 25,486,900 |
| **Implied by "4.8M = 16%"** | **~30,000,000** |

None of the three published figures yields 16% (they give 23%, 22.9%, 18.8%). Flag as unresolved;
relevant to #590 when choosing a forest mask, and note that Table 13's own total (25.5M) already
disagrees with the narrative's "about 21 million" it is supposed to support.

## Other quantities worth auditing

| Claim | Value | Source |
|---|---|---|
| Plans further restrict road construction | 21.8M acres (54.5% of PAE) | DEIS Vol I p. 31 |
| Plans further restrict timber harvest | 26.7M acres (66.5% of PAE) | DEIS Vol I p. 31 |
| Tongass IRA under 2001 rule | 9.3M acres, ~56% of the forest (9.2M in PAE) | DEIS Vol I p. 31 |
| Non-forested vegetation in PAE | 14.9M acres (37%) | DEIS Vol I p. 62 |
| Roads deferred-maintenance backlog | $6.9B (2024, maintenance levels 3–5 only) | FR preamble; Econ. Analysis |
| Initial-attack success, 2014–2024 | >90% for all land designations; highest on other NFS land, lowest in wilderness | DEIS Vol I Table 24 |
| NFS road system | ~368,000 mi, down 18,000 mi over 23 years from a 2000 peak of 386,000 | DEIS Vol I p. 36 |

**"Nearly 60 percent of Forest Service land" in Montana** (Gov. Gianforte, quoted in the release)
**is not an agency figure** — it appears nowhere in the FR preamble, the DEIS, or the Economic
Analysis, and no agency methods support it. #594 noted MT IRA at 6,395,401 acres, which would need
a 10.66M-acre NFS denominator to be 60%. Treat it as a third-party statement; #585 can still test
it, but there is no agency definition to reproduce. (The DEIS's one comparable "% of the forest"
figure is the Tongass at ~56%.)

## Executive orders cited in the preamble

| E.O. | Title | Citation | Signed |
|---|---|---|---|
| 14192 | Unleashing Prosperity Through Deregulation | 90 FR 9065 | 2025-01-31 |
| 14225 | Immediate Expansion of American Timber Production | 90 FR 11365 | 2025-03-01 |
| 14154 | Unleashing American Energy | 90 FR 8353 | 2025-01-20 |
| 14153 | Unleashing Alaska's Extraordinary Resource Potential | 90 FR 8347 | 2025-01-20 |

Against the "does not mandate timber cutting or road construction" claim: the preamble states the
rescission "does not mandate timber cutting or road construction but would relieve regulatory
burden", while E.O. 14153 "directed the Secretary of Agriculture to reinstate the 2020 Alaska
Roadless Rule" — a directive, and one whose reinstatement is not what this rule does (the 2020
Alaska rule was repealed 2023-01-27, returning the Tongass to 2001-rule management).

## What is archived here, and what is not

Committed under `docs/` — the load-bearing and/or transient documents:

| File | What |
|---|---|
| `docs/pi-2026-16965.pdf` | **Public-inspection PDF — transient, not re-fetchable.** |
| `docs/fr-2026-16965.pdf` | Published rule, 91 FR 53827 |
| `docs/deis-vol1.pdf` | **DEIS Volume I, 333 pp — the methods source for all three claims** |
| `docs/economic-analysis.pdf` | Economic Analysis (RFA and CBA) |

Not committed (size, or not load-bearing) — URLs and sha256 in [sources.tsv](sources.tsv), re-fetch
with [fetch-sources.sh](fetch-sources.sh): DEIS Vol II (state maps, 8MB), DEIS Vol III (agency
letters, 75MB), Tribal Summary Impact Statement, Draft BAs (USFWS / NMFS), 2020 Alaska Roadless
Rule FEIS, 2023 Alaska DNA, Data Web Viewer instructions, rescission summary analysis.

⚠️ The supporting documents are served from a **Box shared link**, not Regulations.gov. As of
capture the Regulations.gov docket held only 2 documents (the NPRM and the 2025 NOI) and reported
`supporting_documents_count: 0` — the DEIS is **not** on the docket. Box shared links are not
durable identifiers; `fetch-sources.sh` will break when that link rotates. The sha256 values in
`sources.tsv` are the durable part.

If a `public-usfs` bucket lands via #584, staging the uncommitted PDFs to
`s3://public-usfs/raw/roadless-rule-2026/` would be the durable home for them. Out of scope here
(#589 is explicitly no-bucket-ingest).

## Other links

- Regulations.gov docket: <https://www.regulations.gov/docket/FS-2025-0001>
- FS Roadless Areas page: <https://www.fs.usda.gov/managing-land/planning/roadless>
- Box public folder: <https://usfs-public.app.box.com/s/gomzq6rruwsds8rw50o3j3g429utj8f6>
- Interactive DEIS map: <https://experience.arcgis.com/experience/c6122042b4ae46c9b323306912e8b40e>
- FS newsroom release (usda.gov 403s to scripted fetches; this mirror serves fine):
  <https://www.fs.usda.gov/about-agency/newsroom/releases/usda-acts-remove-roadless-rule-restrictions-exacerbate-rising>
- IRA shapefile (see #584): <https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.RoadlessArea_2001.zip>

ANILCA § 810 subsistence hearings for Alaska will be announced in a subsequent FR notice and posted
on the FS Roadless Areas page — worth re-checking before the comment deadline.
