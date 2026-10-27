"""Live check against api.meta.ai. Uses the network and your key: `uv run python scripts/smoke.py`."""

import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta_sam_parser import CompletedOutcome, image_segmentation_format  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app import llm  # noqa: E402

results = {}


def check(name, fn):
    """Runs one check; a failure is printed and the next check still runs."""
    try:
        ok, detail = fn()
    except Exception as e:  # report and keep going
        ok, detail = False, f"{type(e).__name__}: {e}"
    results[name] = ok
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")


def models():
    ids = {m.id for m in llm.client().models.list()}
    missing = [m for m in (llm.SPARK, llm.SAM, llm.VOICE) if m not in ids]
    return not missing, f"{len(ids)} models" + (f", missing {missing}" if missing else "")


def chat():
    reply = llm.chat([{"role": "user", "content": 'Reply with exactly "OK".'}], purpose="smoke").content
    return "OK" in (reply or ""), repr(reply)


def chat_json():
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}},
              "required": ["answer"], "additionalProperties": False}
    out = llm.chat_json([{"role": "user", "content": "What is 2 + 2?"}], schema, "sum", purpose="smoke")
    return out.get("answer") == 4, str(out)


def tools():
    tool = {"type": "function", "function": {"name": "plan_spray", "description": "Plan the spray job.",
                                             "parameters": {"type": "object", "properties": {}}}}
    msg = llm.chat([{"role": "user", "content": "Plan the spray job."}], tools=[tool], purpose="smoke")
    names = [c.function.name for c in msg.tool_calls or []]
    return names == ["plan_spray"], f"tool calls {names}"


def sam(tmp: Path):
    png = tmp / "pond.png"
    img = Image.new("RGB", (256, 256), (96, 140, 60))  # grass
    ImageDraw.Draw(img).ellipse((80, 90, 180, 170), fill=(40, 70, 110))  # a pond
    img.save(png)
    text = llm.sam_raw(png, "pond", purpose="smoke")
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    masks = [r for r in result.records if r.kind == "mask"]
    errors = [d for d in result.diagnostics if d.severity == "error"]
    return not errors, f"{len(masks)} mask(s), confidence {[m.confidence for m in masks]}, {len(errors)} parse errors"


def voice(tmp: Path):
    path = tmp / "silence.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0" * 32000)  # 1 s of silence
    text = llm.transcribe(path, purpose="smoke")
    return isinstance(text, str), f"transcript {text!r}"


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    check("models", models)
    check("chat", chat)
    check("chat_json", chat_json)
    check("tool calling", tools)
    check("sam-3.1", lambda: sam(tmp))
    check("voice transcribe", lambda: voice(tmp))

print("PASS" if all(results.values()) else "FAIL")
sys.exit(0 if all(results.values()) else 1)
