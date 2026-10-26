import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box, mapping

from app import api, label_reader, pipeline
from app.label_reader import LabelRules

FIELD = box(-93.0, 42.0, -92.99, 42.01)
SPRAY = box(-93.0, 42.0, -92.995, 42.01)
NO_SPRAY = box(-92.995, 42.0, -92.99, 42.01)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(api, "DEMO", tmp_path / "demo")
    seen = {}

    def run(field_path, label_path, month, method):
        seen.update(field=field_path, label=label_path, month=month, method=method)
        return {"plan": {"spray_zone": SPRAY, "no_spray": NO_SPRAY}}

    monkeypatch.setattr(pipeline, "run", run)
    monkeypatch.setattr(pipeline, "to_json", lambda r: {"status": "adjust"})
    c = TestClient(api.app)
    c.seen = seen
    return c


def post_plan(client, label_name="label.pdf", **form):
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": (label_name, b"%PDF")}
    return client.post("/api/plan", files=files, data={"month": "2026-11", **form})


def test_plan_saves_uploads(client):
    r = post_plan(client)
    assert r.status_code == 200 and r.json()["status"] == "adjust"
    assert client.seen["label"].name == "label.pdf" and client.seen["method"] == "drone"
    assert client.seen["field"].read_text() == json.dumps(mapping(FIELD))


@pytest.mark.parametrize("kw", [{"label_name": "label.exe"}, {"month": "Nov"}, {"method": "jet"}])
def test_plan_rejects_bad_input(client, kw):
    assert post_plan(client, **kw).status_code == 422


def test_plan_missing_label(client):
    r = client.post("/api/plan", files={"field": ("f.geojson", "{}")}, data={"month": "2026-11"})
    assert r.status_code == 422


@pytest.mark.parametrize("err, code", [(ValueError("no polygon"), 422), (LookupError("no NAIP"), 502)])
def test_plan_maps_errors(client, monkeypatch, err, code):
    def boom(*a):
        raise err

    monkeypatch.setattr(pipeline, "run", boom)
    r = post_plan(client)
    assert r.status_code == code and str(err) in r.json()["detail"]


def test_kml_round_trip(client):
    run_id = post_plan(client).json()["run_id"]
    r = client.get(f"/api/kml/{run_id}")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.text.count("<Placemark") == 2 and "Spray zone" in r.text and "No spray" in r.text


def test_kml_keeps_holes(client, monkeypatch):
    holed = Polygon(FIELD.exterior.coords, [box(-92.998, 42.002, -92.996, 42.004).exterior.coords])
    monkeypatch.setattr(pipeline, "run", lambda *a: {"plan": {"spray_zone": holed, "no_spray": Polygon()}})
    run_id = post_plan(client).json()["run_id"]
    text = client.get(f"/api/kml/{run_id}").text
    assert "innerBoundaryIs" in text and text.count("<Placemark") == 1


@pytest.mark.parametrize("run_id", ["nope", "../" * 3 + "etc", "0" * 32])
def test_kml_bad_run_id(client, run_id):
    assert client.get(f"/api/kml/{run_id}").status_code == 404


def test_demo_missing_files(client):
    r = client.get("/api/demo")
    assert r.status_code == 404 and "data/demo" in r.json()["detail"]


def test_demo_runs(client, tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "field.geojson").write_text(json.dumps(mapping(FIELD)))
    (tmp_path / "demo" / "label.pdf").write_bytes(b"%PDF")
    r = client.get("/api/demo?month=2026-11&method=ground")
    assert r.status_code == 200 and client.seen["method"] == "ground"


def test_label(client, monkeypatch):
    lr = LabelRules(product_name="Acme", epa_reg_no="1-2", rules=[], dropped=[], source="pdf")
    monkeypatch.setattr(label_reader, "read_label", lambda p: lr)
    r = client.post("/api/label", files={"label": ("x.pdf", b"%PDF")})
    assert r.status_code == 200 and r.json()["epa_reg_no"] == "1-2"


def test_serves_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "<title>ClearSwath</title>" in r.text
