"""Muse Wonder points out hazards on the aerial tile, SAM 3.1 outlines them, and Wonder checks the outlines once.

SAM 3.1 returns no masks for "tree line", "creek" or "building" on NAIP tiles, but outlines a feature closely when
given a box around it, so Wonder supplies the boxes. The models only propose shapes; buffers.plan decides.
"""

import json
import math
from pathlib import Path

import numpy as np
from meta_sam_parser import (CompletedOutcome, FramePrompt, PromptBox, PromptObject, build_object_prompt,
                             decode_mask_to_raster, image_segmentation_format)
from PIL import Image, ImageDraw

from app import llm, segment

# Wonder's words -> the hazard lists buffers.plan reads
KINDS = {"tree line": "habitat", "woods": "habitat", "building": "building", "water": "water"}
MIN_CONFIDENCE = 0.5  # SAM masks below this are dropped
# "low": ~25 s and every hazard kind on the SD tile; default effort took 1-3 min, "minimal" missed buildings
REASONING = "low"
SAM_BATCH = 16  # objects per SAM request: the API refuses more ("exceed this model's limit of 16")
_HAZARD = {"type": "object", "additionalProperties": False, "required": ["kind", "box", "note"], "properties": {
    "kind": {"type": "string", "enum": list(KINDS)},
    "box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    "note": {"type": "string"}}}
FIND = {"type": "object", "additionalProperties": False, "required": ["hazards"],
        "properties": {"hazards": {"type": "array", "items": _HAZARD}}}
REVIEW = {"type": "object", "additionalProperties": False, "required": ["keep", "add"], "properties": {
    "keep": {"type": "array", "items": {"type": "integer"}}, "add": {"type": "array", "items": _HAZARD}}}


def _ask(png: Path, prompt: str, schema: dict, name: str) -> dict:
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                             {"type": "image_url", "image_url": {"url": llm.data_url(png)}}]}]
    return llm.chat_json(messages, schema, name, purpose=f"scout:{name}", model=llm.WONDER, provider="meta",
                         reasoning_effort=REASONING)


def _clip(b: list[int], width: int, height: int) -> PromptBox | None:
    """A box from the model, clamped to the image (right and bottom are exclusive); None if nothing is left."""
    left, top = max(0, min(b[0], b[2])), max(0, min(b[1], b[3]))
    right, bottom = min(width, max(b[0], b[2])), min(height, max(b[1], b[3]))
    return PromptBox(left=left, top=top, right=right, bottom=bottom) if right > left and bottom > top else None


def _masks(png: Path, boxes: dict[int, PromptBox], width: int, height: int) -> dict:
    """SAM on all boxes, SAM_BATCH per call -> {box number: mask record}, confident masks only."""
    out, items = {}, list(boxes.items())
    for i in range(0, len(items), SAM_BATCH):
        objects = [PromptObject(id=n, prompts=[FramePrompt(frame=0, box=b)]) for n, b in items[i:i + SAM_BATCH]]
        text = llm.sam_raw(png, build_object_prompt(size=(width, height), objects=objects), purpose="scout:sam")
        parser = image_segmentation_format().create_parser()
        parser.push(text)
        out |= {int(r.object_id): r for r in parser.finish(CompletedOutcome()).result.records
                if r.kind == "mask" and (r.confidence is None or r.confidence >= MIN_CONFIDENCE)}
    return out


def _overlay(png: Path, masks: dict, out: Path) -> Path:
    """The tile with each mask in magenta and its box number, for Wonder's review."""
    image = Image.open(png).convert("RGBA")
    layer = np.zeros((image.height, image.width, 4), dtype=np.uint8)
    for rec in masks.values():
        m = np.frombuffer(decode_mask_to_raster(rec.mask), dtype=np.uint8).reshape(rec.mask.height, rec.mask.width)
        top, left = max(rec.bounds.top, 0), max(rec.bounds.left, 0)
        sub = layer[top:top + m.shape[0], left:left + m.shape[1]]
        sub[m[:sub.shape[0], :sub.shape[1]] == 1] = (196, 18, 122, 120)
    image = Image.alpha_composite(image, Image.fromarray(layer))
    draw = ImageDraw.Draw(image)
    for n, rec in masks.items():
        draw.text((rec.bounds.left + 3, rec.bounds.top + 3), str(n), fill=(255, 255, 0, 255))
    image.convert("RGB").save(out)
    return out


def scout(png: str | Path) -> dict:
    """Aerial tile (with its imagery.fetch_tile sidecar) -> hazard polygons in lon/lat, plus a trace of each step."""
    png = Path(png)
    meta = json.loads(png.with_suffix(".json").read_text())
    width, height = meta["width"], meta["height"]
    gsd = round(math.hypot(meta["transform"][0], meta["transform"][1]), 2)

    found = _ask(png, llm.load_prompt("scout_find").format(width=width, height=height, gsd=gsd), FIND, "find")
    items = {n: h for n, h in enumerate(found["hazards"], 1)}
    boxes = {n: b for n, h in items.items() if (b := _clip(h["box"], width, height))}
    masks = _masks(png, boxes, width, height)
    trace = [f"Muse Wonder marked {len(items)} features; SAM 3.1 outlined {len(masks)} of them"]

    kept, added = set(masks), {}
    if masks:
        listing = "\n".join(f"{n}: {items[n]['kind']} ({items[n]['note']})" for n in sorted(masks))
        review = _ask(_overlay(png, masks, png.with_name("scout_review.png")),
                      llm.load_prompt("scout_review").format(width=width, height=height, items=listing), REVIEW,
                      "review")
        kept = set(review["keep"]) & set(masks)
        trace.append(f"Muse Wonder checked the outlines: kept {len(kept)}, dropped {len(masks) - len(kept)}")
        start = max(items) + 1
        added = {start + i: h for i, h in enumerate(review["add"])}
        new = _masks(png, {n: b for n, h in added.items() if (b := _clip(h["box"], width, height))}, width, height)
        if added:
            trace.append(f"Muse Wonder marked {len(added)} features it had missed; SAM 3.1 outlined {len(new)}")
        items, masks, kept = items | added, masks | new, kept | set(new)

    out = {kind: [] for kind in set(KINDS.values())}
    for n in sorted(kept):
        out[KINDS[items[n]["kind"]]] += segment.record_polygons(masks[n], width, height, meta["transform"],
                                                                meta["crs"])
    return out | {"trace": trace}
