"""Hunter's spoken field note -> the Montana demo's saved application record. Demo tooling: calls Muse Voice
Transcribe and Muse Spark through app/records.py (paid, a few cents), the same path as the page's "Fill the record".

uv run python scripts/use_note.py [data/video/hunter/note.m4a]

Converts the note to the WAV Voice Transcribe takes (16 kHz mono 16-bit), runs it on the Montana demo's job, and
writes data/demo/cache/mt/record.json (shown on the demo's default plan) plus data/video/hunter/note.wav for the film.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(note: Path) -> None:
    from fastapi.testclient import TestClient

    from app import llm, records
    from app.api import RUNS, app

    wav = ROOT / "data" / "video" / "hunter" / "note.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", note, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav],
                   check=True)
    run_id = TestClient(app).get("/api/demo", params={"field": "mt"}).json()["run_id"]  # the saved run: no model call
    job = json.loads((RUNS / run_id / "job.json").read_text())
    heard = records.transcribe(wav, job)
    if not heard.strip():
        sys.exit("Muse Voice Transcribe heard no words in that note")
    rec = records.fill_record(heard, job)
    out = ROOT / "data" / "demo" / "cache" / "mt" / "record.json"
    out.write_text(json.dumps({"record": rec.model_dump(mode="json"), "model": llm.VOICE,
                               "date": date.today().isoformat(),
                               "voice": "sample field note in Hunter Hagedorn's own voice"}, indent=1))
    print(f"heard: {heard}\nmissing: {rec.missing}\n-> {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "video" / "hunter" / "note.m4a")
