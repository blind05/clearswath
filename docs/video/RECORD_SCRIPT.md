# Narration to record (Hunter)

15 short takes, one per scene of the film (cut E, `docs/video/cuts/E.md`), about two minutes in all. Record each as its
own file, `shot1` ... `shot15` (m4a or wav), into `data/video/hunter/`. Speak at your normal pace; each scene stretches to
fit your take, so you never have to hit a time. Every number is one the film and README already use.

**shot14 is the voice note itself.** It goes through the app for real: Muse Voice Transcribe hears it and Muse Spark
fills the Montana demo's record from it (`scripts/use_note.py`), and the film plays it as you said it. Say it like a
quick note after a job, not like narration. "Pat Miller" is a made-up applicator, and "Sample note" up front says so.

**How:** a quiet room, door shut, fan off. A USB mic, or your phone about 20 cm from your mouth. Say each line once,
cleanly; if you stumble, start that line again in the same file and tell me. Leave a second of quiet before and after.
Say "24.1" as "twenty-four point one" and "18.7" as "eighteen point seven".

| File | Scene | Say |
|---|---|---|
| shot1 | Montana drone map, spray cells, the map alone | Spray 9.7 acres, not all 24.1. ClearSwath finds the weeds and reads the label, so you spray only where both say yes. |
| shot2 | Tordon 22K label pages | I grew up on a South Dakota farm. Every spray job starts with a label like this one: 30 pages, and the label is the law. Drones can spray single weed patches now, but they can't read it. |
| shot3 | South Dakota field to the creek; the camera moves to the decision | So I built ClearSwath, on Meta's models, to read it. This South Dakota field runs right up to a creek. The answer: Adjust, 11.1 acres held back. |
| shot4 | The cursor glides to the strip; click; the card | Click the held-back strip, and it quotes the label, page 14: do not apply within 150 feet of aquatic habitats by air, or 450 feet for ultra-low-volume. |
| shot5 | The Warrior II PDF, page 14, both sentences highlighted | The same sentences, word for word, in the PDF. |
| shot6 | The conditional rules; ULV unticked | Not spraying ultra-low-volume? Untick it, and only 1.6 acres stay held back. |
| shot7 | The corrected outline | Redraw the field clear of the creek, and all 31.2 acres show no conflicts in the checked rules. |
| shot8 | Montana spray cells, close | The weed map is a model I trained on Meta's DINOv2. On plots it had never seen, it found 90 percent of spurge plots, and flagged 10 percent of clean ones. |
| shot9 | Montana decision, then Why and Muse Spark's answer | Muse Spark reads the label into rules, each with its exact sentence. Live runs use the open-weights Muse Spark Open, on Baseten. |
| shot10 | Rules not applied | If the sentence isn't on the page, the rule isn't used. And the decision always comes from tested code. |
| shot11 | SAM alone, then Muse Wonder and SAM | On 20 test tiles, SAM 3.1 alone found 17 percent of trees. With Muse Wonder finding them first, 62 to 69 percent, across three runs. |
| shot12 | Spray volume checked, files | The drone file won't build below the label's 18.7 liters per hectare. It hasn't been flown yet. |
| shot13 | The record form: "Record a note" | After the job, I just talk. Muse Voice Transcribe hears it, Muse Spark fills the record, and anything I don't say stays marked missing. |
| shot14 | Hunter's own note plays; the camera moves down the fields it filled | **Your field note, said like you would after a job:** Sample note. Pat Miller, licence MT4412. Sprayed today, Tordon 22K by drone on leafy spurge, one quart per acre, ten gallons. Nine fifteen to ten forty, wind five from the west, sixty-two degrees. |
| shot15 | End card | The applicator still decides. ClearSwath: find the weeds, read the label, spray only where both say yes. |

When the files are in `data/video/hunter/`: `scripts/use_note.py data/video/hunter/shot14.m4a` fills the demo's record
from your note (a few cents of Meta credit), the screen is re-recorded so the page shows it, and the film is rebuilt to
your takes (`use_voice.py`, `cut_video.py`, `score_video.py`, `teaser_video.py`). The README and VIDEO_QA then drop
"synthetic narration".
