"""Selection rules that turn raw permit records into the analysis categories.

Imported by pull_zoning.py and analyze.py so both use identical rules.
"""
import csv
import datetime as dt
import json
import pathlib

import arcgis

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANUAL = ROOT / "data" / "manual" / "conversion_classification.csv"

INACTIVE = {"Cancelled", "Expired"}
DUPLEX_OCC = {"TFD", "TH"}          # two-family dwelling; two-unit townhouse
TRIPLEX_OCC = {"3to4"}               # city code shared by 3- and 4-unit buildings; 3 units required

DECONVERSION_CATS = {  # category -> units lost
    "duplex_to_sfd": 1,
    "triplex_to_duplex": 1,
    "triplex_to_sfd": 2,
}

CONVERSION_CATS = {
    "sfd_to_duplex": "SFD to duplex",
    "duplex_to_triplex": "Duplex to triplex",
    "sfd_to_triplex": "SFD to triplex",
}


def load(name):
    """Load a raw pull, converting unit counts to int.

    Raw files pulled before the 2026 schema change hold ints; files pulled after it hold
    strings. Comparisons such as dwellingUnitsNew == 2 silently match nothing on strings,
    so every row is normalised here before any selection rule runs.
    """
    rows = json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))
    for r in rows:
        for f in arcgis.UNIT_FIELDS:
            r[f] = arcgis.to_int(r.get(f))
    return rows


def dedupe(rows):
    """Source layer has occasional duplicate rows per permit; keep lowest OBJECTID."""
    out = {}
    for r in sorted(rows, key=lambda r: r["OBJECTID"]):
        out.setdefault(r["permitNumber"], r)
    return out


def year(r):
    return dt.datetime.fromtimestamp(r["issueDate"] / 1000, dt.timezone.utc).year


def manual():
    return list(csv.DictReader(open(MANUAL, encoding="utf-8")))


def records():
    """Return dict with category lists plus the lookup of all raw rows by permit number."""
    new = load("permits_new_construction")
    ref = dedupe(load("permits_manually_classified") + load("permits_conversion_candidates") + new)
    new_d = dedupe(new)
    m = manual()
    by_cat = {}
    for row in m:
        by_cat.setdefault(row["category"], []).append(row["permitNumber"])
    missing = [row["permitNumber"] for row in m if row["permitNumber"] not in ref]
    if missing:
        raise SystemExit(f"Manually classified permits missing from raw pulls: {missing}")

    def get(ids):
        return [ref[i] for i in ids]

    new_duplex = [r for r in new_d.values() if r["occupancyType"] in DUPLEX_OCC
                  and r["dwellingUnitsNew"] == 2 and r["status"] not in INACTIVE]
    new_triplex = [r for r in new_d.values() if r["occupancyType"] in TRIPLEX_OCC
                   and r["dwellingUnitsNew"] == 3 and r["status"] not in INACTIVE]
    ids_d = {r["permitNumber"] for r in new_duplex}
    ids_t = {r["permitNumber"] for r in new_triplex}
    new_duplex += [r for r in get(by_cat.get("new_duplex", [])) if r["permitNumber"] not in ids_d]
    new_triplex += [r for r in get(by_cat.get("new_triplex", [])) if r["permitNumber"] not in ids_t]
    excl = set(by_cat.get("new_sfd_exclude", []))
    new_sfd = [r for r in new_d.values() if r["occupancyType"] == "SFD"
               and r["status"] != "Cancelled" and r["permitNumber"] not in excl]

    cats = {"New duplex": new_duplex, "New triplex": new_triplex}
    for key, label in CONVERSION_CATS.items():
        cats[label] = get(by_cat.get(key, []))
    deconv = [(ref[row["permitNumber"]], row["counted"], row["category"]) for row in m
              if row["category"] in DECONVERSION_CATS]
    return {"plex": cats, "new_sfd": new_sfd, "deconversions": deconv, "manual": m, "ref": ref,
            "new_raw_rows": new}
