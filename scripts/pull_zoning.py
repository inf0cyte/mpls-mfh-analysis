"""Look up the pre-2040 (2017) and mid-2023 primary zoning district at each duplex/triplex permit.

Reads data/raw/permits_*.json (run pull_permits.py first) and writes
data/raw/zoning_point_lookups.csv with one row per permit:
  permitNumber, category, lat, lon, coord_source, geocode_match, zone_2017, zone_2023

Coordinates come from the permit record's Latitude/Longitude. Some permits have several
rows in the source layer with slightly different coordinates; every distinct point is looked
up, and if they all fall in the same districts that point is used. When the permit has no
coordinates, or its points fall in different districts, the address is geocoded with the
Esri World Geocoder and the match is recorded in the geocode_match column so it can be
checked by hand.

Usage:  python scripts/pull_zoning.py
"""
import csv

import arcgis
import classify


def main():
    rec = classify.records()
    rows_of = classify.rows_by_permit("permits_manually_classified", "permits_conversion_candidates",
                                      "permits_new_construction")
    out = classify.RAW / "zoning_point_lookups.csv"
    cols = ["permitNumber", "category", "Display", "lat", "lon", "coord_source",
            "geocode_match", "zone_2017", "zone_2023"]
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for cat, rows in rec["plex"].items():
            for r in rows:
                pts = sorted({(x["Latitude"], x["Longitude"]) for x in rows_of[r["permitNumber"]]
                              if x.get("Latitude") and x.get("Longitude")})
                zones = {(lat, lon): (arcgis.zone_at(arcgis.ZONING_2017, lon, lat),
                                      arcgis.zone_at(arcgis.ZONING_2023, lon, lat)) for lat, lon in pts}
                match = ""
                if pts and len(set(zones.values())) == 1:
                    (lat, lon), (z17, z23) = pts[0], zones[pts[0]]
                    src = "permit record" if len(pts) == 1 else f"permit record ({len(pts)} points agree)"
                else:
                    g = arcgis.geocode(f"{r['Display']}, Minneapolis, MN")
                    lat, lon = g["lat"], g["lon"]
                    src = "esri world geocoder" if not pts else f"esri world geocoder ({len(pts)} permit points disagree)"
                    match = f"{g['match']} (score {g['score']})"
                    z17, z23 = arcgis.zone_at(arcgis.ZONING_2017, lon, lat), arcgis.zone_at(arcgis.ZONING_2023, lon, lat)
                w.writerow({
                    "permitNumber": r["permitNumber"], "category": cat, "Display": r["Display"],
                    "lat": lat, "lon": lon, "coord_source": src, "geocode_match": match,
                    "zone_2017": z17, "zone_2023": z23,
                })
                n += 1
    print(f"wrote {n} zoning lookups to {out}")


if __name__ == "__main__":
    main()
