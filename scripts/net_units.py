"""Count the dwelling units added and removed by permits in the observation window, and the net gain.

Run after pull_permits.py and pull_assessor.py. Reads data/raw/ and data/manual/, writes
data/derived/net_units_*.csv and demolitions_by_parcel.csv, and prints each table. No network
access is needed.

Units added
  new construction    dwellingUnitsNew on every active new-construction permit. Re-issued
                      duplicates are dropped, and miscoded counts are replaced, as listed in
                      data/manual/unit_change_review.csv
  existing buildings  units added to existing buildings, from the reviewed descriptions in
                      unit_change_review.csv (office/warehouse/hotel/church conversions,
                      additions, units added to apartment buildings)
  1-3 unit conversions  single-family to duplex, duplex to triplex, single-family to triplex,
                      from data/manual/conversion_classification.csv
  ADUs                reported separately; the city records an ADU as 0 dwelling units

Units removed
  demolitions         every active Wrecking permit, counted once per parcel, using the units the
                      City Assessor recorded on the parcel before demolition (see units_on_parcel)
  de-conversions      duplex or triplex to fewer units, from conversion_classification.csv
  other               units converted to non-residential use or combined, from unit_change_review.csv

Usage:  python scripts/net_units.py
"""
import collections
import csv
import json
import re

import classify

DER = classify.ROOT / "data" / "derived"
MANUAL = classify.ROOT / "data" / "manual"

PLEX_ADDED = {"sfd_to_duplex": 1, "duplex_to_triplex": 1, "sfd_to_triplex": 2}
# Units assumed for a demolition with no assessor record, from the permit's occupancy code.
# Every other code (Comm, Accessory, Mixed, MFD without a stated count) defaults to 0 and
# needs a demolition_review.csv entry if it removed units.
OCC_UNITS = {"SFD": 1, "TFD": 2, "3to4": 3}
UNIT_TYPE = re.compile(r"\bRES(?:IDENTIAL)?\s*(\d+)\s*UNITS?\b")
FIRST_SNAPSHOT, LAST_SNAPSHOT = 2017, 2026


def active(r):
    return r["status"] not in classify.INACTIVE


def read_csv(name):
    return list(csv.DictReader(open(MANUAL / name, encoding="utf-8")))


def units_on_parcel(year, records):
    """Dwelling units on a parcel in one assessor snapshot, or None if it shows no building.

    2017-2024 snapshots: TOTAL_UNITS, summed over the parcel's records; a record with 0 units
    falls back to a "RESIDENTIAL n UNIT(S)" property type.
    2025-2026 snapshots: TOTALUNITS is 0 for 1-3 unit residential, so the parcel-level property
    type "RESIDENTIAL n UNIT(S)" is used when present, counted once per parcel; otherwise
    TOTALUNITS is summed.
    """
    recs = [r for r in records if not ("VACANT" in (r["propertyType"] or "").upper() and not r["buildingUse"])]
    if not any(r["buildingUse"] or int(r["units"] or 0) for r in recs):
        return None
    if year >= 2025:
        typed = [int(m.group(1)) for r in recs for m in [UNIT_TYPE.search((r["propertyType"] or "").upper())] if m]
        return max(typed) if typed else sum(int(r["units"] or 0) for r in recs)
    total = 0
    for r in recs:
        n = int(r["units"] or 0)
        if n == 0:
            m = UNIT_TYPE.search((r["propertyType"] or "").upper())
            n = int(m.group(1)) if m else 0
        total += n
    return total


def assessor_units(permit, apns, assessor):
    """(parcel id, snapshot year, units) from the latest snapshot at or before the permit year that
    shows a building. A permit can carry several parcel ids; the one with the most units is used."""
    best = None
    for apn in apns:
        snaps = assessor.get(apn, {})
        for y in range(min(classify.year(permit), LAST_SNAPSHOT), FIRST_SNAPSHOT - 1, -1):
            u = units_on_parcel(y, snaps[str(y)]) if str(y) in snaps else None
            if u is not None:
                if best is None or u > best[2]:
                    best = (apn, y, u)
                break
    return best


def demolitions(assessor, review):
    """One row per demolished parcel."""
    rows_of = classify.rows_by_permit("permits_wrecking")
    wrecks = [rs[0] for rs in rows_of.values() if active(rs[0])]
    unknown = sorted(set(review) - {r["permitNumber"] for r in wrecks})
    if unknown:
        raise SystemExit(f"demolition_review.csv names permits that are not active demolitions: {unknown}")
    parcels = collections.defaultdict(list)
    for r in wrecks:
        apns = sorted({x["APN"].strip() for x in rows_of[r["permitNumber"]] if x["APN"] and x["APN"].strip()})
        pick = assessor_units(r, apns, assessor)
        key = pick[0] if pick else (apns[0] if apns else r["permitNumber"])
        parcels[key].append((r, pick))
    rows = []
    for key, items in parcels.items():
        items = sorted(items, key=lambda x: (x[0]["issueDate"], x[0]["permitNumber"]))
        rs = [r for r, _ in items]
        found = [(r, p) for r, p in items if p]
        fallback = sum(int(review[r["permitNumber"]]["units"]) if r["permitNumber"] in review
                       else OCC_UNITS.get(r["occupancyType"], 0) for r in rs)
        if any(review.get(r["permitNumber"], {}).get("decision") == "exclude" for r in rs):
            units, source, snap = 0, "excluded", ""
        elif found:
            r0, (_, snap, units) = max(found, key=lambda x: x[1][2])
            source = "assessor, permit year" if snap == classify.year(r0) else "assessor, earlier snapshot"
        else:
            units, source, snap = fallback, "permit", ""
        coded = sum(OCC_UNITS.get(r["occupancyType"], 0) for r in rs)
        rows.append({
            "parcel": key, "permits": " ".join(r["permitNumber"] for r in rs), "Display": rs[0]["Display"],
            "year": classify.year(rs[0]), "occupancyType": " ".join(sorted({r["occupancyType"] or "" for r in rs})),
            "units_by_permit_code": coded, "assessor_snapshot": snap, "units_removed": units, "source": source,
            "note": "; ".join(review[r["permitNumber"]]["note"] for r in rs if r["permitNumber"] in review),
        })
    return sorted(rows, key=lambda x: (x["year"], x["Display"] or ""))


def size_class(u):
    return "0 (no dwelling)" if u == 0 else "1 unit" if u == 1 else "2 units" if u == 2 else \
        "3 units" if u == 3 else "4+ units"


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
        print("| " + " | ".join([str(r[0])] + [f"{x:,}" if isinstance(x, int) else str(x) for x in r[1:]]) + " |")


def main():
    DER.mkdir(parents=True, exist_ok=True)
    new = classify.dedupe(classify.load("permits_new_construction"))
    changes = classify.dedupe(classify.load("permits_unit_changes"))
    adus = classify.dedupe(classify.load("permits_adu_mentions"))
    ref = classify.dedupe(classify.load("permits_manually_classified") + list(changes.values())
                          + list(adus.values()) + list(new.values()))
    conv = [m for m in classify.manual() if m["counted"] == "yes"
            and (m["category"] in PLEX_ADDED or m["category"] in classify.DECONVERSION_CATS)]
    conv_ids = {m["permitNumber"] for m in conv}
    review = {m["permitNumber"]: m for m in read_csv("unit_change_review.csv")}
    demo_review = {m["permitNumber"]: m for m in read_csv("demolition_review.csv")}

    # Completeness: every permit in the two review universes is decided exactly once.
    universe = set(changes) | set(adus)
    missing = sorted(universe - conv_ids - set(review))
    if missing:
        raise SystemExit(f"Permits not yet reviewed (add them to unit_change_review.csv): {missing}")
    both = sorted(conv_ids & set(review))
    if both:
        raise SystemExit(f"Permits counted in both manual files: {both}")
    absent = sorted(set(review) - set(ref))
    if absent:
        raise SystemExit(f"Reviewed permits missing from raw pulls: {absent}")

    decisions = {"added", "removed", "adu", "not counted", "duplicate", "new construction"}
    bad = sorted(p for p, m in review.items() if m["decision"] not in decisions)
    if bad:
        raise SystemExit(f"Unknown decision in unit_change_review.csv for: {bad}")

    ev = []  # (category, side, permit, units)
    for p, r in new.items():
        m = review.get(p)
        if not active(r) or (m and m["decision"] == "duplicate"):
            continue
        u = int(m["units_added"]) if m and m["units_added"] != "" else (r["dwellingUnitsNew"] or 0)
        if u > 0:
            ev.append(("New construction", "added", r, u))
    for p, m in review.items():
        r = ref[p]
        if not active(r) or m["decision"] == "duplicate":
            continue
        if int(m["adus"] or 0):
            ev.append(("ADUs", "adu", r, int(m["adus"])))
        if p in new:
            continue  # units already taken above
        if int(m["units_added"] or 0):
            ev.append(("Units added to existing buildings", "added", r, int(m["units_added"])))
        if int(m["units_removed"] or 0):
            ev.append(("Units converted to other uses or combined", "removed", r, int(m["units_removed"])))
    for m in conv:
        r = ref[m["permitNumber"]]
        if not active(r):
            continue
        if m["category"] in PLEX_ADDED:
            ev.append(("Conversions of 1-3 unit buildings", "added", r, PLEX_ADDED[m["category"]]))
        else:
            ev.append(("De-conversions (duplex or triplex to fewer units)", "removed", r,
                       classify.DECONVERSION_CATS[m["category"]]))

    assessor = json.loads((classify.RAW / "assessor_demolished_parcels.json").read_text(encoding="utf-8"))
    demo = demolitions(assessor, demo_review)
    write("demolitions_by_parcel.csv", demo, list(demo[0].keys()))

    # ---- Units added and removed, by source -------------------------------------------------
    def summarize(side):
        out = collections.OrderedDict()
        for cat, s, r, u in ev:
            if s == side:
                n, t = out.get(cat, (0, 0))
                out[cat] = (n + (u > 0), t + u)
        return out

    added, removed, adu = summarize("added"), summarize("removed"), summarize("adu")
    demo_units = sum(d["units_removed"] for d in demo)
    demo_parcels = sum(d["units_removed"] > 0 for d in demo)
    rows_a = [[c, n, u] for c, (n, u) in added.items()]
    rows_a.append(["Total dwelling units added", sum(r[1] for r in rows_a), sum(r[2] for r in rows_a)])
    rows_a += [[c, n, u] for c, (n, u) in adu.items()]
    rows_r = [["Demolitions (parcels with units)", demo_parcels, demo_units]] + [[c, n, u] for c, (n, u) in removed.items()]
    rows_r.append(["Total dwelling units removed", sum(r[1] for r in rows_r), sum(r[2] for r in rows_r)])
    table("Units added", ["Source", "Permits", "Units"], rows_a)
    table("Units removed", ["Source", "Permits or parcels", "Units"], rows_r)
    write("net_units_by_source.csv",
          [dict(zip(["side", "source", "permits", "units"], ["added"] + r)) for r in rows_a]
          + [dict(zip(["side", "source", "permits", "units"], ["removed"] + r)) for r in rows_r],
          ["side", "source", "permits", "units"])
    write("net_units_permits.csv",
          [{"permitNumber": r["permitNumber"], "Display": r["Display"], "category": c, "side": s,
            "year": classify.year(r), "units": u} for c, s, r, u in ev if u],
          ["permitNumber", "Display", "category", "side", "year", "units"])

    # ---- Net by year ----------------------------------------------------------------------------
    by = collections.defaultdict(collections.Counter)
    for c, s, r, u in ev:
        by[classify.year(r)][s] += u
    for d in demo:
        by[d["year"]]["removed"] += d["units_removed"]
    rows_y = []
    for y in sorted(by):
        a, rm, ad = by[y]["added"], by[y]["removed"], by[y]["adu"]
        rows_y.append([y, a, rm, a - rm, ad, a - rm + ad])
    rows_y.append(["Total", *[sum(r[i] for r in rows_y) for i in range(1, 6)]])
    table("Net units by year", ["Year", "Added", "Removed", "Net", "ADUs", "Net with ADUs"], rows_y)
    write("net_units_by_year.csv", [dict(zip(["year", "added", "removed", "net", "adus", "net_with_adus"], r))
                                    for r in rows_y], ["year", "added", "removed", "net", "adus", "net_with_adus"])

    # ---- Demolition detail ------------------------------------------------------------------------
    sizes = ["1 unit", "2 units", "3 units", "4+ units", "0 (no dwelling)"]
    rows_s = []
    for s in sizes:
        ds = [d for d in demo if size_class(d["units_removed"]) == s]
        rows_s.append([s, len(ds), sum(d["units_removed"] for d in ds)])
    rows_s.append(["Total", len(demo), demo_units])
    table("Demolished parcels by number of units removed", ["Units on parcel", "Parcels", "Units"], rows_s)

    years = sorted({d["year"] for d in demo})
    rows_dy = []
    for y in years:
        ds = [d for d in demo if d["year"] == y]
        rows_dy.append([y, len(ds), sum(len(d["permits"].split()) for d in ds),
                        *[sum(d["units_removed"] for d in ds if size_class(d["units_removed"]) == s) for s in sizes[:4]],
                        sum(d["units_removed"] for d in ds)])
    rows_dy.append(["Total", *[sum(r[i] for r in rows_dy) for i in range(1, 8)]])
    table("Demolitions by year", ["Year", "Parcels", "Permits", "Units in 1-unit", "in 2-unit", "in 3-unit",
                                  "in 4+ unit", "Units removed"], rows_dy)
    write("demolitions_by_year.csv",
          [dict(zip(["year", "parcels", "permits", "units_1", "units_2", "units_3", "units_4plus", "units"], r))
           for r in rows_dy], ["year", "parcels", "permits", "units_1", "units_2", "units_3", "units_4plus", "units"])

    src = collections.Counter(d["source"] for d in demo)
    srcu = collections.Counter()
    for d in demo:
        srcu[d["source"]] += d["units_removed"]
    table("Where each demolished parcel's unit count came from", ["Source", "Parcels", "Units"],
          [[s, src[s], srcu[s]] for s in ["assessor, permit year", "assessor, earlier snapshot", "permit", "excluded"]])
    cmp_ = [d for d in demo if d["source"].startswith("assessor")]
    table("Assessor count compared with the permit's occupancy code (parcels with an assessor record)",
          ["Comparison", "Parcels", "Units by permit code", "Units by assessor"],
          [[k, len(v), sum(d["units_by_permit_code"] for d in v), sum(d["units_removed"] for d in v)]
           for k, v in [("Same", [d for d in cmp_ if d["units_removed"] == d["units_by_permit_code"]]),
                        ("Assessor higher", [d for d in cmp_ if d["units_removed"] > d["units_by_permit_code"]]),
                        ("Assessor lower", [d for d in cmp_ if d["units_removed"] < d["units_by_permit_code"]])]])
    big = sorted([d for d in demo if d["units_removed"] >= 4], key=lambda d: (-d["units_removed"], d["Display"]))
    table("Demolished buildings with 4 or more units", ["Address", "Year", "Units", "Source"],
          [[d["Display"], str(d["year"]), d["units_removed"], d["source"]] for d in big])


if __name__ == "__main__":
    main()
