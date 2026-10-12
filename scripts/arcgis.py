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

# Permit fields pulled into the repo. Applicant name/address fields exist in the
# source layer but are deliberately NOT pulled (personal data, not needed).
PERMIT_FIELDS = [
    "OBJECTID", "permitNumber", "APN", "Display", "Latitude", "Longitude",
    "Neighborhoods_Desc", "Wards", "permitType", "occupancyType", "workType",
    "status", "milestone", "dwellingUnitsNew", "dwellingUnitsEliminated",
    "value", "issueDate", "completeDate", "comments",
]

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


def count(layer_url, where):
    return _post(layer_url + "/query", {"where": where, "returnCountOnly": "true", "f": "json"})["count"]


def query_all(layer_url, where, out_fields="*", page=2000, return_geometry=False):
    """Return every matching feature's attributes, paging by OBJECTID order."""
    rows, offset = [], 0
    while True:
        payload = _post(layer_url + "/query", {
            "where": where,
            "outFields": out_fields if isinstance(out_fields, str) else ",".join(out_fields),
            "returnGeometry": "true" if return_geometry else "false",
            "orderByFields": "OBJECTID",
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
