import gzip
import json
from collections import deque

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box, mapping

from app import api, imagery, label_reader, llm, pipeline, records, spend
from app.label_reader import LabelRules

REAL_TO_JSON = pipeline.to_json  # the client fixture stubs it; the cached demo test needs the real one
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
    monkeypatch.setenv("RUNS_PER_IP_PER_DAY", "100")  # tests post many runs from one address
    monkeypatch.setattr(api, "DEMO", tmp_path / "demo")
    seen = {}

    def run(field_path, label_path, month, method, excluded_rules=(), managed=(), wind_from_deg=None):
        seen.update(field=field_path, label=label_path, month=month, method=method, excluded=excluded_rules,
                    managed=managed, wind=wind_from_deg)
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
                   "location": "42.00500, -92.99500", "method": "drone", "carrier_min": None,
                   "carrier_unverified": False}


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
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.wav", b"RIFF\x24\x00\x00\x00WAVEfmt ")})
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

    def run(field_path, label_path, month, method, excluded_rules=(), managed=(), wind_from_deg=None):
        seen.update(method=method, label=label_path, excluded=excluded_rules, managed=managed, wind=wind_from_deg)
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
    def boom(*a, **kw):
        raise imagery.NoImageryError("No NAIP imagery")

    monkeypatch.setattr(api.agent, "run", boom)
    r = post_agent(client)
    assert r.status_code == 502 and "NAIP" in r.json()["detail"]


def test_record_bad_audio_is_explained(client, monkeypatch):
    def bad(p):
        raise llm.BadAudioError("Voice note must be mono 16-bit WAV at 16 or 24 kHz.")

    monkeypatch.setattr(records, "transcribe", bad)
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.wav", b"RIFF\x24\x00\x00\x00WAVEfmt ")})
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


@pytest.fixture
def cached_demo(tmp_path, monkeypatch):
    from shapely.geometry import box as _box

    from app import bulletins, segment

    quote = "Do not apply within 100 feet of water."
    raw = {"pages": ["Acme", f"x {quote}"], "source": "pdf",
           "out": {"product_name": "Acme", "epa_reg_no": "1-2", "rules": [
               {"kind": "buffer", "target": "water", "applies_to": "all", "value": 100, "unit": "ft",
                "summary": "100 ft from water", "quote": quote, "page": 2, "condition": None}]}}
    pond = _box(-92.98995, 42.0, -92.9899, 42.01)  # ~4 m east of FIELD's east edge
    blt = {"in_pula": False, "prohibited": False, "limitations": [], "restricted": [], "citation": "c",
           "checked": True}
    for name in ("field", "field_corrected"):
        pipeline.save_inputs(tmp_path / "demo" / "cache" / name, FIELD, raw,
                             {"water": [pond], "building": [], "habitat": [], "imagery_date": "2022-08-03"},
                             blt, "2026-11")

    def offline(*a, **kw):
        raise AssertionError("the cached demo must not go live")

    for mod, fn in ((pipeline, "run"), (segment, "find_hazards"), (bulletins, "check_bulletin")):
        monkeypatch.setattr(mod, fn, offline)
    monkeypatch.setattr(pipeline, "to_json", REAL_TO_JSON)


def test_cached_demo_is_offline_and_recomputed(client, cached_demo):
    r = client.get("/api/demo?method=ground&field=corrected")
    body = r.json()
    assert r.status_code == 200 and body["demo"] == {"field": "corrected", "cached": True, "month": "2026-11",
                                                     "overlay": None}
    assert body["status"] == "adjust" and body["reasons"][0]["distance_ft"] == 100
    assert client.get(f"/api/kml/{body['run_id']}").status_code == 200


def test_demo_with_drone_image(client, cached_demo, tmp_path):
    import shutil

    mt = tmp_path / "demo" / "mt"
    mt.mkdir(parents=True)
    (mt / "block.webp").write_bytes(b"RIFF....WEBP")
    (mt / "block_bounds.json").write_text(json.dumps({"crs": "EPSG:4326", "bounds": [-114.04, 46.70, -114.03, 46.71]}))
    shutil.copytree(tmp_path / "demo" / "cache" / "field", tmp_path / "demo" / "cache" / "mt")
    body = client.get("/api/demo?field=mt").json()
    assert body["demo"]["overlay"] == {"url": "/api/demo/image/mt", "bounds": [-114.04, 46.70, -114.03, 46.71],
                                       "credit": None}
    r = client.get(body["demo"]["overlay"]["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert client.get("/api/demo/image/field").status_code == 404  # that demo has no image
    assert client.get("/api/demo/image/..%2F..%2Fapp").status_code == 404


def test_demo_rejects_unknown_field(client):
    assert client.get("/api/demo?field=other").status_code == 422


def test_page_pins_its_scripts(client):
    """The built page (web/dist) loads nothing from third parties; the plain page pins each script with a hash."""
    import re

    page = client.get("/").text
    tags = re.findall(r"<(?:script|link)[^>]+(?:src|href)=\"https://[^\"]+\"[^>]*>", page)
    if api.WEB.name == "dist":
        assert tags == []
        bundle = "".join(client.get(f"/{src}").text for src in re.findall(r'src="/?(assets/[^"]+\.js)"', page))
        assert "basemap.nationalmap.gov" in bundle and "remain responsible" in bundle
    else:
        assert any("leaflet-draw@1.0.4" in t for t in tags) and len(tags) == 4
        assert all('integrity="sha256-' in t for t in tags)
        assert "basemap.nationalmap.gov" in page and "remain responsible" in page


def test_page_is_revalidated_but_its_bundles_cache(client):
    import re

    page = client.get("/")
    assert page.headers["cache-control"] == "no-cache"
    for src in re.findall(r'src="/?(assets/[^"]+\.js)"', page.text)[:1]:
        r = client.get(f"/{src}")
        assert r.status_code == 200 and "cache-control" not in r.headers


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_access_code_gates_paid_endpoints(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    r = post_plan(client)
    assert r.status_code == 401 and "access code" in r.json()["detail"]
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("label.pdf", b"%PDF")}
    wrong = client.post("/api/plan", files=files, data={"month": "2026-11"}, headers={"X-Access-Code": "nope"})
    assert wrong.status_code == 401
    ok = client.post("/api/plan", files=files, data={"month": "2026-11"}, headers={"X-Access-Code": "s3cret-code-for-tests"})
    assert ok.status_code == 200
    for url in ("/api/agent", "/api/label", "/api/record"):
        assert client.post(url, data={"run_id": "0" * 32, "month": "2026-11"},
                           files={"label": ("x.pdf", b"%PDF"), "field": ("f.geojson", b"{}")}).status_code == 401


def test_free_endpoints_stay_open(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/api/demo").status_code == 404  # no demo files in this test: not 401
    assert client.get("/api/kml/" + "0" * 32).status_code == 404


def test_render_without_a_code_refuses_to_spend(client, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    r = post_plan(client)
    assert r.status_code == 503 and "demo" in r.json()["detail"]


def test_per_ip_daily_limit(client, monkeypatch):
    monkeypatch.setenv("RUNS_PER_IP_PER_DAY", "2")
    assert [post_plan(client).status_code for _ in range(3)] == [200, 200, 429]
    other = client.post("/api/plan", headers={"X-Forwarded-For": "203.0.113.9"}, data={"month": "2026-11"},
                        files={"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("l.pdf", b"%PDF")})
    assert other.status_code == 200  # a different address has its own budget


def test_daily_cap_across_everyone(client, monkeypatch):
    monkeypatch.setenv("DAILY_RUN_CAP", "2")
    codes = [client.post("/api/plan", headers={"X-Forwarded-For": f"203.0.113.{i}"}, data={"month": "2026-11"},
                         files={"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("l.pdf", b"%PDF")}
                         ).status_code for i in range(3)]
    assert codes == [200, 200, 503]


def test_forwarded_for_uses_the_last_hop(client, monkeypatch):
    monkeypatch.setenv("RUNS_PER_IP_PER_DAY", "1")
    spoof = {"X-Forwarded-For": "1.1.1.1, 198.51.100.7"}
    files = lambda: {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("l.pdf", b"%PDF")}  # noqa: E731
    assert client.post("/api/plan", headers=spoof, data={"month": "2026-11"}, files=files()).status_code == 200
    # changing the forged first entry doesn't buy a new budget
    spoof2 = {"X-Forwarded-For": "9.9.9.9, 198.51.100.7"}
    assert client.post("/api/plan", headers=spoof2, data={"month": "2026-11"}, files=files()).status_code == 429


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "no"])
def test_kill_switch_stops_paid_endpoints(client, monkeypatch, value):
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", value)
    r = post_plan(client)
    assert r.status_code == 503 and "switched off" in r.json()["detail"]
    assert client.post("/api/record", data={"run_id": "0" * 32, "text": "x"}).status_code == 503


def test_kill_switch_off_by_default_and_when_on(client, monkeypatch):
    assert post_plan(client).status_code == 200
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", "on")
    assert post_plan(client).status_code == 200


def test_cached_demo_ignores_the_kill_switch(client, cached_demo, monkeypatch):
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", "off")
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    assert client.get("/api/demo?method=ground").status_code == 200


def test_uncached_demo_is_gated_like_a_live_run(client, tmp_path, monkeypatch):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "field.geojson").write_text(json.dumps(mapping(FIELD)))
    (tmp_path / "demo" / "label.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", "off")
    assert client.get("/api/demo").status_code == 503
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", "on")
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    assert client.get("/api/demo").status_code == 401


def test_short_access_code_switches_live_runs_off(client, monkeypatch, caplog):
    monkeypatch.setenv("ACCESS_CODE", "short123")
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("label.pdf", b"%PDF")}
    r = client.post("/api/plan", files=files, data={"month": "2026-11"}, headers={"X-Access-Code": "short123"})
    assert r.status_code == 503 and "shorter than 16" in caplog.text


def test_wrong_codes_lock_out_that_address_only(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    files = lambda: {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("l.pdf", b"%PDF")}  # noqa: E731

    def plan(code, ip="198.51.100.7"):
        return client.post("/api/plan", files=files(), data={"month": "2026-11"},
                           headers={"X-Access-Code": code, "X-Forwarded-For": ip}).status_code

    assert [plan("guess-%d" % i) for i in range(10)] == [401] * 10
    assert plan("s3cret-code-for-tests") == 429  # locked out even with the right code
    assert plan("s3cret-code-for-tests", ip="198.51.100.8") == 200  # other addresses unaffected


def test_oversize_field_is_refused_and_not_kept(client, tmp_path):
    big = b'{"type": "Polygon", "coordinates": [[' + b"[0, 0], " * 200_000 + b"[0, 0]]]}"
    r = client.post("/api/plan", files={"field": ("f.geojson", big), "label": ("l.pdf", b"%PDF")},
                    data={"month": "2026-11"})
    assert r.status_code == 413 and "limit is 1 MB" in r.json()["detail"]
    assert not list((tmp_path / "runs").rglob("field.geojson"))  # the partial file was removed


def test_oversize_label_and_audio_are_refused(client, monkeypatch):
    monkeypatch.setattr(api, "LABEL_MAX", 2 * api.MB)
    r = client.post("/api/label", files={"label": ("x.pdf", b"%PDF" + b"0" * (3 * api.MB))})
    assert r.status_code == 413 and "limit is 2 MB" in r.json()["detail"]
    run_id = post_plan(client).json()["run_id"]
    monkeypatch.setattr(api, "AUDIO_MAX", 1 * api.MB)
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("n.wav", b"RIFF\x00\x00\x00\x00WAVE" + b"0" * (2 * api.MB))})
    assert r.status_code == 413


def test_declared_huge_request_is_refused_before_reading(client):
    r = client.post("/api/label", content=b"x", headers={"content-length": str(41 * api.MB),
                                                          "content-type": "application/octet-stream"})
    assert r.status_code == 413 and "40 MB" in r.json()["detail"]


def test_too_many_pages_is_explained(client, monkeypatch):
    def long_label(*a):
        raise label_reader.LabelTooLongError("Label PDF has 400 pages; the limit is 80.")

    monkeypatch.setattr(pipeline, "run", long_label)
    r = post_plan(client)
    assert r.status_code == 422 and "400 pages" in r.json()["detail"]


def test_counters_never_grow_without_bound(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    monkeypatch.setattr(api, "MAX_TRACKED", 50)
    for i in range(120):  # wrong codes from many addresses
        client.post("/api/label", files={"label": ("x.pdf", b"%PDF")},
                    headers={"X-Access-Code": "wrong", "X-Forwarded-For": f"2001:db8::{i:x}"})
    assert len(api._fails) <= 50
    # the right code passes the lockout lookup without leaving a failure entry behind
    api.reset_limits()
    client.post("/api/label", files={"label": ("x.pdf", b"%PDF")},
                headers={"X-Access-Code": "s3cret-code-for-tests", "X-Forwarded-For": "203.0.113.200"})
    assert "203.0.113.200" not in api._fails and "203.0.113.200" in api._hits


def test_expired_entries_are_dropped(monkeypatch):
    table = {"a": deque([0.0]), "b": deque([5000.0])}
    assert api._count(table, "a", now=4000.0) == 0 and "a" not in table
    assert api._count(table, "b", now=4000.0) == 1 and "b" in table
    assert api._count(table, "zzz", now=4000.0) == 0 and "zzz" not in table


def test_chunked_upload_is_cut_off_at_the_limit(client, monkeypatch):
    monkeypatch.setattr(api, "REQUEST_MAX", 1 * api.MB)
    sent = []

    def chunks():  # no Content-Length: the declared-size check can't see this
        for _ in range(8):
            sent.append(1)
            yield b"0" * (512 * 1024)

    r = client.post("/api/label", content=chunks(),
                    headers={"content-type": "multipart/form-data; boundary=x"})
    assert r.status_code == 413 and "limit is 1 MB" in r.json()["detail"]


def test_unauthorised_upload_is_refused_before_it_is_parsed(client, monkeypatch):
    import starlette.requests

    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")

    async def no_parsing(*a, **kw):
        raise AssertionError("the body was parsed before the access check")

    monkeypatch.setattr(starlette.requests.Request, "form", no_parsing)
    r = post_plan(client)
    assert r.status_code == 401


def test_guard_counts_each_run_once(client, monkeypatch):
    monkeypatch.setenv("RUNS_PER_IP_PER_DAY", "2")
    assert [post_plan(client).status_code for _ in range(3)] == [200, 200, 429]


def test_lru_evicts_the_least_recently_hit(monkeypatch):
    from collections import OrderedDict

    monkeypatch.setattr(api, "MAX_TRACKED", 2)
    table = OrderedDict()
    api._add(table, "a", 1.0)
    api._add(table, "b", 2.0)
    api._add(table, "a", 3.0)  # a is now the most recent
    api._add(table, "c", 4.0)  # evicts b, not a
    assert list(table) == ["a", "c"] and list(table["a"]) == [1.0, 3.0]


def test_any_new_api_write_is_gated_without_being_listed(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    ran = []

    @api.app.post("/api/test-only-new-endpoint")
    def new_endpoint():
        ran.append(1)
        return {"ok": True}

    # routes are matched in order and "/" is mounted last, so move the new route ahead of the static mount
    api.app.router.routes.insert(0, api.app.router.routes.pop())
    try:
        assert client.post("/api/test-only-new-endpoint").status_code == 401 and ran == []
        ok = client.post("/api/test-only-new-endpoint", headers={"X-Access-Code": "s3cret-code-for-tests"})
        assert ok.status_code == 200 and ran == [1]
    finally:
        api.app.router.routes[:] = [r for r in api.app.router.routes
                                    if getattr(r, "path", "") != "/api/test-only-new-endpoint"]


def test_reads_stay_free(client, monkeypatch):
    monkeypatch.setenv("CLEARSWATH_LIVE_MODE", "off")
    assert client.get("/api/health").status_code == 200
    assert client.head("/api/health").status_code not in (401, 429, 503)  # never gated, whatever it returns


def test_bad_field_is_explained(client, monkeypatch):
    from app import geo

    def refuse(*a):
        raise geo.FieldError("The field is 41,158,402 acres; the limit is 640. Split it up.")

    monkeypatch.setattr(pipeline, "run", refuse)
    r = post_plan(client)
    assert r.status_code == 422 and "41,158,402 acres" in r.json()["detail"]


@pytest.mark.parametrize("name, body", [
    ("label.pdf", b"<html>not a pdf</html>"),
    ("label.png", b"%PDF-1.7 pretending"),
    ("label.jpg", b"GIF89a"),
    ("label.webp", b"RIFF\x00\x00\x00\x00WAVE"),
])
def test_label_content_must_match_its_extension(client, tmp_path, name, body):
    r = client.post("/api/label", files={"label": (name, body)})
    assert r.status_code == 415 and "doesn't look like" in r.json()["detail"]
    assert not list((tmp_path / "runs").rglob("label.*"))  # the mismatched file was deleted


def test_audio_content_must_be_wav(client):
    run_id = post_plan(client).json()["run_id"]
    r = client.post("/api/record", data={"run_id": run_id}, files={"audio": ("note.wav", b"ID3 an mp3 file")})
    assert r.status_code == 415 and "WAV" in r.json()["detail"]


def test_clean_up_removes_old_runs_and_field_caches(tmp_path, monkeypatch):
    import os

    from app import segment

    runs, cache = tmp_path / "runs", tmp_path / "cache"
    monkeypatch.setattr(api, "RUNS", runs)
    monkeypatch.setattr(segment, "CACHE", cache)
    now = 10_000_000.0

    def folder(root, name, age_s):
        d = root / name
        d.mkdir(parents=True)
        (d / "x").write_text("x")
        os.utime(d, (now - age_s, now - age_s))
        return d

    old_run, new_run = folder(runs, "a" * 32, 25 * 3600), folder(runs, "b" * 32, 3600)
    stray = folder(runs, "not-a-run", 99 * 3600)  # only names we create are touched
    old_field, new_field = folder(cache, "0123456789ab", 8 * 86400), folder(cache, "ba9876543210", 86400)
    labels, blt = folder(cache, "labels", 99 * 86400), folder(cache, "blt", 99 * 86400)
    api.clean_up(now)
    assert not old_run.exists() and new_run.exists() and stray.exists()
    assert not old_field.exists() and new_field.exists() and labels.exists() and blt.exists()


def test_clean_up_caps_the_folder_count(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(api, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(api, "MAX_RUN_DIRS", 3)
    now = 10_000_000.0
    for i in range(5):
        d = tmp_path / "runs" / (f"{i:x}" * 32)[:32]
        d.mkdir(parents=True)
        os.utime(d, (now - 100 + i, now - 100 + i))
    api.clean_up(now)
    assert sorted(p.name[0] for p in (tmp_path / "runs").iterdir()) == ["2", "3", "4"]  # the 3 newest


def test_clean_up_runs_at_most_hourly(client, monkeypatch):
    calls = []
    monkeypatch.setattr(api, "clean_up", lambda now=None: calls.append(1))
    monkeypatch.setattr(api, "_cleaned", {"at": 0.0})
    for _ in range(3):
        client.get("/api/health")
    import time as _t
    _t.sleep(0.2)  # the clean-up runs in a background thread
    assert calls == [1]


def photo_with_exif() -> bytes:
    import io

    from PIL import Image

    im = Image.new("RGB", (400, 200), "white")
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x0112] = 6  # Orientation: rotate 90 degrees to view
    exif[0x8825] = {1: "N", 2: (44.0, 14.0, 5.0), 3: "W", 4: (96.0, 55.0, 10.0)}  # GPS
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_photo_label_loses_exif_and_gps(client, monkeypatch):
    import io

    from PIL import Image

    raw = photo_with_exif()
    assert len(Image.open(io.BytesIO(raw)).getexif()) > 0  # the fixture really has EXIF
    seen = {}
    lr = LabelRules(product_name="Acme", epa_reg_no="1-2", rules=[], dropped=[], source="image")
    monkeypatch.setattr(label_reader, "read_label", lambda p: seen.update(path=p) or lr)
    assert client.post("/api/label", files={"label": ("photo.jpg", raw)}).status_code == 200
    stored = Image.open(seen["path"])
    assert len(stored.getexif()) == 0 and stored.size == (200, 400)  # no metadata, turned upright


def test_huge_photo_is_shrunk(client, monkeypatch):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (6000, 1500), "white").save(buf, "PNG")
    seen = {}
    lr = LabelRules(product_name=None, epa_reg_no=None, rules=[], dropped=[], source="image")
    monkeypatch.setattr(label_reader, "read_label", lambda p: seen.update(path=p) or lr)
    assert client.post("/api/label", files={"label": ("big.png", buf.getvalue())}).status_code == 200
    assert max(Image.open(seen["path"]).size) == api.MAX_IMAGE_SIDE


def test_unreadable_image_is_refused(client, tmp_path):
    r = client.post("/api/label", files={"label": ("photo.jpg", b"\xff\xd8\xff" + b"garbage" * 10)})
    assert r.status_code == 415 and "couldn't be read" in r.json()["detail"]
    assert not list((tmp_path / "runs").rglob("label.*"))


@pytest.fixture
def weedy_demo(client, cached_demo, tmp_path, monkeypatch):
    """The Montana-style demo: the cached field plus a weed map, on a coarse grid so the test stays fast."""
    import shutil

    monkeypatch.setattr(pipeline, "CELL_M", 50.0)
    src, dst = tmp_path / "demo" / "cache" / "field", tmp_path / "demo" / "cache" / "mt"
    shutil.copytree(src, dst)
    field, _, hazards, bulletin, month = pipeline.load_inputs(dst)
    raw = json.loads(gzip.decompress((dst / "inputs.json.gz").read_bytes()))["label_raw"]
    hazards["weeds"] = [box(-92.9995, 42.0005, -92.9990, 42.0010)]  # SW corner, far from the pond
    pipeline.save_inputs(dst, field, raw, hazards, bulletin, month)
    return client.get("/api/demo?field=mt").json()["run_id"]


def test_spot_spray_exports(client, weedy_demo):
    kml = client.get(f"/api/kml/{weedy_demo}").text
    assert "Spot spray" in kml and "Spray zone" in kml
    r = client.get(f"/api/export/{weedy_demo}/dji", params={"rate": 19})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    import io
    import zipfile

    assert "DJI/Rx/prescription.tif" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    gj = client.get(f"/api/export/{weedy_demo}/geojson").json()
    assert [f["properties"]["name"] for f in gj["features"]] == ["Spray zone", "No spray", "Spot spray"]


@pytest.mark.parametrize("params, code", [({}, 422), ({"rate": 0}, 422), ({"rate": 5000}, 422)])
def test_dji_export_needs_a_sane_rate(client, weedy_demo, params, code):
    assert client.get(f"/api/export/{weedy_demo}/dji", params=params).status_code == code


def test_no_weed_map_no_prescription(client, cached_demo):
    run_id = client.get("/api/demo").json()["run_id"]
    assert client.get(f"/api/export/{run_id}/dji", params={"rate": 19}).status_code == 409
    assert client.get(f"/api/export/{run_id}/shp").status_code == 404
    assert client.get("/api/export/not-a-run/geojson").status_code == 404


def test_demo_agent_saves_an_answer_the_demo_replays(client, cached_demo, monkeypatch, tmp_path):
    from app import agent

    calls = []

    def fake_run(fp, lp, month, method, excluded, inputs=None, **kw):
        calls.append(inputs is not None)
        result = pipeline.assemble(*inputs, month, method, excluded)
        return {"run_id": "r1", "answer": "ADJUST: keep 100 ft from the pond.", "decision": result["plan"]["status"],
                "trace": [{"tool": "plan_spray", "seconds": 0.1}], "mode": "agent", "result": result}

    monkeypatch.setattr(agent, "run", fake_run)
    r = client.post("/api/demo/agent", data={"field": "corrected", "method": "drone"})
    assert r.status_code == 200 and r.json()["answer"].startswith("ADJUST") and calls == [True]
    saved = json.loads((tmp_path / "demo" / "cache" / "field_corrected" / "agent.json").read_text())
    assert saved["drone|"]["decision"] == "adjust"

    replay = client.get("/api/demo?field=corrected&agent_answer=1").json()
    assert replay["mode"] == "replay" and replay["answer"] == "ADJUST: keep 100 ft from the pond."
    assert "answer" not in client.get("/api/demo?field=corrected").json()  # only when asked for
    assert "answer" not in client.get("/api/demo?field=corrected&method=ground&agent_answer=1").json()  # other key


def test_stale_replay_is_never_shown(client, cached_demo, tmp_path):
    (tmp_path / "demo" / "cache" / "field_corrected" / "agent.json").write_text(json.dumps(
        {"drone|": {"answer": "GO: spray it all.", "decision": "go", "trace": [], "model": "m", "date": "d"}}))
    body = client.get("/api/demo?field=corrected&agent_answer=1").json()
    assert body["status"] == "adjust" and "answer" not in body


def test_spend_budget_stops_live_runs(client, monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "1")
    assert post_plan(client).status_code == 200
    spend.record("muse-spark-1.3", {"prompt_tokens": 1_000_000})  # $1.25 spent today
    r = post_plan(client)
    assert r.status_code == 503 and "budget" in r.json()["detail"]
    assert client.get("/api/health").status_code == 200  # free routes keep working


def test_three_live_runs_per_address_per_day_by_default(client, monkeypatch):
    monkeypatch.delenv("RUNS_PER_IP_PER_DAY")
    assert [post_plan(client).status_code for _ in range(4)] == [200, 200, 200, 429]


def test_managed_land_and_wind_reach_the_plan(client):
    near = mapping(box(-92.99, 42.0, -92.985, 42.01))  # a strip along FIELD's east edge
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("label.pdf", b"%PDF")}
    r = client.post("/api/plan", files=files, data={"month": "2026-11", "managed": json.dumps(near), "wind_from": "270"})
    assert r.status_code == 200 and client.seen["wind"] == 270.0
    (land,) = client.seen["managed"]
    assert land.equals(box(-92.99, 42.0, -92.985, 42.01))


@pytest.mark.parametrize("data, detail", [
    ({"wind_from": "400"}, "wind_from"),
    ({"wind_from": "north"}, "wind_from"),
    ({"managed": "not json"}, "isn't valid GeoJSON"),
    ({"managed": json.dumps({"type": "Point", "coordinates": [-92.99, 42.0]})}, "polygons"),
    ({"managed": json.dumps(mapping(box(-80.0, 40.0, -79.9, 40.1)))}, "next to the field"),
])
def test_bad_managed_land_or_wind_is_refused_before_any_run(client, data, detail):
    files = {"field": ("f.geojson", json.dumps(mapping(FIELD))), "label": ("label.pdf", b"%PDF")}
    r = client.post("/api/plan", files=files, data={"month": "2026-11"} | data)
    assert r.status_code == 422 and detail in r.json()["detail"] and client.seen == {}


def test_demo_refuses_a_bad_wind(client, cached_demo):
    assert client.get("/api/demo?wind_from=400").status_code == 422
    assert client.get("/api/demo?wind_from=90").status_code == 200


def test_photo_mode_sends_a_clean_photo_and_returns_the_overlay(client, monkeypatch):
    import io

    from PIL import Image

    sent = {}

    def weed_photo(path):
        sent["exif"] = Image.open(path).getexif()
        return {"width": 40, "height": 30, "share_flagged": 0.1, "overlay_png": "iVBOR", "threshold": 0.4,
                "trained_on": {"cofly": 180}}

    monkeypatch.setattr(llm, "weed_photo", weed_photo)
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {2: (44.0, 14.0, 0.0)}  # a GPS position the server must drop
    Image.new("RGB", (40, 30), "green").save(buf, "JPEG", exif=exif)
    r = client.post("/api/photo", files={"photo": ("field.jpg", buf.getvalue())})
    assert r.status_code == 200 and r.json() == {"width": 40, "height": 30, "share_flagged": 0.1,
                                                 "overlay_png": "iVBOR", "trained_on": {"cofly": 180}}
    assert 0x8825 not in sent["exif"]


@pytest.mark.parametrize("name, data, code", [("notes.pdf", b"%PDF", 422), ("fake.jpg", b"not a jpeg", 415)])
def test_photo_mode_refuses_non_photos(client, monkeypatch, name, data, code):
    monkeypatch.setattr(llm, "weed_photo", lambda p: pytest.fail("must not reach the GPU"))
    assert client.post("/api/photo", files={"photo": (name, data)}).status_code == code


def test_photo_mode_off_until_configured(client, monkeypatch):
    import io

    from PIL import Image

    monkeypatch.delenv("PHOTO_URL", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **kw: None)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "PNG")
    r = client.post("/api/photo", files={"photo": ("p.png", buf.getvalue())})
    assert r.status_code == 502 and "isn't set up" in r.json()["detail"]


def test_photo_mode_is_gated_like_live_runs(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "s3cret-code-for-tests")
    assert client.post("/api/photo", files={"photo": ("p.png", b"x")}).status_code == 401


def _weedy_run_with(client, weedy_demo, tmp_path, **job):
    path = tmp_path / "runs" / weedy_demo / "job.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | job))
    return lambda rate: client.get(f"/api/export/{weedy_demo}/dji", params={"rate": rate})


def test_dji_export_refuses_a_rate_below_the_label_minimum(client, weedy_demo, tmp_path):
    export = _weedy_run_with(client, weedy_demo, tmp_path,
                             carrier_min={"l_ha": 18.7, "quote": "2 or more gallons per acre by air", "page": 28})
    r = export(10)
    assert r.status_code == 422 and "18.7 L/ha" in r.json()["detail"] and "p.28" in r.json()["detail"]
    assert export(19).status_code == 200


def test_dji_export_refused_when_the_minimum_is_unverified(client, weedy_demo, tmp_path):
    export = _weedy_run_with(client, weedy_demo, tmp_path, carrier_unverified=True)
    assert export(50).status_code == 409


def _png_claiming(width: int, height: int) -> bytes:
    """A 1-pixel PNG whose header says width x height: a decompression bomb's shape, without the memory."""
    import io
    import struct
    import zlib

    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (1, 1)).save(buf, "PNG")
    data = bytearray(buf.getvalue())
    ihdr = struct.pack(">II", width, height) + bytes(data[24:29])
    data[16:29] = ihdr
    data[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return bytes(data)


@pytest.mark.parametrize("url, field", [("/api/photo", "photo"), ("/api/label", "label")])
def test_an_image_claiming_to_be_huge_is_refused_before_decoding(client, monkeypatch, url, field):
    from PIL import Image

    def never(*a, **kw):
        raise AssertionError("must not decode")

    # 120 megapixels: under Pillow's own refusal (~179 MP), where it only warns, decodes, and needs ~360 MB
    bomb = _png_claiming(12_000, 10_000)
    monkeypatch.setattr(llm, "weed_photo", never)
    monkeypatch.setattr(Image.Image, "load", never)  # a decode would call this
    r = client.post(url, files={field: ("big.png", bomb)})
    assert r.status_code == 413 and "megapixels" in r.json()["detail"]


def test_a_normal_photo_still_passes_the_size_check(client, monkeypatch):
    import io

    from PIL import Image

    monkeypatch.setattr(llm, "weed_photo", lambda p: {"overlay_png": "x", "share_flagged": 0.0})
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), "green").save(buf, "JPEG")  # a 12-megapixel phone photo
    assert client.post("/api/photo", files={"photo": ("p.jpg", buf.getvalue())}).status_code == 200
