# ClearSwath: project context

The single source of truth for what we're building, why, and the constraints.
Every coding agent reads this before planning work. Rules for *how* to work live in AGENTS.md;
module inputs and outputs live in docs/CONTRACTS.md.

## 1. The hackathon

**Meta Global AI Developer Hackathon** (Meta + Cerebral Valley). Virtual, solo entry, **Indie Developer track**.

| Date (Central time) | What |
| --- | --- |
| Mon Oct 26 | Kickoff; setup |
| Oct 27 – Nov 4 | Building period |
| **Wed Nov 4, 8:00 PM CT (9 PM ET)** | **Submission deadline.** Target noon CT. Late = not considered |
| Nov 5 – 8 | Judging (keep the live site awake) |
| Mon Nov 9, 11:00 AM CT | Closing ceremony; top 5 per track judged live from their videos |
| Nov 9 – 16 | Community vote |

**Rules that shape the code**
- Repository must be **public**.
- **New work only:** everything shown must be built during the event, and the submission must make that clear. Dated commits are the proof.
- Must meaningfully use **Meta Model API and/or Meta open-weight models** (Stage One pass/fail).
- Banned: medical advice, basic RAG, simple image analyzers, education chatbots, job screeners, nutrition coaches, personality analyzers, sports coaches, anything political or war-related, and anything using code, data or assets we don't have rights to.
- Submission needs: a **3-minute demo video**, the public repo, a **live product**, and all contributors.

**Scoring** (after the pass/fail theme check): equal weight on
1. **Impact**
2. **Use of Meta AI tooling**
3. **Technical depth and execution**
4. **Demo quality**

**Bonus prizes we target**
- Best Build on Meta Open Weight Models ($10k): Muse Spark Open on Baseten.
- Best Agentic Use-Case ($5k): a verifiable tool-calling agent.
- Most Viral ($20k): the demo video posted natively on X; engagement counts through Nov 8.
- Community Vote ($10k).

## 2. The product

**One-liner:** Snap a pesticide label, outline a field, and get a legal spray zone in two minutes.

**Problem.** Before every spray job, an applicator must turn the pesticide label and EPA's
endangered-species bulletins (Bulletins Live! Two) into a legal place to spray: read buffer rules,
check restricted areas for that place and month, measure distances to water, buildings and habitat,
then keep application records (plus monthly FAA Part 137 logs for spray drones). Today this means
PDFs, government map sites and manual calculators.

**Who it's for.** Every applicator whose label points to Bulletins Live! Two: farmers spraying
their own ground, co-ops, custom applicators and spray-drone operators. The drone is the demo
hook; ground sprayers are the larger market. FAA-certified spray-drone operators grew about 58%
in a year.

**Founder story (use in the pitch).** Hunter comes from a South Dakota farm family, spent a year
at SDSU, interned at USGS EROS (geospatial), and builds multi-agent systems professionally.
Family farm data is NOT used unless the family explicitly agrees; the demo uses a public field.

**Themes.** "Build for Your World" (a problem he knows firsthand) and "Push the Frontier"
(models controlling a physical system).

**Why it can win.** Uses four Meta models for jobs only they can do; very few entrants will build
it; the decision is verifiable; the demo is visual (red no-spray buffers, a green legal zone).

## 3. The flow

1. **Label in** (PDF or phone photo). Muse Spark extracts every rule that changes where, when
   or how the product may be applied, each with a word-for-word quote and page. Code drops any rule
   whose quote isn't in the label text. Photo-read rules require user confirmation.
2. **Field in.** User draws the field on a map. App fetches free USDA NAIP aerial imagery
   (Microsoft Planetary Computer) and SAM 3.1 outlines water, buildings and tree lines.
   USGS NHD mapped water is the fallback and the accuracy yardstick.
3. **Bulletin check.** Cached Bulletins Live! Two limitations for the demo county and month
   (BLT has no public API; we say so).
4. **Spray zone out.** Tested code (no model) buffers every hazard in a UTM projection and returns
   GO / ADJUST / NO-GO, sprayable acres, cited reasons and a KML for a drone planner or sprayer.
5. **Record out.** Applicator's voice note: Muse Voice Transcribe, then Muse Spark fills the
   application record and flags anything not said. Drones also get a Part 137 log row.

A Muse Spark agent orchestrates the tools and explains the decision, citing a source for every
reason. A fixed pipeline runs the same steps without the agent as a safety net.

## 4. Meta models and endpoints

| Model | Where | ID | Job |
| --- | --- | --- | --- |
| Muse Spark 1.3 | Meta Model API, `https://api.meta.ai/v1`, key `MODEL_API_KEY` | `muse-spark-1.3` | Label reading (structured output), agent (tool calling), record filling |
| Muse Spark Open | Baseten, `https://inference.baseten.co/v1`, key `BASETEN_API_KEY` | `meta-models/muse-spark-open-1026` | Switchable provider for the label reader and agent; compared in evals |
| SAM 3.1 | Meta Model API, Responses API | `sam-3.1` | Water, buildings, tree lines from aerial imagery |
| Muse Voice Transcribe | Meta Model API, `POST /v1/asr/transcribe` | `muse-voice-transcribe-1.0` | Voice notes and video captions |
| Muse Code | coding agent | n/a | Used for a few Meta-specific tasks while building |

**Verified API facts**
- The OpenAI SDK works with both base URLs; pass `api_key` explicitly (it won't read `MODEL_API_KEY` itself).
- **SAM 3.1:** `input_image` accepts a base64 data URL; one noun phrase per request (lists return
  nothing); non-streaming works; `metadata={"include_confidence": "true"}` adds confidence.
  Output is special-token text: parse with the `meta-sam-parser` package
  (`image_segmentation_format`, `decode_mask_to_raster`). Each mask covers only its box; paste
  it at `rec.bounds.top/left`.
- **Muse Voice Transcribe (file):** multipart with two parts: `request` (JSON: `mode`, `model`,
  `audioEncoding: "WAV"`, optional `keywords`) and `audio` (mono 16-bit PCM WAV, 16 or 24 kHz,
  10 min or less, 32 MB or less). Response text is in `transcript`; `turns` have `startMs/endMs`
  in ENDPOINTING mode.
- **Muse Spark Open on Baseten:** no structured outputs, but tool calling works, so force a
  single tool call whose parameters are the JSON schema. Retry 429s with backoff, about 60
  requests per minute.

**Budgets:** $150 Meta credits (spend limit set) and $100 Baseten. Cache every model result.

## 5. Architecture principles (non-negotiable)

1. **The decision comes from code.** `buffers.plan` sets GO / ADJUST / NO-GO. Model text never overrides it.
2. **Every model output is checked:** quotes verified against label text; SAM water compared with
   USGS; missing record fields recomputed in code; agent claims must cite tool results.
3. **No model calls in `app/buffers.py`.** Buffer in a UTM CRS (`estimate_utm_crs`), never degrees.
4. **A fixed pipeline backs up the agent.**
5. **Demo mode always works:** a real, cached run served by `/api/demo`.
6. **Decision support only:** the applicator remains responsible; the UI says so.

Stack: Python 3.12, uv, FastAPI, React + MapLibre + Terra Draw (Astryx, StyleX; USGS imagery tiles), geopandas,
shapely, rasterio, pyproj, pystac-client, planetary-computer, PyMuPDF, simplekml,
meta-sam-parser, pytest. Deployed on Render via Docker. Video tooling (Playwright, Kokoro,
Remotion) stays out of the app's runtime dependencies.

## 6. Build plan and status

Update the Status column as work lands.

| Day | Goal | Status |
| --- | --- | --- |
| Mon Oct 26 | Setup; `llm.py` + smoke test; imagery; SAM + go/no-go test | Done in code (eef7f5e, 39c2fc3, c514b76, d12290a, 4dc0467). Smoke test passes live (models, chat, json_schema, tools, SAM, voice) |
| Tue Oct 27 | Label reader + quote verification + answer-key check | Reader + quote check done (a0b7aaf); reads cached. Warrior II answer key + `scripts/eval_labels.py` drafted (key not yet reviewed by Hunter). Rule conditions extracted; conditional buffers and photo-read rules applied by default and untickable by the user (refused for anything else) |
| Wed Oct 28 | `find_hazards` (SAM + USGS fallback + cache); Muse Spark Open provider | `find_hazards` done (20dc032, a77ec84). Baseten provider built for the label reader and agent (`chat_json` via a forced tool call); not yet run live (needs `BASETEN_API_KEY`). v2 Gate 3 (weeds): SAM 3.1 alone fails on CoFly; DINOv3 head passes 5-fold (95.9% weed hit, 37.9% sprayed at 0.25 m; 0610358, 69f67c0). PhenoBench by flight date with 50 local labelled tiles: passes all 3 dates at 0.1 m (seedlings 97.9% hit, 18.2% sprayed; 4fa5d36). Demo moved to Montana rangeland (MPG Ranch leafy spurge orthomosaic, CC BY 4.0) with Tordon 22K (answer key d895fb0, unreviewed) and Montana ARM 4.10.207 record fields (15e0eb0). Spurge probe (DINOv2-B, 0.4 m) tied the dataset paper's 85%; fine-tuning the last 2 blocks lifts held-out AUC from 0.88 to 0.95 (a965333), and the Montana map at 85% catch now finds 90% of held-out spurge plots and sprays 40% of the block (7659dfb). Live photo mode on Modal (c390664); Spark Open as a patch reviewer tested and dropped, 52% agreement (5c76d17). Drift buffers toward unmanaged land, managed-land marking and wind (9be52d9, 466925c); runoff points force ADJUST (89f3752); $5/day spend cap (8fd6769). Spot-spray grid in the plan (eb50c26, 51d65ee), DJI/GeoJSON/KML exports (5058451; DJI layout TODO(verify)), wording rule enforced (954fe31). Montana demo is the default "Try demo" (4258e51), pinned by `tests/test_e2e.py` |
| Thu Oct 29 | Buffer engine + distance tests + KML | Done (4dc0467, KML in a17fe5a) |
| Fri Oct 30 | Bulletin check, pipeline, agent | Done (c44426c, 1dd8744, d1ffaa6, 4912ccd, ca77b87). BLT queried live, not cached; agent citation check not built |
| Sat Oct 31 | Voice records, demo data, demo cache, e2e test, Playwright recorder | Records done (e859490, be4a4fa); WAV-only transcribe this session. Demo field (eastern SD, public NAIP; mistake + corrected outlines) and offline demo cache done; drone story verified in the browser (ADJUST -> untick ULV -> corrected GO). Offline e2e test pins the demo story (`tests/test_e2e.py`). Part 137 row done (14 CFR 137.71 items, commercial operators; verified live). Playwright recorder done: 8 beats to `data/video/`, offline, from the cached demos (b9c183b) |
| Sun Nov 1 | Web app, polish, deploy to Render | Page rebuilt in React on the `ui-react` branch: MapLibre, Terra Draw, Astryx themed from DESIGN.md, StyleX (964e50d, a9a3ccf). Docker builds it into `web/dist` (eaafcc9); tab roles, ink focus ring, dialog fixed (074043e); the page is revalidated on every load (180e811). Checked in the browser at 1440/1280/390: recorder beats, drawing field and managed land, errors, access-code dialog, record form. Not yet: a live photo run, merge to main, Render deploy |
| Mon Nov 2 | Evals (both providers), prompt tuning. **Feature freeze tonight** | |
| Tue Nov 3 | README, video pipeline, record and edit the video | |
| Wed Nov 4 | Submit by noon CT; post the video on X; submit the X link | |

**Cut order if behind:** weather check, photo labels, live agent (fall back to pipeline).
Never cut tests, the demo cache, or video time.

## 7. Demo story (the video follows this)

1. Label photo: rules appear with quoted lines; user confirms.
2. **Deliberate mistake:** field drawn up to the creek. Result: ADJUST, acres removed, buffer rule quoted.
3. Red buffers along the creek, SAM's blue water outline, the farmstead.
4. Corrected field: green zone, acres, KML download.
5. "Agent steps" shows every tool call.
6. Voice note: the record fills; "applicator missing" shown in yellow.
7. Results card: label accuracy, water recall vs USGS, seconds per field, hosted vs open model.

## 8. Evaluation (numbers for the README and video)

Label rule recall and precision against hand-written answer keys (both providers); SAM water
recall vs USGS within 300 m; buffer correctness (should be 100%); seconds per job (cached and
uncached). Report real numbers only.

## 9. Open risks

- Eligibility: cleared with Cerebral Valley on 2026-10-28.
- SAM may miss small creeks: the USGS fallback covers this.
- BLT data is cached for one county.
- Render's free tier (512 MB) may be too small: use the Starter plan for judging week or rely on the demo cache.

## 10. What not to do

Don't expand scope beyond one state and one or two labels. Don't add features after the freeze.
Don't use family or employer data, code, accounts or devices. Don't claim numbers we didn't measure.
Don't let a model compute distances, areas or the decision.