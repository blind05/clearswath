"""Open-weight SAM 3 (facebook/sam3, gated) on a Modal GPU, for the weed gate before Meta credits land.

Setup (once): `uvx modal setup`; request access to facebook/sam3 on Hugging Face; then
`uvx modal secret create huggingface HF_TOKEN=<your token>`. Not part of the app or its Docker image.
"""

import io
import os

import modal

app = modal.App("clearswath-sam3-eval")
image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "torch", "transformers==5.21.0", "accelerate", "pillow", "numpy")
weights = modal.Volume.from_name("clearswath-hf-cache", create_if_missing=True)
GPU = os.getenv("SAM3_GPU", "L4")  # "none" runs on CPU (slower; GPU needs a payment method on Modal)
DEVICE = "cpu" if GPU == "none" else "cuda"


GATED = ("facebook/sam3", "facebook/dinov3-vits16-pretrain-lvd1689m")


@app.function(image=image, secrets=[modal.Secret.from_name("huggingface")], timeout=120)
def check_access() -> dict:
    """Which gated repos the Hugging Face token can read. CPU only: runs before any GPU is started."""
    from huggingface_hub import auth_check
    from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

    out = {}
    for repo in GATED:
        try:
            auth_check(repo)
            out[repo] = "ok"
        except (GatedRepoError, RepositoryNotFoundError) as e:
            out[repo] = f"no access ({type(e).__name__})"
    return out


@app.cls(image=image, gpu=None if GPU == "none" else GPU, cpu=8.0, memory=16384, timeout=3600,
         volumes={"/root/.cache/huggingface": weights}, secrets=[modal.Secret.from_name("huggingface")],
         retries=0)
class Sam3:
    @modal.enter()
    def load(self):
        import torch
        from transformers import Sam3Model, Sam3Processor

        self.torch = torch
        self.model = Sam3Model.from_pretrained("facebook/sam3").to(DEVICE)
        self.processor = Sam3Processor.from_pretrained("facebook/sam3")

    @modal.method()
    def segment(self, png: bytes, prompt: str) -> tuple[bytes, int, int]:
        """Union of all instance masks for the text prompt, packed to bits."""
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGB")
        inputs = self.processor(images=img, text=prompt, return_tensors="pt").to(DEVICE)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        res = self.processor.post_process_instance_segmentation(
            outputs, threshold=0.5, mask_threshold=0.5, target_sizes=inputs.get("original_sizes").tolist())[0]
        h, w = img.height, img.width
        union = np.zeros((h, w), dtype=bool)
        for m in res["masks"]:
            union |= m.cpu().numpy().astype(bool)
        return np.packbits(union).tobytes(), h, w


def segment_batch(jobs: list[tuple[bytes, str]]) -> list[tuple[bytes, int, int]]:
    """Runs every (png, prompt) on the GPU, after a CPU check that the weights are reachable."""
    with app.run():
        access = check_access.remote()
        if access["facebook/sam3"] != "ok":
            raise SystemExit(f"Hugging Face token can't read facebook/sam3: {access['facebook/sam3']}. "
                             "Request access at https://huggingface.co/facebook/sam3, then rerun.")
        sam = Sam3()
        return list(sam.segment.starmap(jobs))


if __name__ == "__main__":
    with app.run():
        print(check_access.remote())
