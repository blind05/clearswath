# Cut B: the proof moves up

Same scenes as the 2:49 cut, reordered so the creek click (the map quoting the label) comes right after the weed
map instead of near the end, with a rejected rule shown and tighter lines. Synthetic voice (Kokoro), so no "I".
Build: `scripts/narrate_video.py`, `cut_video.py`, `score_video.py`, each with `--script docs/video/cuts/B.md`.

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| hook | - | Montana drone image; spot-spray cells appear; the creek strip stays clear | "24 acres of Montana rangeland, and leafy spurge in a lot of it. The weed map marks 9.7 acres to spray. Not the creek, and not the clean ground." | 9.7 of 24.1 acres marked to spray |
| label | - | Tordon 22K label pages | "On the South Dakota farm where this project started, every spray job begins with a label like this: 30 pages of setbacks, wind limits and rates. Drones can spray single weed patches, but they don't read the label." | A pesticide label is the law |
| plan | - | The Montana plan: Adjust, the label sentence under Why | "ClearSwath reads the label with Muse Spark. Every rule it uses carries the exact sentence, and code checks that sentence is really on the page. The decision never comes from a model: tested geometry makes it." | Muse Spark reads the label. Code decides. |
| dropped | - | Rules not applied | "When the quoted sentence isn't on the page, the rule isn't used. It's listed here, so the applicator can check the label." | Quote not on the page: rule not used |
| scout | - | SAM alone, then Muse Wonder and SAM | "Next, what the sprayer must keep away from. Asked for tree lines from the air, SAM 3.1 finds almost none. So Muse Wonder boxes the tree lines it sees, and SAM outlines what's in each box. On 20 test tiles, that goes from 17 percent of trees found to 62." | SAM alone: 17% of trees. With Muse Wonder: 62% |
| weeds | - | Zoom into the spray cells | "The weeds come from a model trained for this project on Meta's DINOv2 features, on Modal GPUs. On survey plots it never saw, it finds 90 percent of the spurge, and sprays 40 percent of the block instead of all of it." | 90% of spurge found, 40% of the block sprayed |
| creek | - | South Dakota: click the creek strip, untick ULV, pull the edge back | "Here a field is drawn right up to a creek. Click the strip, and the map quotes the label, page 14: 150 feet from water by air, 450 for ULV spraying. Conditional rules like those stay on until you say they don't apply. Pull the edge back, and the plan is clear." | 150 ft from water, page 14 |
| files | - | DJI spray volume: 15 L/ha refused, 50 accepted | "Then planning files for the drone, with the label's minimum spray volume checked. They haven't been flown yet; check them on the controller first." | Planning files: DJI, GeoJSON, KML |
| record | - | The record, filled from the saved voice note | "After the job comes the record. Here a synthetic voice reads a made-up field note. Muse Voice Transcribe hears it, Muse Spark fills the record, and whatever the note didn't say stays marked missing." | A spoken note fills the record |
| agent | - | "How it decided" | "A saved Muse Spark answer explains the plan and shows each tool it called. Live runs read the label with Muse Spark Open on Baseten, with hosted Spark as backup." | The model roster |
| end | - | End card | "Models read and see. Tested code plans. The applicator decides: the weather, the licence, the field on the day. Try it at clearswath.onrender.com." | Models read and see. Tested code plans. The applicator decides. |
