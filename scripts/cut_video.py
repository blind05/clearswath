"""Cuts the demo video from the recorder's takes, following docs/video/SCRIPT.md. Video tooling only: ffmpeg + PIL.

uv run python scripts/record_demo.py           # first: fresh takes and beats.json in data/video/
uv run python scripts/cut_video.py [--out data/video/clearswath.mp4]    # picture, plus cut_timeline.json
uv run python scripts/score_video.py [--vo voiceover.wav]               # music, sound, mix, final MP4

Every shot is the real app (a segment of the recording, or a screenshot held with a slow zoom) or a real saved run;
the only things added are the script's captions and the end card.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "data" / "video"
W, H, FPS = 1920, 1080, 30
INK, PAGE, SPRAY = (30, 43, 36), (242, 244, 241), (196, 18, 122)


def font(weight: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(VID / f"plex-sans-{weight}.ttf"), size)


def caption_png(text: str, path: Path) -> Path:
    """A lower-left caption: ink on a white bar, the app's own type."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(600, 44)
    w, x = d.textlength(text, font=f), 460  # over the map, clear of the app's 400 px side panel
    d.rectangle([x, H - 170, x + w + 56, H - 80], fill=(255, 255, 255, 235))
    d.rectangle([x, H - 170, x + 6, H - 80], fill=SPRAY + (255,))
    d.text((x + 30, H - 158), text, font=f, fill=INK)
    img.save(path)
    return path


def card(lines: list[tuple[str, int, int]], path: Path, image: Path | None = None) -> Path:
    """A plain card on the page colour: (text, weight, size) lines, optionally beside an image."""
    img = Image.new("RGB", (W, H), PAGE)
    d = ImageDraw.Draw(img)
    x, y = 140, 330
    if image:
        pic = Image.open(image).convert("RGB")
        pic.thumbnail((900, 900))
        img.paste(pic, (W - pic.width - 120, (H - pic.height) // 2))
        y = 360
    for text, weight, size in lines:
        d.text((x, y), text, font=font(weight, size), fill=INK)
        y += int(size * 1.45)
    img.save(path)
    return path


def label_pages(pdf: Path, pages: list[int], out: Path) -> list[Path]:
    """Label pages rendered on the page colour, a tilted stack feel kept simple: one page per frame."""
    doc, paths = pymupdf.open(pdf), []
    for n in pages:
        pix = doc[n - 1].get_pixmap(dpi=110)
        page = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        page.thumbnail((W - 400, H - 120))
        img = Image.new("RGB", (W, H), PAGE)
        img.paste(page, ((W - page.width) // 2, (H - page.height) // 2))
        paths.append(out / f"label-p{n}.png")
        img.save(paths[-1])
    return paths


def run(cmd: list) -> None:
    subprocess.run([str(c) for c in cmd], check=True, capture_output=True)


ENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", FPS, "-preset", "medium", "-crf", "20", "-an"]


def still(png: Path, seconds: float, out: Path, caption: Path | None = None, zoom: float = 1.06) -> Path:
    """A screenshot held for `seconds`, zooming slowly towards the centre (scaled up first so it doesn't shimmer)."""
    frames = int(seconds * FPS)
    step = (zoom - 1) / frames
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='1+{step:.6f}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={FPS}")
    inputs = ["-loop", "1", "-t", seconds, "-i", png]
    if caption:
        inputs += ["-i", caption]
        vf = f"[0:v]{vf}[v];[v][1:v]overlay=0:0"
    run(["ffmpeg", "-y", *inputs, "-filter_complex" if caption else "-vf", vf, "-t", seconds, *ENC, out])
    return out


def clip(start: float, end: float, out: Path, caption: Path | None = None) -> Path:
    """A segment of the screen recording, as it happened."""
    inputs = ["-ss", start, "-to", end, "-i", VID / "demo.webm"]
    vf = f"scale={W}:{H},fps={FPS}"
    if caption:
        inputs += ["-i", caption]
        vf = f"[0:v]{vf}[v];[v][1:v]overlay=0:0"
    run(["ffmpeg", "-y", *inputs, "-filter_complex" if caption else "-vf", vf, *ENC, out])
    return out


def main(out: Path) -> None:
    beats = {b["name"]: b for b in json.loads((VID / "beats.json").read_text())}
    prev = {b["name"]: e["end"] for b, e in zip(list(beats.values())[1:], beats.values())}  # each beat's lead-in
    shot = lambda n: VID / f"{beats[n]['beat']:02d}-{n}.png"  # noqa: E731
    tmp = Path(tempfile.mkdtemp())
    cap = lambda text, name: caption_png(text, tmp / f"cap-{name}.png")  # noqa: E731
    parts = []
    # with narration (scripts/narrate_video.py), each shot lasts at least its line plus a breath
    manifest = VID / "voice" / "manifest.json"
    vo = {int(k): v for k, v in json.loads(manifest.read_text())["seconds"].items()} if manifest.exists() else {}
    fit = lambda n, fixed, default: max(default if not vo else 0, vo.get(n, 0) + 0.8 - fixed, 1.5)  # noqa: E731
    span = lambda a, b: b - a  # noqa: E731

    # 1. hook: zoom into the spray cells, as recorded, then hold
    c = cap("9.7 of 24.1 acres marked to spray", "hook")
    lead = span(prev["montana-spot-spray"], beats["montana-spot-spray"]["end"])
    parts += [clip(prev["montana-spot-spray"], beats["montana-spot-spray"]["end"], tmp / "01a.mp4", c),
              still(shot("montana-spot-spray"), fit(1, lead, 2.0), tmp / "01b.mp4", c)]
    # 2. the label
    c = cap("A pesticide label is the law", "label")
    # label pages, not page 1: that is EPA's cover letter
    for i, p in enumerate(label_pages(ROOT / "data" / "labels" / "tordon_22k.pdf", [11, 14, 16, 28], tmp)):
        parts.append(still(p, fit(2, 0, 20.0) / 4, tmp / f"02{i}.mp4", c, zoom=1.04))
    # 3. the demo, from the landing page to the plan
    c = cap("Muse Spark reads the label. Code decides.", "plan")
    lead = span(beats["landing"]["start"], beats["montana-plan"]["end"])
    parts += [clip(beats["landing"]["start"], beats["montana-plan"]["end"], tmp / "03a.mp4", c),
              still(shot("montana-plan"), fit(3, lead, 8.0), tmp / "03b.mp4", c)]
    # 4. the scout: SAM alone, then with Muse Wonder's boxes (a real saved run on the South Dakota tile)
    parts.append(still(card([("SAM 3.1, asked for \"tree line\"", 600, 52), ("finds 17% of trees on 20 test tiles", 400, 40),
                             ("here: none", 400, 40)], tmp / "scout-a.png", ROOT / "docs/video/scout-sam-text-only.png"),
                       fit(4, 0, 30.0) * 0.4, tmp / "04a.mp4", zoom=1.02))
    parts.append(still(card([("Muse Wonder boxes each one,", 600, 52), ("SAM 3.1 outlines it", 600, 52),
                             ("62-69% of trees found, 3 runs", 400, 40)], tmp / "scout-b.png", ROOT / "docs/video/scout-wonder-sam.png"),
                       fit(4, 0, 30.0) * 0.6, tmp / "04b.mp4", zoom=1.02))
    # 5. the spray cells, close
    parts.append(still(shot("montana-spot-spray"), fit(5, 0, 25.0), tmp / "05.mp4",
                       cap("90% of spurge found, 40% of the block sprayed", "weeds"), zoom=1.12))
    # 6. files for the drone
    c = cap("Planning files: DJI, GeoJSON, KML", "files")
    lead = span(prev["montana-dji-export"], beats["montana-dji-export"]["end"])
    parts += [clip(prev["montana-dji-export"], beats["montana-dji-export"]["end"], tmp / "06a.mp4", c),
              still(shot("montana-dji-export"), fit(6, lead, 11.0), tmp / "06b.mp4", c)]
    # 7. South Dakota: the creek buffer, the ULV rule, the corrected outline
    c = cap("150 ft from water, page 14", "creek")
    lead = span(prev["dakota-creek-buffer"], beats["dakota-corrected-go"]["end"])
    parts += [clip(prev["dakota-creek-buffer"], beats["dakota-why-here"]["end"], tmp / "07a.mp4", c),
              clip(beats["dakota-why-here"]["end"], beats["dakota-corrected-go"]["end"], tmp / "07c.mp4",
                   cap("Untick the ULV rule, pull the edge back", "fix")),
              still(shot("dakota-corrected-go"), max(3.0, fit(7, lead, 8.0)), tmp / "07b.mp4",
                    cap("No conflicts in checked rules", "go"))]
    # 8. how it decided
    parts.append(still(shot("montana-agent"), fit(8, 0, 15.0), tmp / "08.mp4",
                       cap("Muse Spark 1.3 · Muse Wonder · SAM 3.1 · DINOv2 · Muse Spark Open", "models")))
    # 9. end card
    parts.append(still(card([("ClearSwath", 600, 96), ("Models read and see. Tested code plans.", 400, 44), ("The applicator decides.", 400, 44), ("", 400, 30),
                             ("clearswath.onrender.com", 400, 40), ("github.com/blind05/clearswath", 400, 40)],
                            tmp / "end.png"), max(6.0, fit(9, 0, 10.0)), tmp / "09.mp4", zoom=1.0))

    timeline, at = [], 0.0  # where each part starts, for scripts/score_video.py
    for p in parts:
        timeline.append({"part": p.stem, "start": round(at, 3)})
        at += float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                   capture_output=True, text=True).stdout)
    (VID / "cut_timeline.json").write_text(json.dumps({"duration": round(at, 3), "parts": timeline}, indent=1))
    listing = tmp / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    silent = tmp / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", silent])
    silent.replace(out)  # picture only; scripts/score_video.py adds music, sound and the voiceover
    seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                                   capture_output=True, text=True).stdout)
    print(f"{out} ({seconds:.0f} s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=VID / "clearswath.mp4")
    a = ap.parse_args()
    if not (VID / "beats.json").exists():
        sys.exit("run scripts/record_demo.py first")
    main(a.out)
