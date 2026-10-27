import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box, mapping

from app import api, imagery, label_reader, llm, pipeline, records
from app.label_reader import LabelRules

FIELD = box(-93.0, 42.0, -92.99, 42.01)
SPRAY = box(-93.0, 42.0, -92.995, 42.01)
NO_SPRAY = box(-92.995, 42.0, -92.99, 42.01)
LABEL = LabelRules(product_name="INTREPID 2F", epa_reg_no="62719-442", rules=[], dropped=[], source="pdf")


def result(spray=SPRAY, no_spray=NO_SPRAY, method="drone"):
    return {"field": FIELD, "label": LABEL,
            "plan": {"spray_zone": spray, "no_spray": no_spray, "spray_acres": 35.5, "method": method}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(api, "DEMO", tmp_path / "demo")
    seen = {}

    def run(field_path, label_path, month, method, excluded_rules=()):
        seen.update(field=field_path, label=label_path, month=month, method=method, excluded=excluded_rules)
        return result(method=method)

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


@pytest.mark.parametrize("err, code, shown", [
    (imagery.NoImageryError("No NAIP imagery covers this"), 502, True),
    (llm.MissingKeyError("MODEL_API_KEY is not set."), 502, True),
    (ValueError("No polygon found in /srv/secret/field.geojson"), 422, False),
    (RuntimeError("upstream 500: internal details"), 502, False),
    (KeyError("plan"), 502, False),  # a bug, not missing imagery
])
def test_plan_maps_errors(client, monkeypatch, caplog, err, code, shown):
    def boom(*a):
        raise err

    monkeypatch.setattr(pipeline, "run", boom)
    r = post_plan(client)
    assert r.status_code == code and (str(err) in r.json()["detail"]) == shown
    if not shown:
        assert str(err) in caplog.text


def test_kml_round_trip(client):
    run_id = post_plan(client).json()["run_id"]
    r = client.get(f"/api/kml/{run_id}")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.text.count("<Placemark") == 2 and "Spray zone" in r.text and "No spray" in r.text


def test_kml_keeps_holes(client, monkeypatch):
    holed = Polygon(FIELD.exterior.coords, [box(-92.998, 42.002, -92.996, 42.004).exterior.coords])
    monkeypatch.setattr(pipeline, "run", lambda *a: result(holed, Polygon()))
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


def test_plan_saves_job(client, tmp_path):
    run_id = post_plan(client).json()["run_id"]
    job = json.loads((tmp_path / "runs" / run_id / "job.json").read_text())
    assert job == {"product_name": "INTREPID 2F", "epa_reg_no": "62719-442", "area_treated_acres": 35.5,
                   "location": "42.00500, -92.99500", "method": "drone"}


@pytest.fixture
def fake_records(monkeypatch):
    seen = {}
    monkeypatch.setattr(records, "transcribe", lambda p: seen.update(audio=p) or "heard text")

    def fill(text, job):
        seen.update(text=text, job=job)
        return records.AppRecord(transcript=text, product_name=job["product_name"], missing=["applicator_name"])

    monkeypatch.setattr(records, "fill_record", fill)
    return seen


def test_record_from_text(client, fake_records):
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id, "text": "Sam, 12 gal"})
    assert r.status_code == 200 and r.json()["product_name"] == "INTREPID 2F"
    assert fake_records["text"] == "Sam, 12 gal" and "audio" not in fake_records


def test_record_from_audio(client, fake_records):
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.wav", b"audio")})
    assert r.status_code == 200 and fake_records["text"] == "heard text"
    assert fake_records["audio"].name == "note.wav"


@pytest.mark.parametrize("data, files, code", [
    ({"text": "x"}, None, 404),
    ({}, None, 422),
    ({"text": "   "}, None, 422),
    ({}, {"audio": ("note.exe", b"x")}, 422),
])
def test_record_rejects(client, fake_records, data, files, code):
    run_id = post_plan(client).json()["run_id"] if code != 404 else "0" * 32
    assert client.post("/api/record", data={"run_id": run_id, **data}, files=files).status_code == code


def post_agent(client, **form):
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("label.pdf", b"%PDF")}
    return client.post("/api/agent", files=files, data={"month": "2026-11", **form})


@pytest.fixture
def fake_agent(monkeypatch):
    seen = {}

    def run(field_path, label_path, month, method, excluded_rules=()):
        seen.update(method=method, label=label_path, excluded=excluded_rules)
        return {"run_id": "a" * 32, "answer": "ADJUST: stay back from the pond.", "decision": "adjust",
                "trace": [{"tool": "plan_spray", "result": {"decision": "ADJUST"}, "seconds": 0.1}],
                "mode": "agent", "result": result()}

    monkeypatch.setattr(api.agent, "run", run)
    return seen


def test_agent_endpoint(client, fake_agent):
    r = post_agent(client, method="ground")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "adjust" and body["decision"] == "adjust"
    assert body["run_id"] == "a" * 32 and body["mode"] == "agent" and body["trace"][0]["tool"] == "plan_spray"
    assert "result" not in body and fake_agent["method"] == "ground" and fake_agent["label"].name == "label.pdf"


def test_agent_endpoint_validates(client, fake_agent):
    assert post_agent(client, month="Nov").status_code == 422 and fake_agent == {}


def test_agent_endpoint_maps_errors(client, monkeypatch):
    def boom(*a):
        raise imagery.NoImageryError("No NAIP imagery")

    monkeypatch.setattr(api.agent, "run", boom)
    r = post_agent(client)
    assert r.status_code == 502 and "NAIP" in r.json()["detail"]


def test_record_bad_audio_is_explained(client, monkeypatch):
    def bad(p):
        raise llm.BadAudioError("Voice note must be mono 16-bit WAV at 16 or 24 kHz.")

    monkeypatch.setattr(records, "transcribe", bad)
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.wav", b"x")})
    assert r.status_code == 422 and "16-bit WAV" in r.json()["detail"]


def test_record_rejects_m4a(client):
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.m4a", b"x")})
    assert r.status_code == 422 and ".wav" in r.json()["detail"]


def test_excluded_rules_reach_the_pipeline(client):
    assert post_plan(client, excluded_rules="1, 3").status_code == 200
    assert client.seen["excluded"] == [1, 3]


def test_excluded_rules_reach_the_agent(client, fake_agent):
    assert post_agent(client, excluded_rules="2").status_code == 200 and fake_agent["excluded"] == [2]


def test_excluded_rules_must_be_ids(client):
    r = post_plan(client, excluded_rules="ulv")
    assert r.status_code == 422 and "rule ids" in r.json()["detail"]


def test_refused_untick_is_explained(client, monkeypatch):
    def refuse(*a):
        raise pipeline.NotConfirmableError("Only conditional or photo-read rules can be unticked (rule ids [0]).")

    monkeypatch.setattr(pipeline, "run", refuse)
    r = post_plan(client, excluded_rules="0")
    assert r.status_code == 422 and "can be unticked" in r.json()["detail"]


class SdkError(Exception):
    """Like openai.APIConnectionError or a STAC/rasterio error: not a ValueError/RuntimeError subclass."""


def test_any_service_error_is_a_friendly_502(client, monkeypatch, caplog):
    def boom(*a):
        raise SdkError("upstream said: internal details")

    monkeypatch.setattr(pipeline, "run", boom)
    r = post_plan(client)
    assert r.status_code == 502 and "details are in the server log" in r.json()["detail"]
    assert "internal details" not in r.text and "internal details" in caplog.text


def test_record_service_error_is_a_friendly_502(client, monkeypatch):
    run_id = post_plan(client).json()["run_id"]

    def boom(text, job):
        raise SdkError("rate limited")

    monkeypatch.setattr(records, "fill_record", boom)
    r = client.post("/api/record", data={"run_id": run_id, "text": "Sam"})
    assert r.status_code == 502 and "rate limited" not in r.text


def test_label_service_error_is_a_friendly_502(client, monkeypatch):
    def boom(p):
        raise SdkError("connection reset")

    monkeypatch.setattr(label_reader, "read_label", boom)
    r = client.post("/api/label", files={"label": ("x.pdf", b"%PDF")})
    assert r.status_code == 502 and "connection reset" not in r.text
