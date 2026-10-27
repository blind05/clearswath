# ClearSwath security review (Phase 1, read-only)

Date: 2026-10-27. Scope: the repo at `10edb81`..`b2765a7` plus working tree, the Docker image built from it, and the
app run locally (the live Render site does not exist yet). Threat model: public GitHub repo; public site where anyone
can upload files and trigger paid Meta Model API / Baseten calls during judging week (Nov 4-9).

## Summary

1. **No secrets leaked**: gitleaks finds nothing in 59 commits; keys live only in the gitignored `.env`, are read only
   in `app/llm.py`, never reach the browser, logs or the Docker image.
2. **The real risk is cost abuse**: every paid endpoint is open to anyone, with no access code, rate limit, budget,
   kill switch, upload size limit or field-size limit. One script could drain the Meta/Baseten credit and break the
   site for judges (Critical).
3. **Input handling is solid**: path traversal, XSS, CORS, shell and eval checks all pass; the demo is cached and free.
4. **Prompt injection is contained**: label quotes are verified, agent tools are fixed and argument-less, and the
   decision always comes from `buffers.plan`.
5. Smaller gaps: no EXIF stripping, no cleanup of run folders, missing timeouts on three outbound clients, an empty
   README (attribution), and an uncommitted `.claude/settings.json` change that drops two agent deny rules.

## Findings

| ID | Severity | Area | Where | Evidence | Fix |
|---|---|---|---|---|---|
| C1 | **Critical** | Cost abuse | `app/api.py:80-127` (`/api/plan`, `/api/agent`, `/api/label`, `/api/record`) | `grep -rn -i "rate.?limit\|budget\|quota\|ACCESS_CODE\|Depends("` in `app/` -> no matches. Each cold plan = 5 SAM calls + a ~25k-token label read (measured); agent adds 3+ Spark calls. Anyone can loop them. | Access code (`ACCESS_CODE` env, FastAPI dependency) on the four paid endpoints; demo stays open. Per-IP rate limit (e.g. 5 live runs/hour) and a global daily cap on paid calls (counter in `llm.log_call`). |
| H1 | **High** | Cost/abuse | none | No env switch to stop spending; the only stop is suspending the Render service, which also kills the demo. | `CLEARSWATH_LIVE_MODE=off` -> paid endpoints return 503 "live mode is off, try the demo"; read on every request, so flipping it in Render needs no code change. |
| H2 | **High** | Uploads | `app/api.py:42-45` (`_save`) | `path.write_bytes(upload.file.read())` reads the whole upload into memory; no size limit anywhere (`grep max_bytes\|MAX_UPLOAD\|content.length` -> none). No PDF page cap (`grep page_count\|MAX_PAGES` -> none): a 2,000-page PDF becomes one huge paid prompt. Container has 512 MB. | Stream uploads with a byte cap (labels/GeoJSON 10 MB, audio 32 MB), reject PDFs over ~80 pages before the model call. |
| H3 | **High** | Input validation | `app/geo.py:17-26` (`load_field`) | Offline probe: a box over most of South Dakota was accepted as a **41,158,402-acre** field; a self-intersecting polygon and lon=500 were also accepted. Nothing stops imagery, 5 SAM calls, USGS and BLT queries on any of them. | Validate before any network call: valid polygon, lon -180..180 / lat -90..90 (ideally CONUS), area <= 640 ac, <= 2,000 vertices. |
| M1 | Medium | Cost abuse | `app/label_reader.py:112`, `app/segment.py` (cache key), `app/bulletins.py:47` | Caches key on raw file bytes; adding one space to the GeoJSON or one byte to the PDF is a new key and a new paid run. Amplifies C1. | Key caches on normalised content (e.g. geometry rounded to 1e-6, PDF text hash); mainly solved by C1/H1. |
| M2 | Medium | Uploads | `app/api.py:49-51,119-121` | Types checked by extension only (`grep %PDF\|magic\|RIFF` -> none). Any bytes named `.pdf` reach PyMuPDF and then the model. | Check magic bytes (`%PDF-`, PNG/JPEG/WebP signatures, `RIFF....WAVE`) before saving. |
| M3 | Medium | Disk | `app/api.py:77,84,105,153` | No cleanup of `data/runs` or `data/cache` (`grep rmtree\|unlink\|retention` -> none). The free, unauthenticated `/api/demo` writes a new run folder on every call. Locally `data/runs` already has 17 folders / 3.9 MB. | Delete run folders older than 24 h at startup and hourly; cap folder count. |
| M4 | Medium | Privacy | `app/llm.py:192-197`, `app/label_reader.py` (`_pages`) | Photo labels are stored and sent to Meta as raw bytes; no EXIF handling (`grep exif\|ImageOps` -> none), so phone GPS goes with them. | Re-encode photos with Pillow (already a dependency) without EXIF before saving and sending. |
| M5 | Medium | Availability | `app/llm.py:70`, `app/imagery.py:44,67,79` | OpenAI client uses the SDK default (600 s per attempt, x2-5 retries); `pystac_client.Client.open` and rasterio/GDAL reads have no timeout. A hung upstream holds worker threads. (BLT 30 s, USGS 120 s, ASR 120 s are set.) | `OpenAI(timeout=60)`; STAC client timeout; `GDAL_HTTP_TIMEOUT=60` and `GDAL_HTTP_MAX_RETRY` env. |
| M6 | Medium | Agent guardrails | `.claude/settings.json` (uncommitted) | `git diff .claude/settings.json` removes `"Bash(git rebase:*)"` and `"Bash(git commit --amend:*)"` from `deny`; AGENTS.md forbids both. | Restore the committed version (`git restore .claude/settings.json`) unless the change was deliberate. |
| L1 | Low | Uploads | `app/api.py:82-86` | Uploads are saved before month/method are validated, so invalid requests still write files. | Validate form fields first. |
| L2 | Low | Docs/licensing | `README.md` (0 lines) | No data attribution (USDA NAIP, USGS NHD + National Map imagery, EPA PPLS label, EPA BLT "informational"), no "built during the event" statement (a rule). | Write the README (planned for Tue Nov 3). |
| L3 | Low | Privacy | `docs/PROJECT_CONTEXT.md:171`, `:54` | Public doc names Hunter's employer and family background. | Hunter's call; remove the employer name if it shouldn't be public. |
| L4 | Low | GitHub | repo settings | `gh api repos/blind05/clearswath` -> `dependabot: disabled`; `branches/main/protection` -> `Branch not protected` (404). Secret scanning and push protection: **enabled**. | Enable Dependabot alerts; protect `main` against force-push and deletion (see manual steps). |
| L5 | Low | Agent guardrails | `.claude/settings.json` | `Read(./.env)` blocks the Read tool only, not shell reads like `cat .env`; `git commit --no-verify` is not denied (commits are on `ask`, so each needs approval). | Add `Bash(cat .env*)`, `Bash(git commit --no-verify:*)`, `Bash(git commit -n:*)` to `deny`. |
| L6 | Low | Logging | `app/api.py:36` | `log.exception` logs full exception text; a Pydantic error on a record can include fragments of model output from a voice transcript. Server log only, never sent to the browser. | Accept, or log only the exception type for record errors. |
| L7 | Low | Repo history | `git log --format='%an <%ae>'` | 4 early commits have a garbled author: `Hunter Hagedorn”git config user.email “dnilbyt@gmail.com <you@personal-email.com>`. Rewriting history is forbidden by AGENTS.md. | Accept (cosmetic; no extra data exposed). |

## Checks that passed

| Area | Check | Evidence |
|---|---|---|
| Secrets | No secrets in history | `gitleaks git . --redact --log-opts=--all` (v8.30.1): 59 commits, "no leaks found". Regex sweep of `git log -p --all` for key/Bearer/private-key/AKIA/ghp_ patterns: only the `.env.example` placeholders (`MODEL_API_KEY=past…`, `BASETEN_API_KEY=past…`). |
| Secrets | Keys only in `.env` | `gitleaks dir .`: 2 hits, both `.env` lines 2-3 (`generic-api-key`, redacted). `.env` is ignored (`.gitignore:1`) and never committed (`git log --all -- .env` -> empty). |
| Secrets | Placeholders only | `.env.example`: `paste-your-key-here`, `paste-your-baseten-key-here`, `LLM_PROVIDER=meta`. |
| Secrets | Keys never reach the browser | `grep -i "api_key\|MODEL_API\|BASETEN\|api.meta.ai\|baseten.co\|bearer" web/` -> none. Only `app/llm.py:47` reads keys; all model calls go through `app/llm.py`. |
| Secrets | Keys never logged | `data/logs/calls.jsonl`: 78 rows, fields `model, purpose, seconds, ts, usage` only, 0 key-like strings. Exceptions are logged server-side; httpx/OpenAI messages carry URLs and response bodies, not the `Authorization` header. |
| Secrets | Docker | `.dockerignore` excludes `.env`, `.git`, `data/cache`, `data/runs`, `data/logs` (`video/` doesn't exist). COPY lines copy only `pyproject.toml`, `uv.lock`, `app`, `web`, `data/demo`. Image env has no keys (`GPG_KEY` is the Python base image's public signing fingerprint); `find / -name .env` in the image -> none; `docker history` -> 0 key mentions. `render.yaml` declares keys with `sync: false`. |
| Cost | Repeat-charge caching | Label reads, hazards (incl. SAM) and BLT are cached on disk (`label_reader.py:112`, `segment.py`, `bulletins.py:47`); the demo is fully cached and makes no paid calls (`tests/test_e2e.py` blocks sockets). Bypassable, see M1. |
| Cost | Audio duration cap | `app/llm.py` `check_wav`: mono 16-bit WAV, 16/24 kHz, <= 10 min, <= 32 MB, checked before the ASR call (after the upload is read, see H2). |
| Input | Path traversal | Probed with TestClient: `/api/kml/..%2F..%2F.env`, `/api/kml/../../.env`, `/..%2F.env`, `/%2e%2e/%2e%2e/.env`, `/../app/llm.py`, `/web/../.env` -> 404; `/api/demo?field=../../.env` -> 422; `POST /api/record run_id=../../../etc` -> 404; upload filenames `../../evil.geojson` -> only the suffix is used, files are saved as fixed names under `data/runs/<uuid4>/`. Run IDs must match `^[0-9a-f]{32}$` before use (`api.py:114-116,173-175`). |
| Input | XSS | `web/index.html`: no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, Leaflet popups or tooltips. All DOM is built by `el()` (`createElement`, `append` of text, `setAttribute`), so labels, model output and transcripts are inserted as text. |
| Input | Errors | `_http_error` (`api.py:29-39`) returns only messages we wrote (missing key, no imagery, bad audio, refused untick) or a generic 422/502; details go to the server log (`tests/test_api.py` checks no leakage). No `debug=True`, no `--reload` in the Dockerfile. |
| Input | CORS | No `CORSMiddleware`: the browser's same-origin policy applies. |
| Input | Subprocess | No `subprocess`, `os.system`, `shell=True`, `eval`, `exec`, `pickle` or `yaml.load` in `app/`. ffmpeg is not used. |
| Model | Label text is data; quotes verified | Label pages go in the user message under a fixed system prompt (`label_reader.py`); every rule's quote must appear in the PDF text or it is dropped (`verify`), also when loaded from cache (`tests/test_pipeline.py::test_loaded_label_is_reverified`). Injected text can only affect the uploader's own result. |
| Model | Agent tools | `app/agent.py:19-27`: four fixed tools with no parameters (no shell, file write or arbitrary network); unknown tool names get an error reply; `MAX_STEPS = 8`; decision from `buffers.plan`; an answer naming a different status is replaced (`tests/test_agent.py`). |
| Model | No model output in code/SQL/paths | The one model value in a query, the EPA Reg. No., must match `^\s*(\d+-\d+)` before it enters the BLT `where` clause (`bulletins.py`, tested). No eval/exec/shell; no model value in a path. |
| Model | Structured output validated | `LabelRule`/`LabelRules`, `AppRecord`, `Part137` are Pydantic models; out-of-schema values are dropped or rejected (`tests/test_label_reader.py`). |
| Privacy | Demo data public | Demo field: public USDA NAIP + USGS NHD, rural eastern SD, no owner details; label from EPA PPLS. Logs hold no transcripts or uploads. |
| Supply chain | Known vulnerabilities | `uvx pip-audit -r <uv export --frozen --no-dev>` (87 pinned packages): "No known vulnerabilities found"; dev deps: same. |
| Supply chain | Pinning and sources | `uv.lock`: 92 packages, all from `https://pypi.org/simple`, none from git/URL/path. CDN scripts pinned (`leaflet@1.9.4`, `leaflet-draw@1.0.4`) with SRI hashes (`tests/test_api.py::test_page_pins_its_scripts`). |
| Supply chain | Dockerfile | `python:3.12-slim`, `uv sync --frozen --no-dev`, runs as user `clearswath` (`docker exec ... id -un` -> `clearswath`). |
| Repo | Agent config | No `.mcp.json`, no `.claude/settings.local.json`, no `bypassPermissions`; `git add`/`git commit` are `ask`; push and reset denied (see M6, L5). |
| Repo | Git hooks | `core.hooksPath = .githooks`; `pre-commit` (blocks `.env`, keys, failing tests) and `commit-msg` are executable; `git grep no-verify` -> none. |
| Repo | GitHub secret scanning | `secret_scanning: enabled`, `push_protection: enabled`. |

**N/A**: `web/app.js`, `label_id`, ffmpeg, NWS weather calls and `video/` (incl. `npm audit`) don't exist in this repo.

## Fix before going live (Critical / High)

1. **C1** Access code on paid endpoints + per-IP rate limit + global daily cap on paid calls.
2. **H1** `CLEARSWATH_LIVE_MODE=off` kill switch (demo keeps working).
3. **H2** Upload byte caps while reading; PDF page cap.
4. **H3** Field validation: valid polygon, coordinate bounds, <= 640 acres, vertex cap, before any network call.

## Fix this week (Medium / Low)

M2 magic bytes; M3 run-folder cleanup; M4 EXIF stripping; M5 timeouts; M6 restore agent deny rules; L1 validate
before saving; L2 README with attribution; L5 extra deny rules. M1 is mostly covered by C1/H1.

## Accepted risks

- **L6** exception text in the server log: server-only, short-lived on Render, useful for debugging during judging.
- **L7** garbled author on 4 commits: cosmetic; rewriting history is against the project rules.
- **Docker base images pinned by tag, not digest**: the slim tag and uv `0.12.15` are pinned; digest pinning adds
  churn for little gain over one week.
- **Git hooks live in local git config**: a fresh clone needs `git config core.hooksPath .githooks`; solo project.
- **Injected text in a label can colour the agent's wording** for that uploader's own result: decision, quotes and
  buffers are code-checked.
- **Bulletin data from BLT's informational map service**: the citation tells users to print the official Bulletin.

## Manual steps for Hunter

1. **Meta and Baseten budgets**: confirm the Meta spend limit is set low enough to survive abuse, and set a Baseten
   spend limit or alert. These cap the worst case even before C1 ships.
2. **Render**: create the service from `render.yaml`; paste `MODEL_API_KEY` and `BASETEN_API_KEY` in the dashboard;
   after C1/H1, also set `ACCESS_CODE` and `CLEARSWATH_LIVE_MODE`. Put the access code only in the private submission
   notes, never in the repo or video.
3. **GitHub**: Settings > Code security > enable **Dependabot alerts**; Settings > Branches > add a rule for `main`
   blocking force pushes and deletion. Keep secret scanning and push protection on.
4. **`.claude/settings.json`**: decide whether the removed rebase/amend deny rules were intentional (M6).
5. **Demo field**: confirm the field near 44.234 N, 96.92 W isn't family or a neighbour's land.
6. **Employer mention** (L3): decide whether the employer name should stay in the public `PROJECT_CONTEXT.md`.
7. **Eligibility**: the open question in PROJECT_CONTEXT section 9 still stands.
