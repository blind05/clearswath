import json
from types import SimpleNamespace

import pymupdf
import pytest

from app import label_reader, llm

PAGES = ["Acme Weed-B-Gone  EPA Reg. No. 123-45\nRead the label.",
         "Do not apply within 25 feet of\nlakes, ponds or streams.\nDo not apply when wind exceeds 10 mph."]


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(label_reader, "CACHE", tmp_path / "label_cache")
    return tmp_path / "label_cache"


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "label.pdf"
    doc = pymupdf.open()
    for text in PAGES:
        doc.new_page().insert_text((72, 72), text)
    doc.save(p)
    return p


def rule(**kw):
    base = {"kind": "buffer", "target": "water", "applies_to": "all", "value": 25, "unit": "ft",
            "summary": "25 ft from water", "quote": "Do not apply within 25 feet of lakes, ponds or streams.",
            "page": 2}
    return base | kw


def fake_model(monkeypatch, rules):
    seen = {}

    def chat_json(messages, schema, name, **kw):
        seen["text"] = messages[1]["content"]
        return {"product_name": "Acme Weed-B-Gone", "epa_reg_no": "123-45", "rules": rules}

    monkeypatch.setattr(llm, "chat_json", chat_json)
    return seen


def test_keeps_verified_rules(monkeypatch, pdf):
    wind = rule(kind="wind", target=None, value=10, unit="mph",
                quote="Do not apply when wind exceeds 10 mph.")
    seen = fake_model(monkeypatch, [rule(), wind])
    out = label_reader.read_label(pdf)
    assert out.source == "pdf" and out.epa_reg_no == "123-45" and out.dropped == []
    assert [r.kind for r in out.rules] == ["buffer", "wind"]
    assert "=== Page 2 ===" in seen["text"]


def test_runoff_rule_is_kept_only_with_a_real_quote(monkeypatch, pdf):
    runoff = rule(kind="runoff", target=None, value=None, unit=None, quote="Read the label.", page=1)
    fake_model(monkeypatch, [runoff, runoff | {"quote": "Achieve 3 runoff mitigation points."}])
    out = label_reader.read_label(pdf)
    assert [r.kind for r in out.rules] == ["runoff"] and out.dropped[0]["reason"] == "quote not found in label text"


def test_drops_invented_quote(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(quote="Do not apply within 5 feet of water.")])
    out = label_reader.read_label(pdf)
    assert out.rules == [] and out.dropped[0]["reason"] == "quote not found in label text"


def test_drift_rule_needs_a_distance_but_no_target(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(kind="drift", target=None, unit="feet")])
    (r,) = label_reader.read_label(pdf).rules
    assert r.kind == "drift" and r.target is None and r.unit == "ft"


def test_fixes_wrong_page(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(page=1)])
    assert label_reader.read_label(pdf).rules[0].page == 2


@pytest.mark.parametrize("bad, reason", [
    ({"target": None}, "buffer without a target"),
    ({"unit": "yards"}, "buffer without a distance in ft or m"),
    ({"value": None}, "buffer without a distance in ft or m"),
    ({"target": "river"}, "invalid fields: target"),
    ({"kind": "drift", "target": None, "value": None}, "drift without a distance in ft or m"),
    ({"kind": "setback", "applies_to": "drones"}, "invalid fields: kind, applies_to"),
])
def test_drops_unusable_rules(monkeypatch, pdf, bad, reason):
    fake_model(monkeypatch, [rule(**bad)])
    out = label_reader.read_label(pdf)
    assert out.rules == [] and out.dropped[0]["reason"] == reason


def test_image_uses_transcription(monkeypatch, tmp_path):
    img = tmp_path / "label.png"
    img.write_bytes(b"png")
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: SimpleNamespace(content="\n".join(PAGES)))
    fake_model(monkeypatch, [rule(page=1)])
    out = label_reader.read_label(img)
    assert out.source == "image" and out.rules[0].page == 1


def test_model_output_is_cached(monkeypatch, pdf, cache):
    calls = []
    fake_model(monkeypatch, [rule()])
    real = llm.chat_json
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: calls.append(1) or real(*a, **kw))
    first = label_reader.read_label(pdf)
    second = label_reader.read_label(pdf)
    assert len(calls) == 1 and first == second and len(list(cache.iterdir())) == 1


def test_cache_still_checks_quotes(monkeypatch, pdf, cache):
    fake_model(monkeypatch, [rule()])
    label_reader.read_label(pdf)
    # a cached rule whose quote is no longer in the page text is dropped on the next read
    (path,) = cache.iterdir()
    raw = json.loads(path.read_text())
    raw["out"]["rules"][0]["quote"] = "Do not apply within 5 feet of water."
    path.write_text(json.dumps(raw))
    out = label_reader.read_label(pdf)
    assert out.rules == [] and out.dropped[0]["reason"] == "quote not found in label text"


def test_cache_key_changes_with_prompt(monkeypatch, pdf, cache):
    fake_model(monkeypatch, [rule()])
    label_reader.read_label(pdf)
    monkeypatch.setattr(llm, "load_prompt", lambda name: "a different prompt")
    label_reader.read_label(pdf)
    assert len(list(cache.iterdir())) == 2


def test_condition_passes_through(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(condition="California only"), rule(kind="wind", target=None, value=10, unit="mph",
                                                                     quote="Do not apply when wind exceeds 10 mph.")])
    out = label_reader.read_label(pdf)
    assert [r.condition for r in out.rules] == ["California only", None]
    assert label_reader.RULE_SCHEMA["required"][-1] == "condition"


def test_provider_has_its_own_cache_entry(monkeypatch, pdf, cache):
    seen = []
    fake_model(monkeypatch, [rule()])
    real = llm.chat_json
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: seen.append(kw.get("provider")) or real(*a, **kw))
    label_reader.read_label(pdf)
    label_reader.read_label(pdf, provider="baseten")
    label_reader.read_label(pdf, provider="baseten")
    assert seen == [None, "baseten"] and len(list(cache.iterdir())) == 2


def test_photo_transcription_stays_on_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "baseten")
    img = tmp_path / "label.png"
    img.write_bytes(b"png")
    seen = {}
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: seen.update(kw) or SimpleNamespace(content="\n".join(PAGES)))
    fake_model(monkeypatch, [rule(page=1)])
    label_reader.read_label(img)
    assert seen["provider"] == "meta"


@pytest.mark.parametrize("unit, stored", [("feet", "ft"), ("Feet", "ft"), ("foot", "ft"), ("ft", "ft"),
                                          ("meters", "m"), ("metres", "m"), ("m", "m")])
def test_buffer_unit_spellings_are_normalised(monkeypatch, pdf, unit, stored):
    fake_model(monkeypatch, [rule(unit=unit)])
    out = label_reader.read_label(pdf)
    assert out.dropped == [] and out.rules[0].unit == stored


def test_pdf_over_the_page_limit_never_reaches_the_model(monkeypatch, tmp_path):
    doc = pymupdf.open()
    for _ in range(label_reader.MAX_PAGES + 1):
        doc.new_page()
    p = tmp_path / "long.pdf"
    doc.save(p)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: pytest.fail("model called"))
    with pytest.raises(label_reader.LabelTooLongError, match="81 pages"):
        label_reader.read_label(p)
