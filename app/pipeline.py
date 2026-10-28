"""Field + label + month -> spray plan. Wires the modules together; status always comes from buffers.plan."""

import json
from pathlib import Path

from shapely import union_all
from shapely.geometry import mapping, shape

from app import buffers, bulletins, cells, geo, label_reader, segment

CELL_M = 1.0  # ponytail: one spot-spray cell size for every sprayer; make it a setting when sprayers differ
SHAPES = ("water", "building", "habitat", "weeds")


class NotConfirmableError(ValueError):
    """An excluded rule id the user may not untick; the message is safe to show users."""


def run(field_path, label_path, month: str, method: str = "drone", excluded_rules=()) -> dict:
    field = geo.load_field(field_path)  # validated first: a bad field must not cost a paid label read
    label = label_reader.read_label(label_path)
    hazards = segment.find_hazards(field_path)
    bulletin = bulletins.check_bulletin(field_path, month, label.epa_reg_no)
    return assemble(field, label, hazards, bulletin, month, method, excluded_rules)


def confirmable(label) -> list[int]:
    """Rule ids (indexes into label.rules) the user may untick: conditional buffers (the only conditional rules
    that change the map), or every rule read from a photo."""
    return [i for i, r in enumerate(label.rules) if (r.condition and r.kind == "buffer") or label.source == "image"]


def assemble(field, label, hazards: dict, bulletin: dict, month: str, method: str, excluded_rules=()) -> dict:
    """Plan from already-gathered inputs, plus the warnings the applicator must see.

    Every rule is applied unless the user unticked it, and only rules needing confirmation can be
    unticked. A model's condition can only make the plan stricter; loosening it takes a human.
    """
    excluded = sorted(set(excluded_rules))
    allowed = confirmable(label)
    if bad := [i for i in excluded if i not in allowed]:
        raise NotConfirmableError(f"Only conditional or photo-read rules can be unticked (rule ids {bad}).")
    rules = [r for i, r in enumerate(label.rules) if i not in excluded]
    # Data the plan can't do without. Each makes the plan NO-GO (fail closed) instead of a warning.
    gaps = list(hazards.get("water_warnings") or [])
    dropped_buffers = [d for d in label.dropped if d.get("kind") == "buffer"]
    if dropped_buffers:
        gaps.append(f"{len(dropped_buffers)} buffer rule(s) on the label could not be verified, so a required "
                    "setback may be missing. Check the label, or try again.")
    plan = buffers.plan(field, hazards, [r.model_dump() for r in rules],
                        bulletin["restricted"], method, bulletin["prohibited"], gaps)

    warnings = [f"You unticked: {label.rules[i].summary} (label p.{label.rules[i].page}"
                + (f", only when {label.rules[i].condition}" if label.rules[i].condition else "") + ")."
                for i in excluded]
    if not bulletin["checked"]:  # also covers a label with no usable EPA Reg. No.
        warnings.append(bulletin["citation"])
    unread = [x for x in bulletin["limitations"] if not bulletins.PROHIBITS.search(x["limitation"] or "")]
    for x in unread:
        warnings.append(f"Bulletin limitation (PULA {x['pula_id']}, code {x['code']}) must be read "
                        f"and followed: {x['limitation']}")
    if other_dropped := len(label.dropped) - len(dropped_buffers):
        warnings.append(f"{other_dropped} label rule(s) could not be verified and were not "
                        "applied. Check the label yourself.")
    if label.source == "image":
        warnings.append("Label was read from a photo; quotes were checked against a model transcription.")
    warnings += hazards.get("imagery_warnings") or []  # water gaps are reasons for NO-GO, not warnings
    if not hazards.get("imagery_date"):
        warnings.append("No aerial imagery date; hazards may be incomplete.")

    grid = spot_cells(field, plan, hazards["weeds"]) if hazards.get("weeds") is not None else None
    return {"field": field, "month": month, "label": label, "hazards": hazards, "bulletin": bulletin,
            "plan": plan, "cells": grid, "warnings": warnings, "excluded_rules": excluded}


def spot_cells(field, plan: dict, weeds: list) -> dict:
    """Spot-spray grid: weed cells inside the spray zone. On a NO-GO plan the whole field is blocked."""
    blocked = field if plan["status"] == "no-go" else plan["no_spray"]
    return cells.classify(field, weeds, blocked, CELL_M)


def save_inputs(cache_dir: Path, field, label_raw: dict, hazards: dict, bulletin: dict, month: str) -> None:
    """Everything a plan needs except the user's choices, as JSON (the demo cache)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    shapes = SHAPES
    (cache_dir / "inputs.json").write_text(json.dumps({
        "month": month, "field": mapping(field), "label_raw": label_raw,
        "hazards": {k: ([mapping(s) for s in v] if k in shapes else v) for k, v in hazards.items()},
        "bulletin": bulletin | {"restricted": [mapping(s) for s in bulletin["restricted"]]},
    }))


def load_inputs(cache_dir: Path) -> tuple:
    """(field, label, hazards, bulletin, month) from save_inputs. The label's quotes are re-verified."""
    d = json.loads((Path(cache_dir) / "inputs.json").read_text())
    shapes = SHAPES
    hazards = {k: ([shape(g) for g in v] if k in shapes else v) for k, v in d["hazards"].items()}
    bulletin = d["bulletin"] | {"restricted": [shape(g) for g in d["bulletin"]["restricted"]]}
    return shape(d["field"]), label_reader.verify(d["label_raw"]), hazards, bulletin, d["month"]


def save_run(result: dict, run_dir: Path) -> None:
    """Writes what /api/kml and /api/record read back: plan.geojson and job.json."""
    plan, label, centre = result["plan"], result["label"], result["field"].centroid
    geo.save_shapes([plan["spray_zone"], plan["no_spray"]], Path(run_dir) / "plan.geojson",
                    [{"name": "Spray zone"}, {"name": "No spray"}])
    treated = cells.summary(result["cells"])["treated_acres"] if result.get("cells") else plan["spray_acres"]
    job = {"product_name": label.product_name, "epa_reg_no": label.epa_reg_no, "area_treated_acres": treated, "location": f"{centre.y:.5f}, {centre.x:.5f}",
           "method": plan["method"]}
    (Path(run_dir) / "job.json").write_text(json.dumps(job))


def _fc(shapes) -> dict:
    return geo.to_feature_collection([s for s in shapes if s is not None and not s.is_empty])


def _cell_layers(grid: dict | None) -> dict:
    """One merged shape per state: a field has ~10,000 cells per hectare, far too many to send one by one."""
    if grid is None:
        return {}
    return {f"{state}_cells": _fc([union_all([c["geometry"] for c in grid["cells"] if c["state"] == state])])
            for state in ("spray", "buffered")}


def to_json(result: dict) -> dict:
    plan, bulletin, grid = result["plan"], result["bulletin"], result.get("cells")
    return {
        "status": plan["status"],
        "method": plan["method"],
        "month": result["month"],
        "acres": {k: plan[k] for k in ("field_acres", "spray_acres", "excluded_acres")},
        "reasons": plan["reasons"],
        "warnings": result["warnings"],
        "label": result["label"].model_dump(),
        # rules the user can untick; each is applied unless its id is in excluded_rules
        "confirm": [{"id": i, **result["label"].rules[i].model_dump(),
                     "applied": i not in result.get("excluded_rules", [])}
                    for i in confirmable(result["label"])],
        "excluded_rules": result.get("excluded_rules", []),
        "bulletin": {k: v for k, v in bulletin.items() if k != "restricted"},
        "imagery_date": result["hazards"].get("imagery_date"),
        "water_source": result["hazards"].get("water_source"),
        "weed_source": result["hazards"].get("weed_source"),
        "spot": cells.summary(grid) if grid else None,
        "layers": {
            "field": mapping(result["field"]),
            "spray_zone": _fc([plan["spray_zone"]]),
            "no_spray": _fc([plan["no_spray"]]),
            "restricted": _fc(bulletin["restricted"]),
            **{h: _fc(result["hazards"].get(h) or []) for h in ("water", "building", "habitat")},
            **_cell_layers(grid),
        },
    }
