"""Reproduce every figure in README.md from data/raw + data/manual.

Run after pull_permits.py and pull_zoning.py. Writes data/derived/*.csv and
prints each table. No network access is needed.

Usage:  python scripts/analyze.py
"""
import collections
import csv
import datetime as dt
import re

import classify

DER = classify.ROOT / "data" / "derived"

UNITS_ADDED = {"New duplex": 2, "New triplex": 3, "SFD to duplex": 1,
               "Duplex to triplex": 1, "SFD to triplex": 2}
TRIPLEX_CATS = {"New triplex", "Duplex to triplex", "SFD to triplex"}
# Pre-2040 zoning code: "Duplexes are first allowed in the R2 District and triplexes
# are first allowed in the R3 District" (CPED staff report, Oct 7 2019).
NEWLY_ALLOWED = {"duplex": {"R1", "R1A"}, "triplex": {"R1", "R1A", "R2", "R2B"}}

STRONG = re.compile(
    r"CONVER\w*.{0,60}?\b(TO|INTO)\b\s+(A\s+)?(DUPLEX|DUPEX|DUPELX|TRIPLEX|TWO.?FAMILY|TFD|SFD|SINGLE.?FAMILY)"
    r"|\b(SFD|SINGLE.?FAMILY\w*)\b.{0,25}?\b(TO|INTO)\b.{0,12}?(DUPLEX|TWO.?FAMILY|TFD|TRIPLEX)"
    r"|\b(DUPLEX|TWO.?FAMILY\w*|TFD)\b.{0,25}?\b(TO|INTO)\b.{0,12}?(SFD|SINGLE.?FAMILY|TRIPLEX)"
    r"|\b(ADD\w*|NEW|CREATE\w*)\b.{0,30}?\b(SECOND|2ND|THIRD|3RD)\b.{0,12}?(DWELLING|UNIT)",
    re.S)


def write(name, rows, cols):
    with open(DER / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def table(title, header, rows):
    print(f"\n## {title}")
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")


def main():
    DER.mkdir(parents=True, exist_ok=True)
    rec = classify.records()
    zones = {r["permitNumber"]: r for r in csv.DictReader(open(classify.RAW / "zoning_point_lookups.csv", encoding="utf-8"))}

    # ---- Classified duplex/triplex permits -------------------------------------------------
    out = []
    for cat, rows in rec["plex"].items():
        kind = "triplex" if cat in TRIPLEX_CATS else "duplex"
        for r in rows:
            z = zones.get(r["permitNumber"])
            if z is None:
                raise SystemExit(f"No zoning lookup for {r['permitNumber']}; rerun pull_zoning.py")
            out.append({
                "permitNumber": r["permitNumber"], "category": cat, "Display": r["Display"],
                "status": r["status"], "occupancyType": r["occupancyType"], "workType": r["workType"],
                "issueDate_utc": dt.datetime.fromtimestamp(r["issueDate"] / 1000, dt.timezone.utc).date().isoformat(),
                "year": classify.year(r), "units_added": UNITS_ADDED[cat],
                "zone_2017": z["zone_2017"], "zone_2023": z["zone_2023"],
                "coord_source": z["coord_source"],
                "newly_allowed": z["zone_2017"] in NEWLY_ALLOWED[kind],
            })
    write("classified_plex_permits.csv", out, list(out[0].keys()))

    cats = list(rec["plex"].keys())
    summ = []
    for c in cats:
        rs = [r for r in out if r["category"] == c]
        nw = [r for r in rs if r["newly_allowed"]]
        summ.append([c, len(rs), sum(r["units_added"] for r in rs), len(nw), sum(r["units_added"] for r in nw)])
    summ.append(["Total", *[sum(s[i] for s in summ) for i in range(1, 5)]])
    write("summary_plex_by_category.csv",
          [dict(zip(["category", "permits", "units_added", "permits_newly_allowed", "units_newly_allowed"], s)) for s in summ],
          ["category", "permits", "units_added", "permits_newly_allowed", "units_newly_allowed"])
    table("Duplex/triplex permits by category (2020-01-01 to pull date)",
          ["Category", "Permits", "Units added (gross)", "Permits in newly-allowed zones", "Units in newly-allowed zones"], summ)

    years = sorted({r["year"] for r in out})
    by_year = []
    for y in years:
        row = {"year": y}
        for c in cats:
            rs = [r for r in out if r["category"] == c and r["year"] == y]
            row[f"{c} total"] = len(rs)
            row[f"{c} newly_allowed"] = sum(r["newly_allowed"] for r in rs)
        by_year.append(row)
    write("summary_plex_by_year.csv", by_year, list(by_year[0].keys()))
    conv = ["SFD to duplex", "Duplex to triplex", "SFD to triplex"]
    table("Permits by year (newly allowed / total)", ["Year", "New duplex", "New triplex", "Conversions"],
          [[b["year"], f"{b['New duplex newly_allowed']} of {b['New duplex total']}",
            f"{b['New triplex newly_allowed']} of {b['New triplex total']}",
            f"{sum(b[c + ' newly_allowed'] for c in conv)} of {sum(b[c + ' total'] for c in conv)}"] for b in by_year])

    zc = collections.Counter((r["category"], r["zone_2017"]) for r in out)
    table("2017 zoning district of each permit", ["Category", "2017 zone", "Permits"],
          [[c, z, n] for (c, z), n in sorted(zc.items())])
    changed = [r for r in out if r["zone_2017"] != r["zone_2023"]]
    table("Permits whose zone differs between the 2017 and 2023 maps", ["Permit", "Address", "Category", "2017", "2023"],
          [[r["permitNumber"], r["Display"], r["category"], r["zone_2017"], r["zone_2023"]] for r in changed])

    # ---- De-conversions -----------------------------------------------------------------
    dc = [{"permitNumber": r["permitNumber"], "Display": r["Display"], "category": cat, "status": r["status"],
           "year": classify.year(r), "counted": counted,
           "units_lost": classify.DECONVERSION_CATS[cat] if counted == "yes" else 0}
          for r, counted, cat in rec["deconversions"]]
    write("deconversions.csv", dc, ["permitNumber", "Display", "category", "status", "year", "counted", "units_lost"])
    dcs = collections.Counter((d["category"], d["counted"]) for d in dc)
    table("De-conversion permits (units removed from 2- and 3-unit buildings)",
          ["Category", "Physical (counted)", "Records/legalization only", "Units lost (counted)"],
          [[c, dcs[(c, "yes")], dcs[(c, "record_only")],
            sum(d["units_lost"] for d in dc if d["category"] == c)] for c in classify.DECONVERSION_CATS]
          + [["Total", sum(v for (c, k), v in dcs.items() if k == "yes"),
              sum(v for (c, k), v in dcs.items() if k == "record_only"), sum(d["units_lost"] for d in dc)]])

    # ---- New single-family homes ----------------------------------------------------------
    sfd_years = collections.Counter(classify.year(r) for r in rec["new_sfd"])
    plex_years = {y: (sum(1 for r in out if r["category"] == "New duplex" and r["year"] == y),
                      sum(1 for r in out if r["category"] == "New triplex" and r["year"] == y)) for y in years}
    rows = [[y, sfd_years.get(y, 0), *plex_years.get(y, (0, 0))] for y in sorted(set(sfd_years) | set(years))]
    rows.append(["Total", sum(sfd_years.values()), sum(p[0] for p in plex_years.values()), sum(p[1] for p in plex_years.values())])
    write("summary_new_construction_by_year.csv",
          [dict(zip(["year", "new_sfd", "new_duplex", "new_triplex"], r)) for r in rows],
          ["year", "new_sfd", "new_duplex", "new_triplex"])
    table("New construction permits by year", ["Year", "New single-family", "New duplex", "New triplex"], rows)
    sfd_adu = sum(bool(re.search(r"\bADU\b|ACCESSORY DWELLING", (r["comments"] or "").upper())) for r in rec["new_sfd"])
    sfd_zero = sum(r["dwellingUnitsNew"] == 0 for r in rec["new_sfd"])
    print(f"\nNew SFD permits mentioning an ADU: {sfd_adu}; new SFD permits with dwellingUnitsNew = 0: {sfd_zero}")

    # ---- Raw-data quality checks quoted in README -------------------------------------------
    raw_new = rec["new_raw_rows"]
    nd2 = [r for r in raw_new if r["dwellingUnitsNew"] == 2]
    nd3 = [r for r in raw_new if r["dwellingUnitsNew"] == 3]
    print(f"\nRaw rows workType=New & dwellingUnitsNew=2: {len(nd2)} rows, {len({r['permitNumber'] for r in nd2})} distinct permits")
    print(f"Raw rows workType=New & dwellingUnitsNew=3: {len(nd3)} rows, {len({r['permitNumber'] for r in nd3})} distinct permits")
    print("  occupancyType of those =2 rows:", dict(collections.Counter(r["occupancyType"] for r in nd2)))
    print("  occupancyType of those =3 rows:", dict(collections.Counter(r["occupancyType"] for r in nd3)))

    # ---- Candidates the manual review has not classified -----------------------------------
    reviewed = {m["permitNumber"] for m in rec["manual"]}
    cands = classify.dedupe(classify.load("permits_conversion_candidates"))
    unrev = [r for r in cands.values()
             if r["permitNumber"] not in reviewed and r["status"] not in classify.INACTIVE
             and STRONG.search((r["comments"] or "").upper())]
    write("unreviewed_conversion_candidates.csv",
          [{"permitNumber": r["permitNumber"], "Display": r["Display"], "permitType": r["permitType"],
            "workType": r["workType"], "status": r["status"], "year": classify.year(r),
            "comments": (r["comments"] or "")[:300]} for r in unrev],
          ["permitNumber", "Display", "permitType", "workType", "status", "year", "comments"])
    print(f"\nActive candidates whose description matches a conversion phrase but are NOT in the manual "
          f"classification: {len(unrev)} (see data/derived/unreviewed_conversion_candidates.csv)")


if __name__ == "__main__":
    main()
