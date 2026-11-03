# Adversarial review (2026-11-03)

Independent reviews were run with Muse Code (Muse Spark 1.3, read-only, on Meta API credits), not Claude subagents.
Each got the same repo state and real screenshots or film frames; each finding was then checked against the code by
hand before anything changed. Scores are the reviewers' estimates, not organizer scores.

| Round | Reviewer | Input | Score | Cost |
|---|---|---|---|---|
| 1 | Five roles in one pass: judge, Meta AI engineer, geospatial QA, release, designer | Repo at 803cb7d, 3 screenshots | 6.25 | ~$1.02 |
| 2 | Film fact-checker | 2:48 cut: captions + 14 frames | 33 claims | ~$1.30 |
| 2 | Product designer, hackathon judge, accessibility | Live site, 7 screenshots (desktop + phone) | judge 6.4 | not logged |
| 3 | Final judge | Live site after the UI pass, README, film captions | 6.2 | not logged |

## What changed because of a review

- A failed aerial scout or an unavailable bulletin check could still give a clean GO; it now caps the plan at ADJUST
  (6e5949c).
- The film said the label is 70 pages (it is 30), that Muse Wonder boxes "each" tree line (62-69% recall), and did not
  say the agent answer is saved; the roster caption missed Muse Voice Transcribe and ran off the frame (aa535e9,
  c0292aa).
- The landing opened on a continent; the draw tools covered the result; "1 rule(s)"; two near-identical South Dakota
  quotes without their conditions; the spot-spray acres were buried; small tap targets and a focus ring lost over
  imagery (ef52092..99156f1).
- Found while checking the designer's phone screenshots: phones opened every page scrolled to the bottom, because the
  phone layout was a `column-reverse` scroller (ef52092).

## Rejected, with the reason

- "Buffer touches under 0.01 ac get sprayed": wrong; the map always subtracts the whole zone (`app/buffers.py:161`).
- Rounded acres as "overstated": 9.7 of 24.1 is the page's own rounding of 9.73 of 24.07.
- "The label is the law" unsupported: it is EPA's own phrase.
- Dropping model names from the hazard lines: for judges they are the evidence of Meta model use.
- Hatched fills for colour-blind readers: worth doing, but it changes the map paint and the film on the last day.
- Remove the photo tab, or the live agent: they work and are labelled; removing them buys nothing by the deadline.

## Still open (only Hunter can close these)

- A person's narration instead of the disclosed synthetic voice (all judge passes rank it first).
- Reviewed label answer keys, so the measured label precision and recall can be claimed.
- The video uploaded, its link opened logged-out, the form filled.
