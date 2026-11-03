"""Synthetic narration for the demo video, from the VO column of docs/video/SCRIPT.md. Video tooling only.

uv run --with kokoro --with soundfile python scripts/narrate_video.py [--voice am_michael] [--check]

Kokoro-82M (Apache-2.0, hexgrad/Kokoro-82M) speaks each shot's line into data/video/voice/<shot>.wav and writes
manifest.json (shot -> seconds). --check sends each take to Muse Voice Transcribe and compares the words with the
script, a test of intelligibility. This is a disclosed synthetic voice, a fallback until Hunter records his own;
it is never presented as his.
"""

import argparse
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "video" / "voice"
SR = 24000
# spoken forms for the speech engine only; captions and the screen keep the real spellings
SAY = {"ClearSwath": "Clear Swath", "SAM 3.1": "Sam three point one", "DINOv2": "dino vee two",
       "Muse Spark Open": "Muse Spark Open", "ULV": "U L V", "GeoJSON": "geo Jason", "KML": "K M L",
       "Tordon 22K": "Tordon twenty-two K", "Modal": "Modal"}


def lines() -> list[str]:
    """The VO column, one entry per shot, quotes stripped."""
    rows = [l for l in (ROOT / "docs/video/SCRIPT.md").read_text().splitlines() if re.match(r"^\| \d:\d\d-\d:\d\d \|", l)]
    return [re.sub(r'^"|"$', "", r.split("|")[3].strip()) for r in rows]


def spoken(text: str) -> str:
    for a, b in SAY.items():
        text = text.replace(a, b)
    return text


def write(path: Path, audio: np.ndarray) -> float:
    pad = np.zeros(int(0.25 * SR), dtype=np.float32)
    audio = np.concatenate([pad, audio.astype(np.float32), pad])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return len(audio) / SR


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())


def main(voice: str, check: bool, speed: float) -> None:
    from kokoro import KPipeline

    tts = KPipeline(lang_code="a")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for n, text in enumerate(lines(), 1):
        audio = np.concatenate([np.asarray(a) for _, _, a in tts(spoken(text), voice=voice, speed=speed)])
        manifest[n] = round(write(OUT / f"shot{n}.wav", audio), 2)
    (OUT / "manifest.json").write_text(json.dumps({"voice": voice, "speed": speed, "engine": "Kokoro-82M",
                                                   "seconds": manifest}, indent=1))
    print(voice, "total", round(sum(manifest.values()), 1), "s", manifest)
    if check:
        from app import llm
        for n, text in enumerate(lines(), 1):
            heard = llm.transcribe(OUT / f"shot{n}.wav", purpose="narration-check")
            want, got = words(spoken(text)), set(words(heard))
            missing = [w for w in want if w not in got]
            print(f"shot {n}: {len(want) - len(missing)}/{len(want)} words heard; missing {missing[:8]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--check", action="store_true", help="transcribe each take with Muse Voice Transcribe (paid)")
    a = ap.parse_args()
    main(a.voice, a.check, a.speed)
