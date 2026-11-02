"""Mix a locked picture cut, original music, voiceover and optional sound effects.

Example (run after editing the picture):
    python scripts/mix_demo_audio.py \
        --video data/video/cut.mp4 \
        --voice data/video/voice.wav \
        --music data/video/audio/clearswath_music_under_vo.mp3 \
        --sfx data/video/audio/clearswath_sfx_timeline.mp3 \
        --output data/video/clearswath_submission.mp4

No footage or narration is fabricated. Requires ffmpeg and ffprobe.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--video", type=Path, required=True, help="Visually edited and timed picture cut")
    p.add_argument("--voice", type=Path, help="Recorded narration, ideally WAV")
    p.add_argument("--music", type=Path, required=True, help="Original or appropriately licensed soundtrack")
    p.add_argument("--sfx", type=Path, help="Optional sync-designed effects track")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            p.error(f"{name} is not available")
    for f in (a.video, a.voice, a.music, a.sfx):
        if f and not f.is_file():
            p.error(f"Missing file: {f}")

    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(a.video)],
        text=True,
    ).strip())
    if duration > 179.5:
        p.error(f"Video is {duration:.1f}s: reduce the picture cut below 3 minutes first")

    inputs = ["-i", str(a.video), "-stream_loop", "-1", "-i", str(a.music)]
    graph = [f"[1:a]volume=0.85,afade=t=in:st=0:d=1,atrim=duration={duration}[music]"]
    stems = ["[music]"]
    index = 2
    if a.voice:
        inputs += ["-i", str(a.voice)]
        graph.append(
            f"[{index}:a]highpass=f=80,"
            "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=180,"
            "volume=1.0[voice]"
        )
        stems.append("[voice]")
        index += 1
    if a.sfx:
        inputs += ["-i", str(a.sfx)]
        graph.append(f"[{index}:a]volume=0.48,atrim=duration={duration}[fx]")
        stems.append("[fx]")
    graph.append(
        "".join(stems)
        + f"amix=inputs={len(stems)}:duration=longest:dropout_transition=0:"
        + f"normalize=0,atrim=duration={duration},alimiter=limit=0.91[aout]"
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y", *inputs, "-filter_complex", ";".join(graph),
        "-map", "0:v:0", "-map", "[aout]", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-shortest", str(a.output),
    ], check=True)
    print(f"Wrote {a.output} ({duration:.1f}s). Listen and verify before submission.")


if __name__ == "__main__":
    main()
