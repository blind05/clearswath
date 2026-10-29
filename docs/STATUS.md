# What's real (audit, 2026-10-29)

Classified from what runs today, not from older plans. "Live" means the code path calls the model or service when a
user acts; "replay" means the demo serves a saved real run.

| Feature | State | Evidence |
|---|---|---|
| Label PDF -> rules with verified quotes (`label_reader`) | Working, live | Fireworks Spark Open: Tordon 1/1 recall, 9/9 precision; Warrior 6/6, 8/8 (answer keys unreviewed). Not yet run on Muse Spark 1.3 |
| Label photo -> rules | Working in code, untested live | Image parts are sent as `data:` URLs, marked TODO(verify) in `app/llm.py` |
| Mapped water (NHD) | Working, live; cached for demos | Both demos: `water_source: usgs` |
| SAM 3.1 hazards from NAIP (water, buildings, tree lines) | Code path works, contributes nothing to either demo | Demo caches hold no SAM shapes; smoke test passes on the Meta API (2026-10-29) |
| Bulletins Live! Two check | Working, live; cached for demos | Queried 2026-10-28 |
| Buffer and decision engine (`buffers.plan`, `cells`) | Working, tested | Unit and e2e tests (`tests/test_buffers.py`, `tests/test_e2e.py`) |
| Spot-spray grid from a weed map | Working | Montana map from a DINOv2-B model fine-tuned on Modal: 90% of held-out spurge plots found, 40% of the block sprayed |
| Photo mode (DINOv3 head) | Working, live on Modal | Endpoint deployed; held-out CoFly 94.3% hit / 30.7% sprayed |
| Agent explanation (four tools) | Working live on Fireworks; demo is a replay | Saved answer: `muse-spark-open` on Fireworks, 2026-10-28 |
| Baseten Spark Open | Working for chat and agent fallback; fails on long labels | Returns zero rules on long label reads |
| Muse Spark 1.3 (Meta API) | Reachable, not used by any demo or eval yet | Smoke test: chat, JSON, tools pass (2026-10-29) |
| Muse Voice Transcribe -> application record | Working in code; WAV only | Smoke test passes on a silent clip; not yet run on real speech |
| Muse Wonder 1.0, Muse Image 1.0 | Available on the key, not used | |
| Exports: KML, GeoJSON | Working | Tests |
| Export: DJI prescription | Built, not flight-tested | Folder layout TODO(verify) |
| Access code, per-IP limit, daily budget | Working | Tests; X-Forwarded-For behind Render's proxy not yet checked |
| React page (Astryx, MapLibre, Terra Draw) | Working | Recorder's 8 beats; QA at 1440/1280/390 |
| Live URL | Not deployed | `render.yaml` ready |
| README, video | README drafted, no screenshots; no video | |

## Meta calls, from user action to screen

- **Plan the spray (live):** label upload -> Spark reads pages -> rules with quotes -> "Why" excerpts and the rules
  to untick. Field -> SAM 3.1 on NAIP tiles + NHD -> buffers on the map. Weed map -> magenta cells.
- **Ask Muse Spark to explain:** Spark agent calls read_label, find_hazards, check_bulletin, plan_spray -> the
  answer and "How it decided"; the decision shown is always `buffers.plan`'s.
- **Fill the record:** WAV -> Voice Transcribe -> Spark fills the record schema -> table with missing fields in red.
- **Check a photo:** photo -> Modal DINOv3 head -> magenta overlay and share flagged.

## Biggest obstacle

The demo a judge sees uses no Meta API model at all: water came from NHD, and the saved explanation is from Spark
Open on Fireworks. The models are wired in but invisible. Second: no live URL.
