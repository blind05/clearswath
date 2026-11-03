# Submission readiness (2026-11-03)

**Deadline:** Wednesday, November 4, 2026, 9:00 PM ET (dev.meta.ai/events/global-hackathon). Indie Developer track,
"judged on creativity, technical ambition, and whether it works."

**Verdict: CONDITIONAL GO.** The app, repo and a finished narrated, scored and subtitled video exist and are checked.
Conditions: one listen by Hunter, the video uploaded to a public link, and the submission form.

## What was tested

- `main` at the commit that adds this file, pushed to github.com/blind05/clearswath.
- `uv run pytest`: 446 passed (no test calls a network or a model).
- `npm run build` in `web-app/`: TypeScript check and build pass.
- `scripts/record_demo.py`: all 8 beats on the current build, at 1920x1080 in headless Chromium.
- Earlier browser QA (React build): 1440, 1280 and 390 px; drawing, errors, access-code dialog, record form,
  keyboard focus ring, tab roles.
- Live site, https://clearswath.onrender.com (Render free plan): health 200; both demos and the agent replay answer;
  live runs without the access code get a 401 with a plain message; page served with `Cache-Control: no-cache`.

## Real, replayed or limited

| Shown | What it is |
|---|---|
| Both demos (Montana, South Dakota) | Saved real runs: real label reads (Muse Spark 1.3), real scout runs (Muse Wonder + SAM 3.1), real bulletin and water lookups; the plan is recomputed by tested code on every choice |
| "Saved Muse Spark answer" | A replay of a real Muse Spark 1.3 run of 2026-10-29, labelled as such on screen |
| Live plan on your own field and label | Live and paid; needs the access code; 3 per address per day, $5 daily cap |
| Muse Spark Open on Baseten | Live label reader for live runs; not used by the demos (it reads Warrior's ULV-only buffer as unconditional) |
| Montana weed map | A real DINOv2-B model fine-tuned on Modal; 90% of held-out spurge plots found, 40% of the block sprayed |
| Hazard scout numbers | 20 NAIP tiles, WorldCover 2021 and Microsoft footprints as truth; per-tile mean, one run per tile; Wonder varies run to run |
| Label accuracy | Measured (`evals/results_labels.md`) but not claimed publicly: the answer keys are unreviewed |
| DJI prescription | A planning file; not flight-tested |
| Photo mode | Live on Modal; trained on cotton and sugar beet |
| Voice record | Works in code; not yet run on real speech |

## Video

See `VIDEO_QA.md`. 2:31, 1920x1080 H.264, AAC 48 kHz, -16.3 LUFS, subtitles embedded and as SRT. Narration is a
disclosed synthetic voice (Kokoro-82M); 97% of script words heard back by Muse Voice Transcribe. Not yet listened to
by a person.

## Remaining, in order

1. Hunter listens to the video once; optionally replaces the synthetic narration with his own take.
2. Upload the final MP4 (YouTube unlisted or similar) and open the link in a private window.
3. Uptime ping on `/api/health` every 10 minutes through Nov 8, so judges don't hit a sleeping server.
4. ~~Run the `/api/whoami` checks~~ Done 2026-11-03: the limit read Render's internal proxy, so every visitor
   shared one budget and one wrong-code lockout. Now reads `CF-Connecting-IP`; deploy, then re-run whoami
   (`address_used` should be your own address).
5. Fill the Cerebral Valley form from `docs/video/SCRIPT.md` (name, one-liner, problem statement, description),
   then tag the release.
