# Research for the final stretch

Collected 2026-10-27 for later sessions. Third-party tools are leads, not endorsements: check each repo
and license before installing anything, and ask before adding a dependency (AGENTS.md).

## UI that doesn't look AI-generated

What the sources agree on:
- **Commit design tokens first** (CSS variables for colour, spacing, radius, type scale) and a fixed
  component list, then build screens from them. Agents reuse whatever tokens they find in the CSS.
- **One accent colour**, neutral surfaces; no decorative gradients, glassmorphism or hero sections in a tool.
- Avoid the default fonts every generated UI uses (Inter, Roboto, Arial, system-ui).
- Polish is many small details: text wrapping, nested border radii, shadows instead of borders.

Leads:
- The `frontend-design` skill already available in Claude Code (aesthetic direction, typography, no templated defaults).
- [avoid-ai-design](https://skills.cat/skills/funboy322/avoid-ai-design) (audits and rewrites "AI-looking" UI);
  [design-anti-patterns](https://tessl.io/registry/skills/github/Jamie-BitFlight/claude_skills/design-anti-patterns/review)
  (Linear/Raycast/Stripe/GitHub constraints); [Hallmark (Nutlope)](https://instagit.com/Nutlope/hallmark/what-are-the-design-principles-behind-hallmark-ai.md);
  [13Labs guide](https://www.13labs.au/guides/ai-ui-that-doesnt-look-ai-generated).

## Demo video

- Pipeline in the guide (Playwright -> voiceover -> captions -> Remotion) still looks right.
- [OpenScreen](https://docsearch.algolia.com/mcp/docs/repo/siddharthvaddem/openscreen) (MIT): native screen recorder with auto-zoom and cursor smoothing.
- [OpenMontage playwright-recording skill](https://skillselion.com/skills/calesthio/openmontage/playwright-recording)
  (AGPL-3.0: use as a tool, don't copy its code into this repo): Playwright demos with an injected cursor, output for Remotion.
- [claude-code-video-toolkit](https://smithery.ai/skills/digitalsamba/playwright-recording) (MIT, named in the guide).
- Testreel (npm; only a community post found, verify first): Playwright/YAML scripts to demo videos with cursor and click ripples.
- Structure from hackathon guides ([reskilll](https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/),
  [hackathon.com](https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know),
  [five-time winner](https://sustained.substack.com/p/lessons-from-winning-five-hackathons)): problem in ~20 s,
  product in action by ~0:40, demo is most of the time, then impact; realistic data; no terminal or code; don't
  show half-built features; the video is all many judges will see.
- Past Meta hackathon winners to study: Llama Impact London winner Guardian (NHS A&E triage,
  [Meta announcement](https://about.fb.com/news/2024/11/metas-llama-impact-hackathon-pioneering-ai-solutions-for-public-good/?noamp=mobile));
  [SF recap](https://lablab.ai/blog/llama-impact-hackathon-sf-summary); [Pan-LATAM recap](https://lablab.ai/blog/llama-impact-pan-latam-hack-summary)
  (winner: Tachiwin indigenous-language translator). Their submission pages on lablab.ai link the demo videos.

## README

- [awesome-readme](https://best-of-web.builder.io/library/matiassingers/awesome-readme) (annotated examples:
  logo, demo GIF up top, clear one-liner, install steps), [standard-readme](https://best-of-web.builder.io/library/RichardLitt/standard-readme),
  [art-of-readme](https://best-of-web.builder.io/library/hackergrrl/art-of-readme), [Best-README-Template](https://github.com/d4interactive/Best-README-Template).
- For a hackathon: one-liner, demo GIF, video and live links, how it works, Meta models used, real eval numbers,
  "built during the event", data sources and licences, run-it commands, limits (matches the guide's Prompt 14).

## Meta Model API

- Official cookbook: [meta-models/meta-model-cookbook](https://github.com/meta-models/meta-model-cookbook) (MIT,
  65 recipes; docs mirror at [dev.meta.ai cookbook](https://dev.meta.ai/docs/getting-started/cookbook)). Worth reading:
  - `01_api_fundamentals/04` structured output and `/09` error handling (jittered backoff, no retry on client errors).
  - `01_api_fundamentals/05` **prompt caching**: the label prompt is a stable prefix, so repeat reads could cost less.
  - `07_sam/01` SAM API basics with the `meta-sam` package: compare with our hand-built Responses calls.
  - `06_muse_voice/01` speech to text (HTTP, streaming, diarization).
  - `04_muse_code/07` goal tracking with a judge and `/06` subagent fan-out: patterns for a review council.
- Launch post: [Build with Muse Spark](https://developer.meta.com/ai/resources/blog/build-with-muse-spark/) (note model
  versions differ between pages; use the IDs `scripts/smoke.py` confirms).

## "Train a model to decrease spraying" (assessment, not a plan)

- Spot spraying cuts herbicide use: independent trials report about 23-35% (35% average over 25 ha of sugarcane, up to
  65% in low-weed strips; [JCU trial](https://researchonline.jcu.edu.au/89739/1/89739.pdf),
  [Florida tomato trial](https://specialtycropgrower.com/precision-sprayer-can-reduce-herbicide-use/)); vendors claim
  ~77-78% ([Greeneye](https://futurefarming.com/crop-solutions/weed-pest-control/ai-precision-spraying-technology-to-cut-herbicide-use-by-78),
  [See & Spray via MSU Extension](https://extension.msstate.edu/publications/see-spray-technology?page=1)).
- Weed detection needs close-range imagery (cm per pixel); NAIP is 0.6 m per pixel and can't see weeds. It also needs
  labelled training data, and accuracy drops when weeds and crop look alike or are small
  ([2026 review](https://reference-global.com/download/article/10.2478/agriceng-2026-0001.pdf)).
- Conclusion: not feasible to do well in this event; it also breaks PROJECT_CONTEXT section 10 (scope) and the Nov 2
  freeze. ClearSwath's honest reduction story is different: it keeps pesticide off water, homes and habitat, and its
  results can say how many acres a correct buffer kept unsprayed. Spot-spray zones from drone imagery is a credible
  "what's next" line for the video and README.
