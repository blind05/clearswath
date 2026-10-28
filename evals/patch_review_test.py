"""How often is Spark's second opinion on a photo-mode patch right? Scored against CoFly-WeedDB's weed masks.

Not part of the app: the review lost (evals/results_patch_review.md), so its code lives here with its evaluation.

PHOTO_URL=... uv run --with pyarrow python evals/patch_review_test.py [--n 20] [--provider fireworks]
Live: one Modal call and up to MAX_PATCHES Spark calls per image. A patch counts as a real weed patch when
at least WEED_SHARE of its pixels are weed in CoFly's mask (data/datasets/cofly/train.parquet).
"""

import argparse
import base64
import io
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.features import shapes
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

log = logging.getLogger(__name__)
MAX_PATCHES = 10  # the largest patches only: cost and latency stay bounded on a messy photo
MIN_PIXELS = 64  # specks below this aren't worth a model call
CROP_PX = 448  # longest side of the crop Spark sees
WORKERS = 4  # patches asked at once
SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["weed", "crop", "soil"]},
                   "confidence": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["label", "confidence", "reason"],
    "additionalProperties": False,
}


def split(mask: np.ndarray) -> list:
    """The flagged area as separate patches (pixel-coordinate polygons), largest first; specks dropped."""
    found = [shape(g) for g, v in shapes(mask.astype(np.uint8), mask=mask) if v]
    return sorted((p for p in found if p.area >= MIN_PIXELS), key=lambda p: -p.area)


def _crop(photo: Image.Image, patch, pad: float = 0.3) -> str:
    """data: URL of the photo around the patch's box, widened by pad on each side so Spark sees the context."""
    x0, y0, x1, y1 = patch.bounds
    dx, dy = (x1 - x0) * pad + 16, (y1 - y0) * pad + 16
    box = (max(0, int(x0 - dx)), max(0, int(y0 - dy)), min(photo.width, int(x1 + dx)), min(photo.height, int(y1 + dy)))
    piece = photo.crop(box)
    piece.thumbnail((CROP_PX, CROP_PX))
    buf = io.BytesIO()
    piece.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _ask(photo: Image.Image, patch, provider) -> dict:
    messages = [{"role": "system", "content": llm.load_prompt("patch_review")},
                {"role": "user", "content": [
                    {"type": "text", "text": "What is the patch in the middle of this crop mostly?"},
                    {"type": "image_url", "image_url": {"url": _crop(photo, patch)}}]}]
    answer = llm.chat_json(messages, SCHEMA, "patch_review", purpose="patch_review", provider=provider)
    if answer.get("label") not in ("weed", "crop", "soil"):
        raise ValueError("unexpected patch label")
    return answer


def review(photo_path, overlay_png: str, provider: str | None = None) -> dict:
    """Spark's opinion on each of the largest patches in the weed head's overlay (base64 RGBA PNG)."""
    mask = np.asarray(Image.open(io.BytesIO(base64.b64decode(overlay_png))).convert("RGBA"))[..., 3] > 0
    photo = Image.open(photo_path).convert("RGB").resize((mask.shape[1], mask.shape[0]))
    patches = split(mask)
    asked = patches[:MAX_PATCHES]
    try:
        with ThreadPoolExecutor(WORKERS) as pool:
            answers = list(pool.map(lambda p: _ask(photo, p, provider), asked))
    except Exception:
        log.warning("patch review failed", exc_info=True)
        return {"status": "failed", "patches": len(patches), "answers": []}
    rows = [{"bounds": [round(v) for v in p.bounds], "label": a["label"], "confidence": float(a["confidence"]),
             "reason": a["reason"]} for p, a in zip(asked, answers, strict=True)]
    return {"status": "done", "model": llm.spark_model(provider), "patches": len(patches), "reviewed": len(asked),
            "answers": rows}


COFLY = ROOT / "data" / "datasets" / "cofly" / "train.parquet"
WEED_SHARE = 0.2


def truth_per_patch(overlay_png: str, truth: np.ndarray, n: int) -> list[bool]:
    """For the n patches review asked about (same split, same order): is each a real weed patch?"""
    from rasterio.features import rasterize

    m = np.asarray(Image.open(io.BytesIO(base64.b64decode(overlay_png))))[..., 3] > 0
    t = np.asarray(Image.fromarray(truth).resize((m.shape[1], m.shape[0]), Image.NEAREST))
    out = []
    for p in split(m)[:n]:
        inside = rasterize([p], out_shape=m.shape, fill=0, default_value=1).astype(bool) & m
        out.append(bool(t[inside].mean() >= WEED_SHARE) if inside.any() else False)
    return out


def main(n: int, provider: str | None, seed: int) -> None:
    import pyarrow.parquet as pq

    table = pq.read_table(COFLY)
    ids = np.random.default_rng(seed).choice(table.num_rows, size=n, replace=False)
    counts = {"weed_said_weed": 0, "weed_said_not": 0, "not_said_weed": 0, "not_said_not": 0}
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i in ids:
            row = table.slice(int(i), 1).to_pylist()[0]
            path = Path(tmp) / f"{i}.jpg"
            Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB").save(path, quality=92)
            truth = np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"]))) > 0
            try:
                head = llm.weed_photo(path)
            except Exception as e:  # a dropped connection to Modal costs one image, not the run
                print(int(i), f"skipped: {type(e).__name__}", flush=True)
                failed += 1
                continue
            r = review(path, head["overlay_png"], provider)
            if r["status"] != "done":
                failed += 1
                continue
            for real, a in zip(truth_per_patch(head["overlay_png"], truth, len(r["answers"])), r["answers"],
                               strict=True):
                counts[f"{'weed' if real else 'not'}_said_{'weed' if a['label'] == 'weed' else 'not'}"] += 1
            print(int(i), counts, flush=True)
    real_weed = counts["weed_said_weed"] + counts["weed_said_not"]
    print(f"\n{n} CoFly images, Spark via {llm.spark_model(provider)}; skipped or failed: {failed}")
    print(counts)
    print(f"real weed patches Spark called weed: {counts['weed_said_weed']}/{real_weed}; "
          f"agreement overall: {(counts['weed_said_weed'] + counts['not_said_not']) / max(sum(counts.values()), 1):.0%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--provider", choices=["meta", "baseten", "fireworks"])
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    main(a.n, a.provider, a.seed)
