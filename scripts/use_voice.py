"""Hunter's own narration in place of the synthetic voice. Video tooling only: ffmpeg.

uv run python scripts/use_voice.py [data/video/hunter] [--script docs/video/cuts/E.md]

Takes shot1..shotN in any format ffmpeg reads (m4a, wav, mp3), one per line of docs/video/RECORD_SCRIPT.md, and
writes what scripts/narrate_video.py writes: <cut>/voice/shot<n>.wav (24 kHz mono, quiet trimmed to 0.25 s at
each end) and manifest.json. Then run scripts/cut_video.py and scripts/score_video.py as usual.
"""

import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "data" / "video"
# trim leading and trailing quiet, then pad 0.25 s each side, like narrate_video.write
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
        "adelay=250|250,apad=pad_dur=0.25")


def main(src: Path, script: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from cut_video import work_dir
    out = work_dir(script) / "voice"
    takes = sorted((p for p in src.iterdir() if p.stem.startswith("shot") and p.stem[4:].isdigit()),
                   key=lambda p: int(p.stem[4:]))
    if not takes:
        sys.exit(f"no shot1..shotN files in {src}")
    out.mkdir(parents=True, exist_ok=True)
    seconds = {}
    for p in takes:
        n = int(p.stem[4:])
        wav = out / f"shot{n}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-af", TRIM, "-ac", "1", "-ar", "24000",
                        "-c:a", "pcm_s16le", str(wav)], check=True)
        with wave.open(str(wav)) as w:
            seconds[n] = round(w.getnframes() / w.getframerate(), 2)
    (out / "manifest.json").write_text(json.dumps({"voice": "Hunter Hagedorn", "engine": "recorded",
                                                   "seconds": seconds}, indent=1))
    print(f"{len(seconds)} takes, {sum(seconds.values()):.1f} s: {seconds}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", type=Path, default=VID / "hunter")
    ap.add_argument("--script", type=Path, default=ROOT / "docs" / "video" / "SCRIPT.md")
    a = ap.parse_args()
    main(a.src, a.script)
