# ClearSwath demo video: script and shot list (draft for Hunter)

Target 2:45, under 3:00. Every shot is the real app or a real saved run; nothing is staged. "VO" is Hunter's
voiceover; "ON SCREEN" is the only text added in the edit. Takes come from `scripts/record_demo.py` (1920x1080).

| Time | Shot | VO | ON SCREEN |
|---|---|---|---|
| 0:00-0:08 | Montana drone image; magenta spot-spray cells appear; the creek strip stays clear | "A drone is about to spray leafy spurge on 24 acres of Montana rangeland. ClearSwath says: spray 9.7 of them, and here is why." | 9.7 of 24.1 acres |
| 0:08-0:28 | Tordon 22K label PDF, pages scrolling | "I grew up on a farm in South Dakota. Every spray job starts with a label like this: a legal document, 70 pages of setbacks, wind limits and rates. Drones can now spray single weed patches, but nothing reads the label for them." | A pesticide label is the law |
| 0:28-0:50 | Click "Try the demo"; the decision "Adjust" and the label sentence under "Why" | "ClearSwath reads the label with Muse Spark. Every rule it uses carries the exact sentence from the label, and code checks that sentence is really on the page. The decision itself never comes from a model: tested geometry makes it." | Muse Spark reads the label. Code decides. |
| 0:50-1:20 | `docs/video/scout-sam-text-only.png`, then `scout-wonder-sam.png` (South Dakota NAIP tile) | "Next, what the sprayer must keep away from. Asked for tree lines from the air, SAM 3.1 finds almost none. So Muse Wonder looks at the photo and draws a box around each one, and SAM outlines what's in the box. On 20 test tiles, that goes from 17 percent of trees found to 62." | SAM alone: 17% of trees. With Muse Wonder: 62%. |
| 1:20-1:45 | Zoom into the Montana spray cells (beat 3) | "The weeds come from a model I trained on Meta's DINOv2 features, on Modal GPUs. On survey plots it never saw, it finds 90 percent of the spurge, and sprays 40 percent of the block instead of all of it." | 90% of spurge found, 40% of the block sprayed |
| 1:45-2:00 | DJI spray volume field: 15 L/ha refused, 50 accepted (beat 5) | "Then the files for the drone. If I set a spray volume below the label's minimum, it refuses, and quotes the line that says why." | DJI, GeoJSON and KML files |
| 2:00-2:25 | South Dakota: field drawn to the creek, 150 ft setback quoted from page 14 (beat 6); untick ULV (7); corrected outline: "No conflicts in checked rules" (8) | "Here a field is drawn right up to a creek. The label says 150 feet from water by air, so that strip is held back. Some rules only apply in certain cases; they stay on until you say they don't. Pull the edge back, and the plan is clear." | 150 ft from water, page 14 |
| 2:25-2:40 | "How it decided" trace (beat 4) | "Muse Spark explains the plan and shows each tool it called. On live runs, the label is read with Muse Spark Open on Baseten, open weights, with hosted Spark as backup." | Muse Spark 1.3 · Muse Wonder · SAM 3.1 · DINOv2 · Muse Spark Open |
| 2:40-2:50 | End card | "Models read and see. Tested code decides. You still check the weather and your licence. ClearSwath." | clearswath.onrender.com · github.com/blind05/clearswath |

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
held-out plots found, 40% of the block sprayed). Live runs read labels with Muse Spark Open on Baseten. Tested
geometry, not a model, makes every decision. Built during the event: all of it; third-party parts are listed in the
README.

## X post (draft)

> This drone was about to spray 24 acres. The label said 9.7.
>
> ClearSwath reads the pesticide label, finds the weeds and the tree lines, and plans spraying only where both say
> yes. Muse Spark, Muse Wonder, SAM 3.1 and DINOv2, with tested code making the call.
>
> What would you want it to check next?

Self-reply: the live link, the repo, and the video.
