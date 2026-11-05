# Submission fields and launch posts (drafts for Hunter)

**Name:** ClearSwath
**One-liner:** Find the weeds. Read the label. Spray only where both say yes.
**Track:** Indie Developer. **Problem statement:** Build for Your World.

**Description (about 150 words):** ClearSwath turns a field outline, a pesticide label and a drone weed map into a spray
plan you can check. Muse Spark reads the label into rules, each carrying its exact sentence, and code drops any rule
whose sentence isn't on the page. Muse Wonder boxes the tree lines on the aerial photo and SAM 3.1 outlines them: on 20
test tiles that finds 62-69% of trees, against 17% for SAM alone. A DINOv2 model fine-tuned on Modal maps leafy spurge
on a Montana block (90% of held-out plots found, 40% of the block marked). Tested geometry makes the decision; click any
spot to see which label sentence holds it back. Live runs read labels with Muse Spark Open on Baseten. Outputs: spot-
spray map, planning files (DJI, not flight-tested; GeoJSON; KML) and a draft application record, which a note spoken
into the page fills through Muse Voice Transcribe. Demos are saved real runs.

**Links:** https://clearswath.onrender.com, https://github.com/blind05/clearswath, video: (Hunter's upload).

**X post:**
> 24 acres of Montana rangeland. The weed map marks 9.7 to spray, and keeps off the creek.
>
> ClearSwath reads the pesticide label, finds the weeds and the tree lines, and plans spraying only where both say yes.
> Click any held-back spot and it shows the label sentence behind it.
>
> What should it check next?

Attach `data/video/ClearSwath_teaser_square.mp4` (31 s, 1080x1080, captioned). First reply: the live link, the repo,
the full video.

**LinkedIn:** I built ClearSwath for the Meta hackathon. It reads a pesticide label with Muse Spark, finds tree lines on
aerial photos with Muse Wonder and SAM 3.1, maps leafy spurge with a DINOv2 model, and plans spray cells only where the
label's setbacks allow, with the quoted sentence behind each held-back acre. After the job, a spoken note fills the
application record through Muse Voice Transcribe, with anything unsaid marked missing. It's decision support: the applicator
still checks weather, licence and the field. Demo and code: (links).

**Don't claim:** that the label said 9.7 acres; that a plan is safe, legal or compliant; that the DJI file was flown;
label accuracy numbers (keys unreviewed); that the field note's applicator is real (it's a sample job, in Hunter's voice).

## Posting order (after the form is in; from the promotion team, 2026-11-03)

1. **X, right after submitting:** the square teaser and the X post above; first reply with the live link, repo and
   full video.
2. **Show HN, about 4 hours later:** "Show HN: ClearSwath – read the label, map the weeds, spray only where both say
   yes", linking the live site. First comment: the demos are saved real runs (free, no sign-up); live runs on your own
   field need an access code.
3. **LinkedIn, the next morning:** the LinkedIn text above, with the Montana plan screenshot.
4. **r/PrecisionAg, after asking the moderators:** text first, leading with the South Dakota click: 150 ft from water
   by air, 450 ft for ULV, page 14. No cross-posting.
5. **Meta developer Discord / event channel:** the X link and two lines.

Never: say a plan endorses spraying, that the DJI file was flown, a label-accuracy number, that the field note is a real
applicator's job, or that the label stated the acreage.
