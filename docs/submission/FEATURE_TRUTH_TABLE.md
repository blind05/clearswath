# Feature truth table (2026-11-03)

| Feature | What it is | Models |
|---|---|---|
| Montana and South Dakota demos | Saved real runs; the plan is recomputed by tested code on every choice | Muse Spark 1.3 (labels), Muse Wonder + SAM 3.1 (scout), DINOv2-B fine-tuned (Montana weeds) |
| Decision, buffers, spot-spray cells | Deterministic geometry in UTM, tested (`app/buffers.py`, `app/cells.py`) | none |
| Click the map: why is this spot held back? | Real per-rule zones from `buffers.plan`; clean ground says nothing checked holds it | none (shows the model-read, quote-checked rules) |
| Rules not applied | Real: Muse Spark 1.3 quoted a page-14 drift sentence that isn't in the Tordon 22K text, so the plan dropped it | Muse Spark 1.3 |
| Saved Muse Spark answer | Replay of a real run of 2026-10-29, labelled on screen | Muse Spark 1.3 |
| Hazard scout numbers | 20 NAIP tiles vs ESA WorldCover 2021 and Microsoft footprints; trees per tile 17% (SAM text) vs 62-69% (Wonder + SAM, 3 runs) | Muse Wonder 1.0, SAM 3.1 |
| Live plan on your own field and label | Live, paid, behind the access code (3 per address per day, $5 daily cap) | Muse Spark Open on Baseten reads the label (Spark 1.3 fallback); Wonder + SAM; Spark 1.3 agent |
| Label accuracy | Measured (`evals/results_labels.md`), not claimed: answer keys unreviewed | Spark 1.3, Spark Open (Baseten, Fireworks) |
| DJI prescription | Planning file, not flight-tested | none |
| Photo mode | Live on Modal; trained on cotton and sugar beet | DINOv3 ViT-S/16 + head |
| Voice record | Works in code; not run on real field speech | Muse Voice Transcribe, Muse Spark |
| Video narration | Synthetic voice, Kokoro-82M (Apache-2.0); not Hunter's voice | none (Muse Voice Transcribe used only to check intelligibility) |
