# source.coop repos (account: cboettig)

**Scope: 27 repos** (all created in the web UI as of 2026-06-17). Create with **visibility: public**.
⚠️ = non-commercial (label NC). See `license-inventory.md` + `README.md`.

> Note: `public-wyoming` is intentionally NOT mirrored — a Wyoming-clipped collection whose datasets now live in full-extent buckets; kept on NRP, migration tracked in #225.

## ✅ Created (27 in scope)

`ca-dac` (CC-BY-4.0), `calenviroscreen` (public-domain), `carbon` (CC-BY-NC-4.0 ⚠️),
`census` (public-domain), `cgs` (public-domain), `cpad` (CC-BY-4.0), `ecoregion` (CC-BY-4.0),
`epa-water` (public-domain), `fire` (CC-BY-4.0), `gbif` (various/NC ⚠️), `gfw` (CC-BY-NC-4.0 ⚠️),
`high-seas` (various; `mpa-candidates` excluded), `inat` (CC-BY-NC-4.0 ⚠️), `indigenous` (CC-BY-4.0),
`land-cover` (various: CGLS-LC100 CC-BY-4.0 + NLCD PD), `mappinginequality` (CC-BY-NC-SA-4.0 ⚠️),
`mobi` (CC-BY-NC-4.0 ⚠️; **copy-mode**, see README), `ncp` (CC-BY-4.0),
`overturemaps` (CDLA-Permissive-2.0), `padus` (public-domain; legacy `pad-us-3` kept),
`population` (CC-BY-4.0; GHS-POP 2020), `rap` (public-domain),
`rivers` (various; `american-rivers/{campaigns,ira-watersheds,roo-cjest}` excluded; legacy `us-rivers` kept),
`social-vulnerability` (public-domain), `trails` (public-domain), `usfws` (public-domain),
`wetlands` (various: Ramsar PD + GLWD CC-BY-4.0 + NWI PD)

## ⛔ Not mirrored (held — NOT a license problem)

- **`tpl`** — the only license-clear collection in `public-tpl` was `wcb-approved-projects`
  (CDFW BIOS ds672, CA Wildlife Conservation Board), a CDFW **state-agency** product misfiled
  under "tpl". Being relocated to the planned `public-cdfw` bucket (geo-agent-ops #19;
  data-workflows #228) — mirror as `cboettig/cdfw` afterward. The rest of `public-tpl`
  (Conservation Almanac, LandVote) is HOLD pending TPL terms, so `cboettig/tpl` was not created.
- **`ca-wolves`** — license is clear (`CC0-1.0`), but it is a **real-time updated** product
  (`wolf_*_latest.geojson` + `snapshots/`); a static mirror would be a stale copy presented as
  current. Held until we decide whether to publish only the dated `snapshots/`.
