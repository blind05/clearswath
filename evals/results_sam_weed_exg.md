# Gate 3: SAM weed test (exg, CoFly-WeedDB, 20 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 32 px: weed hit / sprayed | 96 px: weed hit / sprayed | verdict |
|---|---|---|---|---|
| (excess green) | 0.012 | 60.2% / 73.7% | 96.4% / 97.1% | FAIL |
