"""Generate original synthesizer music + subtle interface sound effects.

The notes, rhythms, timbres and audio are generated here without third-party samples.
Usage: uv run --with scipy python scripts/create_demo_audio.py [output-dir]
Requires numpy, scipy and ffmpeg. No binary music is checked into git.
"""
from __future__ import annotations
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 32000
DURATION = 156.0
BPM = 112
BEAT = 60.0 / BPM
RNG = np.random.default_rng(42)


def add(audio, at, clip, gain=1.0):
    idx = int(at * SR)
    end = min(audio.size, idx + len(clip))
    if 0 <= idx < end:
        audio[idx:end] += clip[:end - idx] * gain


def tone(hz, length, attack=.02, release=.15, kind="soft"):
    t = np.arange(max(1, int(length * SR)), dtype=np.float32) / SR
    if kind == "bass":
        y = np.sin(2 * np.pi * hz * t) + .28 * np.sin(4 * np.pi * hz * t)
    elif kind == "bell":
        y = np.sin(2 * np.pi * hz * t) + .35 * np.sin(2 * np.pi * hz * 2.01 * t)
    else:
        y = np.sin(2 * np.pi * hz * t) + .22 * np.sin(4 * np.pi * hz * t)
    envelope = np.minimum(1., t / max(.001, attack)) * np.minimum(
        1., (length - t) / max(.001, release)
    )
    return (y * envelope).astype(np.float32)


def kick():
    t = np.arange(int(.38 * SR)) / SR
    phase = 2 * np.pi * (65 * t + 75 * (1 - np.exp(-t * 28)) / 28)
    return (.65 * np.sin(phase) * np.exp(-t * 19)).astype(np.float32)


def snare():
    t = np.arange(int(.18 * SR)) / SR
    noise = RNG.normal(0, 1, len(t)).astype(np.float32)
    noise = sosfilt(butter(2, 1000, fs=SR, btype="highpass", output="sos"), noise)
    return (.13 * noise * np.exp(-t * 23)).astype(np.float32)


def hat():
    t = np.arange(int(.1 * SR)) / SR
    noise = RNG.normal(0, 1, len(t)).astype(np.float32)
    noise = sosfilt(butter(2, 4700, fs=SR, btype="highpass", output="sos"), noise)
    return (.095 * noise * np.exp(-t * 48)).astype(np.float32)


def whoosh():
    t = np.arange(int(.52 * SR)) / SR
    noise = RNG.normal(0, 1, len(t)).astype(np.float32)
    noise = sosfilt(butter(2, 800, fs=SR, btype="highpass", output="sos"), noise)
    return (.11 * noise * np.sin(np.pi * t / .52) ** 2).astype(np.float32)


def save(path, mono):
    mono = np.clip(mono, -.98, .98)
    stereo = np.stack([mono, np.roll(mono, 17) * .995], axis=-1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
        "-codec:a", "libmp3lame", "-qscale:a", "3", str(path.with_suffix(".mp3"))
    ], check=True)


def main(destination):
    destination.mkdir(parents=True, exist_ok=True)
    music = np.zeros(int(DURATION * SR), dtype=np.float32)
    sfx = np.zeros_like(music)
    chords = [
        (50, [62, 65, 69, 74]), (46, [58, 62, 65, 69]),
        (53, [57, 60, 65, 69]), (48, [60, 64, 67, 74])
    ]
    drum_kick, drum_snare, drum_hat = kick(), snare(), hat()
    for step in range(int(DURATION / BEAT) + 1):
        at = step * BEAT
        root, notes = chords[(step // 16) % 4]
        if at < 4:
            continue
        if at < 142 and step % 4 in (0, 2):
            add(music, at, drum_kick, .6 if at < 12 else 1.)
        if at < 142 and step % 4 in (1, 3):
            add(music, at, drum_snare, .56 if at < 12 else .8)
        if at < 148:
            add(music, at, drum_hat, .65)
            add(music, at + BEAT / 2, drum_hat, .26)
        if step % 2 == 0 and at < 146:
            add(music, at, tone(440 * 2 ** ((root - 69) / 12), .44, .007, .19, "bass"), .22)
        if step % 4 == 0 and at < 143:
            for note in notes:
                add(music, at, tone(440 * 2 ** ((note - 69) / 12), BEAT * 3.3, .25, .6), .027)
        if 15 < at < 136 and step % 2 == 1:
            note = notes[[0, 2, 1, 3][(step // 2) % 4]] + 12
            add(music, at + BEAT * .4, tone(440 * 2 ** ((note - 69) / 12), .21, .008, .11, "bell"), .033)
    for at, note in [(145, 74), (147, 69), (149, 65), (151, 62)]:
        add(music, at, tone(440 * 2 ** ((note - 69) / 12), 3.8, .15, 1.6), .055)
    for at in [0., 11.2, 30., 53., 80., 102., 126., 142.]:
        add(sfx, at, whoosh(), .55)
    for at in [7.2, 30.8, 80.6, 115.]:
        add(sfx, at, tone(770, .12, .001, .1, "bell"), .16)
    n = np.arange(len(music))
    music *= np.minimum(1, n / float(SR)) * np.minimum(1, (len(music) - n) / float(3 * SR))
    music = sosfilt(butter(2, 9000, fs=SR, btype="lowpass", output="sos"), music)
    music *= .5 / max(1., float(np.max(np.abs(music))))
    under_voice = music.copy() * .24
    for start, end in [(0., 7.), (140., DURATION)]:
        under_voice[int(start * SR):int(end * SR)] *= 2.2
    save(destination / "clearswath_music_full.wav", music)
    save(destination / "clearswath_music_under_vo.wav", under_voice)
    save(destination / "clearswath_sfx_timeline.wav", sfx)
    print("Generated WAV and MP3 original demo sound assets:", destination)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/video/audio"))
