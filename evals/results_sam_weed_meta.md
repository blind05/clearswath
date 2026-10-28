# Gate 3: SAM weed test (meta, CoFly-WeedDB, 20 images, seed 7)

Cell sprayed when predicted cover >= 1%. PASS: >= 95% of weed hit while spraying <= 50%, at the finest cell.

| prompt | mean IoU | 32 px: weed hit / sprayed | 96 px: weed hit / sprayed | verdict |
|---|---|---|---|---|
| weed | 0.000 | 0.0% / 0.0% | 0.0% / 0.0% | FAIL |
| plant | 0.009 | 8.1% / 11.9% | 22.2% / 18.2% | FAIL |
| green plant | 0.007 | 14.6% / 15.8% | 41.6% / 24.9% | FAIL |

## Probe: prompt and zoom sweep (2 weediest images, 185 and 199)

Weed px hit at full frame / at 640x360 quarter tiles. Plant-like prompts outline the cotton rows, not the weeds.

| prompt | image 185 (37% weed) | image 199 (25% weed) |
|---|---|---|
| weed | 0.0% / 9.0% | 0.0% / 1.0% |
| plant | 0.0% / 22.6% (covers 44%) | 2.7% / 2.7% (covers 36%) |
| leaf | 0.0% / 0.2% | 0.0% / 1.1% |
| vegetation | 0.0% / 5.7% (covers 37%) | 2.5% / 2.3% (covers 35%) |
| seedling | 0.0% / 0.0% | 0.0% / 0.9% |
| crop row | 6.5% / 2.1% | 1.8% / 0.0% |
| grass | 27.4% / 30.5% | 0.0% / 0.2% |

Control: the same SAM call that found 90 buildings on a NAIP tile on Oct 26 found 89 on Oct 27, so the
request and parsing work; the empty answers are SAM 3.1 finding no instances. CoFly's masks are hand-drawn
patch polygons around sprouts, which understates any model's IoU; the cell-level hit rate is the fair measure.
