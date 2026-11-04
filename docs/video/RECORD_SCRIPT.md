# Narration to record (Hunter)

Eleven short lines, one per scene of the 2:22 film (cut C, `docs/video/SCRIPT.md`). Record each as its own file:
`shot1` ... `shot11` (m4a or wav), into `data/video/hunter/`. Speak at your normal pace; the film fits itself to your
takes, so you never have to hit a time. Every number here is the one the film and README already use.

**How:** a quiet room, door shut, fan off. A USB mic, or your phone about 20 cm from your mouth. Say each line once,
cleanly; if you stumble, start that line again in the same file and tell me. Leave a second of quiet before and
after. Say the site as "clearswath dot onrender dot com".

| File | Scene | Say |
|---|---|---|
| shot1 | Montana drone image, spray cells appear | 24 acres of Montana rangeland. The weed map marks 9.7 acres of leafy spurge to spray. Not the creek, and not the clean ground. |
| shot2 | South Dakota: click the creek strip, untick ULV, pull the edge back | Why is a spot held back? Here's a field drawn right up to a creek. Click the strip, and the map quotes the label, page 14: 150 feet from water by air, 450 for ULV spraying. Untick the rule that doesn't apply, pull the edge back, and the plan is clear. |
| shot3 | Label pages | I grew up on a South Dakota farm, where every spray job starts with a label like this: 30 pages of setbacks, wind limits and rates. Drones can spray single weed patches now, but they don't read the label. |
| shot4 | The Montana plan: Adjust, and the label's words | So ClearSwath does. Muse Spark reads it, every rule carries the exact sentence, and my code checks that sentence is on the page. The decision never comes from a model. |
| shot5 | Rules not applied | A rule whose sentence isn't on the page isn't used. |
| shot6 | SAM alone, then Muse Wonder and SAM | From the air, SAM 3.1 alone finds almost no tree lines. Muse Wonder boxes the ones it sees, and SAM outlines them: 17 percent of trees found becomes 62, on 20 test tiles. |
| shot7 | Zoom into the spray cells | The weed map is a model I trained on Meta's DINOv2 features, on Modal. On survey plots it never saw, it found 90 percent of the spurge. Here, it marks 40 percent of the block to spray. |
| shot8 | DJI spray volume, files | Planning files for the drone check the label's minimum spray volume. They haven't been flown yet, so check them on the controller first. |
| shot9 | The record, filled from a voice note | A spoken note, here a synthetic one, becomes the application record through Muse Voice Transcribe and Muse Spark. |
| shot10 | "How it decided" | A saved Muse Spark answer shows each tool it called. Live label reads run on Muse Spark Open, on Baseten. |
| shot11 | End card | Models read and see. Tested code plans. The applicator decides. Try it at clearswath.onrender.com. |

When the eleven files are in `data/video/hunter/`: `uv run python scripts/use_voice.py`, then `cut_video.py`,
`score_video.py` and `teaser_video.py`. Each scene lasts as long as your line. The captions come from SCRIPT.md, so
its VO column takes these words, and the README and VIDEO_QA drop "synthetic narration".
