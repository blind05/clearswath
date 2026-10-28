"""PhenoBench (UAV sugar beet, crop vs weed) downloaded once into the Modal volume, never to this machine.

uv run --with modal python train/phenobench_modal.py            # download the parquet parts, print rows per date and labels
uv run --with modal python train/phenobench_modal.py evaluate   # leave-one-date-out: head vs baselines
CC BY-SA 4.0 (www.phenobench.org): derived masks we publish must carry the same licence.
Labels: 0 soil, 1 crop, 2 weed, 3 partial crop, 4 partial weed; weeds = 2 and 4. GSD 1 mm/px (paper).
"""

import modal

app = modal.App("clearswath-phenobench")
image = modal.Image.debian_slim(python_version="3.12").pip_install("requests", "numpy", "pillow", "pyarrow")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
# The official zip (phenobench.org) serves at ~0.24 MB/s, so we use AgML's reformat of the same data on
# Hugging Face: 13 parquet files, image + mask per row, train and val merged, with each tile's flight date.
HF = "https://huggingface.co/datasets/Project-AgML/PhenoBench_segmentation/resolve/main/data/"
PARTS = [f"train-{i:05d}-of-00013.parquet" for i in range(13)]
ROOT = "/data/phenobench"
WEED, CROP = (2, 4), (1, 3)
gpu_image = (modal.Image.debian_slim(python_version="3.12")
             .pip_install("torch", "torchvision", "transformers==5.21.0", "accelerate", "pillow", "numpy", "pyarrow")
             .add_local_python_source("weedhead"))


@app.function(image=image, volumes={"/data": volume}, timeout=3600, cpu=4.0, memory=16384)
def fetch() -> dict:
    """Downloads the parquet parts once; reports rows per flight date and the label values in the masks."""
    import io
    import os
    from collections import Counter

    import numpy as np
    import pyarrow.parquet as pq
    import requests
    from PIL import Image

    os.makedirs(ROOT, exist_ok=True)
    for name in PARTS:
        path = f"{ROOT}/{name}"
        if not os.path.exists(path):
            with requests.get(HF + name, stream=True, timeout=600) as r, open(path + ".part", "wb") as f:
                r.raise_for_status()
                for chunk in r.iter_content(8 << 20):
                    f.write(chunk)
            os.rename(path + ".part", path)
    volume.commit()
    dates, values = Counter(), Counter()
    for name in PARTS:
        t = pq.read_table(f"{ROOT}/{name}", columns=["date"])
        dates.update(t.column("date").to_pylist())
    sample = pq.read_table(f"{ROOT}/{PARTS[0]}").slice(0, 10).to_pylist()
    for row in sample:
        values.update(np.unique(np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"])))).tolist())
    img = Image.open(io.BytesIO(sample[0]["image"]["bytes"]))
    return {"rows_per_date": dict(sorted(dates.items())), "mask_values_in_10_rows": dict(values),
            "image": [img.mode, img.size], "plant_id_example": sample[0]["plant_id"]}


@app.function(image=gpu_image, gpu="L4", timeout=3 * 3600, volumes={"/data": volume}, memory=49152,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def evaluate(cells_px=(100, 250, 500), target=0.97, epochs=12, tune_n=100, sam3_n=100, seed=0) -> dict:
    """Leave-one-date-out: for each flight date, train on the other two (minus tune_n to set the threshold) and
    test on that whole date. Baselines on the same tiles: broadcast, spray everything green, zero-shot SAM 3."""
    import io
    import os
    import random

    os.environ["HF_HOME"] = "/data"  # model weights live in the same volume
    import numpy as np
    import pyarrow.parquet as pq
    import torch
    from PIL import Image

    import weedhead as wh

    features = wh.load_dino()
    tiles = []  # (date, features, patch target, weed mask, crop mask, green mask)
    for name in PARTS:
        for row in pq.read_table(f"{ROOT}/{name}").to_pylist():
            img = np.asarray(Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB"))
            sem = np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"])))
            weed, crop = np.isin(sem, WEED), np.isin(sem, CROP)
            rgb = img.astype(np.float32)
            tot = rgb.sum(2) + 1e-6
            green = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) / tot > 0.1
            f = features(img)
            tiles.append((row["date"], f, wh.patch_target(weed, f.shape[1:]).to("cuda"), weed, crop, green))
    dates = sorted({t[0] for t in tiles})

    folds = []
    for d in dates:
        pool = [t for t in tiles if t[0] != d]
        test = [t for t in tiles if t[0] == d]
        random.Random(seed).shuffle(pool)
        tune, fit = pool[:tune_n], pool[tune_n:]
        head = wh.train_head([(t[1], t[2]) for t in fit], seed, epochs)
        tune_pairs = [(wh.probability(head, t[1], t[3].shape), t[3]) for t in tune]
        threshold = wh.pick_threshold(tune_pairs, target, min(cells_px))
        probs = [(wh.probability(head, t[1], t[3].shape), t[3]) for t in test]
        crop_px = sum(t[4].sum() for t in test)
        crop_hit = sum(((p >= threshold) & t[4]).sum() for (p, _), t in zip(probs, test))
        inter = sum(((p >= threshold) & w).sum() for p, w in probs)
        union = sum(((p >= threshold) | w).sum() for p, w in probs)
        green = [(t[5].astype(np.float32), t[3]) for t in test]
        folds.append({"test_date": d, "train_n": len(fit), "tune_n": len(tune), "test_n": len(test),
                      "threshold": threshold, "tune": wh.coverage(tune_pairs, threshold, min(cells_px)),
                      "head": {c: wh.coverage(probs, threshold, c) for c in cells_px},
                      "head_crop_pixels_sprayed": float(crop_hit / max(crop_px, 1)),
                      "head_weed_iou": float(inter / max(union, 1)),
                      "green": {c: wh.coverage(green, 0.5, c) for c in cells_px}})
        del head, probs, green
        torch.cuda.empty_cache()

    sam = {}
    if sam3_n:
        from transformers import Sam3Model, Sam3Processor

        model = Sam3Model.from_pretrained("facebook/sam3").to("cuda").eval()
        proc = Sam3Processor.from_pretrained("facebook/sam3")
        picks = random.Random(seed).sample(range(len(tiles)), sam3_n)
        rows = [r for name in PARTS for r in pq.read_table(f"{ROOT}/{name}", columns=["image"]).to_pylist()]
        sam_pairs = []
        for k in picks:
            pil = Image.open(io.BytesIO(rows[k]["image"]["bytes"])).convert("RGB")
            inputs = proc(images=pil, text="weed", return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = model(**inputs)
            res = proc.post_process_instance_segmentation(out, threshold=0.5, mask_threshold=0.5,
                                                          target_sizes=inputs.get("original_sizes").tolist())[0]
            m = np.zeros(tiles[k][3].shape, bool)
            for mk in res["masks"]:
                m |= mk.cpu().numpy().astype(bool)
            sam_pairs.append((m.astype(np.float32), tiles[k][3]))
        sam = {"n": len(sam_pairs), "prompt": "weed", **{str(c): wh.coverage(sam_pairs, 0.5, c) for c in cells_px}}
    return {"dates": dates, "folds": folds, "sam3_zero_shot": sam, "cells_px": list(cells_px), "gsd_m": 0.001}


if __name__ == "__main__":
    import json
    import sys

    with app.run():
        if sys.argv[1:] == ["evaluate"]:
            print(json.dumps(evaluate.remote(), indent=1))
        else:
            print(json.dumps(fetch.remote(), indent=1)[:6000])
