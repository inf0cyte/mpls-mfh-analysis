"""Look up the pre-2040 (2017) and mid-2023 primary zoning district at each duplex/triplex permit.

Reads data/raw/permits_*.json (run pull_permits.py first) and writes
data/raw/zoning_point_lookups.csv with one row per permit:
  permitNumber, category, lat, lon, coord_source, geocode_match, zone_2017, zone_2023

Coordinates come from the permit record's Latitude/Longitude. When those are
blank, the address is geocoded with the Esri World Geocoder and the match is
recorded in the geocode_match column so it can be checked by hand.

Usage:  python scripts/pull_zoning.py
"""
import csv

import arcgis
import classify


def main():
    rec = classify.records()
    out = classify.RAW / "zoning_point_lookups.csv"
    cols = ["permitNumber", "category", "Display", "lat", "lon", "coord_source",
            "geocode_match", "zone_2017", "zone_2023"]
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for cat, rows in rec["plex"].items():
            for r in rows:
                lat, lon, src, match = r.get("Latitude"), r.get("Longitude"), "permit record", ""
                if not lat or not lon:
                    g = arcgis.geocode(f"{r['Display']}, Minneapolis, MN")
                    lat, lon, src = g["lat"], g["lon"], "esri world geocoder"
                    match = f"{g['match']} (score {g['score']})"
                w.writerow({
                    "permitNumber": r["permitNumber"], "category": cat, "Display": r["Display"],
                    "lat": lat, "lon": lon, "coord_source": src, "geocode_match": match,
                    "zone_2017": arcgis.zone_at(arcgis.ZONING_2017, lon, lat),
                    "zone_2023": arcgis.zone_at(arcgis.ZONING_2023, lon, lat),
                })
                n += 1
    print(f"wrote {n} zoning lookups to {out}")


if __name__ == "__main__":
    main()
