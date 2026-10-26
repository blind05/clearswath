"""The only place that talks to Meta models. OpenAI-compatible API at api.meta.ai/v1."""

import base64
import json
import mimetypes
import os
import time
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from meta_sam_parser import CompletedOutcome, image_segmentation_format
from openai import OpenAI

BASE_URL = "https://api.meta.ai/v1"
SPARK = "muse-spark-1.3"
SAM = "sam-3.1"
VOICE = "muse-voice-transcribe-1.0"

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
LOG_PATH = ROOT / "data" / "logs" / "calls.jsonl"


@cache
def client() -> OpenAI:
    load_dotenv(ROOT / ".env")
    key = os.getenv("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set. Copy .env.example to .env and add your key.")
    # The SDK only reads OPENAI_API_KEY on its own, so pass the key explicitly.
    return OpenAI(base_url=BASE_URL, api_key=key)


def log_call(model: str, purpose: str, seconds: float, usage) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    row = {"ts": time.time(), "model": model, "purpose": purpose,
           "seconds": round(seconds, 3), "usage": usage}
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _complete(purpose: str, **kwargs):
    start = time.perf_counter()
    resp = client().chat.completions.create(**kwargs)
    log_call(kwargs["model"], purpose, time.perf_counter() - start, resp.usage)
    return resp


def chat(messages: list[dict], tools: list[dict] | None = None, *,
         purpose: str = "", model: str = SPARK):
    """Returns the reply message (with .content and .tool_calls)."""
    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools  # TODO(verify): tool-calling shape on api.meta.ai
    return _complete(purpose, **kwargs).choices[0].message


def chat_json(messages: list[dict], schema: dict, name: str, *,
              purpose: str = "", model: str = SPARK) -> dict:
    if schema.get("type") != "object":
        raise ValueError("chat_json schema must have an object root")
    # TODO(verify): json_schema response_format support on api.meta.ai
    fmt = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
    resp = _complete(purpose, model=model, messages=messages, response_format=fmt)
    return json.loads(resp.choices[0].message.content)


def segment(image_path: str | Path, phrase: str, *, purpose: str = "") -> list:
    """SAM noun-phrase segmentation of one image. Returns meta_sam_parser mask records."""
    start = time.perf_counter()
    # TODO(verify): request shape. The SAM protocol only says the noun phrase goes in input_text.
    stream = client().responses.create(model=SAM, stream=True, input=[{"role": "user", "content": [
        {"type": "input_image", "image_url": data_url(image_path)},
        {"type": "input_text", "text": phrase},
    ]}])
    text, usage = "", None
    for ev in stream:
        if ev.type == "response.content_part.done" and ev.part.type == "output_text":
            text += ev.part.text  # the live SAM API only finalizes text this way
        elif ev.type == "response.completed":
            usage = ev.response.usage
        elif ev.type in ("response.failed", "response.incomplete", "error"):
            raise RuntimeError(f"SAM request ended with {ev.type}")
    log_call(SAM, purpose, time.perf_counter() - start, usage)
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    return [r for r in parser.finish(CompletedOutcome()).result.records if r.kind == "mask"]


def data_url(path: str | Path) -> str:
    """Image file -> data: URL for an image_url content part."""
    # TODO(verify): api.meta.ai accepts data: URLs in image_url parts
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()
