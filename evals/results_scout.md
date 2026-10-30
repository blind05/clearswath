# Hazard scout eval (2026-10-29)

20 NAIP tiles (about 0.6 km across each): the 2 demo fields and 18 squares at fixed random offsets around them, eastern South Dakota and western Montana. Made by `evals/scout_eval.py`.

Truth, which no Meta model made: trees and shrubs (the app's tree lines and woods) and water from ESA WorldCover 2021 v200 (10 m cells, CC BY 4.0); buildings from Microsoft Global ML Building Footprints (ODbL), 40 m2 and up. A building counts as found if an outline touches it (3 m tolerance).

| Method | Trees and shrubs, mean per tile: recall / precision | Trees and shrubs, all cells pooled: recall / precision | Water: precision / recall | Buildings found | Building outlines on a building |
|---|---|---|---|---|---|
| SAM 3.1, text prompts | 17% / 68% | 8% / 74% | 95% / 42% | 27 of 35 (77%) | 30 of 39 |
| The app: Wonder boxes for trees, SAM text for the rest | 62% / 57% | 64% / 65% | 95% / 42% | 27 of 35 (77%) | 30 of 39 |
| The app plus Wonder's review of its tree outlines | 62% / 57% | 64% / 65% | 95% / 42% | 27 of 35 (77%) | 30 of 39 |

Mean per tile is over the 16 tiles with at least 20 tree or shrub cells; it is the fairer number, because one wooded Montana tile holds a third of all tree cells and dominates the pooled figure. One Wonder run per tile: on single tiles Wonder varies a lot between runs (in two runs the same day, field_00 went from 0% to 91% recall and field_16 from 100% to 49%).

Per tile (trees and shrubs: true positive / false positive / missed 10 m cells, after review):

| Tile | NAIP date | Tree and shrub cells | Water cells | Buildings | After review |
|---|---|---|---|---|---|
| field | 2022-08-03 | 742 | 0 | 0 | 576 / 318 / 166 |
| block | 2023-10-19 | 415 | 0 | 0 | 145 / 210 / 270 |
| field_00 | 2022-08-03 | 23 | 0 | 0 | 21 / 38 / 2 |
| field_01 | 2022-08-01 | 81 | 0 | 3 | 37 / 44 / 44 |
| field_02 | 2022-08-03 | 65 | 0 | 1 | 33 / 113 / 32 |
| field_03 | 2022-08-03 | 381 | 0 | 5 | 227 / 112 / 154 |
| field_04 | 2022-08-01 | 73 | 0 | 2 | 36 / 63 / 37 |
| field_05 | 2022-08-03 | 0 | 44 | 0 | 0 / 125 / 0 |
| field_06 | 2022-08-03 | 344 | 0 | 3 | 229 / 39 / 115 |
| field_07 | 2022-08-03 | 240 | 0 | 8 | 145 / 100 / 95 |
| field_08 | 2022-08-01 | 128 | 0 | 1 | 50 / 48 / 78 |
| field_09 | 2022-08-03 | 588 | 0 | 10 | 333 / 64 / 255 |
| field_10 | 2022-08-03 | 0 | 0 | 0 | 0 / 17 / 0 |
| field_11 | 2022-08-03 | 0 | 33 | 0 | 0 / 252 / 0 |
| field_12 | 2022-08-03 | 209 | 73 | 1 | 157 / 52 / 52 |
| field_13 | 2023-10-19 | 15 | 0 | 0 | 15 / 77 / 0 |
| field_14 | 2023-10-19 | 143 | 0 | 0 | 108 / 225 / 35 |
| field_15 | 2023-10-19 | 2156 | 697 | 1 | 1916 / 186 / 240 |
| field_16 | 2023-10-19 | 3129 | 0 | 0 | 1524 / 764 / 1605 |
| field_17 | 2023-10-19 | 415 | 0 | 0 | 323 / 291 / 92 |

Why the split: in the first run (same tiles, same day) Wonder also boxed buildings and water. It found the same 27 of 35 buildings as SAM's text prompts but only 29 of its 44 building outlines were on a building (text prompts: 30 of 39), and its water was 14% precise (28% after its review) against 95% for text prompts. On trees that first prompt scored the same as the trees-only one (mean per tile 62% recall, 64% precision), and its review left trees unchanged.

Limits: WorldCover is 10 m and from 2021, so a 15 m shelterbelt may fill only part of a cell, and trees planted or cut since then count against the models. Footprints miss some farm buildings and include some that are gone. Water here is the scout's possible water, which the app never cuts out.
