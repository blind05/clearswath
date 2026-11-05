# Cut E: cut D in Hunter's voice

Built from what strong product demos do: the outcome in the first seconds, the problem in plain words with its
stakes, then one unbroken demo (a field, a decision, why, a fix), then how the models did it, and the one-line
promise to close. The camera eases onto the part of the screen that matters (`cam` in `scripts/cut_video.py`), so
the label's words are readable on a phone. Written for Hunter to read (first person). Until his takes exist, Kokoro af_heart stands in for timing.
Build: `scripts/narrate_video.py --voice af_heart`, `cut_video.py`, `score_video.py`, each with
`--script docs/video/cuts/E.md`.

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| opening | - | Montana drone map, spray cells, the map alone | "Spray 9.7 acres, not all 24.1. ClearSwath finds the weeds and reads the label, so you spray only where both say yes." | 9.7 of 24.1 acres marked to spray |
| problem | - | Tordon 22K label pages | "I grew up on a South Dakota farm. Every spray job starts with a label like this one: 30 pages, and the label is the law. Drones can spray single weed patches now, but they can't read it." | 30 pages of rules. Not one map. |
| field | - | South Dakota field to the creek; the camera moves to the decision | "So I built ClearSwath, on Meta's models, to read it. This South Dakota field runs right up to a creek. The answer: Adjust, 11.1 acres held back." | Adjust: 11.1 of 37 acres held back |
| why | - | The cursor glides to the strip; click; the card | "Click the held-back strip, and it quotes the label, page 14: do not apply within 150 feet of aquatic habitats by air, or 450 feet for ultra-low-volume." | Warrior II label, page 14 |
| proof | - | The Warrior II PDF, page 14, both sentences highlighted | "The same sentences, word for word, in the PDF." | Warrior II label PDF, page 14 |
| untick | - | The conditional rules; ULV unticked | "Not spraying ultra-low-volume? Untick it, and only 1.6 acres stay held back." | Untick what doesn't apply |
| clear | - | The corrected outline | "Redraw the field clear of the creek, and all 31.2 acres show no conflicts in the checked rules." | Redrawn: all 31.2 acres clear |
| spurge | - | Montana spray cells, close | "The weed map is a model I trained on Meta's DINOv2. On plots it had never seen, it found 90 percent of spurge plots, and flagged 10 percent of clean ones." | Found 90% of spurge plots, flagged 10% of clean ones |
| reads | - | Montana decision, then Why and Muse Spark's answer | "Muse Spark reads the label into rules, each with its exact sentence. Live runs use the open-weights Muse Spark Open, on Baseten." | Muse Spark reads the label. Code decides. |
| rejected | - | Rules not applied | "If the sentence isn't on the page, the rule isn't used. And the decision always comes from tested code." | Quote not on the page: rule not used |
| hazards | - | SAM alone, then Muse Wonder and SAM | "On 20 test tiles, SAM 3.1 alone found 17 percent of trees. With Muse Wonder finding them first, 62 to 69 percent, across three runs." | SAM alone: 17% of trees. With Muse Wonder: 62-69% |
| export | - | Spray volume checked, files | "The drone file won't build below the label's 18.7 liters per hectare. It hasn't been flown yet." | 15 L/ha refused, 50 accepted: the label's minimum is 18.7 |
| notes | - | The record form: "Record a note" | "After the job, I just talk. Muse Voice Transcribe hears it, Muse Spark fills the record, and anything I don't say stays marked missing." | A spoken note fills the record |
| fieldnote | - | Hunter's own note plays; the camera moves down the fields it filled | "Sample note. Pat Miller, licence MT4412. Sprayed today, Tordon 22K by drone on leafy spurge, one quart per acre, ten gallons. Nine fifteen to ten forty, wind five from the west, sixty-two degrees." | Hunter's voice, heard by Muse Voice Transcribe |
| close | - | End card | "The applicator still decides. ClearSwath: find the weeds, read the label, spray only where both say yes." | Find the weeds. Read the label. Spray only where both say yes. |
