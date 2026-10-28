"""Leafy spurge per plot, fine-tuning the last DINOv2-B blocks instead of a frozen probe. Same test as the sweep.

uv run --with modal python train/spurge_finetune_modal.py
Each plot's centre 448 px (5.7 m) goes through DINOv2-B; the last two blocks and a linear head on the centre
2 x 2 patch tokens (0.36 m) are trained, with flips and quarter turns. Scored leave-one-cluster-out (9 folds) and on
the official test split, to compare with evals/results_spurge.md (frozen probe: 85.0% official, LOCO AUC 0.88).
"""

import modal

app = modal.App("clearswath-spurge-finetune")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch", "transformers==5.21.0", "pillow", "numpy", "scikit-learn", "huggingface_hub")
         .add_local_python_source("spurge_modal", "weedhead"))
BACKBONE = "facebook/dinov2-base"
CROP = 448  # px at 1.27 cm; a multiple of the 14 px patch


@app.function(image=image, gpu=["L4", "A10G"], timeout=4 * 3600, volumes={"/data": volume}, memory=32768,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def evaluate(epochs: int = 8, unfrozen: int = 2, seed: int = 0) -> dict:
    import os

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    import torch
    import torch.nn as nn
    from sklearn.metrics import roc_auc_score
    from transformers import AutoModel

    from spurge_modal import _load_plots

    plots, imgs = _load_plots()
    c0 = (imgs[0].shape[0] - CROP) // 2
    x_all = torch.stack([torch.from_numpy(np.ascontiguousarray(i[c0:c0 + CROP, c0:c0 + CROP])) for i in imgs])
    x_all = x_all.permute(0, 3, 1, 2).contiguous()  # N, 3, H, W uint8 on the CPU
    y_all = torch.tensor([p["y"] for p in plots], dtype=torch.float32)
    clusters = np.array([p["cluster"] for p in plots])
    official = np.array([p["split"] == "test" for p in plots])
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1)
    grid = CROP // 14

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

        def forward(self, x):
            tokens = self.dino(pixel_values=(x.float() / 255 - mean) / std).last_hidden_state[:, 1:]
            tokens = tokens.reshape(x.shape[0], grid, grid, -1)
            c = grid // 2
            return self.head(tokens[:, c - 1:c + 1, c - 1:c + 1].mean((1, 2)))[:, 0]  # the plot's 0.36 m

    def augment(x):
        x = torch.rot90(x, int(torch.randint(4, (1,))), (2, 3))
        return x.flip(3) if torch.rand(1) < 0.5 else x

    def fit_predict(train_idx, test_idx):
        torch.manual_seed(seed)
        net = Net().cuda()
        opt = torch.optim.AdamW([{"params": net.head.parameters(), "lr": 1e-3},
                                 {"params": [p for n, p in net.dino.named_parameters() if p.requires_grad],
                                  "lr": 2e-5}], weight_decay=0.05)
        loss_fn = nn.BCEWithLogitsLoss()
        for _ in range(epochs):
            net.train()
            order = np.random.default_rng(seed).permutation(train_idx)
            for k in range(0, len(order), 16):
                b = order[k:k + 16]
                loss = loss_fn(net(augment(x_all[b].cuda())), y_all[b].cuda())
                opt.zero_grad()
                loss.backward()
                opt.step()
        net.eval()
        with torch.no_grad():
            return np.concatenate([torch.sigmoid(net(x_all[test_idx[k:k + 32]].cuda())).cpu().numpy()
                                   for k in range(0, len(test_idx), 32)])

    y = y_all.numpy()
    folds = []
    for c in sorted(set(clusters.tolist())):
        test, train = np.where(clusters == c)[0], np.where(clusters != c)[0]
        p = fit_predict(train, test)
        yt = y[test]
        # accuracy at 0.5 and AUC, the frozen-probe table's columns; a recall-tuned threshold would need a
        # second fine-tune per fold
        folds.append({"cluster": c, "acc@0.5": float(((p >= 0.5) == yt).mean()), "auc": float(roc_auc_score(yt, p))})
    p_off = fit_predict(np.where(~official)[0], np.where(official)[0])
    return {"backbone": BACKBONE, "unfrozen_blocks": unfrozen, "epochs": epochs,
            "official_test_acc": float(((p_off >= 0.5) == y[official]).mean()),
            "official_test_auc": float(roc_auc_score(y[official], p_off)),
            "loco_acc": float(np.mean([f["acc@0.5"] for f in folds])),
            "loco_auc": float(np.mean([f["auc"] for f in folds])), "folds": folds}


if __name__ == "__main__":
    import json

    with app.run(detach=True):  # detached and polled: the local link to Modal drops on long calls
        call = evaluate.spawn()
        print(f"evaluate call {call.object_id}", flush=True)
        while True:
            try:
                print(json.dumps(call.get(timeout=60), indent=1))
                break
            except TimeoutError:
                continue
            except (modal.exception.ConnectionError, OSError):
                continue
