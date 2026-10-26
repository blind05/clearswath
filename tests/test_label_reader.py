from types import SimpleNamespace

import pymupdf
import pytest

from app import label_reader, llm

PAGES = ["Acme Weed-B-Gone  EPA Reg. No. 123-45\nRead the label.",
         "Do not apply within 25 feet of\nlakes, ponds or streams.\nDo not apply when wind exceeds 10 mph."]


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


def test_drops_invented_quote(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(quote="Do not apply within 5 feet of water.")])
    out = label_reader.read_label(pdf)
    assert out.rules == [] and out.dropped[0]["reason"] == "quote not found in label text"


def test_fixes_wrong_page(monkeypatch, pdf):
    fake_model(monkeypatch, [rule(page=1)])
    assert label_reader.read_label(pdf).rules[0].page == 2


@pytest.mark.parametrize("bad, reason", [
    ({"target": None}, "buffer without a target"),
    ({"unit": "yards"}, "buffer without a distance in ft or m"),
    ({"value": None}, "buffer without a distance in ft or m"),
    ({"target": "river"}, "invalid fields: target"),
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
