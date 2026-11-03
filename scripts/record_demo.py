"""Records the demo story for the video: a .webm and a PNG per beat in data/video/. Offline: the cached demos only.

uv run python scripts/record_demo.py [--port 8766] [--slow 1.0]
Needs the dev dependency Playwright and its browser: uv add --dev playwright && uv run playwright install chromium
Starts the app itself; the agent's answer is the saved replay, so no model is called.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "video"
SIZE = {"width": 1920, "height": 1080}


def wait_for(url: str, seconds: float = 30) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"the app didn't start at {url}")


def main(port: int, slow: float) -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api:app", "--port", str(port)], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for(f"http://127.0.0.1:{port}/api/health")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport=SIZE, record_video_dir=str(OUT), record_video_size=SIZE)
            page = context.new_page()
            # headless Chromium draws no cursor: a ring that follows the mouse, so the film shows the click itself
            page.add_init_script("""addEventListener('DOMContentLoaded', () => {
                const c = Object.assign(document.createElement('div'), {style: 'position:fixed;z-index:9999;width:22px;'
                  + 'height:22px;margin:-11px 0 0 -11px;border:3px solid #fff;border-radius:50%;box-shadow:0 0 0 2px #1E2B24;'
                  + 'pointer-events:none;left:-40px;top:-40px'});
                document.body.append(c);
                addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; });
            });""")
            beat, start, beats = 0, time.time(), []

            def shot(name: str, hold: float = 2.5) -> None:
                """Holds, then screenshots; beats.json gets each beat's start and end in the video, for the edit."""
                nonlocal beat
                beat += 1
                began = time.time() - start
                page.wait_for_timeout(int(hold * 1000 * slow))
                page.screenshot(path=str(OUT / f"{beat:02d}-{name}.png"))
                beats.append({"beat": beat, "name": name, "start": round(began, 2), "end": round(time.time() - start, 2)})

            page.goto(f"http://127.0.0.1:{port}/")
            shot("landing", 3)
            # 1. Montana: the label, the stream, the spurge map and Muse Spark's saved answer
            page.get_by_role("button", name="Field and label").click()  # the form starts folded under the welcome
            page.get_by_role("checkbox", name="Ask Muse Spark to explain the plan").click()
            page.click("#demo")
            page.wait_for_selector("text=Saved Muse Spark answer", timeout=120_000)
            shot("montana-plan", 4)
            page.wait_for_timeout(int(1500 * slow))  # the map's one reveal: field, buffers and water, then weeds
            page.click(".maplibregl-ctrl-zoom-in")
            page.click(".maplibregl-ctrl-zoom-in")
            shot("montana-spot-spray", 4)
            page.click("text=How it decided")
            page.locator(".agent").scroll_into_view_if_needed()
            shot("montana-agent", 5)
            # 2. the sprayer files: the label's minimum spray volume is enforced
            page.locator("#dji-rate").scroll_into_view_if_needed()
            page.fill("#dji-rate", "50")
            shot("montana-dji-export", 3)
            # the record: the demo's saved voice note, heard by Muse Voice Transcribe and filled by Muse Spark
            page.get_by_text("Saved voice note").scroll_into_view_if_needed()
            shot("montana-voice-record", 4)
            # 3. South Dakota cropland: the creek buffer, then the corrected outline
            page.get_by_role("button", name="Field and label").click()  # the form folds away after a plan
            page.get_by_role("checkbox", name="Ask Muse Spark to explain the plan").click()
            page.click("#demo-switch")
            page.wait_for_selector("text=Show the corrected field", timeout=60_000)
            shot("dakota-creek-buffer", 4)
            # click inside the creek strip: the map says which label sentences hold that spot back
            strip = page.evaluate("""() => {
                const f = window.__clearswathMap.querySourceFeatures('reasons');
                const ring = f[f.length - 1].geometry.coordinates.flat(Infinity);
                const xs = ring.filter((_, i) => i % 2 === 0), ys = ring.filter((_, i) => i % 2 === 1);
                return [xs.reduce((a, b) => a + b) / xs.length, ys.reduce((a, b) => a + b) / ys.length];
            }""")
            box = page.locator(".maplibregl-canvas").bounding_box()
            p = page.evaluate("ll => window.__clearswathMap.project(ll)", strip)
            x, y = box["x"] + p["x"], box["y"] + p["y"]
            page.mouse.move(x - 160, y + 90)
            page.mouse.move(x, y, steps=25)  # the cursor glides to the strip, so the click reads on screen
            page.wait_for_timeout(int(400 * slow))
            page.mouse.click(x, y)
            page.wait_for_selector("[data-why]", timeout=10_000)
            shot("dakota-why-here", 5)
            page.keyboard.press("Escape")
            ulv = page.locator("[data-rule-row]", has_text="ULV").get_by_role("checkbox")
            if ulv.count():
                ulv.first.click()
                page.wait_for_timeout(int(3000 * slow))
                shot("dakota-ulv-unticked", 3)
            page.click("#demo-switch")
            page.wait_for_selector("#status.go", timeout=60_000)
            shot("dakota-corrected-go", 4)
            video = page.video.path() if page.video else None
            (OUT / "beats.json").write_text(json.dumps(beats, indent=1))
            context.close()
            browser.close()
        if video:
            final = OUT / "demo.webm"
            Path(video).replace(final)
            print(f"video: {final}")
        print(f"{beat} screenshots in {OUT}")
    finally:
        server.terminate()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--slow", type=float, default=1.0, help="multiply every pause by this")
    a = ap.parse_args()
    main(a.port, a.slow)
