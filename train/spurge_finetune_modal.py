"""Leafy spurge per plot, fine-tuning the last DINOv2-B blocks instead of a frozen probe. Same test as the sweep.

uv run --with modal python train/spurge_finetune_modal.py
Each plot's centre 448 px (5.7 m) goes through DINOv2-B; the last two blocks and a linear head on the centre
2 x 2 patch tokens (0.36 m) are trained, with flips and quarter turns. Scored leave-one-cluster-out (9 folds) and on
the official test split, to compare with evals/results_spurge.md (frozen probe: 85.0% official, LOCO AUC 0.88).
map_block maps a block of the orthomosaic with the same model (scripts/build_demo_mt.py --finetune).
"""

import modal

app = modal.App("clearswath-spurge-finetune")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch", "transformers==5.21.0", "pillow", "numpy", "scikit-learn", "huggingface_hub",
                      "rasterio")
         .add_local_python_source("spurge_modal", "weedhead"))
BACKBONE = "facebook/dinov2-base"
CROP = 448  # px at 1.27 cm; a multiple of the 14 px patch
GRID = CROP // 14
EPOCHS, UNFROZEN, SEED = 8, 2, 0


def _plots_tensors():
    """(plots, x uint8 N x 3 x CROP x CROP on the CPU, y float)."""
    import numpy as np
    import torch

    from spurge_modal import _load_plots

    plots, imgs = _load_plots()
    c0 = (imgs[0].shape[0] - CROP) // 2
    x = torch.stack([torch.from_numpy(np.ascontiguousarray(i[c0:c0 + CROP, c0:c0 + CROP])) for i in imgs])
    return plots, x.permute(0, 3, 1, 2).contiguous(), torch.tensor([p["y"] for p in plots], dtype=torch.float32)


def _net(unfrozen: int = UNFROZEN):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoModel

    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.dino = AutoModel.from_pretrained(BACKBONE)
            for p in self.dino.parameters():
                p.requires_grad = False
            for block in self.dino.encoder.layer[-unfrozen:]:
                for p in block.parameters():
                    p.requires_grad = True
            for p in self.dino.layernorm.parameters():
                p.requires_grad = True
            self.head = nn.Linear(self.dino.config.hidden_size, 1)

        def tokens(self, x):
            out = self.dino(pixel_values=(x.float() / 255 - mean) / std).last_hidden_state[:, 1:]
            return out.reshape(x.shape[0], GRID, GRID, -1)

        def forward(self, x):
            c = GRID // 2
            return self.head(self.tokens(x)[:, c - 1:c + 1, c - 1:c + 1].mean((1, 2)))[:, 0]  # the plot's 0.36 m

        def score_map(self, x):
            """The same head on every 2 x 2 token window: a logit map of (GRID - 1) x (GRID - 1)."""
            t = self.tokens(x).permute(0, 3, 1, 2)
            pooled = F.avg_pool2d(t, 2, stride=1)
            return self.head(pooled.permute(0, 2, 3, 1))[0, ..., 0]

    return Net().cuda()


def _fit(x_all, y_all, train_idx, epochs: int = EPOCHS, seed: int = SEED):
    import numpy as np
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    net = _net()
    opt = torch.optim.AdamW([{"params": net.head.parameters(), "lr": 1e-3},
                             {"params": [p for p in net.dino.parameters() if p.requires_grad], "lr": 2e-5}],
                            weight_decay=0.05)
    loss_fn = nn.BCEWithLogitsLoss()
    for _ in range(epochs):
        net.train()
        order = np.random.default_rng(seed).permutation(train_idx)
        for k in range(0, len(order), 16):
            b = order[k:k + 16]
            x = torch.rot90(x_all[b].cuda(), int(torch.randint(4, (1,))), (2, 3))
            x = x.flip(3) if torch.rand(1) < 0.5 else x
            loss = loss_fn(net(x), y_all[b].cuda())
            opt.zero_grad()
            loss.backward()
            opt.step()
    return net.eval()


def _predict(net, x_all, idx):
    import numpy as np
    import torch

    with torch.no_grad():
        return np.concatenate([torch.sigmoid(net(x_all[idx[k:k + 32]].cuda())).cpu().numpy()
                               for k in range(0, len(idx), 32)])


@app.function(image=image, gpu=["L4", "A10G"], timeout=4 * 3600, volumes={"/data": volume}, memory=32768,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def evaluate(epochs: int = EPOCHS) -> dict:
    import os

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    from sklearn.metrics import roc_auc_score

    plots, x_all, y_all = _plots_tensors()
    clusters = np.array([p["cluster"] for p in plots])
    official = np.array([p["split"] == "test" for p in plots])
    y = y_all.numpy()
    folds = []
    for c in sorted(set(clusters.tolist())):
        test, train = np.where(clusters == c)[0], np.where(clusters != c)[0]
        p = _predict(_fit(x_all, y_all, train, epochs), x_all, test)
        yt = y[test]
        # accuracy at 0.5 and AUC, the frozen-probe table's columns
        folds.append({"cluster": c, "acc@0.5": float(((p >= 0.5) == yt).mean()), "auc": float(roc_auc_score(yt, p))})
    off_test = np.where(official)[0]
    p_off = _predict(_fit(x_all, y_all, np.where(~official)[0], epochs), x_all, off_test)
    return {"backbone": BACKBONE, "unfrozen_blocks": UNFROZEN, "epochs": epochs,
            "official_test_acc": float(((p_off >= 0.5) == y[official]).mean()),
            "official_test_auc": float(roc_auc_score(y[official], p_off)),
            "loco_acc": float(np.mean([f["acc@0.5"] for f in folds])),
            "loco_auc": float(np.mean([f["auc"] for f in folds])), "folds": folds}


@app.function(image=image, gpu=["L4", "A10G"], timeout=4 * 3600, volumes={"/data": volume}, memory=32768,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def map_block(rows_: list[int], cols: list[int], holdout: list[int], target_recall: float = 0.95,
              out_m: float = 0.1016) -> dict:
    """map_block in spurge_modal.py, with the fine-tuned model: the same outputs, so the demo build can use either.

    The final model trains on every cluster not in holdout. Catch-rate thresholds come from leave-one-cluster-out
    predictions within those clusters (one more fine-tune each); the holdout clusters' plots check the map.
    """
    import os

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    import torch

    from spurge_modal import GSD, _outputs, _scan_block

    plots, x_all, y_all = _plots_tensors()
    y = y_all.numpy()
    clusters = np.array([p["cluster"] for p in plots])
    fit = ~np.isin(clusters, holdout)
    inner = np.zeros(len(y))
    for c in sorted(set(clusters[fit].tolist())):
        test, train = np.where(clusters == c)[0], np.where(fit & (clusters != c))[0]
        inner[test] = _predict(_fit(x_all, y_all, train), x_all, test)
    fit_present = inner[fit & (y == 1)]
    threshold = float(np.quantile(fit_present, 1 - target_recall))
    net = _fit(x_all, y_all, np.where(fit)[0])
    hold = np.where(~fit)[0]
    p_hold, y_hold = _predict(net, x_all, hold), y[hold]

    def score(win):
        return net.score_map(torch.from_numpy(win).permute(2, 0, 1)[None].cuda())

    step = round(out_m / GSD)
    prob, ok, origin, rgb = _scan_block(rows_, cols, CROP, score, step)
    flagged, total = int(((prob >= threshold) & ok).sum()), int(ok.sum())
    return {"backbone": f"{BACKBONE} ({UNFROZEN} blocks fine-tuned)", "view": "full", "window_m": 0.36,
            "threshold": threshold, "holdout": holdout, "fit_n": int(fit.sum()), "holdout_n": int(len(hold)),
            "holdout_recall": float((p_hold[y_hold == 1] >= threshold).mean()),
            "holdout_absent_flagged": float((p_hold[y_hold == 0] >= threshold).mean()),
            "share_flagged": flagged / max(total, 1), "crs": "EPSG:32611", **_outputs(prob, ok, origin, rgb, step),
            "fit_present_probs": fit_present.tolist(), "holdout_probs": p_hold.tolist(), "holdout_y": y_hold.tolist()}


def _poll(call):
    """Detached calls are polled: the local link to Modal drops on long calls."""
    while True:
        try:
            return call.get(timeout=60)
        except TimeoutError:
            continue
        except (modal.exception.ConnectionError, OSError):
            continue


def run_map(**kw) -> dict:
    with app.run(detach=True):
        call = map_block.spawn(**kw)
        print(f"map_block call {call.object_id}", flush=True)
        return _poll(call)


if __name__ == "__main__":
    import json

    with app.run(detach=True):
        call = evaluate.spawn()
        print(f"evaluate call {call.object_id}", flush=True)
        print(json.dumps(_poll(call), indent=1))
