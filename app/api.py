"""HTTP API for web/index.html. Run with: uv run uvicorn app.api:app"""

import json
import re
import uuid
from datetime import date
from pathlib import Path

import simplekml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app import agent, geo, label_reader, pipeline, records

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
DEMO = ROOT / "data" / "demo"
LABEL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".webm", ".ogg"}
METHODS = {"drone", "aerial", "ground"}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
RUN_ID = re.compile(r"^[0-9a-f]{32}$")

app = FastAPI(title="ClearSwath")


def _save(upload: UploadFile, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(upload.file.read())
    return path


def _label_suffix(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in LABEL_SUFFIXES:
        raise HTTPException(422, f"Label must be one of {sorted(LABEL_SUFFIXES)}")
    return suffix


def _plan(run_id: str, field_path: Path, label_path: Path, month: str, method: str,
          use_agent: bool = False) -> dict:
    if not MONTH.match(month):
        raise HTTPException(422, "month must look like 2026-11")
    if method not in METHODS:
        raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
    try:
        if use_agent:  # the agent saves its own run under its own run_id
            out = agent.run(field_path, label_path, month, method)
            return {**pipeline.to_json(out.pop("result")), **out}
        result = pipeline.run(field_path, label_path, month, method)
    except ValueError as e:  # bad field or label input
        raise HTTPException(422, str(e)) from e
    except (LookupError, RuntimeError) as e:  # no imagery, missing key, model failure
        raise HTTPException(502, str(e)) from e
    pipeline.save_run(result, RUNS / run_id)
    return {"run_id": run_id, **pipeline.to_json(result)}


def _upload_and_plan(field: UploadFile, label: UploadFile, month: str, method: str, use_agent: bool) -> dict:
    run_id = uuid.uuid4().hex
    run = RUNS / run_id
    suffix = _label_suffix(label)
    return _plan(run_id, _save(field, run / "field.geojson"), _save(label, run / f"label{suffix}"),
                 month, method, use_agent)


@app.post("/api/plan")
def plan(field: UploadFile = File(...), label: UploadFile = File(...),
         month: str = Form(...), method: str = Form("drone")):
    return _upload_and_plan(field, label, month, method, use_agent=False)


@app.post("/api/agent")
def ask_agent(field: UploadFile = File(...), label: UploadFile = File(...),
              month: str = Form(...), method: str = Form("drone")):
    """Same as /api/plan, plus the agent's answer, trace and mode. The decision still comes from buffers.plan."""
    return _upload_and_plan(field, label, month, method, use_agent=True)


@app.post("/api/label")
def label(label: UploadFile = File(...)):
    path = _save(label, RUNS / uuid.uuid4().hex / f"label{_label_suffix(label)}")
    try:
        return label_reader.read_label(path).model_dump()
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/record")
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
    except RuntimeError as e:  # missing key or model failure
        raise HTTPException(502, str(e)) from e


@app.get("/api/demo")
def demo(month: str | None = None, method: str = "drone"):
    labels = [p for p in DEMO.glob("label.*") if p.suffix.lower() in LABEL_SUFFIXES]
    field = DEMO / "field.geojson"
    if not field.exists() or not labels:
        raise HTTPException(404, "Demo files missing: add data/demo/field.geojson and data/demo/label.pdf")
    return _plan(uuid.uuid4().hex, field, labels[0], month or date.today().strftime("%Y-%m"), method)


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
