# What's real (audit, 2026-10-29; updated 2026-11-02)

Classified from what runs today, not from older plans. "Live" means the code path calls the model or service when a
user acts; "replay" means the demo serves a saved real run.

| Feature | State | Evidence |
|---|---|---|
| Label PDF -> rules with verified quotes (`label_reader`) | Working, live; both demos now read by Muse Spark 1.3 | 3 runs per label, answer keys unreviewed: Spark 1.3 Tordon recall 100%, precision 90-100%; Warrior recall 67-100%, precision 89-100%. Baseten Spark Open Tordon recall 0-100% |
| Label photo -> rules | Working in code, untested live on a real label photo | `data:` image URLs work on the Meta API (checked 2026-10-29 with SAM and Wonder) |
| Mapped water (NHD) | Working, live; cached for demos | Both demos: `water_source: usgs` |
| Hazard scout (`app/scout.py`): Muse Wonder boxes tree lines and woods for SAM 3.1; SAM's text prompts find buildings and water | Working, live; in all three demos | On 20 NAIP tiles (`evals/results_scout.md`), trees and shrubs, mean per tile: Wonder + SAM 62% recall / 57% precision, SAM text prompts alone 17% / 68% (median recall 0%). Buildings: text prompts find 27 of 35. Water: text prompts 95% precise; it is "possible water" (forces Adjust, never cut out). Wonder at reasoning effort "low", ~20 s; its second look (review) changed nothing, so the app skips it. Wonder varies a lot run to run on single tiles |
| Bulletins Live! Two check | Working, live; cached for demos | Queried 2026-10-28 |
| Buffer and decision engine (`buffers.plan`, `cells`) | Working, tested | Unit and e2e tests (`tests/test_buffers.py`, `tests/test_e2e.py`) |
| Spot-spray grid from a weed map | Working | Montana map from a DINOv2-B model fine-tuned on Modal: 90% of held-out spurge plots found, 40% of the block sprayed |
| Photo mode (DINOv3 head) | Working, live on Modal | Endpoint deployed; held-out CoFly 94.3% hit / 30.7% sprayed |
| Agent explanation (four tools) | Working live; demo is a replay | Saved Montana answer: `muse-spark-1.3`, 2026-10-29 ($0.017) |
| Baseten Spark Open | Reads labels on live runs (Spark 1.3 as fallback); the agent's fallback | Empty reads are asked again and never cached; 3 runs per label: Tordon recall 100%, Warrior 83-100% (`evals/results_labels.md`). Reads Warrior's ULV-only 450 ft buffer as always applying, so the demos keep Spark 1.3's reads |
| Muse Spark 1.3 (Meta API) | Reads both demo labels; writes the saved agent answer | Smoke test passes (2026-10-29) |
| Muse Voice Transcribe -> application record | Working in code; WAV only | Smoke test passes on a silent clip; not yet run on real speech |
| Muse Image 1.0 | Available on the key, not used | No honest job for it |
| Exports: KML, GeoJSON | Working | Tests |
| Export: DJI prescription | Built, not flight-tested | Folder layout TODO(verify) |
| Access code, per-IP limit, daily budget | Working | Tests; checked on Render with `/api/whoami` (2026-11-03): the visitor is Cloudflare's `CF-Connecting-IP`, not the last X-Forwarded-For hop (Render's internal proxy) |
| React page (Astryx, MapLibre, Terra Draw) | Working | Recorder's 8 beats; QA at 1440/1280/390 |
| Live URL | https://clearswath.onrender.com (Render free plan) | Demo plans computed once (peak 395 MB of 512); sleeps after 15 idle minutes |
| README, video | README with screenshots, diagram and results; video scripted (`docs/video/SCRIPT.md`) | |

## Meta calls, from user action to screen

- **Plan the spray (live):** label upload -> Spark reads pages -> rules with quotes -> "Why" excerpts and the rules
  to untick. Field -> NAIP tile -> Muse Wonder boxes -> SAM 3.1 masks -> Wonder review -> tree lines, buildings and
  possible water on the map; NHD water -> buffers. Weed map -> magenta cells.
- **Ask Muse Spark to explain:** Spark agent calls read_label, find_hazards, check_bulletin, plan_spray -> the
  answer and "How it decided"; the decision shown is always `buffers.plan`'s.
- **Fill the record:** WAV -> Voice Transcribe -> Spark fills the record schema -> table with missing fields in red.
- **Check a photo:** photo -> Modal DINOv3 head -> magenta overlay and share flagged.

## Biggest obstacle

The video. The app is live, the scout is measured, and Baseten reads labels; what judges watch in the final round
doesn't exist yet.
