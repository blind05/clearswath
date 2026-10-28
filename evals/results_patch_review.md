# Muse Spark Open reviewing photo-mode weed patches

The photo mode's weed head (DINOv3 features, trained on CoFly-WeedDB and PhenoBench) draws an overlay; Spark Open
(Fireworks) is shown a crop around each of the 10 largest patches and answers weed, crop or soil.

## As a filter (rejected, 2026-10-28)

First design: a patch Spark called crop or soil with confidence >= 0.8 was removed from the overlay. Scored on 15
CoFly-WeedDB images (seed 3; image 16 lost to a dropped connection) against CoFly's weed masks:

| | weed pixels covered | image flagged |
|---|---|---|
| weed head alone | 93.9% | 16.7% |
| head, then Spark's filter | 27.3% | 4.9% |

On 9 of the 15 images the filter removed every real weed: at this scale small weeds among cracked soil read as
"bare soil" to the model. The review is now advisory only (`app/patches.py`): Spark's answer is shown beside each
patch and never changes the overlay.

## As an advisory (dropped, 2026-10-28)

Second design: Spark's label shown beside each patch, the overlay untouched. Scored on 20 CoFly-WeedDB images
(seed 3, 124 patches; a patch is a real weed patch when >= 20% of its pixels are weed in CoFly's mask):

| | Spark said weed | Spark said crop or soil |
|---|---|---|
| real weed patch (32) | 8 (25%) | 24 |
| not a weed patch (92) | 35 (38%) | 57 |

Agreement 52%, no better than chance, and it calls clean patches weeds more often than real ones. A second opinion
that wrong would mislead, so the review is not in the app. The code and this test stay in
`evals/patch_review_test.py`.
