# Gate 3: SAM weed test (subtract, CoFly-WeedDB, 20 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 32 px: weed hit / sprayed | 96 px: weed hit / sprayed | verdict |
|---|---|---|---|---|
| green minus SAM(crop row + plant), dilate 12 | 0.020 | 28.0% / 6.0% | 36.1% / 9.6% | FAIL |
