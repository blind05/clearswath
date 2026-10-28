"""Shared by the Modal training jobs: frozen DINOv3 patch features, a small crop-vs-weed head, and the
spray-coverage maths used to pick its threshold. Runs inside Modal containers (torch on a GPU)."""

import random

import numpy as np

PATCH = 16
DINO = "facebook/dinov3-vits16-pretrain-lvd1689m"


def load_dino(name: str = DINO):
    """DINOv3 (16 px patches, register tokens) or DINOv2 (14 px); features.patch says which."""
    import torch
    from transformers import AutoModel

    model = AutoModel.from_pretrained(name).to("cuda").eval()
    regs = getattr(model.config, "num_register_tokens", 0)
    patch = model.config.patch_size
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)

    @torch.no_grad()
    def features(img: np.ndarray):
        """RGB uint8 HxWx3 -> C x H/patch x W/patch half-precision patch features (cropped to whole patches)."""
        h, w = img.shape[0] // patch * patch, img.shape[1] // patch * patch
        x = torch.from_numpy(np.ascontiguousarray(img[:h, :w])).to("cuda").permute(2, 0, 1)[None].float() / 255
        out = model(pixel_values=(x - mean) / std).last_hidden_state[0, 1 + regs:]  # patch tokens only
        return out.reshape(h // patch, w // patch, -1).permute(2, 0, 1).half()

    features.patch = patch
    return features


def patch_target(mask: np.ndarray, grid: tuple[int, int]):
    """Share of weed pixels in each 16 px patch."""
    import torch

    gh, gw = grid
    return torch.from_numpy(mask[:gh * PATCH, :gw * PATCH]).float().reshape(gh, PATCH, gw, PATCH).mean((1, 3))


def train_head(samples: list, seed: int, epochs: int):
    """samples: (features, patch target) pairs on the GPU. Weed recall is favoured via pos_weight."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    torch.manual_seed(seed)
    head = nn.Sequential(nn.Conv2d(samples[0][0].shape[0], 128, 3, padding=1), nn.GELU(),
                         nn.Conv2d(128, 64, 3, padding=1), nn.GELU(), nn.Conv2d(64, 1, 1)).to("cuda")
    weed_share = float(torch.stack([t.mean() for _, t in samples]).mean())
    pos_weight = torch.tensor((1 - weed_share) / max(weed_share, 1e-3), device="cuda")
    opt = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-2)
    order = list(range(len(samples)))
    for epoch in range(epochs):
        random.Random(seed + epoch).shuffle(order)
        for k in order:
            f, target = samples[k]
            x, y = (f.flip(-1), target.flip(-1)) if epoch % 2 else (f, target)  # cheap flip augmentation
            loss = F.binary_cross_entropy_with_logits(head(x.float()[None])[0, 0], (y > 0.25).float(),
                                                      pos_weight=pos_weight)
            opt.zero_grad()
            loss.backward()
            opt.step()
    return head


def probability(head, f, shape):
    """Per-pixel weed probability at the image's full size."""
    import torch
    import torch.nn.functional as F

    with torch.no_grad():
        p = torch.sigmoid(head(f.float()[None]))
        return F.interpolate(p, size=shape, mode="bilinear", align_corners=False)[0, 0].cpu().numpy()


def coverage(pairs, threshold: float, cell: int, cover: float = 0.0) -> tuple[float, float]:
    """(weed pixels hit, share sprayed) when a cell x cell block is sprayed if at least `cover` of its pixels
    are >= threshold (any pixel when cover is 0). Edge cells are partial, as in sam_weed_test.cell_scores."""
    hit = weed = sprayed = total = 0
    for p, mask in pairs:
        h, w = mask.shape
        hh, ww = -(-h // cell) * cell, -(-w // cell) * cell
        on, real = np.zeros((hh, ww), np.float32), np.zeros((hh, ww), np.float32)
        on[:h, :w], real[:h, :w] = p >= threshold, 1
        n = on.reshape(hh // cell, cell, ww // cell, cell).sum((1, 3))
        cells = (n > 0) & (n >= cover * real.reshape(hh // cell, cell, ww // cell, cell).sum((1, 3)))
        spray = np.repeat(np.repeat(cells, cell, 0), cell, 1)[:h, :w]
        hit, weed = hit + (spray & mask).sum(), weed + mask.sum()
        sprayed, total = sprayed + spray.sum(), total + h * w
    return float(hit / max(weed, 1)), float(sprayed / total)


def pick_threshold(pairs, target: float, cell: int, cover: float = 0.0) -> float:
    """The highest threshold whose weed hit on these (tuning) pairs reaches target; the floor if none does."""
    for t in np.linspace(0.95, 0.02, 94):
        if coverage(pairs, t, cell, cover)[0] >= target:
            return float(t)
    return 0.02
