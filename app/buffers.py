"""Field + hazards + label rules -> legal spray zone. Pure geometry, never calls a model."""

import geopandas as gpd
from shapely import union_all
from shapely.geometry import Polygon

FT_TO_M = 0.3048
M_PER_UNIT = {"ft": FT_TO_M, "feet": FT_TO_M, "foot": FT_TO_M, "m": 1.0, "meters": 1.0, "meter": 1.0}
SQM_PER_ACRE = 4046.8564224
MIN_ACRES = 0.01  # below this an area counts as nothing
# EPA treats drone application as aerial for label purposes.
METHOD_ALIASES = {"drone": "aerial"}  # label_reader limits applies_to to all/aerial/ground
HAZARD_KINDS = ("water", "building", "habitat")


def _applies(rule: dict, method: str) -> bool:
    applies_to = rule.get("applies_to") or "all"
    if isinstance(applies_to, str):
        applies_to = [applies_to]
    return bool({"all", method, METHOD_ALIASES.get(method, method)} & set(applies_to))


def _acres(geom) -> float:
    return geom.area / SQM_PER_ACRE


def plan(field: Polygon, hazards: dict, rules: list[dict], restricted=(),
         method: str = "drone", prohibited: bool = False) -> dict:
    """restricted: bulletin shapes to exclude. prohibited: bulletin bans the product here."""
    utm = gpd.GeoSeries([field], crs=4326).estimate_utm_crs()

    def to_utm(shapes):
        return list(gpd.GeoSeries(list(shapes), crs=4326).to_crs(utm))

    field_m = to_utm([field])[0]
    hazards_m = {k: to_utm(hazards.get(k) or []) for k in HAZARD_KINDS}
    zones, reasons = [], []

    def reaches(shapes) -> bool:
        """A reason is only listed if its zone takes area out of this field."""
        return any(field_m.intersection(s).area >= 1.0 for s in shapes)  # 1 m2

    if prohibited:
        reasons.append({"source": "bulletin", "summary": "Bulletin prohibits this product here."})
        zones.append(field_m)

    for rule in rules:
        shapes = hazards_m.get(rule.get("target"), [])
        if rule.get("kind") != "buffer" or not shapes or not _applies(rule, method):
            continue
        meters = rule["value"] * M_PER_UNIT[rule["unit"].lower()]
        rule_zones = [s.buffer(meters) for s in shapes]
        zones += rule_zones
        if not reaches(rule_zones):
            continue
        reasons.append({"source": "label", "target": rule["target"],
                        "distance_ft": round(meters / FT_TO_M, 1),
                        "summary": rule.get("summary", ""), "quote": rule["quote"],
                        "page": rule.get("page")})

    water_rule = any(r.get("kind") == "buffer" and r.get("target") == "water" and _applies(r, method) for r in rules)
    if hazards_m["water"] and not water_rule:
        # No label buffer for water: still never spray the water itself.
        zones += hazards_m["water"]
        if reaches(hazards_m["water"]):
            reasons.append({"source": "rule:water",
                            "summary": "No label water buffer applies; water itself is excluded."})

    if restricted:
        restricted_m = to_utm(restricted)
        zones += restricted_m
        if reaches(restricted_m):
            reasons.append({"source": "bulletin", "summary": "Bulletin restricted area excluded."})

    blocked = union_all(zones) if zones else Polygon()
    no_spray, spray = field_m.intersection(blocked), field_m.difference(blocked)
    spray_acres, excluded_acres = _acres(spray), _acres(no_spray)

    if prohibited or spray_acres < MIN_ACRES:
        status = "no-go"
    elif excluded_acres >= MIN_ACRES:
        status = "adjust"
    else:
        status = "go"

    back = list(gpd.GeoSeries([spray, no_spray], crs=utm).to_crs(4326))
    return {"status": status, "method": method, "field_acres": round(_acres(field_m), 2),
            "spray_acres": round(spray_acres, 2), "excluded_acres": round(excluded_acres, 2),
            "spray_zone": back[0], "no_spray": back[1], "reasons": reasons}
