"""Field + label + month -> spray plan. Wires the modules together; status always comes from buffers.plan."""

from shapely.geometry import mapping

from app import buffers, bulletins, geo, label_reader, segment


def run(field_path, label_path, month: str, method: str = "drone") -> dict:
    field = geo.load_field(field_path)
    label = label_reader.read_label(label_path)
    hazards = segment.find_hazards(field_path)
    bulletin = bulletins.check_bulletin(field_path, month, label.epa_reg_no)
    plan = buffers.plan(field, hazards, [r.model_dump() for r in label.rules],
                        bulletin["restricted"], method, bulletin["prohibited"])

    warnings = []
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
    if not hazards.get("imagery_date"):
        warnings.append("No aerial imagery date; hazards may be incomplete.")

    return {"field": field, "month": month, "label": label, "hazards": hazards,
            "bulletin": bulletin, "plan": plan, "warnings": warnings}


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
