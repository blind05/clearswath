# ClearSwath demo video: script and shot list (draft for Hunter)

The cut is 2:22, proof first (cut C of `docs/video/cuts/`; A, the earlier 2:49, and B were the other options); the times below are its shot boundaries from `data/video/cut_timeline.json`, so the voiceover can be read
straight to picture. Record one WAV, then `uv run python scripts/score_video.py --vo data/video/voiceover.wav`. Every shot is the real app or a real saved run; nothing is staged. The narration in the current cut is a synthetic
voice (Kokoro-82M, `scripts/narrate_video.py`), so the script avoids "I"; if Hunter records his own, the first person can
come back. "VO" is Hunter's
voiceover; "ON SCREEN" is the only text added in the edit. Takes come from `scripts/record_demo.py` (1920x1080).

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| hook | 0:00-0:13 | Montana drone image; spot-spray cells appear | "24 acres of Montana rangeland. The weed map marks 9.7 acres of leafy spurge to spray. Not the creek, and not the clean ground." | 9.7 of 24.1 acres marked to spray |
| creek | 0:13-0:39 | South Dakota: click the creek strip, untick ULV, pull the edge back | "Why is a spot held back? Here a field is drawn right up to a creek. Click the strip, and the map quotes the label, page 14: 150 feet from water by air, 450 for ULV spraying. Untick the rule that doesn't apply, pull the edge back, and the plan is clear." | 150 ft from water, page 14 |
| label | 0:39-0:53 | Tordon 22K label pages | "Every one of those rules comes from a label like this: 30 pages of setbacks, wind limits and rates. Drones can spray single weed patches, but they don't read the label." | A pesticide label is the law |
| plan | 0:53-1:06 | The Montana plan: Adjust, the label sentence under Why | "ClearSwath does. Muse Spark reads it, every rule carries the exact sentence, and code checks that sentence is on the page. The decision never comes from a model." | Muse Spark reads the label. Code decides. |
| dropped | 1:06-1:11 | Rules not applied | "A rule whose sentence isn't on the page isn't used." | Quote not on the page: rule not used |
| scout | 1:11-1:28 | SAM alone, then Muse Wonder and SAM | "From the air, SAM 3.1 alone finds almost no tree lines. Muse Wonder boxes the ones it sees, and SAM outlines them: 17 percent of trees found becomes 62, on 20 test tiles." | SAM alone: 17% of trees. With Muse Wonder: 62% |
| weeds | 1:28-1:43 | Zoom into the spray cells | "The weed map is a model trained on Meta's DINOv2 features, on Modal. On survey plots it never saw, it found 90 percent of the spurge. Here, it marks 40 percent of the block to spray." | 90% of spurge found, 40% of the block sprayed |
| files | 1:43-1:54 | DJI spray volume: 15 L/ha refused, 50 accepted | "Planning files for the drone check the label's minimum spray volume. They haven't been flown yet; check them on the controller first." | Planning files: DJI, GeoJSON, KML |
| record | 1:54-2:03 | The record, filled from the saved voice note | "A spoken note, here a synthetic one, becomes the application record through Muse Voice Transcribe and Muse Spark." | A spoken note fills the record |
| agent | 2:03-2:12 | "How it decided" | "A saved Muse Spark answer shows each tool it called. Live label reads run on Muse Spark Open, on Baseten." | The model roster |
| end | 2:12-2:23 | End card | "Models read and see. Tested code plans. The applicator decides. Try it at clearswath.onrender.com." | Models read and see. Tested code plans. The applicator decides. |

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
