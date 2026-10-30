# Hazard scout eval (2026-10-29)

20 NAIP tiles (about 0.6 km across each): the 2 demo fields and 18 squares at fixed random offsets around them, eastern South Dakota and western Montana. Made by `evals/scout_eval.py`.

Truth, which no Meta model made: trees and shrubs (the app's tree lines and woods) and water from ESA WorldCover 2021 v200 (10 m cells, CC BY 4.0); buildings from Microsoft Global ML Building Footprints (ODbL), 40 m2 and up. A building counts as found if an outline touches it (3 m tolerance).

| Method | Trees and shrubs: precision / recall | Water: precision / recall | Buildings found | Building outlines on a building |
|---|---|---|---|---|
| SAM 3.1, text prompts | 74% / 8% | 95% / 42% | 27 of 35 (77%) | 30 of 39 |
| Wonder + SAM, before review | 65% / 82% | 14% / 60% | 27 of 35 (77%) | 29 of 44 |
| Wonder + SAM, after review | 64% / 82% | 28% / 53% | 27 of 35 (77%) | 32 of 61 |

Per tile (trees and shrubs: true positive / false positive / missed 10 m cells, after review):

| Tile | NAIP date | Tree and shrub cells | Water cells | Buildings | After review |
|---|---|---|---|---|---|
| field | 2022-08-03 | 742 | 0 | 0 | 585 / 298 / 157 |
| block | 2023-10-19 | 415 | 0 | 0 | 218 / 471 / 197 |
| field_00 | 2022-08-03 | 23 | 0 | 0 | 0 / 0 / 23 |
| field_01 | 2022-08-01 | 81 | 0 | 3 | 47 / 35 / 34 |
| field_02 | 2022-08-03 | 65 | 0 | 1 | 19 / 60 / 46 |
| field_03 | 2022-08-03 | 381 | 0 | 5 | 212 / 120 / 169 |
| field_04 | 2022-08-01 | 73 | 0 | 2 | 40 / 78 / 33 |
| field_05 | 2022-08-03 | 0 | 44 | 0 | 0 / 18 / 0 |
| field_06 | 2022-08-03 | 344 | 0 | 3 | 233 / 32 / 111 |
| field_07 | 2022-08-03 | 240 | 0 | 8 | 145 / 75 / 95 |
| field_08 | 2022-08-01 | 128 | 0 | 1 | 70 / 48 / 58 |
| field_09 | 2022-08-03 | 588 | 0 | 10 | 357 / 71 / 231 |
| field_10 | 2022-08-03 | 0 | 0 | 0 | 0 / 14 / 0 |
| field_11 | 2022-08-03 | 0 | 33 | 0 | 0 / 0 / 0 |
| field_12 | 2022-08-03 | 209 | 73 | 1 | 166 / 65 / 43 |
| field_13 | 2023-10-19 | 15 | 0 | 0 | 15 / 48 / 0 |
| field_14 | 2023-10-19 | 143 | 0 | 0 | 136 / 290 / 7 |
| field_15 | 2023-10-19 | 2156 | 697 | 1 | 1831 / 300 / 325 |
| field_16 | 2023-10-19 | 3129 | 0 | 0 | 3129 / 2055 / 0 |
| field_17 | 2023-10-19 | 415 | 0 | 0 | 279 / 112 / 136 |

Limits: WorldCover is 10 m and from 2021, so a 15 m shelterbelt may fill only part of a cell, and trees planted or cut since then count against the models. Footprints miss some farm buildings and include some that are gone. Water here is the scout's possible water, which the app never cuts out.
