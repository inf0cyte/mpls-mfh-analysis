"""Pull the raw permit records used in the analysis.

Writes to data/raw/:
  permits_new_construction.{json,csv}   every workType='New' permit issued 2020-01-01 or later
  permits_conversion_candidates.{json,csv}
                                        every non-new Res/Commercial permit issued 2020-01-01 or
                                        later that is a Conversion/UnitCon work type, or whose
                                        description mentions converting/legalizing a building
                                        type, or adding a 2nd/3rd dwelling unit
  permits_manually_classified.{json,csv}
                                        every permit listed in data/manual/conversion_classification.csv
                                        (pulled by permit number, so the manual review is always
                                        backed by the source record even if a keyword search misses it)
  pull_manifest_permits.json           query text, row counts, pull time, source layer edit date

Usage:  python scripts/pull_permits.py [--since 2020-01-01]
"""
import argparse
import csv
import datetime as dt
import json
import pathlib

import arcgis

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

C = "UPPER(comments)"
TYPE_WORDS = ["DUPLEX", "DUPELX", "DUPEX", "TRIPLEX", "TWO%FAMILY", "TFD", "SFD",
              "SINGLE%FAMILY", "THREE%FAMILY"]
UNIT_PHRASES = ["THIRD%UNIT", "3RD%UNIT", "THIRD DWELLING", "3RD DWELLING", "SECOND DWELLING",
                "2ND DWELLING", "SECOND UNIT", "2ND UNIT", "INTO%DUPLEX", "INTO%TRIPLEX"]


def where_new(since):
    return f"workType = 'New' AND issueDate >= DATE '{since}'"


def where_candidates(since):
    types = " OR ".join(f"{C} LIKE '%{t}%'" for t in TYPE_WORDS)
    units = " OR ".join(f"{C} LIKE '%{t}%'" for t in UNIT_PHRASES)
    return (f"issueDate >= DATE '{since}' AND workType <> 'New' "
            f"AND permitType IN ('Res','Commercial') "
            f"AND (workType IN ('Conversion','UnitCon') "
            f"OR (({C} LIKE '%CONVER%' OR {C} LIKE '%LEGALIZ%') AND ({types})) "
            f"OR {units})")


def iso(ms):
    if ms is None:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(name, rows):
    (RAW / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    cols = arcgis.PERMIT_FIELDS + ["issueDate_utc", "completeDate_utc"]
    with open(RAW / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "issueDate_utc": iso(r.get("issueDate")), "completeDate_utc": iso(r.get("completeDate"))})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2020-01-01")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    info = arcgis.layer_info(arcgis.PERMITS)
    manifest = {
        "pulled_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_layer": arcgis.PERMITS,
        "source_layer_last_edit_utc": iso(info.get("editingInfo", {}).get("lastEditDate")),
        "fields": arcgis.PERMIT_FIELDS,
        "queries": {},
    }
    manual = ROOT / "data" / "manual" / "conversion_classification.csv"
    ids = sorted({r["permitNumber"] for r in csv.DictReader(open(manual, encoding="utf-8"))})
    where_manual = "permitNumber IN (" + ",".join(f"'{i}'" for i in ids) + ")"
    for name, where in [("permits_new_construction", where_new(a.since)),
                        ("permits_conversion_candidates", where_candidates(a.since)),
                        ("permits_manually_classified", where_manual)]:
        expected = arcgis.count(arcgis.PERMITS, where)
        rows = arcgis.query_all(arcgis.PERMITS, where, arcgis.PERMIT_FIELDS)
        if len(rows) != expected:
            raise SystemExit(f"{name}: server count {expected} != rows pulled {len(rows)}")
        write(name, rows)
        manifest["queries"][name] = {
            "where": where,
            "rows": len(rows),
            "max_issueDate_utc": iso(max((r["issueDate"] for r in rows if r.get("issueDate")), default=None)),
        }
        print(f"{name}: {len(rows)} rows")
    (RAW / "pull_manifest_permits.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
