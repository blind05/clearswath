# Gate 3: SAM weed test (dinov3, CoFly-WeedDB, 20 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 32 px: weed hit / sprayed | 96 px: weed hit / sprayed | verdict |
|---|---|---|---|---|
| DINOv3 head (threshold 0.11) | 0.223 | 91.4% / 19.6% | 93.9% / 31.1% | FAIL |
