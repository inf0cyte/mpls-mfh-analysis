# Minneapolis 2040 Plan: duplex and triplex permits, 2020 to 2026

How many duplexes and triplexes have been permitted in Minneapolis since the Minneapolis 2040
Comprehensive Plan legalized them citywide, how many of those were in areas where they were
previously banned, how that compares with new single-family homes over the same period, and how many
dwelling units the city gained in total once demolitions and other removals are subtracted.

All figures below are reproduced by `scripts/analyze.py` and `scripts/net_units.py` from the files in `data/`.
The permit data was pulled on **2026-10-14 00:17 UTC** and the assessor data on 2026-10-14 00:18 UTC. The source
permit layer had last been edited at 2026-10-13 20:04 UTC. Every query is limited to permits issued from
2020-01-01 through 2026-09-24.

---

## 1. Scope of the data

| Item | Coverage |
|---|---|
| Geography | City of Minneapolis only |
| Time | Permits issued **2020-01-01** (the day the 2040 Plan's zoning changes took effect) through **2026-09-24**. The window is set by `SINCE` and `UNTIL` in `scripts/arcgis.py`. Years are calendar years of `issueDate` in UTC. |
| Building types in scope | Sections 5.2 to 5.7: 2-unit and 3-unit residential buildings (duplexes, triplexes, 2- and 3-unit townhouse buildings). Fourplexes and larger are out of scope there. New single-family homes are included only for comparison. Sections 5.8 to 5.10 count every dwelling unit, in buildings of any size. |
| Metric | **Building permits pulled** (issued), for new construction, conversion of an existing building, or demolition. A permit is not proof that the work was completed. |
| Excluded | Permits with status `Cancelled` or `Expired`. Trade-only permits (plumbing, mechanical, electrical). ADUs are not counted as duplexes or as dwelling units: the city treats an ADU as accessory to a house. They are reported separately in 5.8. |
| Permit source | City of Minneapolis Construction Code Services permits, ArcGIS feature layer `CCS_Permits` ([open data page](https://opendata.minneapolismn.gov/datasets/cityoflakes::ccs-permits)). |
| Zoning source | City of Minneapolis primary zoning layers on the city's ArcGIS Online organization: `msvcCPED_PrimaryZoning_20170126` (map as of 2017-01-26, before the 2040 Plan) and `PrimaryZoningArchive` (map archived 2023-06-30). |
| Assessor source | City of Minneapolis Assessor yearly parcel snapshots on the same organization: `Assessors_Parcel_Data_2017` to `_2022` and `Assessing_Department_Parcel_Data_2023` to `_2026`. Used only to count the units on demolished parcels. |
| Rule source | City of Minneapolis CPED staff report and draft ordinance for the City Planning Commission, Oct 7 2019: "Duplexes are first allowed in the R2 District and triplexes are first allowed in the R3 District." ([PDF](https://www2.minneapolismn.gov/media/content-assets/www2-documents/business/Staff-report-and-draft-ordinance-prepared-for-the-City-Planning-Commission-(October-7,-2019),wcmsp-220995.pdf)) |
| Not pulled | Applicant names and addresses exist in the source layer but were deliberately left out. Assessor owner fields were not pulled either. |

---

## 2. Repository layout

```
scripts/
  arcgis.py         ArcGIS REST helpers (stdlib only): query with paging, counts, point-in-zone, geocode,
                    permit-layer schema check, observation window, assessor snapshot settings
  pull_permits.py   pulls the six raw permit sets into data/raw/
  pull_zoning.py    looks up the 2017 and 2023 zoning district at every duplex/triplex permit
  pull_assessor.py  pulls assessor records for every parcel with an active demolition permit
  classify.py       the selection rules shared by pull_zoning.py, analyze.py and net_units.py
  analyze.py        produces the duplex, triplex and single-family tables (5.2 to 5.7)
  net_units.py      produces the units added, removed and net tables (5.8 to 5.10)
  run_all.py        runs pull_permits -> pull_zoning -> pull_assessor -> analyze -> net_units
  sample.py         pull arbitrary samples from the live sources to validate the method
data/
  raw/              exactly what the pull scripts wrote (JSON is canonical; CSV is the same rows flattened)
    permits_new_construction.{json,csv}        873 rows: every workType='New' permit in the window
    permits_conversion_candidates.{json,csv}   827 rows: keyword/work-type search for conversions (query in manifest)
    permits_unit_changes.{json,csv}            258 rows: every non-new Res/Commercial permit recording units added or eliminated
    permits_adu_mentions.{json,csv}            238 rows: every Res/Commercial permit whose description mentions an ADU
    permits_wrecking.{json,csv}                658 rows: every demolition (Wrecking) permit
    permits_manually_classified.{json,csv}     182 rows: every permit named in the manual classification file
    pull_manifest_permits.json                 exact SQL where-clauses, row counts, pull time, source edit time,
                                               source field types
    zoning_point_lookups.csv                   186 rows: coordinates used and zone on each map, per permit
    assessor_demolished_parcels.json           assessor records for 628 of the 634 demolished parcel ids
    pull_manifest_assessor.json                services, field names and record counts for each snapshot
  manual/
    conversion_classification.csv             171 permits classified by reading their descriptions (see 3.4)
    unit_change_review.csv                    404 permits reviewed for the citywide unit count (see 3.9)
    demolition_review.csv                     demolitions handled by hand (see 3.9)
  derived/          outputs of analyze.py and net_units.py
```

Requirements: Python 3.9 or newer. No third-party packages are needed.

---

## 3. Methodology

### 3.1 Pulling permits (`pull_permits.py`)
Six queries are sent to the `CCS_Permits` layer, each limited to permits issued in the window. The exact SQL
text of each is saved in `data/raw/pull_manifest_permits.json`.

1. **New construction:** `workType = 'New'`
2. **Conversion candidates:** non-new `Res` or `Commercial` permits where any of these is true:
   - the work type is `Conversion` or `UnitCon`;
   - the description contains CONVER or LEGALIZ together with a building-type word (DUPLEX and its common misspellings, TRIPLEX, TWO%FAMILY, TFD, SFD, SINGLE%FAMILY, THREE%FAMILY);
   - the description contains a unit phrase such as THIRD%UNIT, 3RD DWELLING, SECOND DWELLING or INTO%DUPLEX.
3. **Unit changes:** non-new `Res` or `Commercial` permits with `dwellingUnitsNew > 0` or `dwellingUnitsEliminated > 0`.
4. **ADU mentions:** `Res` or `Commercial` permits, new construction included, whose description contains ADU or ACCESSORY DWELLING.
5. **Demolitions:** `permitType = 'Wrecking'`.
6. **Manually classified permits:** every permit number listed in `data/manual/conversion_classification.csv`. This guarantees the source record behind every manual decision is in the repo, even when the keyword search in query 2 did not find it.

Each query is paged in OBJECTID order. The script aborts if the number of rows pulled differs from the server's count.

Before querying, the script reads the layer's field list and stops if any field the scripts use is missing or
has an unexpected type (`check_permit_schema` in `arcgis.py`). The field types it saw are written to the
manifest as `field_types`.

### 3.2 Automatic selection rules (`classify.py`)
- **Duplicate rows:** the source layer sometimes holds more than one row per permit number. Each permit counts once, using the row with the lowest OBJECTID. Duplicate rows agree on status, codes and unit counts, but can carry different coordinates and parcel ids, so the zoning and assessor lookups use every row (3.5, 3.9).
- **New duplex:** a new-construction permit with `occupancyType` of `TFD` (two-family dwelling) or `TH` (townhouse), `dwellingUnitsNew = 2`, and a status other than Cancelled or Expired. Thirteen more permits are added from the manual file: twelve new two-family dwellings whose unit fields are coded 0 or 1, and one coded as 3 units whose description is a duplex plus an ADU.
- **New triplex:** a new-construction permit with `occupancyType = '3to4'` (the city's code for 3- and 4-unit buildings), `dwellingUnitsNew = 3`, and an active status. One more is added from the manual file: a three-unit townhouse building coded as `Comm`.
- **Excluded two- and three-unit new permits:** mixed-use and commercial projects (`Mixed`, `Comm`, and one `3to4` record that is really a triplex-to-duplex change) are left out. `analyze.py` prints how many raw rows fall under each occupancy code, so the exclusions can be checked.
- **New single-family home:** a new-construction permit with `occupancyType = 'SFD'`, excluding Cancelled permits, minus two permits that only finish a house started under an earlier permit.

### 3.3 Why conversions need manual classification
The permit layer's unit fields cannot be trusted for conversions:
- `dwellingUnitsNew` and `dwellingUnitsEliminated` are used inconsistently. Some single-family-to-duplex permits show `2/1`, others `1/0`, `1/1` or `0/0`. A duplex-to-single-family permit can also show `2/1`.
- `occupancyType` is sometimes the building's type before the work and sometimes its type after.

So conversions were identified by **reading each permit description**. Filtering on unit fields misses some conversions and wrongly includes some reverse conversions.

### 3.4 Manual classification (`data/manual/conversion_classification.csv`)
Every permit whose description describes adding or removing a unit in a 1- to 3-unit building was assigned one category and given a note:

| Category | Counted? | Meaning |
|---|---|---|
| `sfd_to_duplex` | yes (+1 unit) | Single-family home converted to a duplex |
| `duplex_to_triplex` | yes (+1 unit) | Third unit added to a duplex |
| `sfd_to_triplex` | yes (+2 units) | Single-family home converted to a triplex |
| `paper_to_duplex` | no | Legalization, a no-work reconversion, or an existing ADU re-designated as a unit |
| `duplex_to_sfd`, `triplex_to_duplex`, `triplex_to_sfd` | yes, or `record_only` | De-conversions. `record_only` marks records corrections and legalizations with no physical change. |
| `cancelled_or_expired` | no | Would have counted, but the permit is Cancelled or Expired |
| `reviewed_not_counted` | no | Reviewed and not a qualifying conversion (companion permits, commercial-to-SFD, ADUs, and similar) |
| `new_duplex`, `new_triplex`, `new_sfd_exclude` | as noted | Overrides for miscoded new-construction permits (see 3.2) |

As a completeness check, `analyze.py` runs a second regular-expression screen over all 827 candidates. It flags any active permit whose description reads like a conversion but is missing from the manual file, and writes those to `data/derived/unreviewed_conversion_candidates.csv`. **For this pull that file is empty (0 rows).**

### 3.5 Zoning test (`pull_zoning.py`)
For each counted duplex or triplex permit, the permit's `Latitude`/`Longitude` is sent to the city's zoning
layers as an ArcGIS point-intersect query. The district is recorded on two maps:
- the **2017 map** (`msvcCPED_PrimaryZoning_20170126`), used to decide what was allowed before the plan;
- the **2023 map** (`PrimaryZoningArchive`), used only to flag sites rezoned after 2017.

When a permit has several rows with different coordinates, every point is looked up. If they all fall in the same
districts, that point is used; this applied to one permit. Two permits had no coordinates, and one permit's four
points fell in different districts. Those three addresses were geocoded with the Esri World Geocoder, and the
matched address and score are kept in `zoning_point_lookups.csv`. All three matched their street address exactly (score 100).

**Newly allowed** is defined from the CPED staff report's statement of the pre-2040 rules:
- a **duplex** (new build or conversion) is newly allowed if the 2017 district is **R1 or R1A**;
- a **triplex** (new build or conversion) is newly allowed if the 2017 district is **R1, R1A, R2 or R2B**.

### 3.6 Units
Units are gross units added by the permit: new duplex = 2, new triplex = 3, SFD to duplex = +1,
duplex to triplex = +1, SFD to triplex = +2. Sections 5.3 to 5.7 do not subtract demolitions; 5.8 to 5.10 do.

### 3.7 How the scripts were tested
The workspace that wrote these scripts could not reach the city's ArcGIS servers, but a web browser on the
analyst's linked Windows PC could. The scripts were therefore run **unchanged** in CPython 3.12 (Pyodide 0.26.4)
inside that browser:
1. The scripts and manual files were copied into the browser runtime and SHA-256-checked against these copies. All matched.
2. `pull_permits.py`, `pull_zoning.py` and `pull_assessor.py` were run from an empty `data/raw`, then `analyze.py` and `net_units.py`.
3. `sample.py verify --n 20 --seed 42` re-queried 20 random classified permits live and repeated both zoning lookups. All 20 matched.

The only test-harness change was a shim that routes Python's `urllib.request.urlopen` through the browser's
HTTP stack, sending POST bodies exactly as CPython does.

4. The raw JSON and zoning lookups were then copied out of the browser (SHA-256 verified). The raw CSVs and
   everything in `data/derived/` were regenerated with **native CPython 3.11 on Linux** using the same scripts.
   All 11 files in `data/derived/` are byte-identical to the browser run.

**Schema handling (see 3.8).** The unit-field conversion in `classify.py` was tested three ways:
- *Integer data:* run on raw files from before the schema change (integer unit fields), the current scripts produce `data/derived/` files byte-identical to the scripts written for that schema.
- *String data:* the same raw files with every unit value converted to a string also produce byte-identical `data/derived/` files.
- *Live pull:* `pull_permits.py` passed the schema check against the current layer and recorded `dwellingUnitsNew` and `dwellingUnitsEliminated` as `esriFieldTypeString` and `permit_Value` as `esriFieldTypeDouble`.

For comparison, on the same data, scripts that do not convert the unit fields do not fail on string values. They
silently count 3 new duplexes and 1 new triplex, because `"2" == 2` is false in Python. That is why `classify.py` converts the
unit fields on load.

What has **not** been exercised is the network pull (`pull_permits.py`, `pull_zoning.py`, `pull_assessor.py`,
`sample.py`) under a native desktop Python with direct network access. If one fails there, the cause will be in
`arcgis._post`, which is 15 lines of standard `urllib`.

### 3.8 Source schema change (October 2026)
The city changed the `CCS_Permits` schema between 2026-09-28 and 2026-10-13. The old schema was still in place
on 2026-09-28, and the new one was observed on 2026-10-13. The exact date is unknown: the layer is republished
daily, so its edit timestamps change every day and do not date the change.
- `value` (permit valuation) was renamed `permit_Value`. No figure in this README uses it.
- `dwellingUnitsNew` and `dwellingUnitsEliminated` changed from integer fields to string fields. Values now arrive as `"2"` rather than `2`.

The raw files in `data/raw/` were pulled after the change, so they hold `permit_Value` and string unit values
exactly as the server returned them. `classify.load()` converts the unit fields to integers (blank stays blank)
before any rule runs, and also reads raw files pulled under the old schema.

If the city changes the schema again, `pull_permits.py` stops before pulling and names each problem field.
Update `PERMIT_FIELDS` and `PERMIT_FIELD_TYPES` in `scripts/arcgis.py` to match.

### 3.9 Citywide unit count (`net_units.py`)
Every permit in the window that adds or removes a dwelling unit is counted once, in the year it was issued.
Cancelled and Expired permits are left out.

**Units added**
- **New construction:** `dwellingUnitsNew` on every active new-construction permit. `data/manual/unit_change_review.csv` drops 3 re-issued permits (an energy-model re-issue of 650 Portland Ave's 222 units and two re-permits to finish houses) and replaces the recorded count on 19 permits where the description shows it is wrong: 12 two-family dwellings recorded as 0 or 1 units, 6 townhouses and a 7-unit apartment building recorded as 0, 3 new houses recorded as 0, an apartment building whose 45 recorded units include a 54-bed shelter (28 dwelling units), and a duplex whose 3 recorded units include an ADU.
- **Units added to existing buildings:** every permit in the unit-changes query (246 permits) was reviewed by reading its description. Office, warehouse, hotel, motel and church conversions, additions, and new units in existing apartment buildings are counted with the number of units actually added. Not counted: legalizations of existing units, records corrections, finish-outs of condo units in towers whose units were counted when the tower was permitted, companion permits, and rooming units rebuilt as apartments (rooming units are not dwelling units, so these are left out of both sides). Permits with no usable description are counted as their unit fields record them.
- **Conversions of 1- to 3-unit buildings:** the counted conversions in `conversion_classification.csv` (+1 or +2 units each, see 3.6).
- **ADUs:** every permit in the ADU query (235 permits) was reviewed. Only permits that create an ADU are counted, one each. Legalizations, recognitions of existing ADUs, repairs, garages described as "not an ADU", and adult day cares (which match "ADU" inside "ADULT") are not.

**Units removed**
- **Demolitions:** demolition permits do not record units. `pull_assessor.py` pulls the City Assessor's records for every parcel id on any row of an active demolition permit. For each permit, `net_units.py` takes the latest snapshot at or before the permit year that still shows a building. In the 2017 to 2024 snapshots the parcel's units are `TOTAL_UNITS`, summed over its records. In 2025 and 2026 `TOTALUNITS` is 0 for 1- to 3-unit homes, so the parcel's property type ("RESIDENTIAL 2 UNITS", for example) is used, counted once per parcel. Each parcel is counted once even when it had several demolition permits. Where no snapshot shows a building, the permit's occupancy code is used: single-family 1, two-family 2, `3to4` 3, anything else 0. `data/manual/demolition_review.csv` overrides individual permits; it holds one exclusion, a fire-damaged 6-unit building at 712 Olson Memorial Hwy that was rebuilt with 6 units on the same foundation, which is left out of both sides.
- **De-conversions:** the counted de-conversions in `conversion_classification.csv` (−1 or −2 units each).
- **Units converted to other uses or combined:** from the same review of the unit-changes query: apartments turned into offices, a salon, a day care, an assisted living facility or a treatment center, and units combined into larger units. One house demolished to its foundation under a remodel permit is also here.

**Completeness:** `net_units.py` stops if any permit returned by the unit-changes or ADU queries has no decision in
either manual file, if a permit is decided in both, or if a manual entry is missing from the raw data. Of the 470
permits in the two queries, 87 are decided by `conversion_classification.csv` and 383 by `unit_change_review.csv`,
which also holds 21 new-construction entries (the 3 re-issues and 18 count corrections) outside the two queries.

---

## 4. Validating the method yourself

```bash
cd mpls-mfh-analysis
python3 scripts/run_all.py          # re-pulls everything (~2 minutes) and prints every table below
```

Statuses change daily, so a later pull can give slightly different counts even for the same window. To extend
the window, change `UNTIL` in `scripts/arcgis.py`; new permits will then need decisions in the manual files, and
`net_units.py` lists any that are missing.

**Spot-check an arbitrary sample**

```bash
# 1. Random sample of classified permits, re-pulled live, with both zoning lookups repeated
python3 scripts/sample.py verify --n 20 --seed 42

# 2. Any count, using the ArcGIS SQL dialect
python3 scripts/sample.py count "workType='New' AND occupancyType='TFD' AND issueDate >= DATE '2020-01-01'"

# 3. Read the actual permit records behind a count
python3 scripts/sample.py rows "occupancyType='3to4' AND workType='New' AND dwellingUnitsNew=3 AND issueDate >= DATE '2020-01-01'" --limit 40 --out triplexes.csv

# 4. Check the zoning of any point on both maps (latitude longitude)
python3 scripts/sample.py zone 44.94757 -93.30556

# 5. Look for conversions the keyword search could have missed, e.g. a different phrase
python3 scripts/sample.py rows "UPPER(comments) LIKE '%ADD%DWELLING UNIT%' AND issueDate >= DATE '2020-01-01'" --limit 100

# 6. Read a demolition permit and compare it with the assessor record in data/raw/assessor_demolished_parcels.json
python3 scripts/sample.py rows "permitNumber='BLDG1001618'"
```

**Without Python:** paste a query URL into a browser. For example, this returns the number of new
two-family permits since 2020:

```
https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/CCS_Permits/FeatureServer/0/query?where=workType%3D%27New%27+AND+occupancyType%3D%27TFD%27+AND+issueDate+%3E%3D+DATE+%272020-01-01%27&returnCountOnly=true&f=json
```

Replace `returnCountOnly=true` with `outFields=permitNumber,Display,status,dwellingUnitsNew,comments` to see the rows.

**Unit fields in where clauses.** `dwellingUnitsNew` and `dwellingUnitsEliminated` are now text fields (see 3.8).
Write numbers without quotes. An unquoted number is compared numerically; a quoted one is compared as text. Equality
gives the same answer either way, but ranges do not. On 2026-10-13, among new-construction permits since 2020-01-01,
`dwellingUnitsNew >= 5` matched 145 permits (the correct count) and `dwellingUnitsNew >= '5'` matched 57, because
as text `'10'` sorts before `'5'`.

**To audit the manual classification**, pick any rows from `data/manual/conversion_classification.csv`,
find the same `permitNumber` in `data/raw/permits_manually_classified.csv`, and read its `comments`.
The `note` column says why it was classified the way it was. `unit_change_review.csv` works the same way against
`permits_unit_changes.csv`, `permits_adu_mentions.csv` and `permits_new_construction.csv`.
`data/derived/net_units_permits.csv` lists every permit counted in 5.8 and 5.9, and
`data/derived/demolitions_by_parcel.csv` shows each demolished parcel with its permit-code and assessor counts.

---

## 5. Findings

### 5.1 Published estimates (literature, not reproduced by these scripts)
These figures come from the linked publications and were not recomputed here:
- **Minneapolis Fed (Apr 2024):** 46 new 2- to 4-unit buildings were permitted in 2020–2022. Just 20 of the new duplexes and triplexes were in areas zoned single-family before the plan. [source](https://www.minneapolisfed.org/article/2024/minneapolis-2040-plan-data-tool-prepared-to-measure-impacts)
- **Minneapolis Fed (Aug 2025):** 87 new duplex, triplex and fourplex buildings with 225 units were permitted in 2020–2024. The peak was 2023, with 24 buildings and 63 units, 11 of them in formerly single-family-only areas. The Fed's source excludes conversions. Over the same period the city built 11,503 units in apartment buildings of 5+ units. [source](https://www.minneapolisfed.org/article/2025/unpacking-supply-and-demand-in-rent-trends-since-the-minneapolis-2040-plan)
- **Streets.mn (Oct 2023):** 72 new duplexes and 37 triplexes (255 units) were built over about 2.5 years of city permit data. Less than half were in former R1/R1A zones. [source](https://streets.mn/2023/10/24/mapping-minneapolis-duplexes-and-triplexes/)
- **Axios (Mar 2021):** 16 new duplexes and 4 triplexes in 2020, plus 22 existing properties converted to duplexes or triplexes. [source](https://www.axios.com/local/twin-cities/2021/03/01/minneapolis-triplex-legalize-impact-little)
- **Court order:** from 2023-11-04, a Hennepin County District Court order stopped triplexes in areas that previously allowed only single-family homes and duplexes (reported in the Minneapolis Fed 2024 article above).

### 5.2 The permit layer's unit fields are unreliable for conversions
See 3.3. Among raw new-construction rows, 86 rows (83 distinct permits) have `dwellingUnitsNew = 2`, spread across
occupancy codes TFD 80, TH 3, Comm 1, Mixed 1, 3to4 1. Another 34 rows (31 permits) have `dwellingUnitsNew = 3`:
3to4 28, Comm 3, Mixed 1, TFD 1, TH 1. Conversion permits code units inconsistently. This is why conversions
were classified by reading descriptions.

### 5.3 Duplex and triplex permits, 2020-01-01 to 2026-09-24

| Category | Permits | Units added (gross) |
|---|---|---|
| New duplex | 92 | 184 |
| New triplex | 28 | 84 |
| SFD to duplex | 42 | 42 |
| Duplex to triplex | 23 | 23 |
| SFD to triplex | 1 | 2 |
| **Total** | **186** | **335** |

Of the 92 new duplex permits, 20 also record an eliminated unit, usually a demolished house on the same lot.
Those 20 add a net of 1 unit each, not 2. None of the new triplex permits record an eliminated unit.

### 5.4 New duplexes and triplexes by year

| Year | New duplex | New triplex |
|---|---|---|
| 2020 | 14 | 4 |
| 2021 | 16 | 5 |
| 2022 | 8 | 8 |
| 2023 | 15 | 9 |
| 2024 | 15 | 0 |
| 2025 | 18 | 2 |
| 2026 (to Sept 24) | 6 | 0 |
| **Total** | **92** | **28** |

No new triplexes were permitted in 2024, the year after the court order in 5.1, and only 2 have been permitted since.

### 5.5 Conversions versus de-conversions

| Direction | Physical permits | Units |
|---|---|---|
| Conversions: SFD to duplex (42), duplex to triplex (23), SFD to triplex (1) | 66 | +67 |
| De-conversions: duplex to SFD (41), triplex to duplex (1), triplex to SFD (1) | 43 | −44 |
| Records-only de-conversions (no physical change) | 7 | 0 |
| Paper conversions to duplex: legalizations, reconversions, ADU re-designation | 6 | 0 |

Physical permits by year:

| Year | Conversions (permits) | De-conversions (permits) |
|---|---|---|
| 2020 | 13 | 3 |
| 2021 | 9 | 6 |
| 2022 | 15 | 6 |
| 2023 | 8 | 5 |
| 2024 | 6 | 3 |
| 2025 | 11 | 12 |
| 2026 (to Sept 24) | 4 | 8 |

Across the whole period, de-conversions removed about two-thirds as many units as conversions added. In 2025 and 2026 there were more de-conversions than conversions.

### 5.6 How many permits were in areas where the building type was previously banned

| Category | Permits | In newly allowed zone | Share | Units in newly allowed zones |
|---|---|---|---|---|
| New duplex | 92 | 47 | 51% | 94 |
| New triplex | 28 | 25 | 89% | 75 |
| SFD to duplex | 42 | 14 | 33% | 14 |
| Duplex to triplex | 23 | 20 | 87% | 20 |
| SFD to triplex | 1 | 1 | 100% | 2 |
| **Total** | **186** | **107** | **58%** | **205** |

By year (newly allowed permits / all permits in the category):

| Year | New duplex | New triplex | Conversions |
|---|---|---|---|
| 2020 | 11 of 14 | 3 of 4 | 6 of 13 |
| 2021 | 9 of 16 | 5 of 5 | 6 of 9 |
| 2022 | 3 of 8 | 7 of 8 | 8 of 15 |
| 2023 | 6 of 15 | 9 of 9 | 4 of 8 |
| 2024 | 7 of 15 | 0 of 0 | 4 of 6 |
| 2025 | 9 of 18 | 1 of 2 | 6 of 11 |
| 2026 (to Sept 24) | 2 of 6 | 0 of 0 | 1 of 4 |

2017 zoning districts of the counted permits:

| Category | R1 | R1A | R2 | R2B | R3 | R4 | R5 | OR1 | C1 |
|---|---|---|---|---|---|---|---|---|---|
| New duplex | 5 | 42 |  | 40 |  | 4 | 1 |  |  |
| New triplex | 1 | 13 |  | 11 |  |  | 2 | 1 |  |
| SFD to duplex | 4 | 10 | 1 | 22 | 1 | 1 | 2 |  | 1 |
| Duplex to triplex | 1 | 3 |  | 16 |  | 1 | 2 |  |  |
| SFD to triplex |  | 1 |  |  |  |  |  |  |  |

Sites whose zone differs between the 2017 and 2023 maps: 1800 and 1806 Como Ave SE (R2B to R4, new duplexes),
4600 36th Ave S (R1A to R2B, new duplex), 2318 Johnson St NE and 405 31st St E (R1A to R4, new triplexes).
The two triplex sites were probably rezoned for those projects. Counting them as not caused by the plan lowers
the total to **105 of 186**.

Readings:
- Triplexes depend almost entirely on the plan: 46 of 52 triplex permits (new builds and conversions) are in zones that banned them before.
- Most duplex activity was already legal. About half of new duplexes and two-thirds of SFD-to-duplex conversions are in R2B or denser zones.
- Only 61 duplex permits (47 new, 14 conversions) are on formerly single-family-only land, adding 108 units gross.

### 5.7 New single-family homes, same period

| Year | New single-family | New duplex | New triplex |
|---|---|---|---|
| 2020 | 71 | 14 | 4 |
| 2021 | 64 | 16 | 5 |
| 2022 | 55 | 8 | 8 |
| 2023 | 73 | 15 | 9 |
| 2024 | 60 | 15 | 0 |
| 2025 | 57 | 18 | 2 |
| 2026 (to Sept 24) | 29 | 6 | 0 |
| **Total** | **409** | **92** | **28** |

- By building, new single-family homes outnumber new duplexes and triplexes combined about 3.4 to 1.
- By unit, the comparison is 409 single-family units vs 268 duplex and triplex units.
- 7 single-family permit descriptions mention an ADU. Six build a new ADU, and one (5615 Penn Ave S) turns an existing alley house into the ADU.
- 3 single-family permits have no description and `dwellingUnitsNew = 0`. They are kept because their codes say new single-family construction.

### 5.8 All dwelling units permitted, same period

| Source | Permits | Units |
|---|---|---|
| New construction | 711 | 12,431 |
| Units added to existing buildings (office, warehouse, hotel and church conversions; additions; new units in apartment buildings) | 75 | 2,024 |
| Conversions of 1- to 3-unit buildings (5.5) | 66 | 67 |
| **Total dwelling units added** | **852** | **14,522** |
| ADUs (not dwelling units; reported separately) | 84 | 84 |

Duplexes and triplexes are a small share of the total: the 268 units in new duplexes and triplexes (5.3) are about
2% of the units added. ADUs are recorded by the city as 0 dwelling units, and many ADU permits state "THIS PERMIT
DOES NOT CREATE AN ADDITIONAL DWELLING UNIT", so they are kept out of the dwelling-unit total.

### 5.9 Units removed and net gain

| Source | Permits or parcels | Units |
|---|---|---|
| Demolitions (parcels with dwelling units) | 480 | 687 |
| De-conversions (5.5) | 43 | 44 |
| Units converted to other uses or combined | 12 | 15 |
| **Total dwelling units removed** | **535** | **746** |

**Net gain: 13,776 dwelling units** (14,522 added, 746 removed), or 13,860 counting ADUs. Removals offset about 5%
of the units added.

| Year | Added | Removed | Net | ADUs | Net with ADUs |
|---|---|---|---|---|---|
| 2020 | 3,498 | 140 | 3,358 | 17 | 3,375 |
| 2021 | 2,979 | 100 | 2,879 | 11 | 2,890 |
| 2022 | 4,352 | 103 | 4,249 | 13 | 4,262 |
| 2023 | 1,879 | 119 | 1,760 | 8 | 1,768 |
| 2024 | 820 | 100 | 720 | 11 | 731 |
| 2025 | 517 | 118 | 399 | 11 | 410 |
| 2026 (to Sept 24) | 477 | 66 | 411 | 13 | 424 |
| **Total** | **14,522** | **746** | **13,776** | **84** | **13,860** |

Removals stayed at about 100 to 140 units a year while additions fell sharply after 2022. In 2025, removals offset
more than a fifth of the units added.

### 5.10 Demolitions in detail
646 active demolition permits covered 632 parcels; 7 parcels had more than one permit. 152 of the parcels held no
dwelling units (commercial buildings, garages and other structures).

Demolished parcels by the number of dwelling units on them:

| Units on parcel | Parcels | Units |
|---|---|---|
| 1 | 378 | 378 |
| 2 | 81 | 162 |
| 3 | 11 | 33 |
| 4 or more | 10 | 114 |
| 0 (no dwelling) | 152 | 0 |
| **Total** | **632** | **687** |

Units demolished by year and building size:

| Year | Parcels | Permits | In 1-unit | In 2-unit | In 3-unit | In 4+ unit | Units removed |
|---|---|---|---|---|---|---|---|
| 2020 | 129 | 136 | 62 | 40 | 6 | 25 | 133 |
| 2021 | 106 | 108 | 65 | 12 | 9 | 8 | 94 |
| 2022 | 96 | 100 | 56 | 28 | 3 | 8 | 95 |
| 2023 | 87 | 87 | 53 | 36 | 0 | 25 | 114 |
| 2024 | 71 | 71 | 51 | 14 | 3 | 25 | 93 |
| 2025 | 85 | 85 | 60 | 28 | 12 | 4 | 104 |
| 2026 (to Sept 24) | 58 | 59 | 31 | 4 | 0 | 19 | 54 |
| **Total** | **632** | **646** | **378** | **162** | **33** | **114** | **687** |

Where each parcel's unit count came from:

| Source | Parcels | Units |
|---|---|---|
| Assessor snapshot from the permit year | 590 | 644 |
| Earlier assessor snapshot (building already gone from the permit-year snapshot) | 21 | 30 |
| Permit occupancy code (no assessor record shows a building) | 20 | 13 |
| Excluded (712 Olson Memorial Hwy, rebuilt) | 1 | 0 |

The assessor count differs from what the permit's occupancy code implies on 48 of the 611 parcels with an
assessor record:

| Comparison | Parcels | Units by permit code | Units by assessor |
|---|---|---|---|
| Same | 563 | 485 | 485 |
| Assessor higher | 45 | 29 | 186 |
| Assessor lower | 3 | 6 | 3 |

- **Houses that held more than one unit:** 24 parcels with permits coded single-family held 50 units on the assessor's roll (duplexes, double bungalows and triplexes).
- **Apartment buildings:** the `MFD` code carries no unit count. The assessor records 117 units on 13 demolished apartment buildings. The Drake Hotel (416 10th St S) shows no dwelling units, and 712 Olson Memorial Hwy is excluded.
- **Commercial buildings with apartments:** 6 parcels coded commercial held 12 units.
- **Lower counts:** 3927 Upton Ave S was coded single-family but held no dwelling; 1108 7th St SE (coded two-family) held 1 unit; 2341 Penn Ave N (coded `3to4`) held 2.

Demolished buildings with 4 or more units:

| Address | Year | Units | Source |
|---|---|---|---|
| 1829 5th Ave S | 2024 | 25 | assessor, permit year |
| 2003 Aldrich Ave S | 2020 | 25 | assessor, permit year |
| 2312 Lyndale Ave S | 2023 | 25 | assessor, earlier snapshot |
| 5617 Lyndale Ave S | 2026 | 11 | assessor, permit year |
| 1820 4th Ave S | 2021 | 8 | assessor, permit year |
| 1000 Main St NE | 2022 | 4 | assessor, permit year |
| 2500 16th Ave S | 2026 | 4 | assessor, permit year |
| 4146 Fremont Ave N | 2026 | 4 | assessor, permit year |
| 4901 France Ave S | 2022 | 4 | permit codes (three permits: one two-family, two single-family) |
| 718 14th Ave SE | 2025 | 4 | assessor, permit year |

---

## 6. Limitations
- **Permits are not completions.** Some permits are still `Issued` or `Open`: 20 and 3 of the new duplexes, 6 of the new triplexes. Some permitted units will not be built, and a few permitted demolitions may not happen.
- **Conversion counts depend on permit descriptions.** A conversion described in words the searches don't match would be missed. The completeness screen reduces this risk but does not rule it out.
- **The pre-plan map is from January 2017,** three years before the rules changed. Only 5 of 186 permit sites differ from the 2023 map, but rezonings between 2017 and 2019 are not captured directly.
- **Nonconforming uses:** a duplex-to-triplex conversion in R1 or R1A (4 permits) started from an existing duplex that predates the old rules.
- **Scope of the zoning rule:** it is based on the primary residential districts. Overlay districts and other code conditions (lot size, floor-area ratio, height) are not modeled.
- **Gross and net counts:** the duplex and triplex counts in 5.3 to 5.7 are gross. Demolitions are subtracted only in the citywide count (5.9).
- **Recorded unit counts:** new-construction units are taken as the city recorded them except where 3.9 lists a correction. A description that does not state a unit count cannot be checked.
- **Assessor snapshots are yearly** and describe parcels, not buildings. A parcel with several buildings is counted as a whole, and the 20 parcels with no assessor record rely on the permit's occupancy code.
- **ADU removals are not tracked**, so "net with ADUs" counts ADUs created only.
- **The data is live.** Re-running the pull later will give slightly different counts, and permit statuses change. The city can also change the layer's schema without notice (see 3.8).
