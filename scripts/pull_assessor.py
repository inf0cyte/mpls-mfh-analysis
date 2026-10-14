"""Pull City Assessor parcel records for every parcel with an active demolition permit.

Demolition (Wrecking) permits do not record how many dwelling units were removed. The City
Assessor's yearly parcel snapshots do record units, so net_units.py uses them to count the
units on each demolished parcel.

Reads data/raw/permits_wrecking.json (run pull_permits.py first) and writes to data/raw/:
  assessor_demolished_parcels.json    {parcel id: {snapshot year: [record, ...]}}, where each
                                      record holds address, units, buildingUse, propertyType
                                      as the snapshot gives them
  pull_manifest_assessor.json         services, field names, parcels requested and found

Usage:  python scripts/pull_assessor.py
"""
import datetime as dt
import json

import arcgis
import classify

CHUNK = 150


def main():
    # Every parcel id on any row of an active demolition permit (a permit can have several rows).
    rows = classify.rows_by_permit("permits_wrecking")
    apns = sorted({x["APN"].strip() for rs in rows.values() if rs[0]["status"] not in classify.INACTIVE
                   for x in rs if x["APN"] and x["APN"].strip()})
    out, manifest = {}, {
        "pulled_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parcels_requested": len(apns),
        "snapshots": {},
    }
    for year, (svc, key, prefix, fields) in sorted(arcgis.ASSESSOR.items()):
        url = f"{arcgis.ORG}/{svc}/FeatureServer/0"
        oid = arcgis.layer_info(url)["objectIdField"]
        n = 0
        for i in range(0, len(apns), CHUNK):
            ids = ",".join(f"'{prefix}{a}'" for a in apns[i:i + CHUNK])
            rows = arcgis.query_all(url, f"{key} IN ({ids})", [key] + fields, order_by=oid)
            for a in rows:
                apn = str(a[key]).removeprefix(prefix)
                rec = {"address": a[fields[0]], "units": a[fields[1]],
                       "buildingUse": a[fields[2]], "propertyType": a[fields[3]]}
                out.setdefault(apn, {}).setdefault(str(year), []).append(rec)
                n += 1
        manifest["snapshots"][year] = {"service": url, "id_field": key, "id_prefix": prefix,
                                       "fields": fields, "records": n}
        print(f"{year}: {n} records")
    manifest["parcels_found"] = len(out)
    (classify.RAW / "assessor_demolished_parcels.json").write_text(
        json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    (classify.RAW / "pull_manifest_assessor.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(out)} of {len(apns)} parcels found in at least one snapshot")


if __name__ == "__main__":
    main()
