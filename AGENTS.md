# ClearSwath: agent instructions

## What this is
Pesticide label + field outline -> legal spray zone for a drone or ground sprayer,
plus the application record. Python 3.12, uv, FastAPI, Leaflet. Meta Global AI
Developer Hackathon, Oct 26 - Nov 4, 2026. Architecture and contracts: docs/CONTRACTS.md.

## Hard rules
- Commit only after tests pass AND I approve. Before committing, show me the files
  you'll stage and the message, and wait for my yes. One logical change per commit.
- Commit messages are a single subject line: 'type: summary' (feat, fix, test, docs,
  chore, refactor, style), max 72 characters. No body, no trailers, no
  Co-authored-by, no "Generated with", no session links.
- NEVER push, reset, rebase or amend. I push at the end of each session.
- Never put API keys in code. MODEL_API_KEY comes from .env via app/llm.py.
- Don't add dependencies without asking.
- All Meta model calls go through app/llm.py.
- app/buffers.py never calls a model. Buffer in a UTM CRS (geopandas
  estimate_utm_crs), never in degrees. Feet x 0.3048.
- Every label rule carries a quote verified against the label text.
- The GO / ADJUST / NO-GO decision always comes from buffers.plan, never model text.

## How to work
- Start every session by re-reading docs/PROJECT_CONTEXT.md section 6 (status) and continue
  from the next unfinished task. Update that status as work lands.
- First restate the task in 3 bullets and list files you'll touch. Wait for my OK.
- Smallest change that does the task. No unrelated refactors.
- Tests for every behavior change. Tests never call the network or API; mock them.
- After changes run `uv run pytest` and report the result, then propose the commit.
- Meta: base URL https://api.meta.ai/v1; models muse-spark-1.3, sam-3.1,
  muse-voice-transcribe-1.0. If unsure of an API shape, say so and leave
  TODO(verify). Don't guess silently.
