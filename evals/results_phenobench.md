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

## Rerun: 1% cover rule, plus 50 labelled tiles from the test date

Same split, scored like the CoFly gate: a cell is sprayed when >= 1% of its pixels are predicted weed (edge cells
partial). For each date, 50 of its own tiles are held back: 25 join training (repeated to about a quarter of the
steps) and 25 set the threshold. Both heads are scored on the same remaining tiles (962, 516 and 551).

| test date | trained on other dates: 0.1 m hit / sprayed | + 50 local tiles: 0.1 m | crop sprayed (local) | spray all green, 0.1 m |
|---|---|---|---|---|
| 05-15 (seedlings) | 60.0% / 2.9% FAIL | **97.9% / 18.2% PASS** | 9.4% | 82.7% / 18.5% |
| 05-26 | 96.6% / 20.9% PASS | **97.7% / 18.9% PASS** | 4.5% | 92.0% / 36.6% |
| 06-05 | 98.1% / 35.4% PASS | **95.5% / 15.1% PASS** | 1.1% | 98.4% / 59.3% |

With local tiles, 0.25 m: 97.3/45.3, 96.3/43.0, 94.8/32.6. 0.5 m: 96.1/65.3, 93.9/63.5, 92.4/50.7. Under the 1%
rule a coarser cell needs more predicted pixels, so hit falls as cells grow.
SAM 3 zero-shot "weed" (100 random tiles): 73.1% / 21.9% at 0.1 m, FAIL.

Labelling 50 tiles (about 50 m² at 1 mm/px) from the field being sprayed turns the seedling date from a fail into a
pass. The 25 threshold tiles are few, so expect the hit rate to move a few points from field to field.
