# Cut D: the camera follows the proof

Built from what strong product demos do: the outcome in the first seconds, the problem in plain words with its
stakes, then one unbroken demo (a field, a decision, why, a fix), then how the models did it, and the one-line
promise to close. The camera eases onto the part of the screen that matters (`cam` in `scripts/cut_video.py`), so
the label's words are readable on a phone. Synthetic voice (Kokoro af_heart), so no "I".
Build: `scripts/narrate_video.py --voice af_heart`, `cut_video.py`, `score_video.py`, each with
`--script docs/video/cuts/D.md`.

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| opening | - | Montana drone map, spray cells, the map alone | "Twenty-four acres of Montana rangeland. ClearSwath marks just the 9.7 acres with leafy spurge to spray. Not the creek, and not the clean ground." | 9.7 of 24.1 acres marked to spray |
| problem | - | Tordon 22K label pages | "Getting there means reading the label: 30 pages of setbacks, wind limits and rates, and the label is the law. Drones can spray single weed patches, but they can't read it." | 30 pages of rules. Not one map. |
| field | - | South Dakota field to the creek; the camera moves to the decision | "So ClearSwath reads it. Here's a South Dakota field, with a different label, drawn right up to a creek. The answer: Adjust. 11 of its 37 acres are held back." | Adjust: 11.1 of 37 acres held back |
| why | - | The cursor glides to the strip; click; the card | "Click the strip, and it shows why, in the label's own words, with the page: no spraying within 150 feet of water by air, or 450 feet for ultra-low-volume." | Warrior II label, page 14 |
| proof | - | The Warrior II PDF, page 14, both sentences highlighted | "Those are the label's own sentences, on page 14 of the PDF." | Warrior II label PDF, page 14 |
| untick | - | The conditional rules; ULV unticked | "Not flying ultra-low-volume? Untick that rule, and only 1.6 acres stay held back." | Untick what doesn't apply |
| clear | - | The corrected outline | "Redraw the field back from the creek, and all 31.2 acres of the smaller field clear." | Redrawn: all 31.2 acres clear |
| spurge | - | Montana spray cells, close | "The weed map is a model trained on Meta's DINOv2 features. On held-out survey plots it found 90 percent of the spurge. Here, it marks 40 percent of the block instead of all of it." | 90% of spurge found, 40% of the block sprayed |
| reads | - | Montana decision, then Why and Muse Spark's answer | "Muse Spark reads the label into rules, and every rule carries its exact sentence." | Muse Spark reads the label. Code decides. |
| rejected | - | Rules not applied | "Code checks that sentence is really on the page. This one wasn't, so it isn't used. And the decision never comes from a model: tested geometry makes it." | Quote not on the page: rule not used |
| hazards | - | SAM alone, then Muse Wonder and SAM | "On aerial photos, SAM 3.1 alone found 17 percent of trees. With Muse Wonder boxing the tree lines first, 62 to 69 percent across three runs, on 20 test tiles." | SAM alone: 17% of trees. With Muse Wonder: 62% |
| export | - | Spray volume checked, files | "Out come planning files for the drone, with the label's minimum spray volume enforced. They haven't been flown yet, so check them on the controller first." | Planning files: DJI, GeoJSON, KML |
| notes | - | The saved voice note, filled into the record | "After the job, a spoken note, here a synthetic one, becomes the application record through Muse Voice Transcribe and Muse Spark. Anything it didn't hear stays marked missing." | A spoken note fills the record |
| close | - | End card | "The applicator decides. ClearSwath: find the weeds, read the label, and spray only where both say yes." | Find the weeds. Read the label. Spray only where both say yes. |
