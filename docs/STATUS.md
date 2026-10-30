# What's real (audit, 2026-10-29; updated the same evening)

Classified from what runs today, not from older plans. "Live" means the code path calls the model or service when a
user acts; "replay" means the demo serves a saved real run.

| Feature | State | Evidence |
|---|---|---|
| Label PDF -> rules with verified quotes (`label_reader`) | Working, live; both demos now read by Muse Spark 1.3 | 3 runs per label, answer keys unreviewed: Spark 1.3 Tordon recall 100%, precision 90-100%; Warrior recall 67-100%, precision 89-100%. Baseten Spark Open Tordon recall 0-100% |
| Label photo -> rules | Working in code, untested live on a real label photo | `data:` image URLs work on the Meta API (checked 2026-10-29 with SAM and Wonder) |
| Mapped water (NHD) | Working, live; cached for demos | Both demos: `water_source: usgs` |
| SAM 3.1 hazards from NAIP | Working through the scout (`app/scout.py`) | On 20 NAIP tiles (`evals/results_scout.md`): text prompts find 8% of trees and shrubs but 77% of buildings and open water at 95% precision; from Wonder's boxes SAM finds 82% of trees and shrubs. On the two demo tiles text prompts found nothing: no open water or mapped buildings there |
| Muse Wonder 1.0 scout: boxes -> SAM masks -> Wonder reviews the overlay once | Working, live; in both demos | South Dakota: 18 marked, 11 kept, 5 added; Montana: 11 marked, 9 kept, 2 added. ~66 s and ~$0.14 per field at reasoning effort "low". Its water is "possible water": flagged for review (forces Adjust), never cut out, because on rangeland it marked grass and a dry draw as water. Measured on 20 tiles: trees and shrubs 64% precision / 82% recall; the review step doubled water precision (14% to 28%) and left trees unchanged |
| Bulletins Live! Two check | Working, live; cached for demos | Queried 2026-10-28 |
| Buffer and decision engine (`buffers.plan`, `cells`) | Working, tested | Unit and e2e tests (`tests/test_buffers.py`, `tests/test_e2e.py`) |
| Spot-spray grid from a weed map | Working | Montana map from a DINOv2-B model fine-tuned on Modal: 90% of held-out spurge plots found, 40% of the block sprayed |
| Photo mode (DINOv3 head) | Working, live on Modal | Endpoint deployed; held-out CoFly 94.3% hit / 30.7% sprayed |
| Agent explanation (four tools) | Working live; demo is a replay | Saved Montana answer: `muse-spark-1.3`, 2026-10-29 ($0.017) |
| Baseten Spark Open | Working for chat and agent fallback; fails on long labels | Returns zero rules on long label reads |
| Muse Spark 1.3 (Meta API) | Reads both demo labels; writes the saved agent answer | Smoke test passes (2026-10-29) |
| Muse Voice Transcribe -> application record | Working in code; WAV only | Smoke test passes on a silent clip; not yet run on real speech |
| Muse Image 1.0 | Available on the key, not used | No honest job for it |
| Exports: KML, GeoJSON | Working | Tests |
| Export: DJI prescription | Built, not flight-tested | Folder layout TODO(verify) |
| Access code, per-IP limit, daily budget | Working | Tests; X-Forwarded-For behind Render's proxy not yet checked |
| React page (Astryx, MapLibre, Terra Draw) | Working | Recorder's 8 beats; QA at 1440/1280/390 |
| Live URL | Not deployed | `render.yaml` ready |
| README, video | README drafted, no screenshots; no video | |

## Meta calls, from user action to screen

- **Plan the spray (live):** label upload -> Spark reads pages -> rules with quotes -> "Why" excerpts and the rules
  to untick. Field -> NAIP tile -> Muse Wonder boxes -> SAM 3.1 masks -> Wonder review -> tree lines, buildings and
  possible water on the map; NHD water -> buffers. Weed map -> magenta cells.
- **Ask Muse Spark to explain:** Spark agent calls read_label, find_hazards, check_bulletin, plan_spray -> the
  answer and "How it decided"; the decision shown is always `buffers.plan`'s.
- **Fill the record:** WAV -> Voice Transcribe -> Spark fills the record schema -> table with missing fields in red.
- **Check a photo:** photo -> Modal DINOv3 head -> magenta overlay and share flagged.

## Biggest obstacle

No live URL. (Fixed the same evening: the demo a judge sees now uses Muse Wonder, SAM 3.1 and Muse Spark 1.3; before,
water came only from NHD and the saved explanation was from Spark Open on Fireworks.) Next: the scout has no
measured accuracy yet, and Baseten's Spark Open drops rules on long labels.
