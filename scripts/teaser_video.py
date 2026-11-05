"""A ~30 s square teaser for X, cut from the final film. Video tooling only: ffmpeg.

uv run python scripts/teaser_video.py   # after score_video.py; writes data/video/ClearSwath_teaser_square.mp4

The hook keeps its narration; the other moments play over the music alone (no sentence is cut in half).
Each segment is cropped to a square around what matters in it, or fitted whole when it's already zoomed in.
"""

import json
import subprocess
from pathlib import Path

VID = Path(__file__).resolve().parent.parent / "data" / "video"


def main() -> None:
    tl = json.loads((VID / "cut_timeline.json").read_text())
    start = {p["part"]: p["start"] for p in tl["parts"]}
    after_hook = start[tl["lines"][1]]  # where the scene after the hook starts
    # (start, end, crop x on the 1920-wide frame, or None to fit the whole frame in the square; audio: "mix" keeps the
    # voice, "music" doesn't). The hook and the scout crop to the right, where the captions sit; the label card and its
    # PDF page, and the end card, are already zoomed, so they fit whole.
    segments = [(0.0, after_hook - 0.1, 840, "mix"),
                (start["07w"], start["07p"] + 4.0, None, "music"),
                (start["04b"], start["04b"] + 5.0, 840, "music"),
                (start["09"], start["09"] + 5.0, None, "music")]
    final, music = VID / "ClearSwath_Meta_Hackathon_Final.mp4", VID / "audio" / "music.wav"
    inputs, graph, labels = [], [], []
    for i, (a, b, x, audio) in enumerate(segments):
        inputs += ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(final)]
        inputs += ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(final if audio == "mix" else music)]
        v, s = 2 * i, 2 * i + 1
        frame = f"crop=1080:1080:{x}:0" if x is not None else "scale=1080:-2,pad=1080:1080:0:(oh-ih)/2:color=0xF2F4F1"
        graph.append(f"[{v}:v]{frame},setsar=1,setpts=PTS-STARTPTS,fps=30[v{i}]")
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
