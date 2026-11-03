# Narration to record (Hunter)

Ten short lines, one per shot of the film. Record each as its own file: `shot1.wav` ... `shot10.wav`, into
`data/video/hunter/`. About 150 words a minute; the film fits itself to your takes, so you never have to hit a time.
Every number here is the one the film and README already use.

**How:** a quiet room, door shut, fan off. A USB mic, or your phone about 20 cm from your mouth (any format is fine:
m4a, wav). Say each line once, cleanly; if you stumble, start that line again in the same file and tell me. Leave
a second of quiet before and after. Say the site as "clearswath dot onrender dot com".

| File | Shot | Say |
|---|---|---|
| shot1 | Montana drone image, spray cells appear | 24 acres of Montana rangeland, and leafy spurge in a lot of it. The weed map marks 9.7 acres to spray. Not the creek, and not the clean ground. |
| shot2 | Label pages | I grew up on a South Dakota farm, where every spray job starts with a label like this one: 30 pages of setbacks, wind limits and rates. Drones can now spray single patches of weeds, but they don't read the label. |
| shot3 | The Montana plan: Adjust, and the label's words | So ClearSwath does. Muse Spark reads the label, and every rule it uses carries the exact sentence. My code checks that sentence is really on the page, and drops any rule that isn't. The decision never comes from a model: tested geometry makes it. |
| shot4 | SAM alone, then Muse Wonder and SAM | Next, what the sprayer has to stay away from. Asked for tree lines from the air, SAM 3.1 alone finds almost none. So Muse Wonder looks at the photo and boxes the tree lines it sees, and SAM outlines what's in each box. On 20 test tiles, that goes from 17 percent of trees found to 62. |
| shot5 | Zoom into the spray cells | The weeds come from a model I trained on Meta's DINOv2, on Modal GPUs. On survey plots it never saw, it finds 90 percent of the spurge, and sprays 40 percent of the block instead of all of it. |
| shot6 | DJI spray volume, files | Then planning files for the drone, with the label's minimum spray volume checked. They haven't been flown yet, so check them on the controller first. |
| shot7 | The record, filled from a voice note | After the job comes the record. Here a synthetic voice reads a made-up field note. Muse Voice Transcribe hears it, Muse Spark fills the record, and whatever the note didn't say stays marked missing. |
| shot8 | South Dakota: click the creek strip, untick ULV, pull the edge back | Here's a field drawn right up to a creek. Click the strip, and the map quotes the label, page 14: 150 feet from water by air, 450 for ULV spraying. Conditional rules like those stay on until you say they don't apply. Pull the edge back, and the plan is clear. |
| shot9 | "How it decided" | A saved Muse Spark answer explains the plan and shows each tool it called. On live runs, the label is read with Muse Spark Open on Baseten, open weights, with hosted Spark as backup. |
| shot10 | End card | Models read and see. Tested code plans. The applicator decides: the weather, the licence, the field on the day. Try it at clearswath.onrender.com. |

When the ten files are in `data/video/hunter/`, the film is re-cut to your voice: each shot lasts as long as its
line, the captions use these words, and the README drops "synthetic narration".
