"""Field + label + month -> spray plan. Wires the modules together; status always comes from buffers.plan."""

import json
from pathlib import Path

from shapely.geometry import mapping

from app import buffers, bulletins, geo, label_reader, segment


class NotConfirmableError(ValueError):
    """An excluded rule id the user may not untick; the message is safe to show users."""


def run(field_path, label_path, month: str, method: str = "drone", excluded_rules=()) -> dict:
    label = label_reader.read_label(label_path)
    hazards = segment.find_hazards(field_path)
    bulletin = bulletins.check_bulletin(field_path, month, label.epa_reg_no)
    return assemble(geo.load_field(field_path), label, hazards, bulletin, month, method, excluded_rules)


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
    plan = buffers.plan(field, hazards, [r.model_dump() for r in rules],
                        bulletin["restricted"], method, bulletin["prohibited"])

    warnings = [f"You unticked: {label.rules[i].summary} (label p.{label.rules[i].page}"
                + (f", only when {label.rules[i].condition}" if label.rules[i].condition else "") + ")."
                for i in excluded]
    if not bulletin["checked"]:  # also covers a label with no usable EPA Reg. No.
        warnings.append(bulletin["citation"])
    unread = [x for x in bulletin["limitations"] if not bulletins.PROHIBITS.search(x["limitation"] or "")]
    for x in unread:
        warnings.append(f"Bulletin limitation (PULA {x['pula_id']}, code {x['code']}) must be read "
                        f"and followed: {x['limitation']}")
    if label.dropped:
        warnings.append(f"{len(label.dropped)} label rule(s) could not be verified and were not "
                        "applied. Check the label yourself.")
    if label.source == "image":
        warnings.append("Label was read from a photo; quotes were checked against a model transcription.")
    warnings += hazards.get("water_warnings") or []
    if not hazards.get("imagery_date"):
        warnings.append("No aerial imagery date; hazards may be incomplete.")

    return {"field": field, "month": month, "label": label, "hazards": hazards,
            "bulletin": bulletin, "plan": plan, "warnings": warnings, "excluded_rules": excluded}


def save_run(result: dict, run_dir: Path) -> None:
    """Writes what /api/kml and /api/record read back: plan.geojson and job.json."""
    plan, label, centre = result["plan"], result["label"], result["field"].centroid
    geo.save_shapes([plan["spray_zone"], plan["no_spray"]], Path(run_dir) / "plan.geojson",
                    [{"name": "Spray zone"}, {"name": "No spray"}])
    job = {"product_name": label.product_name, "epa_reg_no": label.epa_reg_no,
           "area_treated_acres": plan["spray_acres"], "location": f"{centre.y:.5f}, {centre.x:.5f}",
           "method": plan["method"]}
    (Path(run_dir) / "job.json").write_text(json.dumps(job))


def _fc(shapes) -> dict:
    return geo.to_feature_collection([s for s in shapes if s is not None and not s.is_empty])


def to_json(result: dict) -> dict:
    plan, bulletin = result["plan"], result["bulletin"]
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
        "layers": {
            "field": mapping(result["field"]),
            "spray_zone": _fc([plan["spray_zone"]]),
            "no_spray": _fc([plan["no_spray"]]),
            "restricted": _fc(bulletin["restricted"]),
            **{h: _fc(result["hazards"].get(h) or []) for h in ("water", "building", "habitat")},
        },
    }
