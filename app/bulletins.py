"""EPA Bulletins Live! Two: Pesticide Use Limitation Areas (PULAs) that touch a field."""

import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from shapely import union_all
from shapely.geometry import mapping, shape

from app import geo

BLT = "https://blt.epa.gov/arcgis/rest/services/BLT/PesticideUsageLimitationAreas/MapServer"
BLT_APP = "https://www.epa.gov/endangered-species/bulletins-live-two-view-bulletins"
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "blt"
MAX_AGE_S = 7 * 24 * 3600  # EPA updates PULAs; a week covers a demo without hiding real changes
REG_NO = re.compile(r"^\s*(\d+-\d+)")  # base reg no; drops distributor suffix
# ponytail: keyword match on limitation text; anything else is listed for the applicator to read
PROHIBITS = re.compile(r"\bdo not (apply|use)\b", re.I)


def _query(layer: int, **params) -> dict:
    r = httpx.get(f"{BLT}/{layer}/query", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise httpx.HTTPError(f"BLT error: {data['error']}")
    return data


def _month_end_ms(month: str) -> int:
    """'2026-11' -> first instant of December 2026, in epoch ms."""
    y, m = map(int, month.split("-"))
    nxt = datetime(y + m // 12, m % 12 + 1, 1, tzinfo=timezone.utc)
    return int(nxt.timestamp() * 1000)


def check_bulletin(field_path, month: str, reg_no: str) -> dict:
    """month is 'YYYY-MM'. Limitations for every application method are included.

    Successful checks are cached per field, month and product for MAX_AGE_S; failed ones never are.
    The citation keeps the date BLT was actually queried."""
    base = REG_NO.match(reg_no or "")
    key = hashlib.sha256(Path(field_path).read_bytes()
                         + f"|{month}|{base[1] if base else reg_no}".encode()).hexdigest()[:20]
    cached = CACHE / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < MAX_AGE_S:
        out = json.loads(cached.read_text())
        return out | {"restricted": [shape(g) for g in out["restricted"]]}
    out = _check(field_path, month, reg_no)
    if out["checked"]:
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(out | {"restricted": [mapping(g) for g in out["restricted"]]}))
    return out


def _check(field_path, month: str, reg_no: str) -> dict:
    """The live BLT query behind check_bulletin."""
    field = geo.load_field(field_path)
    out = {"in_pula": False, "prohibited": False, "limitations": [], "restricted": [],
           "citation": f"Could not check Bulletins Live! Two. Check by hand at {BLT_APP}",
           "checked": False}
    base = REG_NO.match(reg_no or "")
    if not base:
        out["citation"] = f"No usable EPA Reg. No. ({reg_no!r}). Check by hand at {BLT_APP}"
        return out
    end = _month_end_ms(month)

    try:
        pulas = _query(0, geometry=json.dumps({"rings": [list(field.exterior.coords)]}),
                       geometryType="esriGeometryPolygon", inSR=4326,
                       spatialRel="esriSpatialRelIntersects", outSR=4326,
                       outFields="pula_id,event_name,effective_date", f="geojson")["features"]
        pulas = [p for p in pulas if (p["properties"]["effective_date"] or 0) < end]
        ids = sorted({p["properties"]["pula_id"] for p in pulas})
        rows = []
        if ids:
            # reg no is digits and a dash only (REG_NO), so it is safe inside the where clause
            where = f"pula_id IN ({','.join(map(str, ids))}) AND product_registration_number='{base[1]}'"
            rows = [f["attributes"] for f in _query(
                1, where=where, outFields="pula_id,code,limitation", f="json")["features"]]
    except (httpx.HTTPError, ValueError, KeyError):
        return out

    events = {p["properties"]["pula_id"]: p["properties"]["event_name"] for p in pulas}
    seen = set()
    for r in rows:
        key = (r["pula_id"], r["code"], r["limitation"])
        if key not in seen:
            seen.add(key)
            out["limitations"].append({**r, "event_name": events.get(r["pula_id"])})

    banned = {r["pula_id"] for r in out["limitations"] if PROHIBITS.search(r["limitation"] or "")}
    if banned:
        area = union_all([shape(p["geometry"]) for p in pulas if p["properties"]["pula_id"] in banned])
        out["restricted"] = [field.intersection(area)]
        out["prohibited"] = field.difference(area).area <= field.area * 1e-6

    used = sorted({r["pula_id"] for r in out["limitations"]})
    out["in_pula"] = bool(ids)
    out["checked"] = True
    out["citation"] = (
        f"EPA Bulletins Live! Two, {month}, EPA Reg. No. {base[1]}: "
        + (f"PULA {', '.join(map(str, used))} applies" if used else "no PULA applies")
        + f". Queried {date.today().isoformat()} from the BLT map service, which is informational;"
        f" print the official Bulletin from {BLT_APP}")
    return out
