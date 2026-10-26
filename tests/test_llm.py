import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import llm


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
    c = MagicMock()
    monkeypatch.setattr(llm, "client", lambda: c)
    return c


def reply(content):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage={"total_tokens": 5})


def test_client_needs_key(monkeypatch):
    llm.client.cache_clear()
    monkeypatch.setattr(llm, "load_dotenv", lambda *a: None)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        llm.client()


def test_client_passes_key(monkeypatch):
    llm.client.cache_clear()
    monkeypatch.setattr(llm, "load_dotenv", lambda *a: None)
    monkeypatch.setenv("MODEL_API_KEY", "k")
    c = llm.client()
    assert c.api_key == "k" and str(c.base_url).startswith(llm.BASE_URL)
    llm.client.cache_clear()


def test_chat_logs(fake):
    fake.chat.completions.create.return_value = reply("OK")
    assert llm.chat([{"role": "user", "content": "hi"}], purpose="t").content == "OK"
    assert "tools" not in fake.chat.completions.create.call_args.kwargs
    row = json.loads(llm.LOG_PATH.read_text())
    assert row["model"] == llm.SPARK and row["purpose"] == "t" and row["usage"] == {"total_tokens": 5}


def test_chat_json(fake):
    fake.chat.completions.create.return_value = reply('{"a": 1}')
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    assert llm.chat_json([], schema, "x") == {"a": 1}
    fmt = fake.chat.completions.create.call_args.kwargs["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["schema"] is schema


def test_chat_json_needs_object_root(fake):
    with pytest.raises(ValueError):
        llm.chat_json([], {"type": "array"}, "x")


def test_data_url(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"hi")
    assert llm.data_url(p) == "data:image/png;base64,aGk="


def event(type, **kw):
    return SimpleNamespace(type=type, **kw)


@pytest.fixture
def img(tmp_path):
    p = tmp_path / "t.png"
    p.write_bytes(b"png")
    return p


def test_sam_raw(fake, img):
    fake.responses.create.return_value = SimpleNamespace(output_text="MASKS", usage={"total_tokens": 9})
    assert llm.sam_raw(img, "pond", purpose="t") == "MASKS"
    kw = fake.responses.create.call_args.kwargs
    assert kw["model"] == llm.SAM and kw["metadata"] == {"include_confidence": "true"}
    assert kw["input"][0]["content"][1] == {"type": "input_text", "text": "pond"}
    assert "stream" not in kw and not fake.responses.stream.called
    row = json.loads(llm.LOG_PATH.read_text())
    assert row["model"] == llm.SAM and row["usage"] == {"total_tokens": 9}


def test_sam_raw_without_confidence(fake, img):
    fake.responses.create.return_value = SimpleNamespace(output_text="M", usage=None)
    llm.sam_raw(img, "pond", include_confidence=False)
    assert "metadata" not in fake.responses.create.call_args.kwargs


def stream_events(fake, *events):
    fake.responses.create.return_value = SimpleNamespace(output_text="", usage=None)
    fake.responses.stream.return_value.__enter__.return_value = iter(events)


def test_sam_raw_falls_back_to_stream_deltas(fake, img):
    stream_events(fake, event("response.output_text.delta", delta="MA"),
                  event("response.output_text.delta", delta="SKS"),
                  event("response.content_part.done", part=SimpleNamespace(type="output_text", text="MASKS")),
                  event("response.completed", response=SimpleNamespace(usage={"total_tokens": 3})))
    assert llm.sam_raw(img, "pond") == "MASKS"
    assert fake.responses.stream.call_args.kwargs["model"] == llm.SAM
    assert json.loads(llm.LOG_PATH.read_text())["usage"] == {"total_tokens": 3}


def test_sam_raw_stream_uses_content_part_without_deltas(fake, img):
    stream_events(fake, event("response.content_part.done", part=SimpleNamespace(type="output_text", text="M")))
    assert llm.sam_raw(img, "pond") == "M"


def test_sam_raw_stream_failure_raises(fake, img):
    stream_events(fake, event("response.failed"))
    with pytest.raises(RuntimeError):
        llm.sam_raw(img, "pond")
