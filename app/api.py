"""HTTP API for web/index.html. Run with: uv run uvicorn app.api:app"""

import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict, deque
from datetime import date
from pathlib import Path

import simplekml
from shapely import union_all
from PIL import Image, ImageOps
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import agent, exports, geo, imagery, llm, label_reader, pipeline, records, segment, spend

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
DEMO = ROOT / "data" / "demo"
LABEL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
AUDIO_SUFFIXES = {".wav"}  # Muse Voice Transcribe takes WAV only
METHODS = {"drone", "aerial", "ground"}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
RUN_ID = re.compile(r"^[0-9a-f]{32}$")

MB = 1024 * 1024
FIELD_MAX = 1 * MB  # a field outline is a few KB
LABEL_MAX = int(os.getenv("MAX_LABEL_MB", "10")) * MB
AUDIO_MAX = int(os.getenv("MAX_AUDIO_MB", "32")) * MB  # Muse Voice Transcribe's own limit
REQUEST_MAX = 40 * MB

log = logging.getLogger(__name__)
app = FastAPI(title="ClearSwath")


# Disk: uploads and results don't pile up. Run folders hold uploads, KML and the record job.
RUN_MAX_AGE_S, MAX_RUN_DIRS = 24 * 3600, 2000
CACHE_MAX_AGE_S, MAX_CACHE_DIRS = 7 * 24 * 3600, 500  # per-field imagery/SAM/USGS caches
FIELD_CACHE = re.compile(r"^[0-9a-f]{12}$")  # data/cache/<field hash>; labels/ and blt/ are left alone
_cleaned = {"at": 0.0}


def clean_up(now: float | None = None) -> None:
    """Deletes old run folders and per-field cache folders, oldest first past the count caps."""
    now = now or time.time()
    for root, max_age, cap, keep in ((RUNS, RUN_MAX_AGE_S, MAX_RUN_DIRS, RUN_ID),
                                     (segment.CACHE, CACHE_MAX_AGE_S, MAX_CACHE_DIRS, FIELD_CACHE)):
        if not root.exists():
            continue
        dirs = sorted((d for d in root.iterdir() if d.is_dir() and keep.match(d.name)), key=lambda d: d.stat().st_mtime)
        for i, d in enumerate(dirs):
            if now - d.stat().st_mtime > max_age or len(dirs) - i > cap:
                shutil.rmtree(d, ignore_errors=True)


def _clean_up_hourly() -> None:
    with _lock:
        if time.time() - _cleaned["at"] < 3600:
            return
        _cleaned["at"] = time.time()
    threading.Thread(target=clean_up, daemon=True).start()  # never makes a request wait


FREE_METHODS = {"GET", "HEAD"}  # the free endpoints (demo, KML, health) are all reads


class Guard:
    """Runs before FastAPI reads a body (it parses uploads before route dependencies run):
    refuses a declared oversize body, gates every non-GET /api/ request from the headers alone (so a new paid
    endpoint is covered without being listed), and counts the bytes that
    actually arrive (chunked bodies too), stopping at REQUEST_MAX. _save then enforces per-file limits."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        _clean_up_hourly()
        request = Request(scope)
        try:
            size = request.headers.get("content-length", "")
            if size.isdigit() and int(size) > REQUEST_MAX:
                raise HTTPException(413, f"Request too large: the limit is {REQUEST_MAX // MB} MB.")
            if scope["method"] not in FREE_METHODS:  # deny by default: any write under /api/ is a paid run
                paid_access(request)
        except HTTPException as e:
            return await JSONResponse({"detail": e.detail}, status_code=e.status_code)(scope, receive, send)

        received = 0

        async def counted():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > REQUEST_MAX:  # FastAPI re-raises this while parsing the form: a 413 response
                    raise HTTPException(413, f"Request too large: the limit is {REQUEST_MAX // MB} MB.")
            return message

        await self.app(scope, counted, send)

# Paid endpoints (model calls) are gated; the cached demo, KML and the page stay open.
_lock = threading.Lock()
# ip -> live-run times (last day) / wrong-code times (last hour), least recently hit first (an LRU)
_hits: OrderedDict[str, deque] = OrderedDict()
_fails: OrderedDict[str, deque] = OrderedDict()
MAX_TRACKED = 10_000  # addresses per table; bounds memory when many addresses (e.g. rotating IPv6) hit us
_day = {"date": None, "count": 0}
MIN_CODE_LEN = 16  # a shorter ACCESS_CODE could be guessed; it switches live runs off instead
MAX_FAILS_PER_HOUR = 10


def reset_limits() -> None:
    """Clears the rate-limit and daily counters (tests; they also reset on restart)."""
    with _lock:
        _hits.clear()
        _fails.clear()
        _day.update(date=None, count=0)


def _count(table: dict, ip: str, now: float, window: float = 3600) -> int:
    """Hits from ip in the last window seconds. Never creates an entry; drops one that has expired."""
    times = table.get(ip)
    if times is None:
        return 0
    while times and now - times[0] > window:
        times.popleft()
    if not times:
        del table[ip]
    return len(times)


def _add(table: OrderedDict, ip: str, now: float) -> None:
    """Records a hit and marks ip most recent; over MAX_TRACKED, evicts the least recent in O(1)."""
    table.setdefault(ip, deque()).append(now)
    table.move_to_end(ip)
    while len(table) > MAX_TRACKED:
        table.popitem(last=False)


def _client_ip(request: Request) -> str:
    # Render's proxy appends the address it saw; the last entry is the one a client can't forge.
    # TODO(verify): X-Forwarded-For order on Render
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "unknown")


def paid_access(request: Request) -> None:
    """Kill switch, access code, per-IP daily limit, a global daily run cap and spend budget, checked before any
    paid model call."""
    if os.getenv("CLEARSWATH_LIVE_MODE", "on").strip().lower() in ("off", "0", "false", "no"):
        raise HTTPException(503, "Live runs are switched off right now. The demo still works.")
    now, ip = time.time(), _client_ip(request)
    code = os.getenv("ACCESS_CODE")
    if code and len(code) < MIN_CODE_LEN:
        log.warning("ACCESS_CODE is shorter than %d characters; live runs are refused", MIN_CODE_LEN)
        raise HTTPException(503, "Live runs aren't switched on for this site yet. Try the demo.")
    if code:
        with _lock:  # checked before comparing, so a locked-out address can't keep guessing
            if _count(_fails, ip, now) >= MAX_FAILS_PER_HOUR:
                raise HTTPException(429, "Too many wrong access codes from your address. Try again later, or use the demo.")
        given = request.headers.get("x-access-code", "")
        if not hmac.compare_digest(given.encode(), code.encode()):
            with _lock:
                _add(_fails, ip, now)
            log.warning("wrong access code from %s", ip)
            raise HTTPException(401, "Live runs need the access code. The demo is open to everyone.")
    elif os.getenv("RENDER"):  # deployed without a code: refuse rather than spend for anyone
        raise HTTPException(503, "Live runs aren't switched on for this site yet. Try the demo.")
    per_day = int(os.getenv("RUNS_PER_IP_PER_DAY", "3"))
    daily_cap = int(os.getenv("DAILY_RUN_CAP", "200"))
    budget = float(os.getenv("DAILY_BUDGET_USD", "5"))
    with _lock:
        if _day["date"] != date.today():
            _day.update(date=date.today(), count=0)
        if _day["count"] >= daily_cap or spend.today() >= budget:
            raise HTTPException(503, "Today's live-run budget is used up. The demo still works.")
        if _count(_hits, ip, now, window=86400) >= per_day:
            raise HTTPException(429, "Too many live runs from your address today. Try again tomorrow, or use the demo.")
        _add(_hits, ip, now)
        _day["count"] += 1




def _http_error(e: Exception) -> HTTPException:
    """Only messages we wrote reach the browser; anything else is logged and replaced."""
    if isinstance(e, (llm.MissingKeyError, imagery.NoImageryError, llm.PhotoUnavailableError)):
        return HTTPException(502, str(e))
    if isinstance(e, (llm.BadAudioError, pipeline.NotConfirmableError, label_reader.LabelTooLongError,
                      geo.FieldError)):
        return HTTPException(422, str(e))
    log.exception("request failed", exc_info=e)
    if isinstance(e, ValueError):  # bad field or label file
        return HTTPException(422, "Could not read the field outline or label. Check the files and try again.")
    return HTTPException(502, "A model or data service failed. Try again; details are in the server log.")


# What the first bytes of each allowed upload type look like (checked after saving, before any use)
SIGNATURES = {
    ".pdf": ("a PDF", lambda h: h.startswith(b"%PDF")),
    ".png": ("a PNG image", lambda h: h.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("a JPEG image", lambda h: h.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("a JPEG image", lambda h: h.startswith(b"\xff\xd8\xff")),
    ".webp": ("a WebP image", lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP"),
    ".wav": ("a WAV file", lambda h: h[:4] == b"RIFF" and h[8:12] == b"WAVE"),
}


def _check_type(path: Path) -> None:
    """Deletes and refuses (415) a file whose content doesn't match its extension."""
    kind = SIGNATURES.get(path.suffix.lower())
    with path.open("rb") as f:
        head = f.read(16)
    if kind and not kind[1](head):
        path.unlink(missing_ok=True)
        raise HTTPException(415, f"That file doesn't look like {kind[0]}.")


IMAGE_FORMATS = {".png": "PNG", ".webp": "WEBP", ".jpg": "JPEG", ".jpeg": "JPEG"}
MAX_IMAGE_SIDE = 3000  # px; plenty to read a label, and it bounds the model's image cost
MAX_IMAGE_PIXELS = 50_000_000  # declared size, checked before decoding: a small file can claim a huge image


def _clean_image(path: Path) -> None:
    """Re-encodes a photo upright, at most MAX_IMAGE_SIDE, with no EXIF (GPS, camera) before it's stored or sent."""
    try:
        with Image.open(path) as im:  # reads only the header: nothing is decoded yet
            if im.width * im.height > MAX_IMAGE_PIXELS:
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"That image is too large: the limit is {MAX_IMAGE_PIXELS // 1_000_000} "
                                         "megapixels.")
            im = ImageOps.exif_transpose(im)  # apply the orientation tag before it's dropped
            im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        fmt = IMAGE_FORMATS[path.suffix.lower()]
        if fmt == "JPEG" and im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.save(path, fmt, quality=90)  # no exif= argument: metadata is not written
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        path.unlink(missing_ok=True)
        raise HTTPException(415, "That image couldn't be read.") from e


def _save(upload: UploadFile, path: Path, max_bytes: int) -> Path:
    """Copies an upload in 1 MB pieces, stopping at max_bytes (413) so a huge file is never held whole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("wb") as out:
        while chunk := upload.file.read(MB):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"{upload.filename or 'File'} is too large: the limit is {max_bytes // MB} MB.")
            out.write(chunk)
    _check_type(path)
    if path.suffix.lower() in IMAGE_FORMATS:
        _clean_image(path)
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


MANAGED_MAX = 512 * 1024  # managed-land GeoJSON, sent as a form field


def _wind(text: str) -> float | None:
    """'' -> None (drift buffers all round); else compass degrees the wind blows from."""
    if not text.strip():
        return None
    try:
        deg = float(text)
    except ValueError:
        deg = -1
    if not 0 <= deg < 360:
        raise HTTPException(422, "wind_from must be compass degrees from 0 to 359, or empty")
    return deg


def _plan(run_id: str, field_path: Path, label_path: Path, month: str, method: str,
          use_agent: bool = False, excluded_rules: str = "", managed: str = "", wind_from: str = "") -> dict:
    excluded = _rule_ids(excluded_rules)
    if not MONTH.match(month):
        raise HTTPException(422, "month must look like 2026-11")
    if method not in METHODS:
        raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
    if len(managed) > MANAGED_MAX:
        raise HTTPException(413, "The managed land is too large; simplify the shapes.")
    wind = _wind(wind_from)
    try:
        land = geo.load_managed(managed, geo.load_field(field_path)) if managed.strip() else []  # before any paid call
        if use_agent:  # the agent saves its own run under its own run_id
            out = agent.run(field_path, label_path, month, method, excluded, managed=land, wind_from_deg=wind)
            return {**pipeline.to_json(out.pop("result")), **out}
        result = pipeline.run(field_path, label_path, month, method, excluded, land, wind)
    except Exception as e:  # any failure: bad input, no imagery, missing key, model or data service down
        raise _http_error(e) from e
    pipeline.save_run(result, RUNS / run_id)
    return {"run_id": run_id, **pipeline.to_json(result)}


def _upload_and_plan(field: UploadFile, label: UploadFile, month: str, method: str, use_agent: bool,
                     excluded_rules: str, managed: str = "", wind_from: str = "") -> dict:
    run_id = uuid.uuid4().hex
    run = RUNS / run_id
    suffix = _label_suffix(label)
    field_path = _save(field, run / "field.geojson", FIELD_MAX)
    label_path = _save(label, run / f"label{suffix}", LABEL_MAX)
    return _plan(run_id, field_path, label_path, month, method, use_agent, excluded_rules, managed, wind_from)


@app.post("/api/plan")  # gated by Guard
def plan(field: UploadFile = File(...), label: UploadFile = File(...),
         month: str = Form(...), method: str = Form("drone"), excluded_rules: str = Form(""),
         managed: str = Form(""), wind_from: str = Form("")):
    """managed: GeoJSON of land next to the field marked as managed (drift buffers skip it); wind_from: degrees."""
    return _upload_and_plan(field, label, month, method, False, excluded_rules, managed, wind_from)


@app.post("/api/agent")  # gated by Guard
def ask_agent(field: UploadFile = File(...), label: UploadFile = File(...),
              month: str = Form(...), method: str = Form("drone"), excluded_rules: str = Form(""),
              managed: str = Form(""), wind_from: str = Form("")):
    """Same as /api/plan, plus the agent's answer, trace and mode. The decision still comes from buffers.plan."""
    return _upload_and_plan(field, label, month, method, True, excluded_rules, managed, wind_from)


@app.post("/api/label")  # gated by Guard
def label(label: UploadFile = File(...)):
    path = _save(label, RUNS / uuid.uuid4().hex / f"label{_label_suffix(label)}", LABEL_MAX)
    try:
        return label_reader.read_label(path).model_dump()
    except Exception as e:
        raise _http_error(e) from e


@app.post("/api/record")  # gated by Guard
def record(run_id: str = Form(...), audio: UploadFile | None = File(None), text: str = Form("")):
    job_path = RUNS / run_id / "job.json"
    if not RUN_ID.match(run_id) or not job_path.exists():
        raise HTTPException(404, "No such run")
    try:
        if audio is not None:
            suffix = Path(audio.filename or "").suffix.lower()
            if suffix not in AUDIO_SUFFIXES:
                raise HTTPException(422, f"Audio must be one of {sorted(AUDIO_SUFFIXES)}")
            text = records.transcribe(_save(audio, RUNS / run_id / f"note{suffix}", AUDIO_MAX))
        if not text.strip():
            raise HTTPException(422, "Send a voice note or type the notes")
        return records.fill_record(text, json.loads(job_path.read_text())).model_dump()
    except HTTPException:
        raise
    except Exception as e:  # bad audio, missing key, model failure
        raise _http_error(e) from e


DEMO_FIELDS = {"": "field", "corrected": "field_corrected", "mt": "mt"}  # mt: Montana rangeland, cache only


def _overlay(name: str) -> dict | None:
    """The demo's drone image for the map, when the demo has one (data/demo/<name>/block.webp)."""
    bounds = DEMO / name / "block_bounds.json"
    if not (DEMO / name / "block.webp").exists() or not bounds.exists():
        return None
    meta = json.loads(bounds.read_text())
    return {"url": f"/api/demo/image/{name}", "bounds": meta["bounds"], "credit": meta.get("credit")}


@app.get("/api/demo/image/{name}")
def demo_image(name: str):
    path = DEMO / name / "block.webp"
    if name not in DEMO_FIELDS.values() or not path.exists():
        raise HTTPException(404, "No image for this demo")
    return FileResponse(path, media_type="image/webp")


def _replay_key(method: str, excluded: list[int]) -> str:
    return f"{method}|{','.join(map(str, sorted(excluded)))}"


@app.post("/api/demo/agent")  # gated by Guard: the model call is live and paid
def demo_agent(field: str = Form(""), method: str = Form("drone"), excluded_rules: str = Form("")):
    """The Muse Spark agent on a cached demo: its tools return the saved inputs, only the model runs live.
    The answer is saved to data/demo/cache/<demo>/agent.json, which GET /api/demo?agent=1 replays for free."""
    if field not in DEMO_FIELDS:
        raise HTTPException(422, f"field must be one of {sorted(k for k in DEMO_FIELDS if k)} or empty")
    if method not in METHODS:
        raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
    cache = DEMO / "cache" / DEMO_FIELDS[field]
    if not pipeline.cache_file(cache):
        raise HTTPException(404, "This demo has no saved inputs")
    excluded = _rule_ids(excluded_rules)
    try:
        shape_, label, hazards, bulletin, month = pipeline.load_inputs(cache)
        out = agent.run(None, None, month, method, excluded, inputs=(shape_, label, hazards, bulletin))
        body = {**pipeline.to_json(out.pop("result")), **out}
    except Exception as e:
        raise _http_error(e) from e
    if out["mode"] == "agent":  # only real model answers are worth replaying
        replays = json.loads((cache / "agent.json").read_text()) if (cache / "agent.json").exists() else {}
        replays[_replay_key(method, excluded)] = {
            k: body[k] for k in ("answer", "decision", "trace")} | {"model": out.get("model") or llm.spark_model(None),
                                                                   "date": date.today().isoformat()}
        (cache / "agent.json").write_text(json.dumps(replays, indent=1, default=str))
    return body | {"demo": {"field": field, "cached": True, "month": month, "overlay": _overlay(DEMO_FIELDS[field])}}


@app.get("/api/demo")
def demo(request: Request, month: str | None = None, method: str = "drone", excluded_rules: str = "",
         field: str = "", agent_answer: bool = False, wind_from: str = ""):
    """The demo field. From data/demo/cache when present (offline, instant; the plan is still recomputed),
    else live. field=corrected is the outline pulled back from the creek."""
    if field not in DEMO_FIELDS:
        raise HTTPException(422, f"field must be one of {sorted(k for k in DEMO_FIELDS if k)} or empty")
    name = DEMO_FIELDS[field]
    cache = DEMO / "cache" / name
    if pipeline.cache_file(cache):
        if method not in METHODS:
            raise HTTPException(422, f"method must be one of {sorted(METHODS)}")
        excluded, wind = _rule_ids(excluded_rules), _wind(wind_from)
        try:
            shape_, label, hazards, bulletin, cached_month = pipeline.load_inputs(cache)
            result = pipeline.assemble(shape_, label, hazards, bulletin, cached_month, method, excluded, wind)
        except Exception as e:
            raise _http_error(e) from e
        run_id = uuid.uuid4().hex
        pipeline.save_run(result, RUNS / run_id)
        body = {"run_id": run_id, **pipeline.to_json(result),
                "demo": {"field": field, "cached": True, "month": cached_month, "overlay": _overlay(name)}}
        saved = json.loads((cache / "agent.json").read_text()) if agent_answer and (cache / "agent.json").exists() else {}
        replay = saved.get(_replay_key(method, excluded))
        if replay and replay["decision"] == result["plan"]["status"]:  # never replay an answer the plan has outgrown
            body |= {"answer": replay["answer"], "trace": replay["trace"], "decision": replay["decision"],
                     "mode": "replay", "replay": {"model": replay["model"], "date": replay["date"]}}
        return body
    labels = [p for p in DEMO.glob("label.*") if p.suffix.lower() in LABEL_SUFFIXES]
    path = DEMO / f"{name}.geojson"
    if not path.exists() or not labels:
        raise HTTPException(404, f"Demo files missing: add data/demo/{name}.geojson and data/demo/label.pdf")
    paid_access(request)  # without a cache the demo is a live, paid run: same gate as /api/plan
    month = month or date.today().strftime("%Y-%m")
    out = _plan(uuid.uuid4().hex, path, labels[0], month, method, excluded_rules=excluded_rules)
    return out | {"demo": {"field": field, "cached": False, "month": month}}


PHOTO_MAX = 15 * MB


@app.post("/api/photo")  # gated by Guard: a GPU call on Modal
def photo(photo: UploadFile = File(...)):
    """Live photo mode: one photo looking down at a crop -> weed overlay from the DINOv3 head."""
    suffix = Path(photo.filename or "").suffix.lower()
    if suffix not in IMAGE_FORMATS:
        raise HTTPException(422, f"Photo must be one of {sorted(IMAGE_FORMATS)}")
    path = _save(photo, RUNS / uuid.uuid4().hex / f"photo{suffix}", PHOTO_MAX)  # upright, no EXIF, <= 3000 px
    try:
        out = llm.weed_photo(path)
    except Exception as e:
        raise _http_error(e) from e
    return {k: out.get(k) for k in ("width", "height", "share_flagged", "overlay_png", "trained_on")}


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
    colors = {"Spray zone": "7f00ff00", "No spray": "7f0000ff", "Spot spray": "cc0051e6"}  # aabbggrr
    names = [f["properties"]["name"] for f in json.loads(path.read_text())["features"]]
    for name, shape in zip(names, geo.load_shapes(path), strict=True):
        for poly in getattr(shape, "geoms", [shape]):
            if poly.is_empty:
                continue
            p = doc.newpolygon(name=name, outerboundaryis=list(poly.exterior.coords),
                               innerboundaryis=[list(r.coords) for r in poly.interiors])
            p.style.polystyle.color = colors.get(name, "7f888888")
    return Response(doc.kml(), media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f'attachment; filename="clearswath-{run_id[:8]}.kml"'})


@app.get("/api/export/{run_id}/{fmt}")
def export(run_id: str, fmt: str, rate: float | None = None):
    """Spot-spray exports. dji: boundary shapefile + prescription GeoTIFF (rate per ha in spray cells).
    geojson: the plan's spray zone, no-spray area and spot-spray cells."""
    run = RUNS / run_id
    if not RUN_ID.match(run_id) or not (run / "plan.geojson").exists():
        raise HTTPException(404, "No such run")
    if fmt == "geojson":
        return Response((run / "plan.geojson").read_text(), media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="clearswath-{run_id[:8]}.geojson"'})
    if fmt != "dji":
        raise HTTPException(404, "Export formats: dji, geojson")
    if not (run / "spot.tif").exists():
        raise HTTPException(409, "This plan has no weed map, so there is no spot-spray prescription")
    if rate is None or not 0 < rate <= 1000:
        raise HTTPException(422, "Give the spray rate per hectare, between 0 and 1000")
    job = json.loads((run / "job.json").read_text()) if (run / "job.json").exists() else {}
    if job.get("carrier_unverified"):
        raise HTTPException(409, "A spray-volume rule on the label couldn't be verified, so the minimum isn't known. "
                                 "Check the label.")
    if (low := job.get("carrier_min")) and rate < low["l_ha"]:
        raise HTTPException(422, f"{rate:g} L/ha is below {low['l_ha']} L/ha, the largest minimum spray volume on the "
                                 f"label (p.{low['page']}: \"{low['quote']}\"). A volume at or above it meets "
                                 "every section's minimum.")
    field = geo.load_shapes(run / "plan.geojson")
    zipped = exports.dji_zip(union_all(field[:2]), run / "spot.tif", rate)
    return Response(zipped, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="clearswath-{run_id[:8]}-dji.zip"'})


app.add_middleware(Guard)
# The React build (web-app/, `npm run build`) when present, else the plain page.
WEB = ROOT / "web" / "dist" if (ROOT / "web" / "dist" / "index.html").exists() else ROOT / "web"
app.mount("/", StaticFiles(directory=WEB, html=True, check_dir=False), name="web")
