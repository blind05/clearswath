# Final changelog (Oct 29 to Nov 3, 2026)

What changed in the last stretch, with the commits that hold it.

- **Meta models doing visible work.** Muse Wonder boxes tree lines and woods on the aerial photo and SAM 3.1 outlines
  them; SAM's own text prompts find buildings and water (2c6c3d6, 22045ef). Measured on 20 NAIP tiles against ESA
  WorldCover and Microsoft footprints: trees found per tile rise from 17% (SAM alone) to 62% (24f8157).
- **Water the photo shows but the national map lacks** is "possible water": it never changes the map, and the plan
  can't be a clean pass until someone checks it (2c6c3d6).
- **Labels:** both demo labels read by Muse Spark 1.3; live runs read with Muse Spark Open on Baseten, falling back to
  Spark 1.3; an empty read is asked again and never cached (29a95cb, 6fc8c45). Three-way eval, 3 runs per label
  (247b31b; answer keys unreviewed).
- **UI:** rebuilt in React on Meta's Astryx design system with StyleX, MapLibre and Terra Draw; ink focus ring, tab
  roles; the first view now opens on a one-click Montana example with the setup form folded.
- **Hosting:** live on Render's free plan; each demo plan is computed once (Montana: 5 s and 440 MB per click before,
  0.2 s after), demo choices are bounded, and cache hits never wait behind a computation (31b0cfe, fe8a8cd).
- **Copy:** the weed map, not the label, marks the 9.7 acres; "No conflicts in checked rules", never "safe" or
  "legal"; the DJI file is a planning file, not flight-tested.
- **Evidence on the map:** click a held-back spot to see the label sentence and page behind it; rules whose quote
  isn't on the page are listed as not applied (95f0478 and the commit before it).
- **Scout spread:** three separate Wonder runs per tile give 62-69% of trees found (7b9e176).
- **Video:** recorded from the real app (`scripts/record_demo.py`), cut to the script (`scripts/cut_video.py`), with
  original music, sound cues, synthetic narration (Kokoro-82M, disclosed) and subtitles (ec131c7).
