"""Pull an arbitrary sample from the live sources to spot-check the analysis.

Examples
  # count permits matching any ArcGIS SQL where clause
  python scripts/sample.py count "workType='New' AND occupancyType='TFD' AND issueDate >= DATE '2020-01-01'"

  # print matching permits (first N) as CSV to stdout, or to a file with --out
  python scripts/sample.py rows "permitNumber='BLDG846524'"
  python scripts/sample.py rows "occupancyType='3to4' AND workType='New' AND dwellingUnitsNew=3 AND issueDate >= DATE '2020-01-01'" --limit 50 --out sample.csv

  # random sample of N permits from data/derived/classified_plex_permits.csv, re-queried live:
  # re-pulls each record and re-looks-up both zoning maps, and flags any difference
  python scripts/sample.py verify --n 15 --seed 7

  # zoning district at a point (lat lon), on both maps
  python scripts/sample.py zone 44.9486 -93.2398
"""
import argparse
import csv
import random
import sys

import arcgis
import classify

FIELDS = ["permitNumber", "Display", "permitType", "occupancyType", "workType", "status",
          "dwellingUnitsNew", "dwellingUnitsEliminated", "issueDate", "Latitude", "Longitude", "comments"]


def cmd_count(a):
    print(arcgis.count(arcgis.PERMITS, a.where))


def cmd_rows(a):
    rows = arcgis.query_all(arcgis.PERMITS, a.where, FIELDS)[: a.limit]
    fh = open(a.out, "w", newline="", encoding="utf-8") if a.out else sys.stdout
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    for r in rows:
        r["comments"] = (r.get("comments") or "")[:400]
        w.writerow(r)
    print(f"{len(rows)} rows", file=sys.stderr)


def cmd_zone(a):
    print("2017:", arcgis.zone_at(arcgis.ZONING_2017, a.lon, a.lat))
    print("2023:", arcgis.zone_at(arcgis.ZONING_2023, a.lon, a.lat))


def cmd_verify(a):
    path = classify.ROOT / "data" / "derived" / "classified_plex_permits.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    zl = {r["permitNumber"]: r for r in csv.DictReader(open(classify.RAW / "zoning_point_lookups.csv", encoding="utf-8"))}
    pick = random.Random(a.seed).sample(rows, min(a.n, len(rows)))
    bad = 0
    for r in pick:
        live = arcgis.query_all(arcgis.PERMITS, f"permitNumber='{r['permitNumber']}'", FIELDS)
        z = zl[r["permitNumber"]]
        lat, lon = float(z["lat"]), float(z["lon"])
        z17, z23 = arcgis.zone_at(arcgis.ZONING_2017, lon, lat), arcgis.zone_at(arcgis.ZONING_2023, lon, lat)
        ok = bool(live) and z17 == r["zone_2017"] and z23 == r["zone_2023"]
        bad += not ok
        desc = (live[0].get("comments") or "")[:90].replace("\n", " ") if live else "NOT FOUND LIVE"
        print(f"{'OK ' if ok else 'DIFF'} {r['permitNumber']:<12} {r['category']:<18} {r['Display']:<28} "
              f"2017={z17:<4} 2023={z23:<4} newly_allowed={r['newly_allowed']:<5} | {desc}")
    print(f"\n{len(pick) - bad} of {len(pick)} match the repo data")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("count"); p.add_argument("where"); p.set_defaults(f=cmd_count)
    p = sub.add_parser("rows"); p.add_argument("where"); p.add_argument("--limit", type=int, default=25)
    p.add_argument("--out"); p.set_defaults(f=cmd_rows)
    p = sub.add_parser("zone"); p.add_argument("lat", type=float); p.add_argument("lon", type=float); p.set_defaults(f=cmd_zone)
    p = sub.add_parser("verify"); p.add_argument("--n", type=int, default=15); p.add_argument("--seed", type=int, default=1)
    p.set_defaults(f=cmd_verify)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
