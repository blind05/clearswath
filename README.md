# ClearSwath

**Find the weeds. Read the label. Spray only where both say yes.**

A pesticide label is a legal document of 20 to 70 pages: setbacks from water, wind limits, rates, endangered-species
bulletins. A drone can now spray single patches of weeds, but nothing reads the label for it. ClearSwath does. Give it
a field, the label PDF and a drone weed map. It returns:

- **a decision** (No conflicts in checked rules, Adjust, or Do not spray), each reason with the label sentence it
  comes from, quoted word for word and checked against the PDF;
- **a spray map**: 1 m cells sprayed only where the weed map found weeds and no label rule, water body or
  endangered-species bulletin says no;
- **files for the sprayer**: a DJI Agras prescription (boundary shapefile plus a rate GeoTIFF), GeoJSON and KML;
- **a draft application record**, filled from the applicator's spoken or typed notes.

Built for the Meta Global AI Developer Hackathon (Indie Developer track), October 26 to November 4, 2026.

## Try it

Press **Try demo**. The demo runs offline from saved inputs, so it is free and instant.

- **Montana rangeland, leafy spurge.** A 24-acre block of a real drone orthomosaic (MPG Ranch, 1.27 cm per
  pixel), sprayed with Tordon 22K. A stream crosses the block. Result: **Adjust**; 23.6 of 24.1 acres may be sprayed,
  and the weed map sprays 19.1 of them. Tick "Ask the Muse Spark agent" to see the saved answer from Muse Spark
  Open, with each tool it called.
- **South Dakota cropland**, linked from the Montana result. A field drawn up to a creek, sprayed with Warrior II.
  The 150 ft aerial buffer takes a strip along the creek (Adjust), and the corrected outline is clear (No conflicts in
  checked rules).

Live runs on your own field and label need an access code: 3 per address per day, within a $5 daily model budget.

Run it yourself (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
uv sync
cp .env.example .env        # add MODEL_API_KEY, or FIREWORKS_API_KEY with LLM_PROVIDER=fireworks
uv run uvicorn app.api:app  # then open http://localhost:8000
uv run pytest               # no test calls the network or a model
```

## How it decides

1. **Field.** Drawn on the map or uploaded as GeoJSON. Mapped water comes from the National Hydrography Dataset;
   SAM 3.1 finds water, buildings and tree lines in NAIP aerial imagery.
2. **Label.** Muse Spark reads every page into a strict schema (setbacks, wind, rain, rates, runoff points), each rule
   with a word-for-word quote. Code drops any rule whose quote is not on the page it claims.
3. **Bulletin.** EPA's Bulletins Live! Two is checked for the product, place and month.
4. **Weeds.** A drone weed map from a trained head on Meta's DINOv2 / DINOv3 image features.
5. **Plan.** Pure geometry in the field's UTM zone. Label setbacks buffer their hazards, water itself is never
   sprayed, a bulletin ban or any missing data means Do not spray, and a label that requires runoff mitigation
   points is Adjust (complete them in EPA's PALM). A cell touching any buffer is held back, which always beats spray.
6. **Export and record.** Prescription files for the sprayed cells, and the record with every missing field flagged.

**No model makes the decision.** Status, buffers and rates come from tested code (`app/buffers.py`, `app/cells.py`).
If the Muse Spark agent's answer names a different status, calls the plan "legal", "compliant" or "safe", or quotes text
that is not on the label, the answer is replaced with the plan's own summary.

## Meta models

| Model | Where | Its job | How its output is checked |
|---|---|---|---|
| Muse Spark 1.3 | Meta Model API | Reads the label into rules; explains the plan as an agent with four tools | Every quote matched to the label text; the decision always from code |
| Muse Spark Open | Fireworks, Baseten | The same jobs on open weights | Same checks; the label eval compares providers |
| SAM 3.1 | Meta Model API, and open weights on Modal | Hazards in aerial imagery; zero-shot weed baseline | Merged with mapped water; scored against weed ground truth |
| DINOv3 ViT-S/16 | Open weights, Modal GPU | Features for the crop-vs-weed head (CoFly, PhenoBench) | Cross-validated against pixel masks |
| DINOv2 ViT-B/14 | Open weights, Modal GPU | Features for the leafy spurge probe and the Montana map | Scored on survey plots it never trained on |
| Muse Voice Transcribe 1.0 | Meta Model API | Turns a spoken job note into the record | Plan values always beat what the model heard; gaps listed |

## Weed results

All numbers are on images the model never trained on. "Hit" is the share of weed pixels inside sprayed cells;
"sprayed" is the share of the area sprayed. Full tables are in `evals/`.

| Dataset | Method | Hit / sprayed |
|---|---|---|
| CoFly-WeedDB (cotton, 201 images, 5-fold) | DINOv3 head | **95.9% / 37.9%** at 0.25 m cells |
| | SAM 3.1, prompt "weed" (zero-shot) | 0% |
| PhenoBench (sugar beet, 3 flight dates) | DINOv3 head + 50 labelled tiles from the date sprayed | **95.5 to 97.9% / 15 to 18%** at 0.1 m |
| | Spray everything green | 83 to 98% / 19 to 59% |
| | SAM 3 open weights, "weed" (zero-shot) | 73% / 22% |
| Leafy spurge (Montana, 900 survey plots) | DINOv2 probe | 85% accuracy on the official test plots, matching the dataset paper |

The spurge probe is the weakest part. On the Montana block, tuned to catch 90% of spurge plots, it found 87% of the
held-out ones and also flagged 41% of clean ones, so it sprays 79% of the block. Catching 70% sprays 35%. The app
states the catch rate next to the map.

## Limits

- **Decision support, not clearance.** The plan checks the rules listed above. It does not check weather and
  inversions, compute runoff points, apply buffer reductions, or know the applicator's licence. The applicator
  follows the label and the official bulletin.
- **Montana and South Dakota only.** The record follows Montana's ARM 4.10.207 for commercial applicators.
- **The DJI prescription is not flight-tested.** Its folder layout follows PIX4Dfields' DJI export; check it on a
  controller first. The GeoJSON and KML work with any controller or GIS.
- **Drone spraying also needs** an FAA Part 137 certificate and a state aerial applicator licence.
- The answer keys for the label eval are not yet independently reviewed, so no label-reading accuracy is claimed here.

## Data and credits

- Leafy Spurge Dataset, MPG Ranch (Doherty et al.), CC BY 4.0, doi:10.57967/hf/2508: the Montana imagery and survey
  plots. Details in `data/demo/mt/SOURCE.md`.
- CoFly-WeedDB, CC BY 4.0. PhenoBench, CC BY-SA 4.0 (www.phenobench.org).
- National Hydrography Dataset, The National Map and NAIP imagery (public domain). EPA Bulletins Live! Two and EPA
  product labels.
- Leaflet and Leaflet.draw (BSD-2-Clause).

## Repository

`app/` the service (FastAPI); `web/` the single-page map; `train/` Modal GPU jobs for the weed models; `evals/`
results and answer keys; `scripts/` demo builders and the label eval; `docs/CONTRACTS.md` module contracts.
