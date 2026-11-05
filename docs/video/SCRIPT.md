# ClearSwath demo video: script and shot list (draft for Hunter)

The film is cut E (`docs/video/cuts/E.md`), 2:31, narrated by Hunter in his own voice; the times below are its shot
boundaries from `data/video/cut_timeline.json`. Earlier cuts A-D are kept in `docs/video/cuts/`. Every shot is the real
app, a real saved run or the label PDFs; nothing is staged. The field note in the record scene is Hunter's own voice
(a made-up sample job, captioned as such), run through Muse Voice Transcribe and Muse Spark by `scripts/use_note.py`.
"ON SCREEN" is the text added in the edit. Takes come from `scripts/record_demo.py` (1920x1080).

| Scene | Time | Shot | VO | ON SCREEN |
|---|---|---|---|---|
| opening | 0:00-0:11 | Montana drone map, spray cells, the map alone | "Spray 9.7 acres, not all 24.1. ClearSwath finds the weeds and reads the label, so you spray only where both say yes." | 9.7 of 24.1 acres marked to spray |
| problem | 0:11-0:22 | Tordon 22K label pages | "I grew up on a South Dakota farm. Every spray job starts with a label like this one: 30 pages, and the label is the law. Drones can spray single weed patches now, but they can't read it." | 30 pages of rules. Not one map. |
| field | 0:22-0:33 | South Dakota field to the creek; the camera moves to the decision | "So I built ClearSwath, on Meta's models, to read it. This South Dakota field runs right up to a creek. The answer: Adjust, 11.1 acres held back." | Adjust: 11.1 of 37 acres held back |
| why | 0:33-0:45 | The cursor glides to the strip; click; the card | "Click the held-back strip, and it quotes the label, page 14: do not apply within 150 feet of aquatic habitats by air, or 450 feet for ultra-low-volume." | Warrior II label, page 14 |
| proof | 0:45-0:49 | The Warrior II PDF, page 14, both sentences highlighted | "The same sentences, word for word, in the PDF." | Warrior II label PDF, page 14 |
| untick | 0:49-0:55 | The conditional rules; ULV unticked | "Not spraying ultra-low-volume? Untick it, and only 1.6 acres stay held back." | Untick what doesn't apply |
| clear | 0:55-1:02 | The corrected outline | "Redraw the field clear of the creek, and all 31.2 acres show no conflicts in the checked rules." | Redrawn: all 31.2 acres clear |
| spurge | 1:02-1:12 | Montana spray cells, close | "The weed map is a model I trained on Meta's DINOv2. On plots it had never seen, it found 90 percent of spurge plots, and flagged 10 percent of clean ones." | Found 90% of spurge plots, flagged 10% of clean ones |
| reads | 1:12-1:21 | Montana decision, then Why and Muse Spark's answer | "Muse Spark reads the label into rules, each with its exact sentence. Live runs use the open-weights Muse Spark Open, on Baseten." | Muse Spark reads the label. Code decides. |
| rejected | 1:21-1:27 | Rules not applied | "If the sentence isn't on the page, the rule isn't used. And the decision always comes from tested code." | Quote not on the page: rule not used |
| hazards | 1:27-1:38 | SAM alone, then Muse Wonder and SAM | "On 20 test tiles, SAM 3.1 alone found 17 percent of trees. With Muse Wonder finding them first, 62 to 69 percent, across three runs." | SAM alone: 17% of trees. With Muse Wonder: 62-69% |
| export | 1:38-1:45 | Spray volume checked, files | "The drone file won't build below the label's 18.7 liters per hectare. It hasn't been flown yet." | 15 L/ha refused, 50 accepted: the label's minimum is 18.7 |
| notes | 1:45-1:54 | The record form: "Record a note" | "After the job, I just talk. Muse Voice Transcribe hears it, Muse Spark fills the record, and anything I don't say stays marked missing." | A spoken note fills the record |
| fieldnote | 1:54-2:23 | Hunter's own note plays; the camera moves down the fields it filled | "Sample note. Pat Miller, licence MT4412. Sprayed today, Tordon 22K by drone on leafy spurge, one quart per acre, ten gallons. Nine fifteen to ten forty, wind five from the west, sixty-two degrees." | Hunter's voice, heard by Muse Voice Transcribe |
| close | 2:23-2:31 | End card | "The applicator still decides. ClearSwath: find the weeds, read the label, spray only where both say yes." | Find the weeds. Read the label. Spray only where both say yes. |

Words to avoid on screen and in VO: legal, compliant, safe, certified, AI-powered.

## Submission text (draft)

**Name:** ClearSwath

**One-liner:** Find the weeds. Read the label. Spray only where both say yes.

**Problem statement:** Build for Your World (a problem I know firsthand), with "gives a spray drone a new capability"
from Push the Frontier.

**Description:** On a 24.1-acre Montana block, ClearSwath marks 9.7 acres to spray: only where a drone weed map
found leafy spurge and no label rule holds the spot back. I grew up on a South Dakota farm, where every spray job
starts with a pesticide label: dozens of pages of setbacks, wind limits and rates that no sprayer reads for you.

Give it a field, the label PDF and a weed map. Muse Spark reads the label into rules, each carrying its exact
sentence; code checks that sentence is on the page and drops any rule whose quote isn't (the plan lists it as not
applied). Click any held-back spot on the map and it quotes the sentence and page behind it. Muse Wonder boxes tree
lines on the aerial photo for SAM 3.1 to outline (17% of trees found by SAM alone, 62-69% with Wonder, 20 test tiles,
three runs). A model trained on Meta's DINOv2 features, on Modal, maps the weeds (90% of held-out spurge plots
found, 10% of clean plots flagged). Out come a 1 m spot-spray map and DJI/GeoJSON/KML files that won't build below the label's minimum spray
volume. After the job, a spoken note goes through Muse Voice Transcribe and Muse Spark fills the application record,
marking anything unsaid as missing; in the video it's my own voice reading a made-up sample job. Live runs read labels with the open-weights Muse
Spark Open on Baseten.

The decision (No conflicts in checked rules, Adjust, Do not spray) always comes from tested geometry code, never a
model, and the applicator still decides. The demos are saved real runs, recomputed in code when you change anything;
the DJI file is a planning file, not flight-tested. Everything was built during the event; third-party parts are
listed in the README.

## X post (draft)

> 24 acres of rangeland. The weed map marks 9.7 to spray, and keeps off the creek.
>
> ClearSwath reads the pesticide label, finds the weeds and the tree lines, and plans spraying only where both say
> yes. Muse Spark, Muse Wonder, SAM 3.1 and DINOv2 read and see; tested code plans.
>
> What would you want it to check next?

Self-reply: the live link, the repo, and the video.
