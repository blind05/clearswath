"""Gate 3: can zero-shot SAM find the weeds? Scored against CoFly-WeedDB's own weed masks.

uv run --with pyarrow python evals/sam_weed_test.py --backend exg            # free baseline, no model
uv run --with pyarrow --with modal python evals/sam_weed_test.py --backend modal   # open SAM 3 on Modal
uv run --with pyarrow python evals/sam_weed_test.py --backend meta           # hosted SAM 3.1 (Meta credits)
uv run --with pyarrow python evals/sam_weed_test.py --backend subtract       # green minus SAM 3.1's crop rows
uv run --with pyarrow --with modal python evals/sam_weed_test.py --backend dinov3   # trained head on Meta DINOv3

A grid cell is sprayed when the predicted mask covers at least --cover of it. The spec's gate: PASS when a prompt
hits >= 95% of weed pixels while spraying <= 50% of the image at the finest cell size; BORDERLINE when that only
holds at a coarser cell; FAIL otherwise. Every model answer is cached by image + prompt + backend.
"""

import argparse
import hashlib
import io
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data" / "datasets" / "cofly" / "train.parquet"
CACHE = ROOT / "data" / "cache" / "sam_eval"
OVERLAYS = ROOT / "evals" / "overlays" / "sam_weed"
RESULTS = ROOT / "evals" / "results_sam_weed.md"
PASS_COVERAGE, MAX_TREATED = 0.95, 0.50
# CoFly: DJI Phantom 4 Pro at 5 m, 84 deg FOV (taken as diagonal), 1280x720 frames -> 2*5*tan(42)/1469 px.
# The paper states no GSD; this is derived. TODO(verify) if a stated value turns up.
COFLY_GSD_M = 2 * 5 * 0.900404 / (1280 ** 2 + 720 ** 2) ** 0.5  # ~0.0061 m per pixel


# ---- scoring (pure, tested) ----

def iou(pred: np.ndarray, truth: np.ndarray) -> float:
    union = np.logical_or(pred, truth).sum()
    return float(np.logical_and(pred, truth).sum() / union) if union else 1.0


def cell_scores(pred: np.ndarray, truth: np.ndarray, cell: int, cover: float) -> tuple[int, int, int, int]:
    """Spray each cell x cell block whose predicted cover >= cover.
    Returns (weed pixels hit, weed pixels, sprayed pixels, all pixels); edge cells are partial."""
    h, w = truth.shape
    sprayed = np.zeros_like(truth, dtype=bool)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            block = pred[y:y + cell, x:x + cell]
            if block.size and block.mean() >= cover and block.any():
                sprayed[y:y + cell, x:x + cell] = True
    return int((sprayed & truth).sum()), int(truth.sum()), int(sprayed.sum()), h * w


def verdict(rows: dict) -> str:
    """rows: cell size -> (coverage, treated). The finest cell is the strict test."""
    sizes = sorted(rows)
    ok = [s for s in sizes if rows[s][0] >= PASS_COVERAGE and rows[s][1] <= MAX_TREATED]
    if sizes[0] in ok:
        return "PASS"
    return "BORDERLINE" if ok else "FAIL"


def excess_green(image: np.ndarray, threshold: float = 0.1) -> np.ndarray:
    """'Spray everything green': ExG = 2g - r - b on chromatic coordinates. Weeds and crop alike."""
    rgb = image[..., :3].astype(float)
    total = rgb.sum(axis=2) + 1e-6
    r, g, b = (rgb[..., i] / total for i in range(3))
    return (2 * g - r - b) > threshold


def dilate(mask: np.ndarray, px: int) -> np.ndarray:
    """Grows a mask by px pixels (8-neighbour), one shift-and-or step at a time."""
    out = mask.copy()
    for _ in range(px):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        g[1:, 1:] |= out[:-1, :-1]
        g[:-1, :-1] |= out[1:, 1:]
        g[1:, :-1] |= out[:-1, 1:]
        g[:-1, 1:] |= out[1:, :-1]
        out = g
    return out


def subtract_crop(image: np.ndarray, crop: np.ndarray, dilate_px: int) -> np.ndarray:
    """Weeds = green pixels that aren't crop. The crop mask is widened by dilate_px so leaf edges aren't weeds."""
    return excess_green(image) & ~dilate(crop, dilate_px)


def mask_from_sam_text(text: str, width: int, height: int, min_score: float = 0.0) -> np.ndarray:
    """Hosted SAM output text -> one boolean mask (union of objects), pasted at each box's corner."""
    from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

    parser = image_segmentation_format().create_parser()
    parser.push(text)
    out = np.zeros((height, width), dtype=bool)
    for rec in parser.finish(CompletedOutcome()).result.records:
        if rec.kind != "mask" or (rec.confidence is not None and rec.confidence < min_score):
            continue
        m, top, left = rec.mask, int(rec.bounds.top), int(rec.bounds.left)
        crop = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width).astype(bool)
        r1, c1 = min(top + m.height, height), min(left + m.width, width)
        if r1 > top and c1 > left:
            out[top:r1, left:c1] |= crop[:r1 - top, :c1 - left]
    return out


# ---- data and backends ----

def load_cofly(n: int, seed: int) -> list[tuple[int, bytes, np.ndarray]]:
    """n random CoFly images (fixed seed) as (index, PNG bytes, weed mask)."""
    import pyarrow.parquet as pq

    table = pq.read_table(DATA)
    picks = sorted(random.Random(seed).sample(range(table.num_rows), n))
    out = []
    for i in picks:
        row = table.slice(i, 1).to_pylist()[0]
        image = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, "PNG")
        mask = np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"]))) > 0
        out.append((i, buf.getvalue(), mask))
    return out


def _cached(backend: str, png: bytes, prompt: str, compute) -> np.ndarray:
    key = hashlib.sha256(png + prompt.encode() + backend.encode()).hexdigest()[:24]
    path = CACHE / f"{key}.npz"
    if path.exists():
        d = np.load(path)
        return np.unpackbits(d["bits"])[: d["h"] * d["w"]].reshape(d["h"], d["w"]).astype(bool)
    mask = compute()
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, bits=np.packbits(mask), h=mask.shape[0], w=mask.shape[1])
    return mask


def predict(backend: str, items: list, prompts: list[str]) -> dict:
    """(index, prompt) -> predicted weed mask, from cache where possible."""
    out = {}
    todo = []
    for idx, png, truth in items:
        for prompt in prompts:
            if backend == "exg":  # free, no model: computed every time
                out[(idx, prompt)] = excess_green(np.asarray(Image.open(io.BytesIO(png))))
                continue
            key = hashlib.sha256(png + prompt.encode() + backend.encode()).hexdigest()[:24]
            if (CACHE / f"{key}.npz").exists():
                out[(idx, prompt)] = _cached(backend, png, prompt, compute=None)
            else:
                todo.append((idx, png, prompt))
    if todo and backend == "meta":
        from app import llm

        for idx, png, prompt in todo:
            tmp = CACHE / "tmp.png"
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(png)
            text = llm.sam_raw(tmp, prompt, purpose="eval:sam_weed")
            w, h = Image.open(io.BytesIO(png)).size
            out[(idx, prompt)] = _cached(backend, png, prompt, lambda: mask_from_sam_text(text, w, h))
    elif todo and backend == "modal":
        import sam3_modal

        results = sam3_modal.segment_batch([(png, prompt) for _, png, prompt in todo])
        for (idx, png, prompt), (bits, h, w) in zip(todo, results, strict=True):
            mask = np.unpackbits(np.frombuffer(bits, dtype=np.uint8))[: h * w].reshape(h, w).astype(bool)
            out[(idx, prompt)] = _cached(backend, png, prompt, lambda: mask)
    return out


def overlay(png: bytes, truth: np.ndarray, pred: np.ndarray, path: Path) -> None:
    """Weed truth in green, prediction in magenta, overlap in white."""
    base = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).copy()
    base[truth & ~pred] = (0.5 * base[truth & ~pred] + [0, 127, 0]).astype(np.uint8)
    base[pred & ~truth] = (0.5 * base[pred & ~truth] + [127, 0, 127]).astype(np.uint8)
    base[pred & truth] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(base).save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["exg", "modal", "meta", "subtract", "dinov3"], default="exg")
    ap.add_argument("--crop-prompts", nargs="+", default=["crop row", "plant"],
                    help="subtract: SAM 3.1 prompts whose union is the crop")
    ap.add_argument("--dilate", type=int, default=12, help="subtract: px the crop mask is widened")
    ap.add_argument("--target-coverage", type=float, default=0.97,
                    help="dinov3: weed-hit target on the tuning images (margin over the 95%% gate)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--prompts", nargs="+", default=["weed", "plant", "green plant"])
    ap.add_argument("--cell", nargs="+", type=int, default=[32, 96])
    ap.add_argument("--cell-m", nargs="+", type=float, help="cell sizes in metres (ground sprayers: 0.25 0.5); "
                    "converted with CoFly's ground resolution and used instead of --cell")
    ap.add_argument("--folds", type=int, default=0, help="dinov3: k-fold cross-validation over --n images")
    ap.add_argument("--cover", type=float, default=0.01, help="share of a cell that triggers spraying")
    args = ap.parse_args()
    prompts = ["(excess green)"] if args.backend == "exg" else args.prompts
    if args.cell_m:
        args.cell = [max(1, round(m / COFLY_GSD_M)) for m in args.cell_m]
    names = {c: (f"{m:g} m" if args.cell_m else f"{c} px") for c, m in zip(args.cell, args.cell_m or args.cell)}

    items = load_cofly(args.n, args.seed)
    if args.backend == "subtract":
        crop = predict("meta", items, args.crop_prompts)  # cached hosted SAM 3.1 answers
        label = f"green minus SAM({' + '.join(args.crop_prompts)}), dilate {args.dilate}"
        prompts = [label]
        preds = {}
        for idx, png, _ in items:
            crop_mask = np.logical_or.reduce([crop[(idx, p)] for p in args.crop_prompts])
            preds[(idx, label)] = subtract_crop(np.asarray(Image.open(io.BytesIO(png))), crop_mask, args.dilate)
    elif args.backend == "dinov3":
        sys.path.insert(0, str(ROOT / "train"))
        import weed_head_modal

        ids = [idx for idx, _, _ in items]
        k = args.folds or 1
        folds = [ids[f::k] for f in range(k)] if args.folds else [ids]  # each image is in exactly one test fold
        report = weed_head_modal.run(folds, args.target_coverage)  # every fold trains on everything else
        label = f"DINOv3 head (tuned to {args.target_coverage:.0%}" + (f", {k}-fold" if args.folds else "") + ")"
        prompts = [label]
        preds = {}
        for idx, png, _ in items:
            bits, h, w = report["preds"][idx]
            preds[(idx, label)] = np.unpackbits(np.frombuffer(bits, np.uint8))[: h * w].reshape(h, w).astype(bool)
        model_dir = ROOT / "data" / "cache" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "weed_head_dinov3.pt").write_bytes(report["head"])
        for r in report["folds"]:
            print(f"fold {r['fold']}: trained on {r['train_n']}, tuned on {r['val_n']} (threshold {r['threshold']:.2f}, "
                  f"val {r['val_coverage']:.1%} hit / {r['val_sprayed']:.1%} sprayed), tested on {r['test_n']} unseen")
    else:
        preds = predict(args.backend, items, prompts)
    lines = [f"# Gate 3: SAM weed test ({args.backend}, CoFly-WeedDB, {args.n} images, seed {args.seed})", "",
             f"Cell sprayed when predicted cover >= {args.cover:.0%}. PASS: >= {PASS_COVERAGE:.0%} of weed hit while "
             f"spraying <= {MAX_TREATED:.0%}, at the finest cell.", "",
             "| prompt | mean IoU | " + " | ".join(f"{names[c]}: weed hit / sprayed" for c in args.cell) + " | verdict |",
             "|---|---|" + "---|" * len(args.cell) + "---|"]
    for prompt in prompts:
        ious, sums = [], {c: [0, 0, 0, 0] for c in args.cell}
        for idx, png, truth in items:
            pred = preds[(idx, prompt)]
            ious.append(iou(pred, truth))
            for c in args.cell:
                sums[c] = [a + b for a, b in zip(sums[c], cell_scores(pred, truth, c, args.cover))]
        rows = {c: (s[0] / max(s[1], 1), s[2] / s[3]) for c, s in sums.items()}
        v = verdict(rows)
        lines.append(f"| {prompt} | {np.mean(ious):.3f} | "
                     + " | ".join(f"{rows[c][0]:.1%} / {rows[c][1]:.1%}" for c in args.cell) + f" | {v} |")
        for idx, png, truth in items[:3]:
            overlay(png, truth, preds[(idx, prompt)], OVERLAYS / f"{args.backend}_{prompt.replace(' ', '_')}_{idx}.png")
    text = "\n".join(lines) + "\n"
    print(text)
    out = RESULTS.with_name(f"results_sam_weed_{args.backend}.md")
    out.write_text(text)
    print(f"wrote {out.relative_to(ROOT)}; overlays in {OVERLAYS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
