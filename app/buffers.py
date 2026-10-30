"""Field + hazards + label rules -> spray zone and GO / ADJUST / NO-GO. Pure geometry, never calls a model."""

import math

import geopandas as gpd
from shapely import union_all
from shapely.affinity import translate
from shapely.geometry import Polygon

FT_TO_M = 0.3048
M_PER_UNIT = {"ft": FT_TO_M, "feet": FT_TO_M, "foot": FT_TO_M, "m": 1.0, "meters": 1.0, "meter": 1.0}
SQM_PER_ACRE = 4046.8564224
MIN_ACRES = 0.01  # below this an area counts as nothing
# EPA treats drone application as aerial for label purposes.
METHOD_ALIASES = {"drone": "aerial"}  # label_reader limits applies_to to all/aerial/ground
HAZARD_KINDS = ("water", "building", "habitat")
SLIVER_M = 0.5  # unmanaged land narrower than this between managed land and the field is ignored


def _applies(rule: dict, method: str) -> bool:
    applies_to = rule.get("applies_to") or "all"
    if isinstance(applies_to, str):
        applies_to = [applies_to]
    return bool({"all", method, METHOD_ALIASES.get(method, method)} & set(applies_to))


def _acres(geom) -> float:
    return geom.area / SQM_PER_ACRE


def drift_zone(field_m, managed_m: list, meters: float, wind_from_deg: float | None = None):
    """The part of the field (metres) within `meters` of unmanaged land: everything outside the field that the user
    hasn't marked as managed. Spraying there could drift onto it.

    With wind_from_deg (compass degrees the wind blows from), drift only travels downwind: a treated point p
    reaches unmanaged q when q = p + t * downwind for t in [0, meters], so unmanaged land is swept upwind by
    `meters` instead of buffered all round.
    """
    outside = field_m.buffer(meters + 1).difference(field_m)  # nothing further out can be reached
    unmanaged = outside.difference(union_all(managed_m)) if managed_m else outside
    # ponytail: gaps under SLIVER_M between marked land and the field are drawing or reprojection noise, not land
    # anything drifts onto; a real unmanaged strip that narrow (a ditch edge) is missed. Snap drawings if it matters.
    unmanaged = unmanaged.buffer(-SLIVER_M / 2).buffer(SLIVER_M / 2)
    if unmanaged.is_empty or meters <= 0:
        return Polygon()
    if wind_from_deg is None:
        reach = unmanaged.buffer(meters)
    else:
        rad = math.radians(wind_from_deg)
        reach = _sweep(unmanaged, meters * math.sin(rad), meters * math.cos(rad))
    return field_m.intersection(reach)


def _sweep(shape, dx: float, dy: float):
    """shape swept along (dx, dy), exactly: the shape, its shifted copy and every edge's parallelogram."""
    parts = [shape, translate(shape, dx, dy)]
    for poly in getattr(shape, "geoms", [shape]):
        for ring in [poly.exterior, *poly.interiors]:
            c = list(ring.coords)
            quads = (Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)]) for a, b in zip(c, c[1:]))
            parts += [q for q in quads if q.area > 0]  # an edge parallel to the wind sweeps no area
    return union_all(parts)


def plan(field: Polygon, hazards: dict, rules: list[dict], restricted=(),
         method: str = "drone", prohibited: bool = False, gaps=(), managed=(), wind_from_deg=None) -> dict:
    """restricted: bulletin shapes to exclude. prohibited: bulletin bans the product here.

    gaps: missing data the plan needs (e.g. USGS water unavailable). Any gap is NO-GO with nothing sprayable:
    a zone that couldn't be checked is never handed to a sprayer.
    hazards["possible_water"]: water only the aerial scout saw; it never changes the map, at most makes it ADJUST.
    managed: land next to the field the user marked as managed (roads, other fields, farmsteads); a drift rule
    buffers the treated area toward everything else. wind_from_deg: if set, drift buffers run downwind only."""
    utm = gpd.GeoSeries([field], crs=4326).estimate_utm_crs()

    def to_utm(shapes):
        return list(gpd.GeoSeries(list(shapes), crs=4326).to_crs(utm))

    field_m = to_utm([field])[0]
    hazards_m = {k: to_utm(hazards.get(k) or []) for k in HAZARD_KINDS}
    zones, reasons = [], []

    def reaches(shapes) -> bool:
        """A reason is only listed if its zone takes area out of this field (same threshold as the status)."""
        return field_m.intersection(union_all(shapes)).area >= MIN_ACRES * SQM_PER_ACRE

    if prohibited:
        reasons.append({"source": "bulletin", "summary": "Bulletin prohibits this product here."})
        zones.append(field_m)
    for gap in gaps:
        reasons.append({"source": "data", "summary": gap})
    if gaps:
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

    managed_m = to_utm(managed)
    for rule in rules:
        if rule.get("kind") != "drift" or not _applies(rule, method):
            continue
        meters = rule["value"] * M_PER_UNIT[rule["unit"].lower()]
        zone = drift_zone(field_m, managed_m, meters, wind_from_deg)
        zones.append(zone)
        if reaches([zone]):
            reasons.append({"source": "label", "kind": "drift", "target": "unmanaged land",
                            "distance_ft": round(meters / FT_TO_M, 1), "summary": rule.get("summary", ""),
                            "quote": rule["quote"], "page": rule.get("page")})

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

    # Water only the aerial scout saw (not in the national water map) is a question, not a fact: it never changes
    # the map, but if it, or the label's water setback around it, reaches the field, the plan can't be a clean GO.
    setback = max((r["value"] * M_PER_UNIT[r["unit"].lower()] for r in rules if r.get("kind") == "buffer"
                   and r.get("target") == "water" and _applies(r, method)), default=0)
    unsure = [s for s in to_utm(hazards.get("possible_water") or []) if s.buffer(setback).intersects(field_m)]
    if unsure:
        reasons.append({"source": "review", "kind": "possible_water", "summary": f"{len(unsure)} possible water "
                        f"area{'s' if len(unsure) > 1 else ''} on the aerial photo {'are' if len(unsure) > 1 else 'is'}"
                        " not in the national water map. Check before spraying: if it holds water, the label's water"
                        " setback applies."})

    # Runoff mitigation points are worked out in EPA's PALM, not here (out of scope); a label that requires
    # them can't be a clean GO, so it forces ADJUST. It never changes the map.
    runoff = [r for r in rules if r.get("kind") == "runoff" and _applies(r, method)]
    for r in runoff:
        reasons.append({"source": "label", "kind": "runoff", "summary": "Runoff mitigation points required: "
                        "complete them in EPA's PALM before spraying.", "quote": r["quote"], "page": r.get("page")})

    blocked = union_all(zones) if zones else Polygon()
    no_spray, spray = field_m.intersection(blocked), field_m.difference(blocked)
    spray_acres, excluded_acres = _acres(spray), _acres(no_spray)

    if prohibited or gaps or spray_acres < MIN_ACRES:
        status = "no-go"
    elif excluded_acres >= MIN_ACRES or runoff or unsure:
        status = "adjust"
    else:
        status = "go"

    back = list(gpd.GeoSeries([spray, no_spray], crs=utm).to_crs(4326))
    return {"status": status, "method": method, "field_acres": round(_acres(field_m), 2),
            "spray_acres": round(spray_acres, 2), "excluded_acres": round(excluded_acres, 2),
            "spray_zone": back[0], "no_spray": back[1], "reasons": reasons}
