# Cut C: two minutes, proof first

The shortest honest cut: the result, then straight to the creek click (why a spot is held back, with the label's
sentence and page), then how each model got there, one line each. Synthetic voice (Kokoro), so no "I".
Build: `scripts/narrate_video.py`, `cut_video.py`, `score_video.py`, each with `--script docs/video/cuts/C.md`.

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| hook | - | Montana drone image; spot-spray cells appear | "24 acres of Montana rangeland. The weed map marks 9.7 acres of leafy spurge to spray. Not the creek, and not the clean ground." | 9.7 of 24.1 acres marked to spray |
| creek | - | South Dakota: click the creek strip, untick ULV, pull the edge back | "Why is a spot held back? Here a field is drawn right up to a creek. Click the strip, and the map quotes the label, page 14: 150 feet from water by air, 450 for ULV spraying. Untick the rule that doesn't apply, pull the edge back, and the plan is clear." | 150 ft from water, page 14 |
| label | - | Tordon 22K label pages | "Every one of those rules comes from a label like this: 30 pages of setbacks, wind limits and rates. Drones can spray single weed patches, but they don't read the label." | A pesticide label is the law |
| plan | - | The Montana plan: Adjust, the label sentence under Why | "ClearSwath does. Muse Spark reads it, every rule carries the exact sentence, and code checks that sentence is on the page. The decision never comes from a model." | Muse Spark reads the label. Code decides. |
| dropped | - | Rules not applied | "A rule whose sentence isn't on the page isn't used." | Quote not on the page: rule not used |
| scout | - | SAM alone, then Muse Wonder and SAM | "From the air, SAM 3.1 alone finds almost no tree lines. Muse Wonder boxes the ones it sees, and SAM outlines them: 17 percent of trees found becomes 62, on 20 test tiles." | SAM alone: 17% of trees. With Muse Wonder: 62% |
| weeds | - | Zoom into the spray cells | "The weed map is a model trained on Meta's DINOv2 features, on Modal. On survey plots it never saw, it found 90 percent of the spurge. Here, it marks 40 percent of the block to spray." | 90% of spurge found, 40% of the block sprayed |
| files | - | DJI spray volume: 15 L/ha refused, 50 accepted | "Planning files for the drone check the label's minimum spray volume. They haven't been flown yet; check them on the controller first." | Planning files: DJI, GeoJSON, KML |
| record | - | The record, filled from the saved voice note | "A spoken note, here a synthetic one, becomes the application record through Muse Voice Transcribe and Muse Spark." | A spoken note fills the record |
| agent | - | "How it decided" | "A saved Muse Spark answer shows each tool it called. Live label reads run on Muse Spark Open, on Baseten." | The model roster |
| end | - | End card | "Models read and see. Tested code plans. The applicator decides. Try it at clearswath.onrender.com." | Models read and see. Tested code plans. The applicator decides. |
