"""The only place that talks to Meta models: the Meta Model API, and Muse Spark Open on Baseten or Fireworks.

All are OpenAI-compatible. Pick the Spark provider per call (provider="meta" | "baseten" | "fireworks") or
with LLM_PROVIDER in .env. SAM and voice are Meta Model API only.
"""

import base64
import json
import mimetypes
import os
import time
import wave
from functools import cache
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app import spend

BASE_URL = "https://api.meta.ai/v1"
SPARK = "muse-spark-1.3"
SAM = "sam-3.1"
VOICE = "muse-voice-transcribe-1.0"
SPARK_OPEN = "meta-models/muse-spark-open-1026"
SPARK_OPEN_FIREWORKS = "accounts/fireworks/models/muse-spark-open"

# provider -> (base URL, key variable, Spark model, SDK retries; the SDK backs off on 429)
PROVIDERS = {
    "meta": (BASE_URL, "MODEL_API_KEY", SPARK, 2),
    "baseten": ("https://inference.baseten.co/v1", "BASETEN_API_KEY", SPARK_OPEN, 5),  # ~60 requests/min
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", SPARK_OPEN_FIREWORKS, 3),
}
NO_STRUCTURED_OUTPUT = {"baseten"}  # chat_json forces one tool call there instead of response_format

MODEL_TIMEOUT_S = 120

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
LOG_PATH = ROOT / "data" / "logs" / "calls.jsonl"


class MissingKeyError(RuntimeError):
    """No API key for a provider; the message is safe to show users."""


class BadAudioError(ValueError):
    """Audio the transcriber won't take; the message is safe to show users."""


class PhotoUnavailableError(RuntimeError):
    """Live photo mode has no endpoint configured; the message is safe to show users."""


PHOTO_MODEL = "dinov3-weed-head"  # DINOv3 + the trained head, served by serve/weeds_modal.py on Modal


def weed_photo(path: str | Path, *, purpose: str = "photo") -> dict:
    """One photo -> weed overlay (PNG, base64), share flagged and what the head was trained on."""
    load_dotenv(ROOT / ".env")
    url, key = os.getenv("PHOTO_URL"), os.getenv("PHOTO_KEY")
    if not url or not key:
        raise PhotoUnavailableError("Live photo mode isn't set up on this site yet. Try the demo.")
    start = time.perf_counter()
    resp = httpx.post(url, content=Path(path).read_bytes(), timeout=MODEL_TIMEOUT_S,
                      headers={"X-Photo-Key": key, "Content-Type": "application/octet-stream"})
    log_call(PHOTO_MODEL, purpose, time.perf_counter() - start, None)  # counted even if it fails: GPU time was used
    resp.raise_for_status()
    out = resp.json()
    if not isinstance(out.get("overlay_png"), str):
        raise ValueError("unexpected photo response")
    return out


def _api_key(var: str = "MODEL_API_KEY") -> str:
    load_dotenv(ROOT / ".env")
    key = os.getenv(var)
    if not key:
        raise MissingKeyError(f"{var} is not set. Copy .env.example to .env and add your key.")
    return key


def resolve_provider(name: str | None = None) -> str:
    """The Spark provider to use: the argument, else LLM_PROVIDER from .env, else meta."""
    load_dotenv(ROOT / ".env")
    name = name or os.getenv("LLM_PROVIDER") or "meta"
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider {name!r}; use one of {sorted(PROVIDERS)}")
    return name


def spark_model(name: str | None = None) -> str:
    return PROVIDERS[resolve_provider(name)][2]


@cache
def client(name: str = "meta") -> OpenAI:
    base_url, key_var, _, retries = PROVIDERS[name]
    # The SDK only reads OPENAI_API_KEY on its own, so pass the key explicitly.
    # 120 s per attempt: a long label read takes ~30 s; the SDK default (600 s) would hold a worker for 10 min
    return OpenAI(base_url=base_url, api_key=_api_key(key_var), max_retries=retries, timeout=MODEL_TIMEOUT_S)


def log_call(model: str, purpose: str, seconds: float, usage) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    row = {"ts": time.time(), "model": model, "purpose": purpose,
           "seconds": round(seconds, 3), "usage": usage}
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")
    spend.record(model, usage)


def _complete(purpose: str, name: str, **kwargs):
    start = time.perf_counter()
    resp = client(name).chat.completions.create(**kwargs)
    log_call(kwargs["model"], purpose, time.perf_counter() - start, resp.usage)
    return resp


def chat(messages: list[dict], tools: list[dict] | None = None, *,
         purpose: str = "", model: str | None = None, provider: str | None = None):
    """Returns the reply message (with .content and .tool_calls)."""
    name = resolve_provider(provider)
    kwargs = {"model": model or PROVIDERS[name][2], "messages": messages}
    if tools:
        kwargs["tools"] = tools
    return _complete(purpose, name, **kwargs).choices[0].message


def chat_json(messages: list[dict], schema: dict, name: str, *,
              purpose: str = "", model: str | None = None, provider: str | None = None) -> dict:
    if schema.get("type") != "object":
        raise ValueError("chat_json schema must have an object root")
    which = resolve_provider(provider)
    model = model or PROVIDERS[which][2]
    if which in NO_STRUCTURED_OUTPUT:
        # No structured outputs here: force one tool call whose parameters are the schema.
        tool = {"type": "function", "function": {"name": name, "description": "Return the result.",
                                                 "parameters": schema}}
        resp = _complete(purpose, which, model=model, messages=messages, tools=[tool],
                         tool_choice={"type": "function", "function": {"name": name}})
        calls = resp.choices[0].message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != name:
            raise RuntimeError(f"Expected one {name} tool call from {model}, got {len(calls)}")
        return json.loads(calls[0].function.arguments)
    fmt = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
    resp = _complete(purpose, which, model=model, messages=messages, response_format=fmt)
    return json.loads(resp.choices[0].message.content)


def sam_raw(png: str | Path, phrase: str, include_confidence: bool = True, *, purpose: str = "") -> str:
    """Raw SAM output text for ONE noun phrase on one image. Lists like "pond, creek" match nothing."""
    start = time.perf_counter()
    req = {"model": SAM, "input": [{"role": "user", "content": [
        {"type": "input_image", "image_url": data_url(png)},
        {"type": "input_text", "text": phrase},
    ]}]}
    if include_confidence:
        req["metadata"] = {"include_confidence": "true"}
    resp = client().responses.create(**req)
    text, usage = resp.output_text, resp.usage
    if not text:
        text, usage = _sam_stream(req)
    log_call(SAM, purpose, time.perf_counter() - start, usage)
    return text


def _sam_stream(req: dict) -> tuple[str, object]:
    """Streaming fallback: output_text deltas, else content_part.done (what the live API sent before)."""
    deltas, parts, usage = "", "", None
    with client().responses.stream(**req) as stream:
        for ev in stream:
            if ev.type == "response.output_text.delta":
                deltas += ev.delta
            elif ev.type == "response.content_part.done" and ev.part.type == "output_text":
                parts += ev.part.text
            elif ev.type == "response.completed":
                usage = ev.response.usage
            elif ev.type in ("response.failed", "response.incomplete", "error"):
                raise RuntimeError(f"SAM request ended with {ev.type}")
    return deltas or parts, usage


def check_wav(path: str | Path) -> float:
    """Raises BadAudioError unless mono 16-bit PCM WAV at 16 or 24 kHz, <= 10 min, <= 32 MB. Returns seconds."""
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise BadAudioError("Voice note must be 32 MB or less.")
    try:
        with wave.open(str(path), "rb") as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as e:
        raise BadAudioError("Voice note must be a WAV file.") from e
    if channels != 1 or width != 2 or rate not in (16000, 24000):
        raise BadAudioError("Voice note must be mono 16-bit WAV at 16 or 24 kHz.")
    if frames / rate > 600:
        raise BadAudioError("Voice note must be 10 minutes or less.")
    return frames / rate


def transcribe(audio_path: str | Path, *, purpose: str = "", mode: str = "ENDPOINTING",
               keywords: list[str] | None = None) -> str:
    """Muse Voice Transcribe on a WAV file: multipart `request` JSON + `audio`; text is in `transcript`."""
    check_wav(audio_path)
    request = {"mode": mode, "model": VOICE, "audioEncoding": "WAV"}  # only ENDPOINTING tried live
    if keywords:
        request["keywords"] = keywords
    start = time.perf_counter()
    try:
        r = httpx.post(f"{BASE_URL}/asr/transcribe", timeout=120,
                       headers={"Authorization": f"Bearer {_api_key()}"},
                       files={"request": (None, json.dumps(request), "application/json"),
                              "audio": (Path(audio_path).name, Path(audio_path).read_bytes(), "audio/wav")})
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Voice transcription failed: {e}") from e
    log_call(VOICE, purpose, time.perf_counter() - start, data.get("usage"))
    return data["transcript"]


def data_url(path: str | Path) -> str:
    """Image file -> data: URL for an image_url content part."""
    # TODO(verify): api.meta.ai accepts data: URLs in image_url parts
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()
