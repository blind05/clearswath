"""Cuts the demo video from the recorder's takes, following docs/video/SCRIPT.md. Video tooling only: ffmpeg + PIL.

uv run python scripts/record_demo.py           # first: fresh takes and beats.json in data/video/
uv run python scripts/cut_video.py [--script docs/video/cuts/B.md]    # picture, plus cut_timeline.json
uv run python scripts/score_video.py [--script ...] [--vo voiceover.wav]  # music, sound, mix, final MP4

The script's Scene column sets the order: each scene below is one VO line.

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


def caption_png(text: str, path: Path, right: bool = False, size: int = 44) -> Path:
    """A lower-left caption: ink on a white bar, the app's own type. right: lower-right, clear of a zoomed side panel."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f, room = font(600, size), W - 460 - 96
    if d.textlength(text, font=f) > room:  # a long line (the model roster) shrinks to fit rather than run off
        f = font(600, int(size * room / d.textlength(text, font=f)))
    w = d.textlength(text, font=f)
    x = W - 60 - w - 56 if right else 460  # over the map, clear of the app's side panel
    top = H - 80 - int(f.size * 2.05)
    d.rectangle([x, top, x + w + 56, H - 80], fill=(255, 255, 255, 235))
    d.rectangle([x, top, x + 6, H - 80], fill=SPRAY + (255,))
    d.text((x + 30, top + int(f.size * 0.27)), text, font=f, fill=INK)
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


def receipt(pdf: Path, page: int, sentences: list[str], out: Path) -> tuple[Path, list]:
    """A label page at twice the frame's size (sharp under the camera) with exact sentences highlighted; returns the
    PNG and each sentence's box in the 1920x1080 frame."""
    p = pymupdf.open(pdf)[page - 1]
    marks = []
    for text in sentences:
        quads = p.search_for(text, quads=True)
        if not quads:
            sys.exit(f"not on {pdf.name} page {page}: {text}")
        p.add_highlight_annot(quads)
        r = pymupdf.Rect()
        for q in quads:
            r |= q.rect
        marks.append(tuple(r))
    if not sentences:  # no sentence to mark: the page's biggest paragraph
        marks.append(max((b[:4] for b in p.get_text("blocks")), key=lambda b: (b[2] - b[0]) * (b[3] - b[1])))
    k = (2 * H - 80) / p.rect.height  # pixels per point at 2x
    pix = p.get_pixmap(matrix=pymupdf.Matrix(k, k), annots=True)
    img = Image.new("RGB", (2 * W, 2 * H), PAGE)
    x0, y0 = (2 * W - pix.width) // 2, 40
    img.paste(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), (x0, y0))
    img.save(out)
    return out, [((x0 + m[0] * k) / 2, (y0 + m[1] * k) / 2, (m[2] - m[0]) * k / 2, (m[3] - m[1]) * k / 2) for m in marks]


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


FULL = (0, 0, W, H)
WIDEN = 0.0  # 0 = the boxes as given; 1 = always the full frame (--widen pulls every camera move out by that share)


def cam(src: Path | tuple[float, float], seconds: float, keys: list[tuple[float, tuple]], out: Path,
        caption: Path | None = None, speed: float = 1.0, lead: float = 0.0) -> Path:
    """A camera move over a screenshot (src a PNG) or a stretch of the recording (src (start, end)): keys are
    (time, (x, y, w, h)) in the 1920x1080 frame, 16:9 boxes the camera eases between, so the part that matters fills
    the screen and stays readable. speed > 1 plays the recording faster; seconds and key times are the recording's.
    lead holds the recording's first frame that long first, so an action lands on the word that names it."""
    seconds = seconds / speed + lead
    # every box is pulled toward the full frame by WIDEN, except a tight one (a 5th item, "tight"): a proof detail
    keys = [(t / speed, r[:4] if len(r) == 5 else tuple(v + (f - v) * WIDEN for v, f in zip(r, FULL))) for t, r in keys]
    def at(vals):  # piecewise smoothstep between keys, on the output time
        t, expr = "(on/30)", str(vals[-1])
        for (t0, _), (t1, _), v0, v1 in reversed(list(zip(keys, keys[1:], vals, vals[1:]))):
            p = f"clip(({t}-{t0})/{max(t1 - t0, 0.01)},0,1)"
            expr = f"if(lt({t},{t1}),{v0}+({v1}-{v0})*{p}*{p}*(3-2*{p}),{expr})"
        return expr
    z = at([round(W / r[2], 4) for _, r in keys])
    cx, cy = at([2 * (r[0] + r[2] / 2) for _, r in keys]), at([2 * (r[1] + r[3] / 2) for _, r in keys])
    vf = (f"fps={FPS},scale={W * 2}:{H * 2},zoompan=z='{z}':x='clip({cx}-iw/zoom/2,0,iw-iw/zoom)'"
          f":y='clip({cy}-ih/zoom/2,0,ih-ih/zoom)':d=1:s={W}x{H}:fps={FPS}")
    if isinstance(src, tuple):
        inputs = ["-ss", src[0], "-to", src[1], "-i", VID / "demo.webm"]
        vf = f"setpts=PTS/{speed},tpad=start_mode=clone:start_duration={lead}," + vf
    else:
        inputs = ["-loop", "1", "-framerate", FPS, "-t", seconds, "-i", src]
    if caption:
        inputs += ["-i", caption]
        vf = f"[0:v]{vf}[v];[v][1:v]overlay=0:0"
    run(["ffmpeg", "-y", *inputs, "-filter_complex" if caption else "-vf", vf, "-t", seconds, *ENC, out])
    return out


def work_dir(script: Path) -> Path:
    """Where a cut's takes, voice and films go: data/video/ for SCRIPT.md, data/video/cuts/<name>/ for an option."""
    return VID if script.name == "SCRIPT.md" else VID / "cuts" / script.stem


def scenes(script: Path) -> list[str]:
    """The script's scene column, in order: one VO line per scene."""
    import re
    return [r.split("|")[1].strip() for r in script.read_text().splitlines() if re.match(r"^\| [a-z]+ \|", r)]


def main(script: Path) -> None:
    work = work_dir(script)
    work.mkdir(parents=True, exist_ok=True)
    out = work / "clearswath.mp4"
    beats = {b["name"]: b for b in json.loads((VID / "beats.json").read_text())}
    prev = {b["name"]: e["end"] for b, e in zip(list(beats.values())[1:], beats.values())}  # each beat's lead-in
    shot = lambda n: VID / f"{beats[n]['beat']:02d}-{n}.png"  # noqa: E731
    tmp = Path(tempfile.mkdtemp())
    cap = lambda text, name: caption_png(text, tmp / f"cap-{name}.png")  # noqa: E731
    order = scenes(script)
    # with narration (scripts/narrate_video.py), each shot lasts at least its line plus a breath
    manifest = work / "voice" / "manifest.json"
    vo = {order[int(k) - 1]: v for k, v in json.loads(manifest.read_text())["seconds"].items()} if manifest.exists() else {}
    hunter = manifest.exists() and json.loads(manifest.read_text())["voice"] == "Hunter Hagedorn"  # his takes (use_voice.py)
    fit = lambda n, fixed, default: max(default if not vo else 0, vo.get(n, 0) + 0.8 - fixed, 1.5)  # noqa: E731
    span = lambda a, b: b - a  # noqa: E731

    def hook():  # zoom into the spray cells, as recorded, then hold
        c = cap("9.7 of 24.1 acres marked to spray", "hook")
        lead = span(prev["montana-spot-spray"], beats["montana-spot-spray"]["end"])
        return [clip(prev["montana-spot-spray"], beats["montana-spot-spray"]["end"], tmp / "01a.mp4", c),
                still(shot("montana-spot-spray"), fit("hook", lead, 2.0), tmp / "01b.mp4", c)]

    def label():  # label pages, not page 1: that is EPA's cover letter
        c = cap("A pesticide label is the law", "label")
        return [still(p, fit("label", 0, 20.0) / 4, tmp / f"02{i}.mp4", c, zoom=1.04)
                for i, p in enumerate(label_pages(ROOT / "data" / "labels" / "tordon_22k.pdf", [11, 14, 16, 28], tmp))]

    def plan():  # the demo, from the landing page to the plan
        c = cap("Muse Spark reads the label. Code decides.", "plan")
        lead = span(beats["landing"]["start"], beats["montana-plan"]["end"])
        return [clip(beats["landing"]["start"], beats["montana-plan"]["end"], tmp / "03a.mp4", c),
                still(shot("montana-plan"), fit("plan", lead, 8.0), tmp / "03b.mp4", c)]

    def dropped():  # a rule whose quote isn't on the page is listed and not used
        return [still(shot("montana-dropped"), fit("dropped", 0, 6.0), tmp / "03c.mp4",
                      cap("Quote not on the page: rule not used", "dropped"), zoom=1.0)]

    def scout(name="scout", alone=0.4):  # SAM alone, then with Muse Wonder's boxes (a real saved run, South Dakota)
        return [still(card([("SAM 3.1, asked for \"tree line\"", 600, 52), ("finds 17% of trees on 20 test tiles", 400, 40),
                            ("here: none", 400, 40)], tmp / "scout-a.png", ROOT / "docs/video/scout-sam-text-only.png"),
                      fit(name, 0, 30.0) * alone, tmp / "04a.mp4", zoom=1.02),
                still(card([("Muse Wonder boxes", 600, 52), ("the tree lines it sees;", 600, 52), ("SAM 3.1 outlines them", 600, 52),
                            ("62-69% of trees found, 3 runs", 400, 40)], tmp / "scout-b.png", ROOT / "docs/video/scout-wonder-sam.png"),
                      fit(name, 0, 30.0) * (1 - alone), tmp / "04b.mp4", zoom=1.02)]

    def weeds():  # the spray cells, close
        return [still(shot("montana-spot-spray"), fit("weeds", 0, 25.0), tmp / "05.mp4",
                      cap("90% of spurge found, 40% of the block sprayed", "weeds"), zoom=1.12)]

    def files():  # files for the drone
        c = cap("Planning files: DJI, GeoJSON, KML", "files")
        lead = span(prev["montana-dji-export"], beats["montana-dji-export"]["end"])
        return [clip(prev["montana-dji-export"], beats["montana-dji-export"]["end"], tmp / "06a.mp4", c),
                still(shot("montana-dji-export"), fit("files", lead, 11.0), tmp / "06b.mp4", c)]

    def record():  # the demo's saved voice note (a synthetic voice, said in the VO and on the page)
        return [still(shot("montana-voice-record"), fit("record", 0, 12.0), tmp / "06v.mp4",
                      cap("A spoken note fills the record", "record"), zoom=1.04)]

    def creek():  # South Dakota: the creek buffer, the ULV rule, the corrected outline
        lead = span(prev["dakota-creek-buffer"], beats["dakota-corrected-go"]["end"])
        return [clip(prev["dakota-creek-buffer"], beats["dakota-why-here"]["end"], tmp / "07a.mp4",
                     cap("150 ft from water, page 14", "creek")),
                clip(beats["dakota-why-here"]["end"], beats["dakota-corrected-go"]["end"], tmp / "07c.mp4",
                     cap("Untick the ULV rule, pull the edge back", "fix")),
                still(shot("dakota-corrected-go"), max(3.0, fit("creek", lead, 8.0)), tmp / "07b.mp4",
                      cap("No conflicts in checked rules", "go"))]

    def agent():  # how it decided
        return [still(shot("montana-agent"), fit("agent", 0, 15.0), tmp / "08.mp4",
                      cap("Muse Spark 1.3 · Muse Wonder · SAM 3.1 · Muse Voice Transcribe · DINOv2 · Muse Spark Open", "models"))]

    def end():
        return [still(card([("ClearSwath", 600, 96), ("Models read and see. Tested code plans.", 400, 44), ("The applicator decides.", 400, 44), ("", 400, 30),
                            ("clearswath.onrender.com", 400, 40), ("github.com/blind05/clearswath", 400, 40)],
                           tmp / "end.png"), max(6.0, fit("end", 0, 10.0)), tmp / "09.mp4", zoom=1.0)]

    # Cut D: a camera that follows the action. Boxes are where things sit in the 1920x1080 recording.
    MAP, SD = (400, 52, 1520, 855), (0, 60, 1100, 619)
    T = lambda x, y, w: (x, y, w, w * 9 / 16, "tight")  # noqa: E731  # a proof detail, as close as it reads  # the map alone; South Dakota's decision and its rules
    CARD, ULV = (560, 40, 1280, 720), (0, 60, 1100, 619)  # the "held back here" card; the conditional rule boxes
    Q450, Q150 = (955, 110, 640, 360), (955, 300, 640, 360)  # the card's two sentences, close
    GO, MT = (0, 40, 1280, 720), (0, 60, 1100, 619)  # "No conflicts" and the map; Montana's decision
    MT_WHY, REJECT = (0, 440, 1100, 619), (0, 420, 1000, 563)  # Montana's Why and Muse Spark's answer; rules not applied
    FILES, NOTE = (0, 400, 1000, 563), (0, 420, 1000, 563)  # spray volume and files; the filled record
    b_ = lambda n: (beats[n]["start"], beats[n]["end"])  # noqa: E731
    capr = lambda text, name: caption_png(text, tmp / f"capr-{name}.png", right=True)  # noqa: E731
    hold = lambda name, used: max(fit(name, used, 2.0), 1.5)  # noqa: E731  # what the line needs beyond the clip
    needs = lambda name, used: not vo or vo.get(name, 0) + 0.8 - used > 0.6  # noqa: E731  # else no still: no flicker
    # a clip longer than its line plays faster, up to 2x, so the picture doesn't wait on silence
    pace = lambda name, used: min(2.0, max(1.0, used / (vo[name] + 0.8))) if name in vo else 1.0  # noqa: E731

    def drift(box, n):  # a hold that keeps moving: in by 8% about the box's centre over n seconds
        x, y, w, h = box
        return [(0, box), (n, (x + w * 0.04, y + h * 0.04, w * 0.92, h * 0.92))]

    def opening():  # the whole Montana field and its spray cells, still, then in to the cells
        c = caption_png("9.7 of 24.1 acres marked to spray", tmp / "capr-hook.png", right=True, size=64)
        n = fit("opening", 0, 8.0)
        return [cam(shot("montana-plan"), 3.5, [(0, MAP), (3.5, (430, 70, 1440, 810))], tmp / "01a.mp4", c),
                cam(shot("montana-spot-spray"), n - 3.5, [(0, MAP), (n - 3.5, (640, 230, 1120, 630))], tmp / "01b.mp4",
                    caption_png("Pink: 9.7 acres to spray. Blue: the creek.", tmp / "capr-key.png", right=True, size=60))]

    def problem():  # the label, a page at a time
        c = capr("30 pages of rules. Not one map.", "problem")
        parts = []
        for i, n in enumerate([11, 28]):  # each page, in to its densest paragraph, then down it
            png, (b,) = receipt(ROOT / "data" / "labels" / "tordon_22k.pdf", n, [], tmp / f"page{n}.png")
            w = max(b[2], 900)
            box = (b[0] + b[2] / 2 - w / 2, max(0, b[1] - 20), w, w * 9 / 16)
            low = (box[0], min(H - box[3], box[1] + box[3] * 0.8), w, box[3])
            n_ = fit("problem", 0, 12.0) / 2
            parts.append(cam(png, n_, [(0, FULL), (0.3, FULL), (n_ * 0.4, box), (n_, low)], tmp / f"02{i}.mp4", c))
        return parts

    def field():  # South Dakota, drawn to the creek: the decision
        n = fit("field", 0, 6.0)  # the field and its held-back strip by the creek, then the decision
        return [cam(shot("dakota-creek-buffer"), n, [(0, FULL), (n * 0.45, (400, 40, 1400, 788)),
                                                      (n * 0.45 + 1.2, SD)],
                    tmp / "07s.mp4", capr("Adjust: 11.1 of 37 acres held back", "field"))]

    def why():  # glide to the strip, click, the card quotes the label
        a, e = beats["dakota-creek-buffer"]["end"], beats["dakota-why-here"]["end"]
        card = beats["dakota-why-here"]["start"] - a
        c = capr("Warrior II label, page 14", "why")
        n = hold("why", (e - a) / pace("why", e - a))  # the 150 ft sentence as it's said, then up to the 450 ft one
        return [cam((a, e), e - a, [(0, SD), (0.7, FULL), (card - 0.2, FULL), (card + 0.7, CARD)], tmp / "07a.mp4", c,
                    speed=pace("why", e - a))] + (
                [cam(shot("dakota-why-here"), n, [(0, CARD), (0.8, T(900, 90, 760)), (n, T(920, 100, 720))],
                     tmp / "07w.mp4", c)] if needs("why", (e - a) / pace("why", e - a)) else [])

    def proof():  # the same sentences on the label's own page 14
        rule = ("Do not apply within {} feet of aquatic habitats (such as, but not limited to, lakes, reservoirs, "
                "rivers, streams, marshes, ponds, estuaries, and commercial fish ponds).")
        png, (r450, r150) = receipt(ROOT / "data" / "labels" / "warrior_ii.pdf", 14,
                                    [rule.format(450), rule.format(150)], tmp / "receipt.png")
        x0, y0 = r450[0] - 90, r450[1] - 60  # the bullet headings sit left of the sentences
        w = r150[0] + r150[2] + 40 - x0
        box = (x0, y0 + (r150[1] + r150[3] + 40 - y0) / 2 - w * 9 / 32, w, w * 9 / 16)
        return [cam(png, fit("proof", 0, 5.0), [(0, FULL), (0.4, FULL), (1.6, box)], tmp / "07p.mp4",
                    capr("Warrior II label PDF, page 14", "proof"))]

    def untick():  # the ULV rule is conditional: untick it, on the words "Untick it"
        a, e = b_("dakota-why-here")[1], beats["dakota-ulv-unticked"]["end"]
        c = capr("Untick what doesn't apply", "untick")
        lead = 2.1  # Hunter's take says "Untick it" 2.3 s in; the click is at the clip's start (re-measure for a new take)
        sp = min(2.0, max(1.0, (e - a) / max(vo.get("untick", 0) + 0.8 - lead, 0.1))) if vo else 1.0
        used = (e - a) / sp + lead
        return [cam((a, e), e - a, [(0, CARD), (0.8, ULV), (lead, ULV), (lead + 0.8, T(0, 110, 800))], tmp / "07c.mp4", c,
                    speed=sp, lead=lead)] + (
                [cam(shot("dakota-ulv-unticked"), hold("untick", used), [(0, T(0, 110, 800))], tmp / "07u.mp4", c)]
                if needs("untick", used) else [])

    def clear():  # the corrected outline
        a, e = beats["dakota-ulv-unticked"]["end"], beats["dakota-corrected-go"]["end"]
        c = capr("Redrawn: all 31.2 acres clear", "go")
        return [cam((a, e), e - a, [(0, ULV), (0.8, GO)], tmp / "07g.mp4", c, speed=pace("clear", e - a))] + (
                [cam(shot("dakota-corrected-go"), hold("clear", (e - a) / pace("clear", e - a)),
                     drift(GO, hold("clear", (e - a) / pace("clear", e - a))), tmp / "07b.mp4", c)]
                if needs("clear", (e - a) / pace("clear", e - a)) else [])

    def spurge():  # the weed map, close
        n = fit("spurge", 0, 10.0)  # in to the weed patches, then across to the creek strip they stop at
        return [cam(shot("montana-spot-spray"), n, [(0, MAP), (n * 0.4, (480, 300, 1200, 675)),
                                                     (n * 0.95, (700, 120, 1200, 675))],
                    tmp / "05.mp4", capr("Found 90% of spurge plots, flagged 10% of clean ones", "weeds"))]

    def reads():  # Muse Spark's rules, each with its sentence
        n = fit("reads", 0, 8.0)
        return [cam(shot("montana-plan"), n, [(0, MT), (n * 0.4, MT), (n * 0.4 + 1, T(0, 600, 760))], tmp / "03b.mp4",
                    capr("Muse Spark reads the label. Code decides.", "plan"))]

    def rejected():  # a quote that isn't on the page
        n = fit("rejected", 0, 6.0)
        return [cam(shot("montana-dropped"), n, [(0, REJECT), (1.0, T(0, 520, 700)), (n, T(0, 540, 660))], tmp / "03c.mp4",
                    capr("Quote not on the page: rule not used", "dropped"))]

    def hazards():  # the scout, the camera moving in to each picture
        n, parts = fit("hazards", 0, 20.0), []
        for part, share, lines, img in [
                ("04a", 0.35, [("SAM 3.1 alone", 600, 52), ("17% of trees found", 400, 40), ("on 20 test tiles", 400, 40),
                               ("here: none outlined", 400, 40)],
                 "scout-sam-text-only.png"),
                ("04b", 0.65, [("Muse Wonder boxes", 600, 52), ("the tree lines it sees;", 600, 52),
                              ("SAM 3.1 outlines them", 600, 52), ("62-69% of trees found, 3 runs", 400, 40)],
                 "scout-wonder-sam.png")]:
            box = (100, 50, W - 160, (W - 160) * 9 / 16)  # a gentle push that keeps the words and the picture whole
            png = card(lines, tmp / f"{part}.png", ROOT / "docs" / "video" / img)
            parts.append(cam(png, n * share, [(0, FULL), (n * share * 0.35, FULL), (n * share * 0.9, box)],
                             tmp / f"{part}.mp4"))
        return parts

    def export():  # the spray volume check and the files
        a, e = prev["montana-dji-export"], beats["montana-dji-export"]["end"]
        c = capr("15 L/ha refused, 50 accepted: the label's minimum is 18.7", "files")
        return [cam((a, e), e - a, [(0, FILES), (1.0, T(0, 480, 700))], tmp / "06a.mp4", c)] + (
                [cam(shot("montana-dji-export"), hold("export", e - a), [(0, T(0, 480, 700))], tmp / "06b.mp4", c)] if needs("export", e - a) else [])

    REC = (0, 260, 1200, 675)  # the record form, mid-left

    def notes():  # the record form; with a live take, the line ends on the click of "Record a note"
        n = fit("notes", 0, 5.0)
        if "montana-note-recording" not in beats:
            return [cam(shot("montana-voice-record"), n, drift((0, 260, 1100, 619), n), tmp / "06v.mp4",
                        capr("A spoken note fills the record", "record"))]
        a, e = beats["montana-voice-record"]["end"], beats["montana-note-recording"]["start"]
        return [cam((a, e), e - a, [(0, REC)], tmp / "06v.mp4", capr("A spoken note fills the record", "record"),
                    lead=max(0.0, n - (e - a)))]

    def fieldnote():  # Hunter's note: recorded on the page as it plays, then filled live, then what was heard
        if "montana-note-recording" not in beats:
            n = fit("fieldnote", 0, 10.0)
            return [cam(shot("montana-voice-record"), n, [(0, (0, 380, 1000, 563)), (n * 0.85, (0, 517, 1000, 563))],
                        tmp / "06f.mp4", capr("Sample note in Hunter's voice; the applicator is made up" if hunter
                                              else "Sample note: a synthetic stand-in voice", "fieldnote"))]
        r, st, fl = beats["montana-note-recording"]["start"], beats["montana-note-stopped"]["start"], beats["montana-note-filled"]
        return [cam((r, st), st - r, [(0, T(0, 300, 1000))], tmp / "06f.mp4",
                    capr("Recorded on the page: Hunter's voice, a made-up sample job", "fieldnote")),
                cam((st, fl["start"]), fl["start"] - st, [(0, T(0, 300, 1000)), (2.0, REC)],
                    tmp / "06g.mp4", capr("Muse Voice Transcribe hears it; Muse Spark fills the record", "filling"),
                    speed=4.0),
                cam(shot("montana-note-filled"), 5.0, [(0, REC), (1.2, T(0, 620, 780)), (5.0, T(0, 640, 760))], tmp / "06h.mp4",
                    capr("Filled from his words; anything unsaid is Missing", "filled"))]

    def close():
        return [still(card([("ClearSwath", 600, 96), ("Find the weeds. Read the label.", 400, 48),
                            ("Spray only where both say yes.", 400, 48), ("", 400, 24),
                            ("Muse Spark 1.3 · Muse Spark Open on Baseten · Muse Wonder · SAM 3.1", 400, 30),
                            ("Muse Voice Transcribe · DINOv2", 400, 30), ("", 400, 24),
                            ("clearswath.onrender.com   ·   github.com/blind05/clearswath", 400, 36),
                            ("Decision support, not clearance to spray. Planning files not flight-tested.", 400, 26)],
                           tmp / "close.png"), max(5.0, fit("close", 0, 10.0)), tmp / "09.mp4", zoom=1.03)]

    build = {f.__name__: f for f in (hook, label, plan, dropped, scout, weeds, files, record, creek, agent, end,
                                     opening, problem, field, why, proof, untick, clear, spurge, reads, rejected, hazards, export,
                                     notes, fieldnote, close)}
    parts, lines = [], []  # lines: the part each VO line starts on, for scripts/score_video.py
    for name in order:
        made = build[name]()
        lines.append(made[0].stem)
        parts += made

    timeline, at = [], 0.0  # where each part starts, for scripts/score_video.py
    for p in parts:
        timeline.append({"part": p.stem, "start": round(at, 3)})
        at += float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                   capture_output=True, text=True).stdout)
    (work / "cut_timeline.json").write_text(json.dumps({"duration": round(at, 3), "parts": timeline, "lines": lines},
                                                       indent=1))
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
    ap.add_argument("--script", type=Path, default=ROOT / "docs" / "video" / "SCRIPT.md",
                    help="an option's script, docs/video/cuts/<name>.md, cuts into data/video/cuts/<name>/")
    ap.add_argument("--widen", type=float, default=0.8, help="pull every camera move toward the full frame (0-1)")
    a = ap.parse_args()
    WIDEN = a.widen
    if not (VID / "beats.json").exists():
        sys.exit("run scripts/record_demo.py first")
    main(a.script)
