"""The demo story end to end on the committed demo cache: real app, real pipeline, no network.

If a change alters what the video shows, a number here fails.
"""

import socket

import pytest
from fastapi.testclient import TestClient

from app import api, llm


@pytest.fixture
def client(tmp_path, monkeypatch):
    def no_network(*a, **kw):
        raise AssertionError("the demo must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    return TestClient(api.app)


def demo(client, field="", method="drone", excluded=""):
    r = client.get("/api/demo", params={"field": field, "method": method, "excluded_rules": excluded})
    assert r.status_code == 200, r.text
    return r.json()


def ulv_id(body) -> str:
    (c,) = [c for c in body["confirm"] if c["value"] == 450 and c["target"] == "water"]
    assert c["applies_to"] == "aerial" and c["condition"]
    return str(c["id"])


def test_demo_story(client):
    # 1. drone, field drawn up to the creek, every rule applied: the ULV 450 ft buffer is in force
    first = demo(client)
    assert first["demo"] == {"field": "", "cached": True, "month": "2026-11"}
    assert first["label"]["epa_reg_no"] == "100-1295" and first["status"] == "adjust"
    assert 450 in [r["distance_ft"] for r in first["reasons"]]

    # 2. untick the ULV-only rule: the 150 ft drone buffer still takes a strip along the creek
    ulv = ulv_id(first)
    mistake = demo(client, excluded=ulv)
    assert mistake["status"] == "adjust" and mistake["acres"]["excluded_acres"] == pytest.approx(1.57, abs=0.05)
    (reason,) = mistake["reasons"]
    assert reason["distance_ft"] == 150 and reason["page"] == 14
    assert reason["quote"].startswith("Do not apply within 150 feet of aquatic habitats")
    assert mistake["warnings"][0].startswith("You unticked:")

    # 3. the corrected outline, same choice: green across the whole field
    fixed = demo(client, field="corrected", excluded=ulv)
    assert fixed["status"] == "go" and fixed["reasons"] == []
    assert fixed["acres"]["spray_acres"] == pytest.approx(31.17, abs=0.05)

    # 4. ground rigs only need 25 ft, which doesn't reach either outline
    for field in ("", "corrected"):
        assert demo(client, field=field, method="ground")["status"] == "go"

    # 5. the KML for the ADJUST run has both zones
    kml = client.get(f"/api/kml/{mistake['run_id']}")
    assert kml.status_code == 200 and kml.text.count("<Placemark") == 2


def test_demo_record_uses_the_plan(client, monkeypatch):
    run_id = demo(client, field="corrected", excluded=ulv_id(demo(client)))["run_id"]
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: {
        "applicator_name": "Sam Ortiz", "certification_number": None, "application_date": "2026-11-02",
        "start_time": None, "end_time": None, "amount_applied": "12 gal", "rate": None,
        "crop_or_site": "soybeans", "wind_speed_mph": 6, "wind_direction": "NW", "temperature_f": None,
        "notes": None})
    r = client.post("/api/record", data={"run_id": run_id, "text": "Sam Ortiz, 12 gallons on soybeans"})
    rec = r.json()
    assert r.status_code == 200 and rec["product_name"] == "Warrior II with Zeon Technology"
    assert rec["epa_reg_no"] == "100-1295" and rec["area_treated_acres"] == pytest.approx(31.17, abs=0.05)
    assert rec["method"] == "drone" and rec["missing"] == ["certification_number"]
