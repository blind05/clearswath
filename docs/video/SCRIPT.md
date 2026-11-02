# ClearSwath — final demo film treatment (production revision)

**Film:** 2:36 target; absolute ceiling 3:00. 1920×1080, 30 fps, actual app captures + clearly identified saved model runs.  
**Objective:** A judge understands the physical outcome in 7 seconds and can see genuine Meta technical depth by 60 seconds.  
**Editorial style:** Documentary-product-film, not an explainer slideshow. Clear, unhurried voice; quick purposeful cuts; restrained motion; tactile original synth soundtrack and subtle UI sounds.

> **Truth check (mandatory):** Current ClearSwath is a label-and-field **spot-spray planning prototype**, not a regulatory-change SaaS. Show working Montana/South Dakota workflows already in the repository. Do not add an invented Watch/Impact feature to the video. “9.7 acres” is the DINO weed-map result, **not a number prescribed by the pesticide label**.

## The 2:36 cut

| Timeline | Picture / real interaction | Voiceover (record naturally; edit for breath) | On-screen typography | Audio / edit |
|---|---|---|---|---|
| **0:00–0:07** | **Cold open.** Drone image fills screen. Magenta weed cells appear across Montana field; the water corridor remains excluded. Match-cut into map. | “Twenty-four acres of rangeland. Only 9.7 marked for spot treatment. Here's how ClearSwath made the plan.” | **24.1 acres → 9.7 spot-treated**; tiny “Demo / saved verified run” | Start with a clean single low hit, music enters quickly. No brand splash, no pre-roll. |
| **0:07–0:20** | Fast cuts: difficult pesticide label PDF, zoom to one excerpt; then zoom back to aerial imagery. | “A pesticide label is dozens of pages of conditions. Spraying a weed patch is easy. Working out exactly where you should hold back isn't.” | “The label becomes a spatial constraint.” | 2–3 purposeful cuts; quiet page-turn sound; music under speech. |
| **0:20–0:38** | Actual `Try the demo` interaction and resulting Montana `Adjust` decision; show exact excerpt in the `Why` panel; show area figures. | “Muse Spark extracts the rules and their exact citations. ClearSwath checks each quote against the source. Then tested geometry applies the conditions to the field.” | **Muse Spark → cited rules** / **Code → mapped result** | Show genuine screen capture with zoom. A soft UI tick on source reveal. |
| **0:38–0:58** | Comparison: `scout-sam-text-only.png` vs `scout-wonder-sam.png`; overlays of tree lines/woods. Return to real map hazard layer. | “SAM alone misses many tree lines from overhead. Muse Wonder locates candidate areas, then SAM 3.1 segments them. On twenty test tiles, tree-and-shrub recall rose from seventeen to sixty-two percent.” | “SAM only: 17%” → “Muse Wonder + SAM: 62%” and small “20-tile evaluation; imperfect reference data” | Reveal with cut/match dissolve, not spinning charts. A restrained rising texture. |
| **0:58–1:17** | Montana map closeup: DINO-derived magenta spot-spray cells and darker held-back cells. Aerial image stays sharp. | “For the weeds, I trained a model on Meta's DINOv2 features. On held-out survey plots, it found ninety percent of the leafy spurge while marking forty percent of this block.” | “90% held-out spurge plots found” / “40% block marked” | Beat drops slightly on map reveal. Preserve image detail; avoid huge captions. |
| **1:17–1:38** | South Dakota field to the creek; 150-foot buffer and exact quoted label line; crop to map, not the entire desktop. | “Now a different label and field. The creek lies inside the original outline. The label's aerial buffer holds back that strip—here's the precise sentence and map geometry.” | “150 ft aerial water setback” / “Label p. 14” | One clean wipe aligned to the creek; low muted caution cue. |
| **1:38–1:57** | Uncheck truly conditional ULV rule, then show corrected field and changed decision. Include on-screen note that operator confirms conditions. | “Some conditions apply only to particular equipment or application methods. Those rules remain on until the operator confirms otherwise. Adjust the field, rerun, inspect the result.” | “Review conditions. Recalculate. Preserve evidence.” | Allow three distinct interface clicks; one quiet click per accepted action. |
| **1:57–2:15** | Actual sprayer export, value check and one example output file; quick cut to `How it decided` agent tool trace. | “The result includes a spot-spray map and files for planning equipment. It also shows the tools Muse Spark called to explain the process. The model never makes the final geographic decision.” | “Plan → export → evidence” / “No model issues a clearance” | 2–3 quick close-ups; sound at export successful, not a cash-register chime. |
| **2:15–2:27** | Wide aerial image with map layers composited by the real app; one quick hero shot of `Adjust` and checked area totals. | “The goal isn't to trust a black box. It's to see the weeds, the label, the restrictions—and the source for every decision the software makes.” | “See what was checked. Know what wasn't.” | Music gains energy during this beat; VO remains first. |
| **2:27–2:36** | Clean end frame: ClearSwath wordmark and one retained field image. Actual URL and GitHub URL. | “Models read and see. Tested code plans. The applicator still decides. ClearSwath.” | **ClearSwath** / “Field-first spray planning” / `clearswath.onrender.com` | One final warm chord, short decaying tail. Hard out before 2:40. |

## Audio direction

- **Narration:** use a natural human performance, not synthetic tech-announcer delivery. Mic 15–20 cm away; capture a few complete takes in a quiet room; remove breaths selectively, not all of them. Primary voice intelligibility comes first.
- **Original soundtrack:** minimalist electronic/organic hybrid. At first 0–7s it's an intentional pulse; under the speaking portion it should be felt, not heard as the focus; raise it only in two short visual reveals (0:58 and 2:15) and the ending. Use only music you created or have documented sync rights to.
- **Sound effects:** limited to document reveal, two meaningful map updates, one accepted input, a soft export confirmation, and final tail. Don't put whooshes on every cut. Silence can emphasize the buffer finding.
- **Mix checks:** prioritize speech around −16 LUFS integrated (measured on the isolated speech), final stereo around −14 to −16 LUFS integrated, max true peak around −1 dBTP; these are practical targets, not pass/fail organizer requirements. Never clip, and verify on laptop speakers.
- **Captions:** burned-in for social cuts, clean subtitle track or tasteful burned-in for the primary submission. Check every agricultural term, registration number, and model name by hand. Maintain high contrast and keep text off the map evidence.
- **Pacing:** average cut 3–5 seconds outside explainable UI interactions; never cut an essential quote before the viewer can read it. No looping cursor, unnecessary loading animation, scrolling through 70 PDF pages, or 15-second logo intro.

## On-screen evidence / source of truth

- Montana: `docs/images/montana-plan.webp`, demo data from `data/demo/mt`, and `scripts/record_demo.py`’s Montana captures. The example percentages must match the locked demo and README on the recording date.
- Scout comparison: `docs/video/scout-sam-text-only.png`, `docs/video/scout-wonder-sam.png`; context and limitations from `evals/results_scout.md`.
- South Dakota: `docs/images/dakota-creek-buffer.webp`, `data/demo` cache, and the actual interactive flow.
- The DJI output is **not flight-tested**. Present it as a planning export, not an aircraft-approved prescription.
- A cached replay is a real **previously recorded** model run; say “saved run” and never imply live inference where the page is using a replay.

## Producer's workflow

1. Review `docs/STATUS.md` and the currently deployed build; resolve discrepancies before recording.
2. Run `scripts/record_demo.py` locally against the built app; save original raw footage and screenshots.
3. Record direct UI takes for interactions the current recorder misses (PDF/page excerpt, controlled conditional rule, export validation). Retain the unedited evidence.
4. Cut the picture **first**, approximately to the table's timings. Use hard cuts and only 1–2 masked, motivated transitions.
5. Record VO to the locked cut; edit the cadence for the timing above rather than stretching words unnaturally.
6. Mix original music and simple sound effects below VO. The separate audio mixing script can combine a locked picture cut and recorded voice.
7. Captions, proofread model names, crop to meaningful UI, review on mobile and desktop, verify the uploaded video link anonymously.
8. **Final QA:** duration <3:00; real/fixture status obvious; no fabricated outputs; actual project additions identifiable as hackathon-built; licensed music/images; no exposed access code; app and repo both available.

## Product UI quality gate (do not sabotage a working release)

Use `DESIGN.md` as design authority: IBM Plex, restrained label-excerpt typography, map as hero, magenta spray cells with safety-related layers in meaningful colors. The site should feel like purpose-built GIS software, **not a generic startup template**.

- The very first viewport should explain the problem and feature a one-click real demonstration; avoid a page of inputs with no context.
- Keep the current 400px evidence sidebar and large image/map workspace where it serves the flow; don't redesign everything into colorful cards.
- Make primary actions and status legible at 1440/1280/390 widths. Check hover, focus, busy, disabled, and failed API states.
- Show a real label quote with a real page number, and no “safe/legal/compliant” clearance wording.
- Review typography, basemap loading, no awkward whitespace, no overflow, no layout shift, no default-library-looking widgets, no accidental capitalized “AI PLATFORM” branding.
- Respect reduced-motion preferences in the app. Video-only cinematic effects need not appear in the product.
- Verify `npm run build`, local backend tests, and manual Playwright paths before merging changes. No automatic merge to main solely for appearance.

## Submission text (review and update from the live repo)

**Name:** ClearSwath  
**One-line:** Find the weeds. Read the label. Build a source-backed spray plan.

**Description:** ClearSwath turns a pesticide label, field outline, mapped hazards, and aerial weed imagery into a reviewable spot-spray plan. Muse Spark extracts quoted requirements; Muse Wonder and SAM 3.1 locate and segment candidate hazards; an adapted Meta DINOv2 model identifies weed patches. Deterministic geometry applies the mapped constraints, and the app shows evidence, application records, and planning exports. The working demo uses cached real model runs so judges can explore it instantly. This is decision support, not clearance to spray.

**Demo sources:** `https://clearswath.onrender.com` and `https://github.com/blind05/clearswath`.

> **For the editor:** The final video cannot be declared finished until actual voice, original/right-cleared music, picture editing, and sound mix are rendered, watched and verified. A storyboard is not a video.
