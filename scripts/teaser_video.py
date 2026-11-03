"""A ~30 s square teaser for X, cut from the final film. Video tooling only: ffmpeg.

uv run python scripts/teaser_video.py   # after score_video.py; writes data/video/ClearSwath_teaser_square.mp4

The hook keeps its narration; the other moments play over the music alone (no sentence is cut in half).
Each segment is cropped to a square around what matters in it.
"""

import json
import subprocess
from pathlib import Path

VID = Path(__file__).resolve().parent.parent / "data" / "video"


def main() -> None:
    start = {p["part"]: p["start"] for p in json.loads((VID / "cut_timeline.json").read_text())["parts"]}
    beats = {b["name"]: b for b in json.loads((VID / "beats.json").read_text())}
    # 07a starts where the beat before the creek ends in the recording; the card opens at the why-here beat
    names = list(beats)
    lead_in = beats[names[names.index("dakota-creek-buffer") - 1]]["end"]
    why = start["07a"] + (beats["dakota-why-here"]["start"] - lead_in) - 0.3
    # (start, end, crop x on the 1920-wide frame: 440 keeps the captions, which start at x=460; audio: "mix" keeps
    # the voice, "music" doesn't)
    segments = [(0.0, start["020"] - 0.1, 440, "mix"),
                (start["04b"], start["04b"] + 6.5, 840, "music"),
                (why, start["07c"], 440, "music"),
                (start["09"], start["09"] + 6.0, 40, "music")]
    final, music = VID / "ClearSwath_Meta_Hackathon_Final.mp4", VID / "audio" / "music.wav"
    inputs, graph, labels = [], [], []
    for i, (a, b, x, audio) in enumerate(segments):
        inputs += ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(final)]
        inputs += ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(final if audio == "mix" else music)]
        v, s = 2 * i, 2 * i + 1
        graph.append(f"[{v}:v]crop=1080:1080:{x}:0,setpts=PTS-STARTPTS,fps=30[v{i}]")
        graph.append(f"[{s}:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.2,"
                     f"afade=t=out:st={b - a - 0.4:.3f}:d=0.4,asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    graph.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]")
    out = VID / "ClearSwath_teaser_square.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(graph),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    main()
