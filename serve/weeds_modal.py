"""Live photo mode: a weed overlay for one uploaded photo, from the DINOv3 head on a Modal GPU.

PYTHONPATH=train uv run --with modal modal deploy serve/weeds_modal.py   (weedhead lives in train/)
The deploy prints the endpoint URL: set it as PHOTO_URL for the app. Requests must send X-Photo-Key matching
PHOTO_KEY in the Modal secret "clearswath-photo" (the app reads the same key from its own environment).
The head comes from train/deploy_head_modal.py (CoFly-WeedDB + PhenoBench).
"""

import modal
from fastapi import Request

app = modal.App("clearswath-photo")
volume = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch", "transformers==5.21.0", "pillow", "numpy", "fastapi[standard]")
         .add_local_python_source("weedhead"))
HEAD = "/data/models/weed_head_v1.pt"
MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 50_000_000  # a decompression bomb is refused before it is decoded
MAX_SIDE = 1536  # photos are shrunk to this: DINOv3 cost grows with the square of the side


@app.cls(image=image, gpu=["L4", "A10G", "T4"], volumes={"/data": volume}, timeout=120, scaledown_window=300,
         max_containers=2, secrets=[modal.Secret.from_name("huggingface"), modal.Secret.from_name("clearswath-photo")])
class Weeds:
    @modal.enter()
    def load(self):
        import os

        os.environ["HF_HOME"] = "/data"
        import torch

        import weedhead as wh

        self.features = wh.load_dino()
        saved = torch.load(HEAD, map_location="cuda", weights_only=True)  # tensors and plain values only
        self.head = wh.make_head(saved["in_channels"]).to("cuda").eval()
        self.head.load_state_dict(saved["state_dict"])
        self.threshold, self.trained_on = saved["threshold"], saved["trained_on"]

    @modal.fastapi_endpoint(method="POST")
    async def analyze(self, request: Request):
        import base64
        import hmac
        import io
        import os

        import numpy as np
        from fastapi import HTTPException
        from PIL import Image, ImageOps

        import weedhead as wh

        given = request.headers.get("x-photo-key", "").encode()
        if not hmac.compare_digest(given, os.environ["PHOTO_KEY"].encode()):
            raise HTTPException(401, "bad key")
        body = await request.body()
        if len(body) > MAX_BYTES:
            raise HTTPException(413, "photo too large")
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        try:
            photo = Image.open(io.BytesIO(body))
            photo.load()
        except Exception as e:  # not an image, truncated, or over MAX_PIXELS
            raise HTTPException(422, "not a readable photo") from e
        photo = ImageOps.exif_transpose(photo).convert("RGB")
        photo.thumbnail((MAX_SIDE, MAX_SIDE))
        rgb = np.asarray(photo)
        prob = wh.probability(self.head, self.features(rgb), rgb.shape[:2])
        weed = prob >= self.threshold
        overlay = np.zeros((*weed.shape, 4), np.uint8)
        overlay[weed] = (230, 81, 0, 150)
        buf = io.BytesIO()
        Image.fromarray(overlay, "RGBA").save(buf, "PNG", optimize=True)
        return {"width": rgb.shape[1], "height": rgb.shape[0], "share_flagged": float(weed.mean()),
                "threshold": self.threshold, "trained_on": self.trained_on,
                "overlay_png": base64.b64encode(buf.getvalue()).decode()}
