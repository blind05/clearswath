"""Crop-vs-weed head on frozen Meta DINOv3 features, trained on CoFly-WeedDB on a Modal GPU.

Not part of the app or its Docker image. Needs the `huggingface` Modal secret with access to
facebook/dinov3-vits16-pretrain-lvd1689m. Called from evals/sam_weed_test.py --backend dinov3.

Split: the gate's test images are never trained on; of the rest, VAL_N tune the threshold, the others train.
"""

import io

import modal

app = modal.App("clearswath-weed-head")
image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "torch", "transformers==5.21.0", "pillow", "numpy", "pyarrow", "requests")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
DINO = "facebook/dinov3-vits16-pretrain-lvd1689m"
COFLY = ("https://huggingface.co/datasets/Project-AgML/CoFly-Weed-DB_weed_segmentation/resolve/main/"
         "data/train-00000-of-00001.parquet")
PATCH, VAL_N, SEED = 16, 21, 0


@app.function(image=image, gpu="L4", timeout=3600, volumes={"/root/.cache/huggingface": volume},
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def train_and_predict(test_ids: list[int], target_coverage: float = 0.95, epochs: int = 60) -> dict:
    """Trains on every CoFly image not in test_ids; returns packed weed masks for test_ids plus a report."""
    import os
    import random

    import numpy as np
    import pyarrow.parquet as pq
    import requests
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from PIL import Image
    from transformers import AutoModel

    path = "/root/.cache/huggingface/cofly.parquet"
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(requests.get(COFLY, timeout=600).content)
    table = pq.read_table(path)

    model = AutoModel.from_pretrained(DINO).to("cuda").eval()
    regs = getattr(model.config, "num_register_tokens", 0)
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)

    def load(i):
        row = table.slice(i, 1).to_pylist()[0]
        img = np.asarray(Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB"))
        mask = np.asarray(Image.open(io.BytesIO(row["mask"]["bytes"]))) > 0
        return img, mask

    @torch.no_grad()
    def features(img):
        h, w = img.shape[0] // PATCH * PATCH, img.shape[1] // PATCH * PATCH
        x = torch.from_numpy(img[:h, :w]).to("cuda").permute(2, 0, 1)[None].float() / 255
        out = model(pixel_values=(x - mean) / std).last_hidden_state[0, 1 + regs:]  # patch tokens only
        return out.reshape(h // PATCH, w // PATCH, -1).permute(2, 0, 1).half()  # C, H/16, W/16

    ids = list(range(table.num_rows))
    pool = [i for i in ids if i not in set(test_ids)]
    random.Random(SEED).shuffle(pool)
    val_ids, train_ids = pool[:VAL_N], pool[VAL_N:]
    cache = {}
    for i in ids:
        img, mask = load(i)
        f = features(img)
        gh, gw = f.shape[1:]
        target = torch.from_numpy(mask[:gh * PATCH, :gw * PATCH]).float().reshape(gh, PATCH, gw, PATCH).mean((1, 3))
        cache[i] = (f, target.to("cuda"), mask)

    head = nn.Sequential(nn.Conv2d(cache[0][0].shape[0], 128, 3, padding=1), nn.GELU(),
                         nn.Conv2d(128, 64, 3, padding=1), nn.GELU(), nn.Conv2d(64, 1, 1)).to("cuda")
    weed_share = float(torch.stack([cache[i][1].mean() for i in train_ids]).mean())
    pos_weight = torch.tensor((1 - weed_share) / max(weed_share, 1e-3), device="cuda")  # favour weed recall
    opt = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-2)
    for epoch in range(epochs):
        random.Random(epoch).shuffle(train_ids)
        for i in train_ids:
            f, target, _ = cache[i]
            flip = epoch % 2 == 1  # horizontal flip of the feature map and target as cheap augmentation
            x, y = (f.flip(-1), target.flip(-1)) if flip else (f, target)
            logits = head(x.float()[None])[0, 0]
            loss = F.binary_cross_entropy_with_logits(logits, (y > 0.25).float(), pos_weight=pos_weight)
            opt.zero_grad()
            loss.backward()
            opt.step()

    @torch.no_grad()
    def prob(i):
        f, _, mask = cache[i]
        p = torch.sigmoid(head(f.float()[None]))
        return F.interpolate(p, size=mask.shape, mode="bilinear", align_corners=False)[0, 0].cpu().numpy(), mask

    def coverage_at(threshold, pairs, cell=32):
        hit = weed = sprayed = total = 0
        for p, mask in pairs:
            pred = p >= threshold
            h, w = mask.shape
            hh, ww = -(-h // cell) * cell, -(-w // cell) * cell
            pad = np.zeros((hh, ww), bool)
            pad[:h, :w] = pred
            cells = pad.reshape(hh // cell, cell, ww // cell, cell).any((1, 3))
            spray = np.repeat(np.repeat(cells, cell, 0), cell, 1)[:h, :w]
            hit, weed = hit + (spray & mask).sum(), weed + mask.sum()
            sprayed, total = sprayed + spray.sum(), total + h * w
        return hit / max(weed, 1), sprayed / total

    val = [prob(i) for i in val_ids]
    threshold = 0.5
    for t in np.linspace(0.95, 0.02, 94):  # the highest threshold that still reaches the coverage target
        if coverage_at(t, val)[0] >= target_coverage:
            threshold = float(t)
            break
    val_cov, val_sprayed = coverage_at(threshold, val)
    preds = {}
    for i in test_ids:
        p, _ = prob(i)
        preds[i] = (np.packbits(p >= threshold).tobytes(), p.shape[0], p.shape[1])
    buf = io.BytesIO()
    torch.save(head.state_dict(), buf)
    return {"preds": preds, "threshold": threshold, "val_coverage": float(val_cov), "val_sprayed": float(val_sprayed),
            "train_n": len(train_ids), "val_n": len(val_ids), "test_n": len(test_ids), "head": buf.getvalue()}


def run(test_ids: list[int], target_coverage: float = 0.95) -> dict:
    with app.run():
        return train_and_predict.remote(test_ids, target_coverage)
