# Gate 3: SAM weed test (dinov3, CoFly-WeedDB, 201 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 0.25 m: weed hit / sprayed | 0.5 m: weed hit / sprayed | verdict |
|---|---|---|---|---|
| DINOv3 head (tuned to 97%, 5-fold) | 0.181 | 95.9% / 37.9% | 97.4% / 47.5% | PASS |
