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
| Voice record | Record in the page or upload any audio; checked end to end on a person's speech |

## Video

See `VIDEO_QA.md`. 2:31, 1920x1080 H.264, AAC 48 kHz, -16.3 LUFS, subtitles embedded and as SRT. Narration is a
disclosed synthetic voice (Kokoro-82M); 97% of script words heard back by Muse Voice Transcribe. Not yet listened to
by a person.

## Remaining, in order

1. Hunter listens to the video once; optionally replaces the synthetic narration with his own take.
2. Upload the final MP4 (YouTube unlisted or similar) and open the link in a private window.
3. Uptime ping on `/api/health` every 10 minutes through Nov 8: `.github/workflows/keepalive.yml` (GitHub may
   delay scheduled runs; delete the file after judging).
4. ~~Run the `/api/whoami` checks~~ Done 2026-11-03: the limit read Render's internal proxy, so every visitor
   shared one budget and one wrong-code lockout. Now reads `CF-Connecting-IP` (451cab4); verified live: whoami
   returns the visitor's own address.
5. Fill the Cerebral Valley form from `docs/video/SCRIPT.md` (name, one-liner, problem statement, description),
   then tag the release.

## Judge pass (2026-11-03, one self-review against the brief's weights, not organizer scores)

Weights from the brief (Impact 30, Meta tooling 25, Technical 20, Demo 25); not yet checked against the
participant guide.

| Category | Estimate | Why, skeptically | Top remaining issue |
|---|---|---|---|
| Impact | 7/10 | A real operator task (label -> lines on a field) with a usable output; framed as decision support, not approval | No user beyond the builder has tried it |
| Meta tooling | 7/10 | Spark 1.3 reads the label with quotes checked in code; Wonder + SAM 3.1 scout (measured over 3 runs); Spark agent replayed. DINOv2 is Meta open weights | Voice Transcribe not run on real speech; Spark Open reads a conditional buffer as unconditional |
| Technical | 8/10 | UTM buffering, quote verification, fail-closed warnings, 447 offline tests, spend cap, per-visitor limit now correct behind Cloudflare | Label accuracy unclaimed: answer keys unreviewed |
| Demo | 7/10 | Opens on the real map with 9.7 of 24.1 acres; click-for-reason; 2:31 | Synthetic narration; nobody has listened to it yet |

Weighted: about 7.2. Estimates from one reviewer who knows the code, so expect them to be generous.

- **Could disqualify:** a video link that doesn't open for an anonymous viewer, or missing form fields.
- **Why another team might win:** a live, unscripted demo, or real users. Here the judge sees saved runs.
- **What would move it:** a human narration take, reviewed answer keys (then label precision and recall can be
  claimed), and one real voice-note record.

## Meta credits used on 2026-11-03

| What | Where it ran | Cost |
|---|---|---|
| App calls (scout spread runs, narration check, voice probes, voice UI check) | `app/llm.py`, logged in `data/logs/spend.json` | $3.90 (local estimate from `spend.py` prices, TODO(verify)) |
| Muse Code review of the repo (5 roles; found the unchecked-source gap, one claim rejected) | `muse exec`, Muse Spark 1.3 | about $1.02 (794k input tokens, mostly cached; 5.4k output) |
| Muse Code: browser recorder and WAV converter (adopted after review) | `muse exec`, Muse Spark 1.3 | not in its log; see the Meta Usage dashboard |

Baseten was not used today. The provider dashboards are the source of truth; these are estimates.
