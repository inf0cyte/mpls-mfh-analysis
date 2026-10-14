"""Minimal ArcGIS REST helpers (Python standard library only).

Used by every other script in this folder. All requests are HTTP POSTs to
public City of Minneapolis ArcGIS Online feature services; no key is needed.
"""
import json
import time
import urllib.parse
import urllib.request

ORG = "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services"

# City of Minneapolis Construction Code Services permits (live, updated daily)
PERMITS = f"{ORG}/CCS_Permits/FeatureServer/0"
# Primary zoning as of 2017-01-26 (pre-Minneapolis 2040)
ZONING_2017 = f"{ORG}/msvcCPED_PrimaryZoning_20170126/FeatureServer/0"
# Primary zoning archived 2023-06-30 (just before the Land Use Rezoning Study map took effect)
ZONING_2023 = f"{ORG}/PrimaryZoningArchive/FeatureServer/0"
# Esri World Geocoder (used only for permits whose record has no coordinates)
GEOCODER = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

# Observation window: permits issued from SINCE through the day before UNTIL.
# 2020-01-01 is the day the 2040 Plan's zoning changes took effect.
SINCE = "2020-01-01"
UNTIL = "2026-09-25"  # exclusive, so the window ends 2026-09-24


def window(since=SINCE, until=UNTIL):
    return f"issueDate >= DATE '{since}' AND issueDate < DATE '{until}'"


# City Assessor yearly parcel snapshots: year -> (service, parcel-id field, id prefix, fields).
# The id field and the address/units/type field names change between years.
# 2017-2020 store the 13-digit parcel id as-is; 2021 onward prefix it with "p".
_A1 = ["FORMATTED_ADDRESS", "TOTAL_UNITS", "BUILDINGUSE", "PROPERTY_TYPE"]
_A2 = ["FORMATTED_ADDRESS", "TOTAL_UNITS", "BUILDINGUSE", "PRIMARY_PROP_TYPE"]
_A3 = ["ADDRESSFORMATTED", "TOTALUNITS", "BUILDINGUSE", "PROPERTYTYPE"]
ASSESSOR = {
    2017: ("Assessors_Parcel_Data_2017", "APN", "", _A1),
    2018: ("Assessors_Parcel_Data_2018", "APN", "", _A1),
    2019: ("Assessors_Parcel_Data_2019", "APN", "", _A1),
    2020: ("Assessors_Parcel_Data_2020", "APN", "", _A1),
    2021: ("Assessors_Parcel_Data_2021", "PIN", "p", _A2),
    2022: ("Assessors_Parcel_Data_2022", "PIN", "p", _A2),
    2023: ("Assessing_Department_Parcel_Data_2023", "PIN", "p", _A2),
    2024: ("Assessing_Department_Parcel_Data_2024", "PIN", "p", _A2),
    2025: ("Assessing_Department_Parcel_Data_2025", "TAX_MAP_UFMT", "p", _A3),
    2026: ("Assessing_Department_Parcel_Data_2026", "F_No_column_name_", "p", _A3),
}

# Permit fields pulled into the repo. Applicant name/address fields exist in the
# source layer but are deliberately NOT pulled (personal data, not needed).
#
# Source schema change (observed 2026-10-13; the layer still had the old schema on
# 2026-09-28): `value` was renamed `permit_Value`, and `dwellingUnitsNew` /
# `dwellingUnitsEliminated` changed from integer fields to string fields.
PERMIT_FIELDS = [
    "OBJECTID", "permitNumber", "APN", "Display", "Latitude", "Longitude",
    "Neighborhoods_Desc", "Wards", "permitType", "occupancyType", "workType",
    "status", "milestone", "dwellingUnitsNew", "dwellingUnitsEliminated",
    "permit_Value", "issueDate", "completeDate", "comments",
]

UNIT_FIELDS = ("dwellingUnitsNew", "dwellingUnitsEliminated")

_T = "esriFieldType"
_NUMBER = {_T + "Integer", _T + "SmallInteger", _T + "BigInteger", _T + "Double"}
# Allowed ArcGIS types for every field the scripts read. Unit counts may be numeric
# (pre-change schema) or string (current schema); classify.py converts either to int.
PERMIT_FIELD_TYPES = {
    "OBJECTID": {_T + "OID"},
    "permitNumber": {_T + "String"},
    "APN": {_T + "String"},
    "Display": {_T + "String"},
    "Latitude": {_T + "Double"},
    "Longitude": {_T + "Double"},
    "Neighborhoods_Desc": {_T + "String"},
    "Wards": {_T + "String"},
    "permitType": {_T + "String"},
    "occupancyType": {_T + "String"},
    "workType": {_T + "String"},
    "status": {_T + "String"},
    "milestone": {_T + "String"},
    "dwellingUnitsNew": _NUMBER | {_T + "String"},
    "dwellingUnitsEliminated": _NUMBER | {_T + "String"},
    "permit_Value": _NUMBER,
    "issueDate": {_T + "Date"},
    "completeDate": {_T + "Date"},
    "comments": {_T + "String"},
}

UA = {"User-Agent": "mpls-mfh-analysis/1.0 (research script)"}


def _post(url, params, retries=4):
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read().decode("utf-8"))
            if "error" in payload:
                raise RuntimeError(f"ArcGIS error from {url}: {payload['error']}")
            return payload
        except (urllib.error.URLError, TimeoutError) as e:  # transient
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def layer_info(layer_url):
    return _post(layer_url, {"f": "json"})


def check_permit_schema(info):
    """Stop if any field the scripts read is missing or has an unexpected type.

    Returns {field: type} for the fields checked, for the pull manifest.
    """
    actual = {f["name"]: f["type"] for f in info.get("fields", [])}
    problems = []
    for name, allowed in PERMIT_FIELD_TYPES.items():
        if name not in actual:
            problems.append(f"missing field {name!r}")
        elif actual[name] not in allowed:
            problems.append(f"{name!r} is {actual[name]}, expected one of {sorted(allowed)}")
    if problems:
        raise SystemExit("CCS_Permits schema changed; update scripts/arcgis.py before pulling:\n  "
                         + "\n  ".join(problems))
    return {name: actual[name] for name in PERMIT_FIELD_TYPES}


def to_int(v):
    """Unit counts arrive as int (old schema) or str (current schema); None/'' stay None."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return int(float(v))


def count(layer_url, where):
    return _post(layer_url + "/query", {"where": where, "returnCountOnly": "true", "f": "json"})["count"]


def query_all(layer_url, where, out_fields="*", page=2000, return_geometry=False, order_by="OBJECTID"):
    """Return every matching feature's attributes, paging in object-id order."""
    rows, offset = [], 0
    while True:
        payload = _post(layer_url + "/query", {
            "where": where,
            "outFields": out_fields if isinstance(out_fields, str) else ",".join(out_fields),
            "returnGeometry": "true" if return_geometry else "false",
            "orderByFields": order_by,
            "resultOffset": offset,
            "resultRecordCount": page,
            "f": "json",
        })
        feats = payload.get("features", [])
        rows.extend(f["attributes"] for f in feats)
        if not payload.get("exceededTransferLimit") and len(feats) < page:
            break
        if not feats:
            break
        offset += len(feats)
    return rows


def zone_at(layer_url, lon, lat):
    """ZONE_CODE(s) of the zoning polygon(s) containing a WGS84 point."""
    payload = _post(layer_url + "/query", {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ZONE_CODE",
        "returnGeometry": "false",
        "f": "json",
    })
    codes = sorted({f["attributes"]["ZONE_CODE"] for f in payload.get("features", [])})
    return "/".join(codes) if codes else "NONE"


def geocode(address):
    """Best single candidate from the Esri World Geocoder (not stored beyond this repo's audit file)."""
    payload = _post(GEOCODER, {"SingleLine": address, "maxLocations": 1, "f": "json"})
    c = (payload.get("candidates") or [None])[0]
    if not c:
        return None
    return {"lon": c["location"]["x"], "lat": c["location"]["y"], "match": c["address"], "score": c["score"]}
