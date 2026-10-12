# Minneapolis 2040 Plan: duplex and triplex permits, 2020 to 2026

How many duplexes and triplexes have been permitted in Minneapolis since the Minneapolis 2040
Comprehensive Plan legalized them citywide, how many of those were in areas where they were
previously banned, and how that compares with new single-family homes over the same period.

All figures below are reproduced by `scripts/analyze.py` from the files in `data/`.
The raw data was pulled on **2026-09-28 21:02 UTC**. The source permit layer had last been edited at
2026-09-28 20:02 UTC, and the newest permit in the pull was issued 2026-09-24.

---

## 1. Scope of the data

| Item | Coverage |
|---|---|
| Geography | City of Minneapolis only |
| Time | Permits issued **2020-01-01** (the day the 2040 Plan's zoning changes took effect) through the pull date. Years are calendar years of `issueDate` in UTC. |
| Building types in scope | 2-unit and 3-unit residential buildings (duplexes, triplexes, 2- and 3-unit townhouse buildings). Fourplexes and larger are out of scope. New single-family homes are included only for comparison. |
| Metric | **Building permits pulled** (issued), for new construction or for conversion of an existing building. A permit is not proof that the building was completed. |
| Excluded | Permits with status `Cancelled` or `Expired`. Trade-only permits (plumbing, mechanical, electrical). ADUs are not counted as duplexes: the city treats an ADU as accessory to a single-family home. |
| Permit source | City of Minneapolis Construction Code Services permits, ArcGIS feature layer `CCS_Permits` ([open data page](https://opendata.minneapolismn.gov/datasets/cityoflakes::ccs-permits)). |
| Zoning source | City of Minneapolis primary zoning layers on the city's ArcGIS Online organization: `msvcCPED_PrimaryZoning_20170126` (map as of 2017-01-26, before the 2040 Plan) and `PrimaryZoningArchive` (map archived 2023-06-30). |
| Rule source | City of Minneapolis CPED staff report and draft ordinance for the City Planning Commission, Oct 7 2019: "Duplexes are first allowed in the R2 District and triplexes are first allowed in the R3 District." ([PDF](https://www2.minneapolismn.gov/media/content-assets/www2-documents/business/Staff-report-and-draft-ordinance-prepared-for-the-City-Planning-Commission-(October-7,-2019),wcmsp-220995.pdf)) |
| Not pulled | Applicant names and addresses exist in the source layer but were deliberately left out. |

---

## 2. Repository layout

```
scripts/
  arcgis.py         ArcGIS REST helpers (stdlib only): query with paging, counts, point-in-zone, geocode
  pull_permits.py   pulls the three raw permit sets into data/raw/
  pull_zoning.py    looks up the 2017 and 2023 zoning district at every duplex/triplex permit
  classify.py       the selection rules shared by pull_zoning.py and analyze.py
  analyze.py        produces every table in this README (writes data/derived/, prints markdown)
  run_all.py        runs pull_permits -> pull_zoning -> analyze
  sample.py         pull arbitrary samples from the live sources to validate the method
data/
  raw/              exactly what the pull scripts wrote (JSON is canonical; CSV is the same rows flattened)
    permits_new_construction.{json,csv}        874 rows: every workType='New' permit issued 2020-01-01 or later
    permits_conversion_candidates.{json,csv}   827 rows: keyword/work-type search for conversions (query in manifest)
    permits_manually_classified.{json,csv}     167 rows: every permit named in the manual classification file
    pull_manifest_permits.json                 exact SQL where-clauses, row counts, pull time, source edit time
    zoning_point_lookups.csv                   173 rows: coordinates used and zone on each map, per permit
  manual/
    conversion_classification.csv             157 permits classified by reading their descriptions (see 3.4)
  derived/          outputs of analyze.py
```

Requirements: Python 3.9 or newer. No third-party packages are needed.

---

## 3. Methodology

### 3.1 Pulling permits (`pull_permits.py`)
Three queries are sent to the `CCS_Permits` layer. The exact SQL text of each is saved in
`data/raw/pull_manifest_permits.json`.

1. **New construction:** `workType = 'New' AND issueDate >= DATE '2020-01-01'`
2. **Conversion candidates:** non-new `Res` or `Commercial` permits issued 2020-01-01 or later where any of these is true:
   - the work type is `Conversion` or `UnitCon`;
   - the description contains CONVER or LEGALIZ together with a building-type word (DUPLEX and its common misspellings, TRIPLEX, TWO%FAMILY, TFD, SFD, SINGLE%FAMILY, THREE%FAMILY);
   - the description contains a unit phrase such as THIRD%UNIT, 3RD DWELLING, SECOND DWELLING or INTO%DUPLEX.
3. **Manually classified permits:** every permit number listed in `data/manual/conversion_classification.csv`. This guarantees the source record behind every manual decision is in the repo, even when the keyword search in query 2 did not find it.

Each query is paged in OBJECTID order. The script aborts if the number of rows pulled differs from the server's count.

### 3.2 Automatic selection rules (`classify.py`)
- **Duplicate rows:** the source layer sometimes holds more than one row per permit number. Each permit counts once, using the row with the lowest OBJECTID.
- **New duplex:** a new-construction permit with `occupancyType` of `TFD` (two-family dwelling) or `TH` (townhouse), `dwellingUnitsNew = 2`, and a status other than Cancelled or Expired. Three more permits are added from the manual file: two new duplexes whose unit fields are coded 0, and one coded as 3 units whose description is a duplex plus an ADU.
- **New triplex:** a new-construction permit with `occupancyType = '3to4'` (the city's code for 3- and 4-unit buildings), `dwellingUnitsNew = 3`, and an active status. One more is added from the manual file: a three-unit townhouse building coded as `Comm`.
- **Excluded two- and three-unit new permits:** mixed-use and commercial projects (`Mixed`, `Comm`, and one `3to4` record that is really a triplex-to-duplex change) are left out. `analyze.py` prints how many raw rows fall under each occupancy code, so the exclusions can be checked.
- **New single-family home:** a new-construction permit with `occupancyType = 'SFD'`, excluding Cancelled permits, minus one permit that only finishes a house started under an earlier permit.

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
For each counted duplex or triplex permit, the permit's own `Latitude`/`Longitude` is sent to the city's zoning
layers as an ArcGIS point-intersect query. The district is recorded on two maps:
- the **2017 map** (`msvcCPED_PrimaryZoning_20170126`), used to decide what was allowed before the plan;
- the **2023 map** (`PrimaryZoningArchive`), used only to flag sites rezoned after 2017.

Three permits had no coordinates. Their addresses were geocoded with the Esri World Geocoder, and the matched
address and score are kept in `zoning_point_lookups.csv`. All three matched their street address exactly (scores 99.87, 100 and 100).

**Newly allowed** is defined from the CPED staff report's statement of the pre-2040 rules:
- a **duplex** (new build or conversion) is newly allowed if the 2017 district is **R1 or R1A**;
- a **triplex** (new build or conversion) is newly allowed if the 2017 district is **R1, R1A, R2 or R2B**.

### 3.6 Units
Units are gross units added by the permit: new duplex = 2, new triplex = 3, SFD to duplex = +1,
duplex to triplex = +1, SFD to triplex = +2. Demolitions are not subtracted (see 5.3 and 6).

### 3.7 How the scripts were tested
The workspace that wrote these scripts could not reach the city's ArcGIS servers, but a web browser on the
analyst's linked Windows PC could. The scripts were therefore run **unchanged** in CPython 3.12 (Pyodide 0.26.4)
inside that browser:
1. The eight files were copied into the browser runtime and SHA-256-checked against these copies. All matched.
2. `run_all.py` was run from an empty `data/raw` and `data/derived`.
3. All four `sample.py` commands were run. `verify` re-queried 12 random permits live, and all 12 matched.

The only test-harness change was a shim that routes Python's `urllib.request.urlopen` through the browser's
HTTP stack, sending POST bodies exactly as CPython does.

4. The raw JSON and zoning lookups were then copied out of the browser (SHA-256 verified). The raw CSVs and
   everything in `data/derived/` were regenerated with **native CPython 3.11 on Linux** using the same scripts.
   All 14 data files are byte-identical to the browser run.

What has **not** been exercised is the network pull (`pull_permits.py`, `pull_zoning.py`, `sample.py`) under a
native desktop Python with direct network access. If one fails there, the cause will be in `arcgis._post`,
which is 15 lines of standard `urllib`.

---

## 4. Validating the method yourself

```bash
cd mpls-mfh-analysis
python3 scripts/run_all.py          # re-pulls everything (~1 minute) and prints every table below
```

Live counts change daily as permits are issued and statuses change. Expect small differences from the
tables here, mostly in 2026.

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
```

**Without Python:** paste a query URL into a browser. For example, this returns the number of new
two-family permits since 2020:

```
https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/CCS_Permits/FeatureServer/0/query?where=workType%3D%27New%27+AND+occupancyType%3D%27TFD%27+AND+issueDate+%3E%3D+DATE+%272020-01-01%27&returnCountOnly=true&f=json
```

Replace `returnCountOnly=true` with `outFields=permitNumber,Display,status,dwellingUnitsNew,comments` to see the rows.

**To audit the manual classification**, pick any rows from `data/manual/conversion_classification.csv`,
find the same `permitNumber` in `data/raw/permits_manually_classified.csv`, and read its `comments`.
The `note` column says why it was classified the way it was.

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
| New duplex | 82 | 164 |
| New triplex | 28 | 84 |
| SFD to duplex | 42 | 42 |
| Duplex to triplex | 20 | 20 |
| SFD to triplex | 1 | 2 |
| **Total** | **173** | **312** |

Of the 82 new duplex permits, 20 also record an eliminated unit, usually a demolished house on the same lot.
Those 20 add a net of 1 unit each, not 2. None of the new triplex permits record an eliminated unit.

### 5.4 New duplexes and triplexes by year

| Year | New duplex | New triplex |
|---|---|---|
| 2020 | 14 | 4 |
| 2021 | 14 | 5 |
| 2022 | 7 | 8 |
| 2023 | 12 | 9 |
| 2024 | 11 | 0 |
| 2025 | 18 | 2 |
| 2026 (to Sept 24) | 6 | 0 |
| **Total** | **82** | **28** |

No new triplexes were permitted in 2024, the year after the court order in 5.1, and only 2 have been permitted since.

### 5.5 Conversions versus de-conversions

| Direction | Physical permits | Units |
|---|---|---|
| Conversions: SFD to duplex (42), duplex to triplex (20), SFD to triplex (1) | 63 | +64 |
| De-conversions: duplex to SFD (41), triplex to duplex (1), triplex to SFD (1) | 43 | −44 |
| Records-only de-conversions (no physical change) | 7 | 0 |
| Paper conversions to duplex: legalizations, reconversions, ADU re-designation | 6 | 0 |

Physical permits by year:

| Year | Conversions (units added) | De-conversions (units removed) |
|---|---|---|
| 2020 | 13 | 3 |
| 2021 | 9 | 6 |
| 2022 | 15 | 6 |
| 2023 | 8 | 5 |
| 2024 | 6 | 3 |
| 2025 | 8 | 12 |
| 2026 (to Sept 24) | 4 | 8 |

Across the whole period, de-conversions removed about two-thirds as many units as conversions added. In 2025 and 2026 there were more de-conversions than conversions.

### 5.6 How many permits were in areas where the building type was previously banned

| Category | Permits | In newly allowed zone | Share | Units in newly allowed zones |
|---|---|---|---|---|
| New duplex | 82 | 40 | 49% | 80 |
| New triplex | 28 | 25 | 89% | 75 |
| SFD to duplex | 42 | 14 | 33% | 14 |
| Duplex to triplex | 20 | 18 | 90% | 18 |
| SFD to triplex | 1 | 1 | 100% | 2 |
| **Total** | **173** | **98** | **57%** | **189** |

By year (newly allowed permits / all permits in the category):

| Year | New duplex | New triplex | Conversions |
|---|---|---|---|
| 2020 | 11 of 14 | 3 of 4 | 6 of 13 |
| 2021 | 7 of 14 | 5 of 5 | 6 of 9 |
| 2022 | 2 of 7 | 7 of 8 | 8 of 15 |
| 2023 | 4 of 12 | 9 of 9 | 4 of 8 |
| 2024 | 5 of 11 | 0 of 0 | 4 of 6 |
| 2025 | 9 of 18 | 1 of 2 | 4 of 8 |
| 2026 (to Sept 24) | 2 of 6 | 0 of 0 | 1 of 4 |

2017 zoning districts of the counted permits:

| Category | R1 | R1A | R2 | R2B | R3 | R4 | R5 | OR1 | C1 |
|---|---|---|---|---|---|---|---|---|---|
| New duplex | 4 | 36 |  | 38 |  | 3 | 1 |  |  |
| New triplex | 1 | 13 |  | 11 |  |  | 2 | 1 |  |
| SFD to duplex | 4 | 10 | 1 | 22 | 1 | 1 | 2 |  | 1 |
| Duplex to triplex | 1 | 3 |  | 14 |  |  | 2 |  |  |
| SFD to triplex |  | 1 |  |  |  |  |  |  |  |

Sites whose zone differs between the 2017 and 2023 maps: 1800 and 1806 Como Ave SE (R2B to R4, new duplexes),
4600 36th Ave S (R1A to R2B, new duplex), 2318 Johnson St NE and 405 31st St E (R1A to R4, new triplexes).
The two triplex sites were probably rezoned for those projects. Counting them as not caused by the plan lowers
the total to **96 of 173**.

Readings:
- Triplexes depend almost entirely on the plan: 44 of 49 triplex permits (new builds and conversions) are in zones that banned them before.
- Most duplex activity was already legal. About half of new duplexes and two-thirds of SFD-to-duplex conversions are in R2B or denser zones.
- Only 54 duplex permits (40 new, 14 conversions) are on formerly single-family-only land, adding 94 units gross.

### 5.7 New single-family homes, same period

| Year | New single-family | New duplex | New triplex |
|---|---|---|---|
| 2020 | 71 | 14 | 4 |
| 2021 | 64 | 14 | 5 |
| 2022 | 55 | 7 | 8 |
| 2023 | 74 | 12 | 9 |
| 2024 | 60 | 11 | 0 |
| 2025 | 57 | 18 | 2 |
| 2026 (to Sept 24) | 31 | 6 | 0 |
| **Total** | **412** | **82** | **28** |

- By building, new single-family homes outnumber new duplexes and triplexes combined about 3.7 to 1.
- By unit, the comparison is 412 single-family units vs 248 duplex and triplex units.
- 7 single-family permit descriptions mention an ADU. Six build a new ADU, and one (5615 Penn Ave S) turns an existing alley house into the ADU.
- 4 single-family permits have no description and `dwellingUnitsNew = 0`. They are kept because their codes say new single-family construction.

---

## 6. Limitations
- **Permits are not completions.** Some permits are still `Issued` or `Open`: 19 and 3 of the new duplexes, 6 of the new triplexes.
- **Conversion counts depend on permit descriptions.** A conversion described in words the searches don't match would be missed. The completeness screen reduces this risk but does not rule it out.
- **The pre-plan map is from January 2017,** three years before the rules changed. Only 5 of 173 permit sites differ from the 2023 map, but rezonings between 2017 and 2019 are not captured directly.
- **Nonconforming uses:** a duplex-to-triplex conversion in R1 or R1A (4 permits) started from an existing duplex that predates the old rules.
- **Scope of the zoning rule:** it is based on the primary residential districts. Overlay districts and other code conditions (lot size, floor-area ratio, height) are not modeled.
- **Demolitions are not netted out** of the gross unit counts, apart from the note in 5.3.
- **The data is live.** Re-running the pull later will give slightly different counts, and permit statuses change.
