"""Leafy spurge present/absent per 0.5 m plot from frozen DINOv3 features, on a Modal GPU.

uv run --with modal python train/spurge_modal.py
Data: mpg-ranch/leafy_spurge on Hugging Face (CC BY 4.0, doi:10.57967/hf/2508), western Montana rangeland,
1.27 cm drone orthomosaic, 1000 GNSS survey plots in 9 spatial clusters. Each 'context' image is 1024 px centred on
its plot. Test: leave one cluster out (the official test split is one whole cluster), so neighbours never leak.
"""

import modal

app = modal.App("clearswath-spurge")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch", "transformers==5.21.0", "pillow", "numpy", "scikit-learn", "huggingface_hub",
                      "rasterio", "shapely")
         .add_local_python_source("weedhead"))
ROOT = "/data/spurge"
GSD = 0.0127
BACKBONES = ["facebook/dinov3-vits16-pretrain-lvd1689m", "facebook/dinov2-base", "facebook/dinov2-large"]
# view name -> (centre crop in px, upscale); windows (m) are averaged around the plot at the image centre
VIEWS = {"full": (1024, 1, (0.4, 0.8, 1.6, 3.2, 13.0)), "zoom": (256, 4, (0.4, 0.8, 1.6, 3.25))}


@app.function(image=image, gpu="L4", timeout=3600, volumes={"/data": volume}, memory=16384,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def evaluate(target_recall=0.95) -> dict:
    """Every backbone x view x window, scored leave-one-cluster-out with a logistic probe."""
    import os

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    import torch
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    import weedhead as wh

    rows, imgs = _load_plots()
    y = np.array([r["y"] for r in rows])
    clusters = np.array([r["cluster"] for r in rows])
    official = np.array([r["split"] == "test" for r in rows])

    feats = {}
    for name in BACKBONES:
        features = wh.load_dino(name)
        for view, (crop, up, windows) in VIEWS.items():
            vecs = {w: [] for w in windows}
            for img in imgs:
                c0 = (img.shape[0] - crop) // 2
                f = features(_upscale(img[c0:c0 + crop, c0:c0 + crop], up)).float()
                gh, gw = f.shape[1:]
                for w in windows:
                    n = max(1, round(w / (features.patch * GSD / up)))
                    y0, x0 = max(0, (gh - n) // 2), max(0, (gw - n) // 2)
                    vecs[w].append(f[:, y0:y0 + n, x0:x0 + n].mean((1, 2)).cpu().numpy())
            for w in windows:
                feats[(name.split("/")[1], view, w)] = np.stack(vecs[w])
        del features
        torch.cuda.empty_cache()

    def model():
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=5000))

    out = {"n": len(rows), "present": int(y.sum()), "results": []}
    for (name, view, w), x in feats.items():
        official_acc = float((model().fit(x[~official], y[~official]).predict(x[official]) == y[official]).mean())
        accs, aucs, hit, flagged = [], [], 0, 0
        for c in sorted(set(clusters.tolist())):
            test, train = clusters == c, clusters != c
            # threshold for target recall, from out-of-fold probabilities on the training clusters only
            inner = cross_val_predict(model(), x[train], y[train], cv=_group_folds(clusters[train]),
                                      method="predict_proba")[:, 1]
            t = np.quantile(inner[y[train] == 1], 1 - target_recall)
            p = model().fit(x[train], y[train]).predict_proba(x[test])[:, 1]
            yt = y[test]
            accs.append(((p >= 0.5) == yt).mean())
            aucs.append(roc_auc_score(yt, p))
            hit, flagged = hit + (p[yt == 1] >= t).sum(), flagged + (p[yt == 0] >= t).sum()
        out["results"].append({"backbone": name, "view": view, "window_m": w, "official_test_acc": official_acc,
                               "loco_acc": float(np.mean(accs)), "loco_auc": float(np.mean(aucs)),
                               "recall": float(hit / y.sum()), "absent_flagged": float(flagged / (y == 0).sum())})
    out["results"].sort(key=lambda r: -r["loco_auc"])
    return out


def _load_plots():
    """(rows, images) for the 900 survey plots: split, cluster, y (1 = spurge present), easting, northing."""
    import csv

    import numpy as np
    from huggingface_hub import snapshot_download
    from PIL import Image

    snapshot_download("mpg-ranch/leafy_spurge", repo_type="dataset", allow_patterns=["data/context/*"],
                      local_dir=ROOT)
    rows, imgs = [], []
    for split in ("train", "test"):
        for r in csv.DictReader(open(f"{ROOT}/data/context/{split}/metadata.csv")):
            imgs.append(np.asarray(Image.open(f"{ROOT}/data/context/{split}/{r['file_name']}").convert("RGB")))
            rows.append({"split": split, "cluster": int(r["cluster"]), "y": int(r["label"] == "present"),
                         "e": float(r["easting"]), "n": float(r["northing"])})
    return rows, imgs


def _upscale(img, up: int):
    import numpy as np
    import torch
    import torch.nn.functional as F

    if up == 1:
        return img
    t = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1)[None].float()
    return F.interpolate(t, scale_factor=up, mode="bicubic").clamp(0, 255)[0].permute(1, 2, 0).byte().numpy()


@app.function(image=image, gpu="L4", timeout=3 * 3600, volumes={"/data": volume}, memory=32768,
              secrets=[modal.Secret.from_name("huggingface")], retries=0)
def map_block(backbone: str, view: str, window_m: float, rows_: list[int], cols: list[int],
              holdout: list[int], target_recall: float = 0.95, out_m: float = 0.1016) -> dict:
    """Spurge map over orthomosaic tiles (rows_ x cols), from a probe trained on every cluster not in holdout.

    The holdout clusters' plots are the honest check of the map. Returns a spurge probability GeoTIFF
    (EPSG:32611, 0-254, 255 = no image), what's needed to pick a catch rate later, the check at
    target_recall, and a JPEG of the block. ponytail: the whole block sits in memory (1.8 GB for 36 tiles); map
    it in strips if blocks get much bigger.
    """
    import io
    import os

    os.environ["HF_HOME"] = "/data"
    import numpy as np
    import rasterio
    import torch
    import torch.nn.functional as F
    from huggingface_hub import hf_hub_download
    from PIL import Image
    from rasterio.transform import from_origin
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    import weedhead as wh

    crop, up, _ = VIEWS[view]
    features = wh.load_dino(backbone)
    n = max(1, round(window_m / (features.patch * GSD / up)))
    plots, imgs = _load_plots()
    x = []
    for img in imgs:
        c0 = (img.shape[0] - crop) // 2
        f = features(_upscale(img[c0:c0 + crop, c0:c0 + crop], up)).float()
        gh, gw = f.shape[1:]
        y0, x0 = max(0, (gh - n) // 2), max(0, (gw - n) // 2)
        x.append(f[:, y0:y0 + n, x0:x0 + n].mean((1, 2)).cpu().numpy())
    x = np.stack(x)
    y = np.array([p["y"] for p in plots])
    clusters = np.array([p["cluster"] for p in plots])
    fit = ~np.isin(clusters, holdout)

    def model():
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=5000))

    inner = cross_val_predict(model(), x[fit], y[fit], cv=_group_folds(clusters[fit]), method="predict_proba")[:, 1]
    threshold = float(np.quantile(inner[y[fit] == 1], 1 - target_recall))
    probe = model().fit(x[fit], y[fit])
    p_hold = probe.predict_proba(x[~fit])[:, 1]
    y_hold = y[~fit]
    sc, lr = probe[0], probe[1]
    mean, scale = (torch.tensor(v, device="cuda", dtype=torch.float32) for v in (sc.mean_, sc.scale_))
    coef = torch.tensor(lr.coef_[0], device="cuda", dtype=torch.float32)
    bias = float(lr.intercept_[0])

    step = round(out_m / GSD)  # output pixel = step x step orthomosaic pixels
    tile = 4096
    h, w = tile * len(rows_), tile * len(cols)
    rgb, valid, origin = np.zeros((h, w, 3), np.uint8), np.zeros((h, w), bool), None
    for r in rows_:
        for c in cols:
            path = hf_hub_download("mpg-ranch/leafy_spurge", f"data/orthomosaic/orthomosaic_{r:02d}_{c:02d}.tif",
                                   repo_type="dataset", local_dir=ROOT)
            with rasterio.open(path) as src:
                rgba, origin = src.read(), origin or (src.bounds.left, src.bounds.top)
            oy, ox = (r - rows_[0]) * tile, (c - cols[0]) * tile  # not y/x: those hold the plots' labels/features
            rgb[oy:oy + tile, ox:ox + tile] = rgba[:3].transpose(1, 2, 0)
            valid[oy:oy + tile, ox:ox + tile] = rgba[3] > 0

    # Overlapping crops over the whole block, each keeping only its centre: near a crop's edge the model sees
    # less context and under-calls spurge, which left unsprayed stripes at every crop and tile seam.
    margin = crop // 8
    keep = crop - 2 * margin
    logits, full = [], []  # raw probe scores per window, before the position correction
    for y0 in range(-margin, h - margin, keep):
        for x0 in range(-margin, w - margin, keep):
            win = np.zeros((crop, crop, 3), np.uint8)
            ys, xs, ye, xe = max(y0, 0), max(x0, 0), min(y0 + crop, h), min(x0 + crop, w)
            win[ys - y0:ye - y0, xs - x0:xe - x0] = rgb[ys:ye, xs:xe]
            f = features(_upscale(win, up)).float()
            pooled = F.avg_pool2d(f[None], n, stride=1, padding=n // 2, count_include_pad=False)[0]
            logit = torch.einsum("chw,c->hw", (pooled - mean[:, None, None]) / scale[:, None, None], coef) + bias
            logits.append((y0, x0, logit.cpu()))
            full.append(ye - ys == crop and xe - xs == crop and valid[ys:ye, xs:xe].all())
    # The features carry their position in the window, and every training plot sat at the centre, so scores
    # drift with position (rows ramped ~30 -> 100 of 254 across each window). The ground is statistically the
    # same everywhere in the block, so the mean score at each position over the fully imaged windows, minus the
    # mean at the centre, is that drift; subtract it.
    avg = torch.stack([lg for (_, _, lg), ok in zip(logits, full, strict=True) if ok]).mean(0)
    c = avg.shape[0] // 2
    drift = avg - avg[c - 1:c + 2, c - 1:c + 2].mean()
    prob = np.zeros((h // step, w // step), np.float32)
    for y0, x0, lg in logits:
        p = torch.sigmoid(lg - drift)[None, None]
        p = F.interpolate(p, size=(crop // step, crop // step), mode="bilinear")[0, 0].numpy()
        cy, cx = y0 + margin, x0 + margin
        ky, kx = min(keep, h - cy), min(keep, w - cx)
        prob[cy // step:(cy + ky) // step, cx // step:(cx + kx) // step] = \
            p[margin // step:(margin + ky) // step, margin // step:(margin + kx) // step]
    ok = valid[::step, ::step]
    flagged, total = int(((prob >= threshold) & ok).sum()), int(ok.sum())
    ph, pw = prob.shape[0] // 2, prob.shape[1] // 2  # probabilities are kept at 2 x out_m
    half = prob[:ph * 2, :pw * 2].reshape(ph, 2, pw, 2).mean((1, 3))
    half_ok = ok[:ph * 2, :pw * 2].reshape(ph, 2, pw, 2).all((1, 3))
    probs = np.where(half_ok, np.round(half * 254), 255).astype(np.uint8)  # 0-254 = probability, 255 = no image
    buf = io.BytesIO()
    Image.fromarray(rgb[::16, ::16]).save(buf, "JPEG", quality=82)
    from rasterio.io import MemoryFile

    with MemoryFile() as mem:
        with mem.open(driver="GTiff", width=probs.shape[1], height=probs.shape[0], count=1, dtype="uint8",
                      crs="EPSG:32611", transform=from_origin(*origin, 2 * step * GSD, 2 * step * GSD), nodata=255,
                      compress="deflate") as dst:
            dst.write(probs, 1)
        prob_tif = mem.read()
    return {"backbone": backbone, "view": view, "window_m": window_m, "threshold": threshold,
            "holdout": holdout, "fit_n": int(fit.sum()), "holdout_n": int((~fit).sum()),
            "holdout_recall": float((p_hold[y_hold == 1] >= threshold).mean()),
            "holdout_absent_flagged": float((p_hold[y_hold == 0] >= threshold).mean()),
            "share_flagged": flagged / max(total, 1), "crs": "EPSG:32611", "jpeg": buf.getvalue(),
            "jpeg_m_per_px": 16 * GSD, "prob_tif": prob_tif,
            # for choosing a catch rate later: thresholds from the training clusters, results on the held-out ones
            "fit_present_probs": inner[y[fit] == 1].tolist(), "holdout_probs": p_hold.tolist(),
            "holdout_y": y_hold.tolist()}


def _group_folds(groups):
    """Leave-one-group-out splits as index pairs, for cross_val_predict."""
    import numpy as np

    return [(np.where(groups != g)[0], np.where(groups == g)[0]) for g in sorted(set(groups.tolist()))]


def run_map(**kw) -> dict:
    with app.run():
        return map_block.remote(**kw)


if __name__ == "__main__":
    import json

    with app.run():
        print(json.dumps(evaluate.remote(), indent=1))
