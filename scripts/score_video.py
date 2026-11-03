"""Original score, sound cues and the final mix for the demo video. Video tooling only: numpy + ffmpeg.

uv run python scripts/cut_video.py                 # first: the picture and data/video/cut_timeline.json
uv run python scripts/score_video.py [--vo data/video/voiceover.wav]

Every note is generated here: no samples, no third-party music. Stems go to data/video/audio/ (music, music ducked
for a voiceover, sound cues), so the mix can be redone. The final MP4 is H.264/AAC with fast start, loudness
normalised to -16 LUFS integrated, true peak about -1.5 dBTP after AAC. Without --vo the film has music and sound but no narration.
"""

import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "data" / "video"
AUDIO = VID / "audio"
SR = 44100
BEAT = 60 / 80  # 80 bpm: unhurried, under a voice
RNG = np.random.default_rng(7)
# chord tones (MIDI), one chord per 8 beats: D add9, B minor 7, G major 7, A sus4
CHORDS = [(50, [62, 64, 66, 69]), (47, [59, 62, 66, 69]), (43, [59, 62, 66, 67]), (45, [57, 62, 64, 69])]


def hz(m: float) -> float:
    return 440 * 2 ** ((m - 69) / 12)


def t_of(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def add(track: np.ndarray, at: float, clip: np.ndarray, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(len(track), i + len(clip))
    if 0 <= i < j:
        track[i:j] += clip[: j - i] * gain


def pad_note(m: int, seconds: float) -> np.ndarray:
    t = t_of(seconds)
    y = np.sin(2 * np.pi * hz(m) * t) + np.sin(2 * np.pi * hz(m) * 1.004 * t) + 0.3 * np.sin(4 * np.pi * hz(m) * t)
    attack, release = 1.6, 2.2
    env = np.minimum(1, t / attack) * np.minimum(1, (seconds - t) / release)
    return y * np.clip(env, 0, 1)


def pluck(m: int) -> np.ndarray:
    t = t_of(0.9)
    y = np.sin(2 * np.pi * hz(m) * t) + 0.35 * np.sin(4 * np.pi * hz(m) * t) + 0.1 * np.sin(6 * np.pi * hz(m) * t)
    return y * np.exp(-t * 7) * np.minimum(1, t / 0.004)


def bass_note(m: int, seconds: float) -> np.ndarray:
    t = t_of(seconds)
    y = np.sin(2 * np.pi * hz(m) * t) + 0.25 * np.sin(4 * np.pi * hz(m) * t)
    return y * np.minimum(1, t / 0.03) * np.clip((seconds - t) / 0.4, 0, 1) * (0.6 + 0.4 * np.exp(-t * 2))


def chime(m: int) -> np.ndarray:
    t = t_of(2.4)
    f = hz(m)
    y = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3)
    return y * np.exp(-t * 2.2) * np.minimum(1, t / 0.003)


def soft(noise: np.ndarray, width: int) -> np.ndarray:
    """A crude low-pass: moving average."""
    return np.convolve(noise, np.ones(width) / width, mode="same")


def page_turn() -> np.ndarray:
    t = t_of(0.45)
    y = soft(RNG.normal(0, 1, len(t)), 6) - soft(RNG.normal(0, 1, len(t)), 60)  # band-limited hiss
    return y * np.sin(np.pi * np.minimum(1, t / 0.45)) ** 3


def thump() -> np.ndarray:
    t = t_of(0.7)
    phase = 2 * np.pi * (42 * t + 30 * (1 - np.exp(-t * 18)) / 18)
    return np.sin(phase) * np.exp(-t * 6)


def tick() -> np.ndarray:
    t = t_of(0.05)
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120)


def score(duration: float, cues: dict) -> tuple[np.ndarray, np.ndarray]:
    music, sfx = np.zeros(int(duration * SR) + SR), np.zeros(int(duration * SR) + SR)
    bar = 8 * BEAT
    end = cues["end"]
    pulse_on = [(cues["demo"], cues["sam_alone"]), (cues["wonder"], end)]
    for k in range(int(duration / bar) + 1):
        at = k * bar
        root, notes = CHORDS[k % 4]
        if at >= end:  # the end card resolves on D
            root, notes = CHORDS[0]
        length = min(bar + 2.2, duration - at + 0.5)
        thin = cues["label"] <= at < cues["demo"] or cues["sam_alone"] <= at < cues["wonder"]
        for i, m in enumerate(notes):
            if thin and i in (1, 3):
                continue
            add(music, at, pad_note(m, length), 0.022)
        if at >= cues["wonder"]:
            add(music, at, bass_note(root, bar), 0.11)
        for b in range(16):  # eighth notes
            when = at + b * BEAT / 2
            if any(s <= when < e for s, e in pulse_on) and when < duration - 4:
                m = [notes[0] + 12, notes[2], notes[1] + 12, notes[3], notes[2] + 12, notes[1], notes[3] + 12, notes[0]][b % 8]
                add(music, when, pluck(m), 0.045 if b % 2 == 0 else 0.03)
    n = np.arange(len(music))
    music *= np.minimum(1, n / (1.5 * SR)) * np.clip((duration * SR - n) / (4 * SR), 0, 1)  # in and out
    add(sfx, 0.25, thump(), 0.35)
    for at in cues["pages"]:
        add(sfx, at + 0.05, page_turn(), 0.16)
    add(sfx, cues["wonder"] + 0.3, chime(88), 0.09)
    add(sfx, cues["files"] + 0.5, tick(), 0.12)
    add(sfx, cues["go"] + 0.2, chime(86), 0.08)
    add(sfx, end + 0.4, chime(81), 0.07)
    return music[: int(duration * SR)], sfx[: int(duration * SR)]


def write(path: Path, mono: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    stereo = np.stack([mono, np.roll(mono, 23)], axis=-1)  # a touch of width
    peak = max(1e-9, float(np.abs(stereo).max()))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((stereo / peak * 0.7 * 32767).astype("<i2").tobytes())
    return path


def ff(*args) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-y", *map(str, args)], check=True, capture_output=True,
                          text=True).stderr


def main(vo: Path | None, out: Path) -> None:
    tl = json.loads((VID / "cut_timeline.json").read_text())
    start = {p["part"]: p["start"] for p in tl["parts"]}
    cues = {"label": start["020"], "pages": [start[f"02{i}"] for i in range(4)], "demo": start["03a"],
            "sam_alone": start["04a"], "wonder": start["04b"], "files": start["06a"], "go": start["07b"],
            "end": start["09"]}
    music, sfx = score(tl["duration"], cues)
    voice = VID / "voice" / "manifest.json"
    if vo is None and voice.exists():  # narration from scripts/narrate_video.py: each line at the start of its shot
        firsts = ["01a", "020", "03a", "04a", "05", "06a", "07a", "08", "09"]
        track = np.zeros(int(tl["duration"] * SR) + SR)
        for n, part in enumerate(firsts, 1):
            with wave.open(str(VID / "voice" / f"shot{n}.wav")) as w:
                line = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float) / 32767
                rate = w.getframerate()
            line = np.interp(np.arange(0, len(line), rate / SR), np.arange(len(line)), line)  # to 44.1 kHz
            add(track, start[part] + 0.4, line)
        vo = AUDIO / "voice.wav"
        with wave.open(str(vo), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
            w.writeframes((np.clip(track[: int(tl["duration"] * SR)], -1, 1) * 32767).astype("<i2").tobytes())
    dry = write(AUDIO / "music_dry.wav", music)
    write(AUDIO / "sfx.wav", sfx)
    # room and polish in ffmpeg: a gentle low-pass, a short room echo
    ff("-i", dry, "-af", "lowpass=f=7500,aecho=0.8:0.6:70|140:0.22|0.12", AUDIO / "music.wav")
    ff("-i", AUDIO / "music.wav", "-af", "volume=-9dB", AUDIO / "music_under_vo.wav")
    if vo:
        mix = ("[1:a]aformat=channel_layouts=stereo,aresample=44100,loudnorm=I=-16:TP=-2,asplit=2[v1][v2];"
               "[0:a][v1]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=400[m];"
               "[m][v2][2:a]amix=inputs=3:normalize=0,loudnorm=I=-16:TP=-2:LRA=11,aresample=48000[a]")
        ff("-i", AUDIO / "music_under_vo.wav", "-i", vo, "-i", AUDIO / "sfx.wav", "-filter_complex", mix,
           "-map", "[a]", AUDIO / "mix.wav")
    else:
        ff("-i", AUDIO / "music.wav", "-i", AUDIO / "sfx.wav", "-filter_complex",
           "[0:a][1:a]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-2:LRA=11,aresample=48000[a]", "-map", "[a]", AUDIO / "mix.wav")
    subs = []
    if voice.exists():  # captions: each line split into sentences, timed by word count within its shot's take
        import re
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from narrate_video import lines
        seconds = json.loads(voice.read_text())["seconds"]
        firsts = ["01a", "020", "03a", "04a", "05", "06a", "07a", "08", "09"]
        cues_ = []
        for n, (part, text) in enumerate(zip(firsts, lines()), 1):
            sentences = [x for x in re.split(r"(?<=[.:?!])\s+", text) if x]
            t, span = start[part] + 0.4 + 0.25, seconds[str(n)] - 0.5
            total = sum(len(x.split()) for x in sentences)
            for x in sentences:
                d = span * len(x.split()) / total
                cues_.append((t, t + d, x))
                t += d
        stamp = lambda v: f"{int(v // 3600):02d}:{int(v % 3600 // 60):02d}:{int(v % 60):02d},{int(v % 1 * 1000):03d}"  # noqa: E731
        srt = out.with_suffix(".srt")
        srt.write_text("\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{x}\n" for i, (a, b, x) in enumerate(cues_, 1)))
        subs = ["-i", srt, "-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    ff("-i", VID / "clearswath.mp4", "-i", AUDIO / "mix.wav", *subs[:2], "-map", "0:v", "-map", "1:a", *subs[2:],
       "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out)
    report = ff("-i", out, "-af", "ebur128=peak=true", "-f", "null", "-")
    summary = report[report.rfind("Summary:"):]
    print(out)
    print(" ".join(line.strip() for line in summary.splitlines() if any(k in line for k in ("I:", "Peak:", "LRA:"))))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vo", type=Path, help="Hunter's voiceover, one WAV")
    ap.add_argument("--out", type=Path, default=VID / "ClearSwath_Meta_Hackathon_Final.mp4")
    a = ap.parse_args()
    main(a.vo, a.out)
