"""The weed head the live photo mode serves: DINOv3 features, trained on CoFly-WeedDB and PhenoBench together.

uv run --with modal python train/deploy_head_modal.py
10% of each dataset is held back: it sets the threshold (95% of weed pixels inside 32 px cells sprayed at >= 1%
cover, as in the gates) and reports held-out results per dataset. Saves /data/models/weed_head_v1.pt in the volume.
"""

import modal

app = modal.App("clearswath-deploy-head")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch", "transformers==5.21.0", "pillow", "numpy", "pyarrow")
         .add_local_python_source("weedhead"))
PHENOBENCH = [f"/data/phenobench/train-{i:05d}-of-00013.parquet" for i in range(13)]
COFLY = "/data/cofly.parquet"
OUT = "/data/models/weed_head_v1.pt"


@app.function(image=image, gpu=["L4", "A10G"], timeout=3 * 3600, volumes={"/data": volume}, memory=49152,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def train(epochs: int = 12, target: float = 0.95, cell: int = 32, cover: float = 0.01, seed: int = 0) -> dict:
    import io
    import os
    import random

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    import pyarrow.parquet as pq
    import torch
    from PIL import Image

    import weedhead as wh

    features = wh.load_dino()
    tiles = []  # (dataset, features, patch target, weed mask)
    for source, paths, is_weed in (("cofly", [COFLY], lambda m: m > 0),
                                   ("phenobench", PHENOBENCH, lambda m: np.isin(m, (2, 4)))):
        for path in paths:
            for row in pq.read_table(path, columns=["image", "mask"]).to_pylist():
                img = np.asarray(Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB"))
                weed = is_weed(np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"]))))
                f = features(img)
                tiles.append((source, f, wh.patch_target(weed, f.shape[1:]).to("cuda"), weed))
    rng = random.Random(seed)
    rng.shuffle(tiles)
    held = {}
    for source in ("cofly", "phenobench"):
        mine = [t for t in tiles if t[0] == source]
        held[source] = mine[:max(10, len(mine) // 10)]
    held_ids = {id(t) for ts in held.values() for t in ts}
    fit = [t for t in tiles if id(t) not in held_ids]
    head = wh.train_head([(t[1], t[2]) for t in fit], seed, epochs)
    pairs = {s: [(wh.probability(head, t[1], t[3].shape), t[3]) for t in ts] for s, ts in held.items()}
    threshold = wh.pick_threshold(pairs["cofly"] + pairs["phenobench"], target, cell, cover)
    report = {s: dict(zip(("hit", "sprayed"), wh.coverage(p, threshold, cell, cover))) for s, p in pairs.items()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    torch.save({"state_dict": head.state_dict(), "threshold": threshold, "in_channels": tiles[0][1].shape[0],
                "dino": wh.DINO, "trained_on": {s: len([t for t in fit if t[0] == s]) for s in held},
                "held_out": report, "cell_px": cell, "cover": cover}, OUT)
    volume.commit()
    return {"threshold": threshold, "fit": len(fit), "held_out": report}


if __name__ == "__main__":
    import json

    with app.run(detach=True):  # detached and polled: the local link to Modal drops on long calls
        call = train.spawn()
        print(f"train call {call.object_id}", flush=True)
        while True:
            try:
                print(json.dumps(call.get(timeout=60), indent=1))
                break
            except TimeoutError:
                continue
            except (modal.exception.ConnectionError, OSError):
                continue
