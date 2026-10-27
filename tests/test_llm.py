import json
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
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


def wav(path, seconds=0.5, rate=16000, channels=1, width=2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\0" * int(seconds * rate) * channels * width)
    return path


def test_transcribe(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
    monkeypatch.setattr(llm, "_api_key", lambda: "k")
    seen = {}

    def post(url, **kw):
        seen.update(url=url, **kw)
        return httpx.Response(200, json={"transcript": "twelve gallons", "turns": []},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm.transcribe(wav(tmp_path / "a.wav"), purpose="t", keywords=["Intrepid"]) == "twelve gallons"
    assert seen["url"] == "https://api.meta.ai/v1/asr/transcribe"
    assert seen["headers"]["Authorization"] == "Bearer k"
    request = json.loads(seen["files"]["request"][1])
    assert request == {"mode": "ENDPOINTING", "model": llm.VOICE, "audioEncoding": "WAV", "keywords": ["Intrepid"]}
    assert seen["files"]["audio"][2] == "audio/wav"
    assert json.loads(llm.LOG_PATH.read_text())["model"] == llm.VOICE


def test_transcribe_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_api_key", lambda: "k")
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: httpx.Response(
        500, request=httpx.Request("POST", url)))
    with pytest.raises(RuntimeError, match="Voice transcription failed"):
        llm.transcribe(wav(tmp_path / "a.wav"))


@pytest.mark.parametrize("kw", [{"channels": 2}, {"width": 1}, {"rate": 44100}, {"seconds": 601}])
def test_check_wav_rejects(tmp_path, kw):
    with pytest.raises(llm.BadAudioError):
        llm.check_wav(wav(tmp_path / "a.wav", **kw))


def test_check_wav_rejects_non_wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"not audio")
    with pytest.raises(llm.BadAudioError, match="WAV"):
        llm.check_wav(p)


def test_check_wav_accepts_24k(tmp_path):
    assert llm.check_wav(wav(tmp_path / "a.wav", rate=24000, seconds=2)) == 2
