# ClearSwath demo video: script and shot list (draft for Hunter)

The cut is 2:50 (`scripts/cut_video.py`); the times below are its shot boundaries, so the voiceover can be read
straight to picture. Record one WAV, then `uv run python scripts/score_video.py --vo data/video/voiceover.wav`. Every shot is the real app or a real saved run; nothing is staged. The narration in the current cut is a synthetic
voice (Kokoro-82M, `scripts/narrate_video.py`), so the script avoids "I"; if Hunter records his own, the first person can
come back. "VO" is Hunter's
voiceover; "ON SCREEN" is the only text added in the edit. Takes come from `scripts/record_demo.py` (1920x1080).

| Time | Shot | VO | ON SCREEN |
|---|---|---|---|
| 0:00-0:09 | Montana drone image; magenta spot-spray cells appear; the creek strip stays clear | "24 acres of Montana rangeland, and leafy spurge in a lot of it. The weed map marks 9.7 acres to spray. Not the creek, and not the clean ground." | 9.7 of 24.1 acres marked to spray |
| 0:09-0:29 | Tordon 22K label PDF, pages scrolling | "On the South Dakota farm where this project started, every spray job begins with a label like this: a legal document, 70 pages of setbacks, wind limits and rates. Drones can now spray single weed patches, but nothing reads the label for them." | A pesticide label is the law |
| 0:29-0:51 | Click "Try the demo"; the decision "Adjust" and the label sentence under "Why" | "ClearSwath reads the label with Muse Spark. Every rule it uses carries the exact sentence from the label, and code checks that sentence is really on the page. The decision itself never comes from a model: tested geometry makes it." | Muse Spark reads the label. Code decides. |
| 0:51-1:21 | `docs/video/scout-sam-text-only.png`, then `scout-wonder-sam.png` (South Dakota NAIP tile) | "Next, what the sprayer must keep away from. Asked for tree lines from the air, SAM 3.1 finds almost none. So Muse Wonder looks at the photo and draws a box around each one, and SAM outlines what's in the box. On 20 test tiles, that goes from 17 percent of trees found to 62." | SAM alone: 17% of trees. With Muse Wonder: 62%. |
| 1:21-1:46 | Zoom into the Montana spray cells (beat 3) | "The weeds come from a model trained for this project on Meta's DINOv2 features, on Modal GPUs. On survey plots it never saw, it finds 90 percent of the spurge, and sprays 40 percent of the block instead of all of it." | 90% of spurge found, 40% of the block sprayed |
| 1:46-2:01 | DJI spray volume field: 15 L/ha refused, 50 accepted (beat 5) | "Then a planning file for the drone, with the label's minimum spray volume checked. It hasn't been flown yet; check it on the controller first." | Planning files: DJI, GeoJSON, KML |
| 1:42-1:55 | Application record: the demo's saved voice note, filled (beat 6) | "After the job comes the record. Here a synthetic voice reads a made-up field note. Muse Voice Transcribe hears it, Muse Spark fills the state record, and whatever the note didn't say stays marked missing." | A spoken note fills the record |
| 2:01-2:25 | South Dakota: field drawn to the creek (beat 6); click the strip, the card quotes page 14 (7); untick ULV (8); corrected outline: "No conflicts in checked rules" (8) | "Here a field is drawn right up to a creek. Click the strip, and the map shows the sentences holding it back: 150 feet from water by air, 450 for ULV spraying. Rules like that stay on until you say they don't apply. Pull the edge back, and the plan is clear." | 150 ft from water, page 14 |
| 2:25-2:40 | "How it decided" trace (beat 4) | "Muse Spark explains the plan and shows each tool it called. On live runs, the label is read with Muse Spark Open on Baseten, open weights, with hosted Spark as backup." | Muse Spark 1.3 · Muse Wonder · SAM 3.1 · DINOv2 · Muse Spark Open |
| 2:40-2:50 | End card | "Models read and see. Tested code plans. The applicator decides: the weather, the licence, the field on the day. ClearSwath." | Models read and see. Tested code plans. The applicator decides. |

Words to avoid on screen and in VO: legal, compliant, safe, certified, AI-powered.

## Submission text (draft)

**Name:** ClearSwath

**One-liner:** Find the weeds. Read the label. Spray only where both say yes.

**Problem statement:** Build for Your World (a problem I know firsthand), with "gives a spray drone a new capability"
from Push the Frontier.

**Description:** ClearSwath turns a field outline, a pesticide label PDF and a drone weed map into a spray plan: a
decision (No conflicts in checked rules, Adjust, Do not spray), a 1 m spot-spray map, DJI/GeoJSON/KML files and a
draft application record. Muse Spark reads the label into rules, each with a quote verified against the PDF. Muse
Wonder boxes tree lines and woods on the aerial photo for SAM 3.1 to outline (17% to 62% of trees found on 20 test
tiles); SAM's text prompts find buildings and water. A DINOv2 model fine-tuned on Modal maps leafy spurge (90% of
held-out plots found, 40% of the block sprayed). Live runs read labels with Muse Spark Open on Baseten. A
note spoken into the page goes through Muse Voice Transcribe, and Muse Spark fills the application record, leaving
whatever wasn't said marked missing. Tested
geometry, not a model, makes every decision; the applicator still decides whether to fly. The demos are saved real
runs. Built during the event: all of it; third-party parts are listed in the
README.

## X post (draft)

> 24 acres of rangeland. The weed map marks 9.7 to spray, and keeps off the creek.
>
> ClearSwath reads the pesticide label, finds the weeds and the tree lines, and plans spraying only where both say
> yes. Muse Spark, Muse Wonder, SAM 3.1 and DINOv2 read and see; tested code plans.
>
> What would you want it to check next?

Self-reply: the live link, the repo, and the video.
