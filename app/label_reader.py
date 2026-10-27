"""Pesticide label (PDF or image) -> LabelRules. Every kept rule's quote is found in the label text."""

import hashlib
import json
from pathlib import Path
from typing import Literal

import pymupdf
from pydantic import BaseModel, ValidationError

from app import llm

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "labels"
KINDS = ["buffer", "wind", "rain", "rate", "other"]
TARGETS = ["water", "building", "habitat"]
APPLIES_TO = ["all", "aerial", "ground"]
# a label says "feet" or "ft"; store the short form buffers.plan expects
BUFFER_UNITS = {"ft": "ft", "feet": "ft", "foot": "ft", "m": "m", "meter": "m", "meters": "m",
                "metre": "m", "metres": "m"}


class LabelRule(BaseModel):
    kind: Literal["buffer", "wind", "rain", "rate", "other"]
    target: Literal["water", "building", "habitat"] | None
    applies_to: Literal["all", "aerial", "ground"]
    value: float | None
    unit: str | None
    summary: str
    quote: str
    page: int
    condition: str | None = None  # e.g. "ULV aerial only", "New York only"; None = always applies


class LabelRules(BaseModel):
    product_name: str | None
    epa_reg_no: str | None
    rules: list[LabelRule]
    dropped: list[dict]  # model rules that failed checks, each with a "reason"
    source: Literal["pdf", "image"]  # image text is the model's own transcription


RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "target": {"type": ["string", "null"], "enum": [*TARGETS, None]},
        "applies_to": {"type": "string", "enum": APPLIES_TO},
        "value": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "quote": {"type": "string"},
        "page": {"type": "integer"},
        "condition": {"type": ["string", "null"]},
    },
    "required": ["kind", "target", "applies_to", "value", "unit", "summary", "quote", "page", "condition"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": ["string", "null"]},
        "epa_reg_no": {"type": ["string", "null"]},
        "rules": {"type": "array", "items": RULE_SCHEMA},
    },
    "required": ["product_name", "epa_reg_no", "rules"],
    "additionalProperties": False,
}


def _norm(s: str) -> str:
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("­", "")):
        s = s.replace(a, b)
    return " ".join(s.split()).lower()


def _pages(path: Path) -> tuple[list[str], str]:
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            return [p.get_text() for p in doc], "pdf"
    msg = llm.chat([{"role": "user", "content": [
        {"type": "text", "text": "Transcribe all text on this pesticide label exactly, word for word."},
        {"type": "image_url", "image_url": {"url": llm.data_url(path)}},
    ]}], purpose="label_ocr", provider="meta")  # image input verified on the Meta Model API only
    return [msg.content or ""], "image"


def _check(rule: dict, pages: list[str]) -> str | None:
    """Fixes rule["page"] if the quote is on another page. Returns a reason to drop, or None."""
    quote = _norm(rule.get("quote") or "")
    if not quote:
        return "empty quote"
    claimed = rule.get("page")
    order = [claimed] + [n for n in range(1, len(pages) + 1) if n != claimed]
    found = next((n for n in order if 1 <= n <= len(pages) and quote in _norm(pages[n - 1])), None)
    if found is None:
        return "quote not found in label text"
    rule["page"] = found
    if rule.get("kind") == "buffer":
        if rule.get("target") is None:
            return "buffer without a target"
        unit = BUFFER_UNITS.get((rule.get("unit") or "").strip().lower())
        if rule.get("value") is None or unit is None:
            return "buffer without a distance in ft or m"
        rule["unit"] = unit
    return None


def read_raw(path: str | Path, provider: str | None = None) -> dict:
    """The model's part: page text (a transcription for photos) and raw rules. Cached on disk per model."""
    path = Path(path)
    prompt = llm.load_prompt("label")
    key = hashlib.sha256(path.read_bytes() + prompt.encode() + llm.spark_model(provider).encode()
                         + json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()[:20]
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    pages, source = _pages(path)
    text = "\n\n".join(f"=== Page {n} ===\n{t}" for n, t in enumerate(pages, 1))
    out = llm.chat_json([{"role": "system", "content": prompt},
                         {"role": "user", "content": text}], SCHEMA, "label_rules", purpose="label",
                        provider=provider)
    raw = {"pages": pages, "source": source, "out": out}
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(raw))
    return raw


def read_label(path: str | Path, provider: str | None = None) -> LabelRules:
    """Quotes are re-checked on every call, so cached model output never skips verification.

    provider picks the Spark that extracts rules (llm.resolve_provider); photos are transcribed on Meta.
    """
    return verify(read_raw(path, provider))


def verify(raw: dict) -> LabelRules:
    """Checks every rule's quote against the page text; failures go to `dropped`. Pure code, no model."""
    pages, source, out = raw["pages"], raw["source"], raw["out"]
    rules, dropped = [], []
    for r in out["rules"]:
        reason = _check(r, pages)
        if not reason:
            try:
                rules.append(LabelRule(**r))
                continue
            except ValidationError as e:
                reason = f"invalid fields: {', '.join(str(x['loc'][0]) for x in e.errors())}"
        dropped.append({**r, "reason": reason})
    return LabelRules(product_name=out["product_name"], epa_reg_no=out["epa_reg_no"],
                      rules=rules, dropped=dropped, source=source)
