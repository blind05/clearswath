"""HTTP API for web/index.html. Run with: uv run uvicorn app.api:app"""

import hmac
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

import simplekml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app import agent, geo, imagery, llm, label_reader, pipeline, records

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
DEMO = ROOT / "data" / "demo"
LABEL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
AUDIO_SUFFIXES = {".wav"}  # Muse Voice Transcribe takes WAV only
METHODS = {"drone", "aerial", "ground"}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
RUN_ID = re.compile(r"^[0-9a-f]{32}$")

log = logging.getLogger(__name__)
app = FastAPI(title="ClearSwath")

# Paid endpoints (model calls) are gated; the cached demo, KML and the page stay open.
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)  # ip -> request times in the last hour
_day = {"date": None, "count": 0}


def reset_limits() -> None:
    """Clears the rate-limit and daily counters (tests; they also reset on restart)."""
    with _lock:
        _hits.clear()
        _day.update(date=None, count=0)


def _client_ip(request: Request) -> str:
    # Render's proxy appends the address it saw; the last entry is the one a client can't forge.
    # TODO(verify): X-Forwarded-For order on Render
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "unknown")


def paid_access(request: Request) -> None:
    """Access code, per-IP hourly limit and a global daily cap, checked before any paid model call."""
    code = os.getenv("ACCESS_CODE")
    if code:
        given = request.headers.get("x-access-code", "")
        if not hmac.compare_digest(given.encode(), code.encode()):
            raise HTTPException(401, "Live runs need the access code. The demo is open to everyone.")
    elif os.getenv("RENDER"):  # deployed without a code: refuse rather than spend for anyone
        raise HTTPException(503, "Live runs aren't switched on for this site yet. Try the demo.")
    per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "20"))
    daily_cap = int(os.getenv("DAILY_RUN_CAP", "200"))
    now, ip = time.time(), _client_ip(request)
    with _lock:
        if _day["date"] != date.today():
            _day.update(date=date.today(), count=0)
        if _day["count"] >= daily_cap:
            raise HTTPException(503, "Today's live-run budget is used up. The demo still works.")
        hits = _hits[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= per_hour:
            raise HTTPException(429, "Too many live runs from your address. Try again within the hour, or use the demo.")
        hits.append(now)
        _day["count"] += 1


PAID = [Depends(paid_access)]


def _http_error(e: Exception) -> HTTPException:
    """Only messages we wrote reach the browser; anything else is logged and replaced."""
    if isinstance(e, (llm.MissingKeyError, imagery.NoImageryError)):
        return HTTPException(502, str(e))
    if isinstance(e, (llm.BadAudioError, pipeline.NotConfirmableError)):
        return HTTPException(422, str(e))
    log.exception("request failed", exc_info=e)
    if isinstance(e, ValueError):  # bad field or label file
        return HTTPException(422, "Could not read the field outline or label. Check the files and try again.")
    return HTTPException(502, "A model or data service failed. Try again; details are in the server log.")


def _save(upload: UploadFile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(upload.file.read())
    return path


def _label_suffix(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in LABEL_SUFFIXES:
        raise HTTPException(422, f"Label must be one of {sorted(LABEL_SUFFIXES)}")
    return suffix


def _rule_ids(text: str) -> list[int]:
    """'1,3' -> [1, 3]: the label rules the user unticked."""
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(422, "excluded_rules must be comma-separated rule ids, e.g. 1,3") from e


def _plan(run_id: str, field_path: Path, label_path: Path, month: str, method: str,
          use_agent: bool = False, excluded_rules: str = "") -> dict:
    excluded = _rule_ids(excluded_rules)
    if not MONTH.match(month):
        raise HTTPException(422, "month must look like 2026-11")
    if method not in METHODS:
        raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
    try:
        if use_agent:  # the agent saves its own run under its own run_id
            out = agent.run(field_path, label_path, month, method, excluded)
            return {**pipeline.to_json(out.pop("result")), **out}
        result = pipeline.run(field_path, label_path, month, method, excluded)
    except Exception as e:  # any failure: bad input, no imagery, missing key, model or data service down
        raise _http_error(e) from e
    pipeline.save_run(result, RUNS / run_id)
    return {"run_id": run_id, **pipeline.to_json(result)}


def _upload_and_plan(field: UploadFile, label: UploadFile, month: str, method: str, use_agent: bool,
                     excluded_rules: str) -> dict:
    run_id = uuid.uuid4().hex
    run = RUNS / run_id
    suffix = _label_suffix(label)
    return _plan(run_id, _save(field, run / "field.geojson"), _save(label, run / f"label{suffix}"),
                 month, method, use_agent, excluded_rules)


@app.post("/api/plan", dependencies=PAID)
def plan(field: UploadFile = File(...), label: UploadFile = File(...),
         month: str = Form(...), method: str = Form("drone"), excluded_rules: str = Form("")):
    return _upload_and_plan(field, label, month, method, False, excluded_rules)


@app.post("/api/agent", dependencies=PAID)
def ask_agent(field: UploadFile = File(...), label: UploadFile = File(...),
              month: str = Form(...), method: str = Form("drone"), excluded_rules: str = Form("")):
    """Same as /api/plan, plus the agent's answer, trace and mode. The decision still comes from buffers.plan."""
    return _upload_and_plan(field, label, month, method, True, excluded_rules)


@app.post("/api/label", dependencies=PAID)
def label(label: UploadFile = File(...)):
    path = _save(label, RUNS / uuid.uuid4().hex / f"label{_label_suffix(label)}")
    try:
        return label_reader.read_label(path).model_dump()
    except Exception as e:
        raise _http_error(e) from e


@app.post("/api/record", dependencies=PAID)
def record(run_id: str = Form(...), audio: UploadFile | None = File(None), text: str = Form("")):
    job_path = RUNS / run_id / "job.json"
    if not RUN_ID.match(run_id) or not job_path.exists():
        raise HTTPException(404, "No such run")
    try:
        if audio is not None:
            suffix = Path(audio.filename or "").suffix.lower()
            if suffix not in AUDIO_SUFFIXES:
                raise HTTPException(422, f"Audio must be one of {sorted(AUDIO_SUFFIXES)}")
            text = records.transcribe(_save(audio, RUNS / run_id / f"note{suffix}"))
        if not text.strip():
            raise HTTPException(422, "Send a voice note or type the notes")
        return records.fill_record(text, json.loads(job_path.read_text())).model_dump()
    except HTTPException:
        raise
    except Exception as e:  # bad audio, missing key, model failure
        raise _http_error(e) from e


DEMO_FIELDS = {"": "field", "corrected": "field_corrected"}


@app.get("/api/demo")
def demo(month: str | None = None, method: str = "drone", excluded_rules: str = "", field: str = ""):
    """The demo field. From data/demo/cache when present (offline, instant; the plan is still recomputed),
    else live. field=corrected is the outline pulled back from the creek."""
    if field not in DEMO_FIELDS:
        raise HTTPException(422, f"field must be one of {sorted(k for k in DEMO_FIELDS if k)} or empty")
    name = DEMO_FIELDS[field]
    cache = DEMO / "cache" / name
    if (cache / "inputs.json").exists():
        if method not in METHODS:
            raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
        excluded = _rule_ids(excluded_rules)
        try:
            shape_, label, hazards, bulletin, cached_month = pipeline.load_inputs(cache)
            result = pipeline.assemble(shape_, label, hazards, bulletin, cached_month, method, excluded)
        except Exception as e:
            raise _http_error(e) from e
        run_id = uuid.uuid4().hex
        pipeline.save_run(result, RUNS / run_id)
        return {"run_id": run_id, **pipeline.to_json(result),
                "demo": {"field": field, "cached": True, "month": cached_month}}
    labels = [p for p in DEMO.glob("label.*") if p.suffix.lower() in LABEL_SUFFIXES]
    path = DEMO / f"{name}.geojson"
    if not path.exists() or not labels:
        raise HTTPException(404, f"Demo files missing: add data/demo/{name}.geojson and data/demo/label.pdf")
    month = month or date.today().strftime("%Y-%m")
    out = _plan(uuid.uuid4().hex, path, labels[0], month, method, excluded_rules=excluded_rules)
    return out | {"demo": {"field": field, "cached": False, "month": month}}


@app.get("/api/health")
def health():
    """For the host's health check: the app is up. Makes no model or network calls."""
    return {"ok": True}


@app.get("/api/kml/{run_id}")
def kml(run_id: str):
    path = RUNS / run_id / "plan.geojson"
    if not RUN_ID.match(run_id) or not path.exists():
        raise HTTPException(404, "No such run")
    doc = simplekml.Kml()
    for name, shape in zip(("Spray zone", "No spray"), geo.load_shapes(path), strict=True):
        for poly in getattr(shape, "geoms", [shape]):
            if poly.is_empty:
                continue
            p = doc.newpolygon(name=name, outerboundaryis=list(poly.exterior.coords),
                               innerboundaryis=[list(r.coords) for r in poly.interiors])
            p.style.polystyle.color = "7f00ff00" if name == "Spray zone" else "7f0000ff"
    return Response(doc.kml(), media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f'attachment; filename="clearswath-{run_id[:8]}.kml"'})


app.mount("/", StaticFiles(directory=ROOT / "web", html=True, check_dir=False), name="web")
