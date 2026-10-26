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


def test_water_warnings_reach_the_applicator(monkeypatch, field_path):
    wire(monkeypatch)
    monkeypatch.setattr(segment, "find_hazards", lambda p: {
        "water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09",
        "water_source": "usgs", "water_warnings": ["USGS pond and lake data was unavailable"]})
    result = pipeline.run(field_path, "label.pdf", "2026-11")
    assert result["warnings"] == ["USGS pond and lake data was unavailable"]
    assert result["plan"]["status"] == "adjust"  # warnings never change the decision
