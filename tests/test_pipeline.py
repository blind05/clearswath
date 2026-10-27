import json

import geopandas as gpd
import pytest
from shapely.geometry import box, mapping

from app import bulletins, label_reader, pipeline, segment
from app.label_reader import LabelRule, LabelRules

UTM = 32615
X, Y = 500_000, 4_650_000


def ll(*shapes):
    return list(gpd.GeoSeries(shapes, crs=UTM).to_crs(4326))


FIELD, POND = ll(box(X, Y, X + 400, Y + 400), box(X + 410, Y + 150, X + 460, Y + 250))
RULE = LabelRule(kind="buffer", target="water", applies_to="all", value=100, unit="ft",
                 summary="100 ft from water", quote="Do not apply within 100 feet of water.", page=2)


def label(**kw):
    base = dict(product_name="Acme", epa_reg_no="123-45", rules=[RULE], dropped=[], source="pdf")
    return LabelRules(**(base | kw))


def bulletin(**kw):
    base = {"in_pula": False, "prohibited": False, "limitations": [], "restricted": [],
            "citation": "EPA BLT: no PULA applies.", "checked": True}
    return base | kw


@pytest.fixture
def field_path(tmp_path):
    p = tmp_path / "field.geojson"
    p.write_text(json.dumps(mapping(FIELD)))
    return p


def wire(monkeypatch, lbl=None, blt=None):
    seen = {}
    monkeypatch.setattr(label_reader, "read_label", lambda p: lbl or label())
    monkeypatch.setattr(segment, "find_hazards", lambda p: {
        "water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09",
        "water_source": "usgs"})

    def check(fp, month, reg_no):
        seen["reg_no"] = reg_no
        return blt or bulletin()

    monkeypatch.setattr(bulletins, "check_bulletin", check)
    return seen


def test_run_adjusts_for_label_buffer(monkeypatch, field_path):
    seen = wire(monkeypatch)
    result = pipeline.run(field_path, "label.pdf", "2026-11")
    assert result["plan"]["status"] == "adjust" and result["warnings"] == []
    assert seen["reg_no"] == "123-45"
    assert result["plan"]["reasons"][0]["quote"] == RULE.quote


def test_bulletin_prohibition_is_no_go(monkeypatch, field_path):
    wire(monkeypatch, blt=bulletin(in_pula=True, prohibited=True, restricted=[FIELD],
                                   limitations=[{"pula_id": 2, "code": "100", "event_name": "X",
                                                 "limitation": "Do not apply within this county"}]))
    result = pipeline.run(field_path, "label.pdf", "2026-11")
    assert result["plan"]["status"] == "no-go"
    assert result["warnings"] == []  # a ban is applied as geometry, not repeated as a warning


def test_warnings(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(epa_reg_no=None, source="image", dropped=[{"reason": "x"}]),
         blt=bulletin(checked=False, citation="Could not check BLT.",
                      limitations=[{"pula_id": 15, "code": "T1", "event_name": "Y",
                                    "limitation": "See link for limitations."}]))
    w = pipeline.run(field_path, "label.png", "2026-11")["warnings"]
    assert len(w) == 4
    assert "Could not check BLT." in w and any("PULA 15" in x for x in w)


def test_to_json_is_serializable(monkeypatch, field_path):
    wire(monkeypatch)
    out = pipeline.to_json(pipeline.run(field_path, "label.pdf", "2026-11"))
    json.dumps(out)
    assert out["status"] == "adjust" and out["acres"]["excluded_acres"] > 0
    assert len(out["layers"]["water"]["features"]) == 1
    assert out["layers"]["restricted"]["features"] == []
    assert out["label"]["rules"][0]["page"] == 2


def test_missing_water_data_is_no_go(monkeypatch, field_path):
    wire(monkeypatch)
    monkeypatch.setattr(segment, "find_hazards", lambda p: {
        "water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09",
        "water_source": "usgs", "water_warnings": ["USGS stream data was unavailable"]})
    result = pipeline.run(field_path, "label.pdf", "2026-11")
    plan = result["plan"]
    assert plan["status"] == "no-go" and plan["spray_acres"] == 0 and plan["spray_zone"].is_empty
    assert {"source": "data", "summary": "USGS stream data was unavailable"} in plan["reasons"]
    assert result["warnings"] == []  # it's the reason for NO-GO, not repeated as a warning


def test_unverified_buffer_rule_is_no_go(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(dropped=[{"kind": "buffer", "reason": "quote not found in label text"},
                                         {"kind": "wind", "reason": "quote not found in label text"}]))
    result = pipeline.run(field_path, "label.pdf", "2026-11")
    assert result["plan"]["status"] == "no-go"
    assert any(r["source"] == "data" and r["summary"].startswith("1 buffer rule(s)") for r in result["plan"]["reasons"])
    assert result["warnings"] == ["1 label rule(s) could not be verified and were not applied. Check the label yourself."]


def test_unverified_non_buffer_rule_is_only_a_warning(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(dropped=[{"kind": "wind", "reason": "quote not found in label text"}]))
    assert pipeline.run(field_path, "label.pdf", "2026-11")["plan"]["status"] == "adjust"


ULV = RULE.model_copy(update={"value": 2000.0, "condition": "ULV aerial only",
                             "quote": "Do not apply within 2000 feet of water."})


def test_conditional_rule_applies_until_unticked(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(rules=[RULE, ULV]))
    # applied by default: 2000 ft swallows the field
    strict = pipeline.run(field_path, "label.pdf", "2026-11")
    assert strict["plan"]["status"] == "no-go" and strict["excluded_rules"] == []
    out = pipeline.to_json(strict)
    assert [(c["id"], c["applied"], c["condition"]) for c in out["confirm"]] == [(1, True, "ULV aerial only")]

    # the applicator unticks it: back to the 100 ft rule, and the result says a human did that
    loose = pipeline.run(field_path, "label.pdf", "2026-11", excluded_rules=[1])
    assert loose["plan"]["status"] == "adjust"
    assert [r["distance_ft"] for r in loose["plan"]["reasons"]] == [100]
    assert loose["warnings"][0].startswith("You unticked: 100 ft from water (label p.2, only when ULV aerial only)")
    assert pipeline.to_json(loose)["confirm"][0]["applied"] is False


def test_unconditional_rule_cannot_be_unticked(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(rules=[RULE, ULV]))
    with pytest.raises(pipeline.NotConfirmableError, match=r"rule ids \[0\]"):
        pipeline.run(field_path, "label.pdf", "2026-11", excluded_rules=[0])


def test_photo_rules_all_need_confirmation(monkeypatch, field_path):
    wire(monkeypatch, lbl=label(source="image"))
    result = pipeline.run(field_path, "label.png", "2026-11", excluded_rules=[0])
    assert result["plan"]["status"] == "go"  # the only buffer was unticked
    assert [c["id"] for c in pipeline.to_json(result)["confirm"]] == [0]


def test_conditional_non_buffer_rules_need_no_confirmation(monkeypatch, field_path):
    rice = RULE.model_copy(update={"kind": "other", "target": None, "condition": "rice only"})
    wire(monkeypatch, lbl=label(rules=[RULE, rice, ULV]))
    assert [c["id"] for c in pipeline.to_json(pipeline.run(field_path, "l.pdf", "2026-11"))["confirm"]] == [2]


def test_imagery_warnings_reach_the_applicator(monkeypatch, field_path):
    wire(monkeypatch)
    monkeypatch.setattr(segment, "find_hazards", lambda p: {
        "water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09",
        "water_source": "usgs", "imagery_warnings": ["Aerial imagery is missing for 37%"]})
    assert pipeline.run(field_path, "label.pdf", "2026-11")["warnings"] == ["Aerial imagery is missing for 37%"]


def raw_label():
    quote = RULE.quote
    return {"pages": ["Acme EPA Reg. No. 123-45", f"x {quote} y"], "source": "pdf",
            "out": {"product_name": "Acme", "epa_reg_no": "123-45", "rules": [RULE.model_dump() | {"page": 2}]}}


def test_inputs_round_trip_gives_the_same_plan(tmp_path):
    hazards = {"water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09",
               "water_source": "usgs", "water_warnings": [], "imagery_warnings": []}
    pipeline.save_inputs(tmp_path / "c", FIELD, raw_label(), hazards, bulletin(), "2026-11")
    field, lbl, hz, blt, month = pipeline.load_inputs(tmp_path / "c")
    again = pipeline.assemble(field, lbl, hz, blt, month, "drone")
    direct = pipeline.assemble(FIELD, label_reader.verify(raw_label()), hazards, bulletin(), "2026-11", "drone")
    assert month == "2026-11" and lbl.rules[0].quote == RULE.quote
    assert {k: again["plan"][k] for k in ("status", "spray_acres")} == {k: direct["plan"][k] for k in ("status", "spray_acres")}


def test_loaded_label_is_reverified(tmp_path):
    raw = raw_label()
    raw["out"]["rules"][0]["quote"] = "Do not apply within 5 feet of water."  # not on the label
    pipeline.save_inputs(tmp_path / "c", FIELD, raw, {"water": [], "building": [], "habitat": []}, bulletin(), "2026-11")
    _, lbl, *_ = pipeline.load_inputs(tmp_path / "c")
    assert lbl.rules == [] and lbl.dropped[0]["reason"] == "quote not found in label text"
