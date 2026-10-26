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
