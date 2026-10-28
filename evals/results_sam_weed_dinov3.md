# Gate 3: SAM weed test (dinov3, CoFly-WeedDB, 20 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 32 px: weed hit / sprayed | 96 px: weed hit / sprayed | verdict |
|---|---|---|---|---|
| DINOv3 head (tuned to 97%, threshold 0.02) | 0.147 | 94.8% / 31.3% | 97.9% / 46.5% | BORDERLINE |
