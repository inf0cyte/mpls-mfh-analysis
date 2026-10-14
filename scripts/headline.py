"""Headline figures: duplex and triplex units permitted where the 2040 Plan first allowed them,
the existing units removed from the same lots to build them, and their share of the city's net
housing growth.

Run after analyze.py and net_units.py. Reads data/derived/classified_plex_permits.csv,
data/derived/net_units_by_year.csv, data/derived/demolitions_by_parcel.csv, the raw new-construction,
manually classified and wrecking pulls, and data/manual/rezoned_sites.csv and
data/manual/same_lot_review.csv. Writes data/derived/headline_by_type.csv,
headline_by_year.csv and headline_same_lot.csv and prints each table.

A permit is plan-enabled when its site is in a zone that did not allow the building type before
the plan (see NEWLY_ALLOWED in analyze.py), unless the site was rezoned by an owner's application
(rezoned_sites.csv): either between the 2017 zoning map and the plan, so the building type was
already allowed, or after the plan through the same site-by-site route that existed before it.

Unit counts for each plan-enabled permit:
  units in the building    every unit the permit adds (new duplex 2, new triplex 3,
                           SFD to duplex 1, duplex to triplex 1, SFD to triplex 2)
  existing units removed   dwelling units that stood on the same lot and were removed on or after
  from the same lot        SINCE (2020-01-01) to make way for a new duplex or triplex. Conversions
                           keep the existing building, so they remove none.
                             - Wrecking permits: every active wrecking permit in the pull (all are
                               issued on or after SINCE) whose parcel id or address matches any row
                               of the new building's permit. Its units are the units_removed of its
                               parcel in demolitions_by_parcel.csv, counted once per parcel.
                             - Every plan-enabled new building with no matching wrecking permit
                               needs a row in same_lot_review.csv, which records from the assessor
                               snapshots and permit history whether a dwelling stood on the lot and
                               when it was removed. Units removed before SINCE are not subtracted.
  net units                units in the building minus existing units removed from the same lot

Each removal is subtracted in the year the duplex or triplex permit was issued.

Usage:  python scripts/headline.py
"""
import collections
import csv

import arcgis
import classify

DER = classify.ROOT / "data" / "derived"
MANUAL = classify.ROOT / "data" / "manual"
REZONED = MANUAL / "rezoned_sites.csv"
SAME_LOT = MANUAL / "same_lot_review.csv"
NEW_BUILDS = {"New duplex", "New triplex"}
TYPES = ["New duplex", "New triplex", "SFD to duplex", "Duplex to triplex", "SFD to triplex"]
SINCE_YEAR = int(arcgis.SINCE[:4])


def table(title, header, rows):
    print(f"\n## {title}")
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join([str(r[0])] + [f"{x:,}" if isinstance(x, int) else str(x) for x in r[1:]]) + " |")


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else ""


def read(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def removed_on_or_after_since(value):
    """`removed` in same_lot_review.csv is an ISO date (from a wrecking permit) or a year (from the
    assessor snapshots: the last year whose snapshot still shows the dwelling)."""
    value = value.strip()
    if len(value) == 4:
        return int(value) >= SINCE_YEAR
    return value >= arcgis.SINCE


def same_lot_removals(enabled):
    """{permitNumber: (units removed, source, wrecking permits, parcels, evidence, note)} for every
    plan-enabled new duplex or triplex."""
    new_rows = classify.rows_by_permit("permits_new_construction", "permits_manually_classified")
    wrecks = {p: rs for p, rs in classify.rows_by_permit("permits_wrecking").items()
              if rs[0]["status"] not in classify.INACTIVE}
    early = sorted(p for p, rs in wrecks.items() if classify.year(rs[0]) < SINCE_YEAR)
    if early:
        raise SystemExit(f"Wrecking permits issued before {arcgis.SINCE} in the pull: {early}")
    parcel_of, units_of = {}, {}
    for d in read(DER / "demolitions_by_parcel.csv"):
        units_of[d["parcel"]] = int(d["units_removed"])
        for p in d["permits"].split():
            parcel_of[p] = d["parcel"]
    review = {r["permitNumber"]: r for r in read(SAME_LOT)}

    out, matched, used = {}, set(), collections.defaultdict(list)
    for r in enabled:
        p = r["permitNumber"]
        rows = new_rows.get(p)
        if not rows:
            raise SystemExit(f"{p} is missing from the raw new-construction and manually classified pulls")
        apns = {x["APN"].strip() for x in rows if x["APN"] and x["APN"].strip()}
        addrs = {x["Display"].strip() for x in rows if x["Display"] and x["Display"].strip()}
        hits = sorted(w for w, ws in wrecks.items()
                      if any((x["APN"] or "").strip() in apns or (x["Display"] or "").strip() in addrs for x in ws))
        if hits:
            matched.add(p)
            parcels = sorted({parcel_of[w] for w in hits})
            for k in parcels:
                used[k].append(p)
            out[p] = (sum(units_of[k] for k in parcels), "wrecking permit", " ".join(hits), " ".join(parcels), "", "")
        elif p in review:
            m = review[p]
            u = int(m["units_removed"])
            if u and not m["removed"].strip():
                raise SystemExit(f"same_lot_review.csv: {p} removes units but has no removal date or year")
            counted = u if u and removed_on_or_after_since(m["removed"]) else 0
            out[p] = (counted, "same_lot_review.csv", "", "", m["evidence"], m["note"])
        else:
            raise SystemExit(f"{p} ({r['Display']}) has no matching wrecking permit and no row in "
                             f"same_lot_review.csv; check the assessor snapshots and add one")
    shared = {k: v for k, v in used.items() if len(v) > 1}
    if shared:
        raise SystemExit(f"Demolished parcels matched to more than one new building (split them in "
                         f"same_lot_review.csv): {shared}")
    stray = sorted(set(review) - ({r["permitNumber"] for r in enabled} - matched))
    if stray:
        raise SystemExit(f"same_lot_review.csv names permits that are not plan-enabled new buildings "
                         f"without a wrecking permit: {stray}")
    return out


def main():
    plex = read(DER / "classified_plex_permits.csv")
    rezoned = {r["permitNumber"]: r for r in read(REZONED)}
    known = {r["permitNumber"] for r in plex}
    missing = sorted(set(rezoned) - known)
    if missing:
        raise SystemExit(f"rezoned_sites.csv names permits that are not classified duplex/triplex permits: {missing}")
    newly = [r for r in plex if r["newly_allowed"] == "True"]
    enabled = [r for r in newly if r["permitNumber"] not in rezoned]
    excluded = [r for r in newly if r["permitNumber"] in rezoned]

    lots = same_lot_removals([r for r in enabled if r["category"] in NEW_BUILDS])

    def removed(r):
        return lots[r["permitNumber"]][0] if r["permitNumber"] in lots else 0

    with open(DER / "headline_same_lot.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["permitNumber", "Display", "category", "year", "units_in_building",
                    "existing_units_removed_same_lot", "net_units", "source", "wrecking_permits",
                    "demolished_parcels", "evidence", "note"])
        for r in sorted((r for r in enabled if r["permitNumber"] in lots), key=lambda r: (r["year"], r["Display"])):
            u, src, wp, parcels, ev, note = lots[r["permitNumber"]]
            w.writerow([r["permitNumber"], r["Display"], r["category"], r["year"], int(r["units_added"]),
                        u, int(r["units_added"]) - u, src, wp, parcels, ev, note])

    rows = []
    for t in TYPES:
        rs = [r for r in enabled if r["category"] == t]
        b, x = sum(int(r["units_added"]) for r in rs), sum(removed(r) for r in rs)
        rows.append([t, len(rs), b, x, b - x])
    rows.append(["Total", *[sum(r[i] for r in rows) for i in (1, 2, 3, 4)]])
    table("Plan-enabled duplex and triplex permits", ["Type", "Permits", "Units in the building",
                                                      "Existing units removed from the same lot", "Net units"], rows)
    with open(DER / "headline_by_type.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["type", "permits", "units_in_building", "existing_units_removed_same_lot", "net_units"])
        w.writerows(rows)

    nb = [r for r in enabled if r["category"] in NEW_BUILDS]
    with_removal = [r for r in nb if removed(r) > 0]
    src = collections.Counter(lots[r["permitNumber"]][1] for r in with_removal)
    print(f"\nNew buildings on lots where existing units were removed: {len(with_removal)} of {len(nb)} "
          f"({src['wrecking permit']} with a wrecking permit, {src['same_lot_review.csv']} from the assessor "
          f"record only); units removed: {sum(removed(r) for r in nb)}")
    for c in sorted(NEW_BUILDS):
        cs = [r for r in nb if r["category"] == c]
        print(f"  {c}: {sum(removed(r) > 0 for r in cs)} of {len(cs)} lots, {sum(removed(r) for r in cs)} units")

    net = {r["year"]: int(r["net"]) for r in read(DER / "net_units_by_year.csv")}
    by = collections.defaultdict(lambda: [0, 0, 0])
    for r in enabled:
        b = by[r["year"]]
        b[0] += 1
        b[1] += int(r["units_added"])
        b[2] += removed(r)
    yrows = []
    for y in sorted(k for k in net if k != "Total"):
        p, u, x = by[y]
        yrows.append([y, p, u, x, u - x, net[y], pct(u, net[y]), pct(u - x, net[y])])
    tp, tu, tx, tn = (sum(r[i] for r in yrows) for i in (1, 2, 3, 4))
    yrows.append(["Total", tp, tu, tx, tn, net["Total"], pct(tu, net["Total"]), pct(tn, net["Total"])])
    table("Plan-enabled units by year, and share of net housing growth",
          ["Year", "Permits", "Units in the building", "Existing units removed from the same lot", "Net units",
           "Citywide net gain", "Share (units in the building)", "Share (net units)"], yrows)
    with open(DER / "headline_by_year.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "permits", "units_in_building", "existing_units_removed_same_lot", "net_units",
                    "net_gain", "share_units_in_building", "share_net_units"])
        w.writerows([r[:6] + [round(r[2] / r[5], 4), round(r[4] / r[5], 4)] for r in yrows])

    print(f"\nExcluded as rezoned by application: {len(excluded)} permits, "
          f"{sum(int(r['units_added']) for r in excluded)} units in the building "
          f"({', '.join(r['Display'] for r in excluded)})")


if __name__ == "__main__":
    main()
