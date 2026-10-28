# PhenoBench: DINOv3 weed head, leave-one-date-out

Sugar beet vs weed, 2,179 tiles at 1 mm/px from three flight dates (AgML's Hugging Face copy of PhenoBench,
CC BY-SA 4.0). Each date is tested by a head trained on the other two dates. 100 of the training tiles are
held back to set the threshold, aiming for 97% weed hit at 0.1 m. Twelve epochs, seed 0.
Run: `uv run --with modal python train/phenobench_modal.py evaluate` (L4).

A cell is sprayed when any pixel in it is at or above the threshold. This is stricter than the CoFly gate,
which sprays a cell at >= 1% predicted cover. PASS: >= 95% of weed pixels hit while spraying <= 50% of the area.

## Trained head (weed hit / area sprayed)

| test date | tiles | 0.1 m | 0.25 m | 0.5 m | crop pixels sprayed | weed IoU |
|---|---|---|---|---|---|---|
| 05-15 (earliest) | 1012 | 57.4% / 2.6% | 64.4% / 11.5% | 75.2% / 34.6% | 0.5% | 0.14 |
| 05-26 | 566 | **96.5% / 21.0%** | 98.5% / 62.7% | 99.8% / 94.2% | 3.9% | 0.19 |
| 06-05 | 601 | **96.2% / 28.0%** | 98.3% / 69.7% | 99.2% / 94.8% | 2.5% | 0.33 |

The tuning tiles reached 97% on every fold (97.1%, 97.1%, 97.0%). The 05-26 and 06-05 folds pass at 0.1 m.
The 05-15 fold fails: its plants are seedlings, a growth stage the head never saw in training. The threshold
tuned on later dates misses 43% of the weed pixels. The head needs examples from the growth stage it sprays.

## Baselines

| method | 0.1 m | 0.25 m | 0.5 m |
|---|---|---|---|
| Spray everything green (ExG > 0.1, any pixel), mean of folds | ~100% / 85-99% | 100% / 98-100% | 100% / ~100% |
| SAM 3 zero-shot "weed", 100 random tiles (open weights) | 73.9% / 24.5% | 75.9% / 50.6% | 83.5% / 76.7% |

Spraying everything green turns into broadcast at 1 mm/px: almost every 0.1 m cell has a few green pixels.
SAM 3 does much better here than on CoFly (0% there), but it misses a quarter of the weeds.

Caveats: three dates from one field and one season. A tile is only about 1 m across, so a 0.5 m cell covers
about a quarter of a tile, and the coarser columns are close to spraying whole tiles.
