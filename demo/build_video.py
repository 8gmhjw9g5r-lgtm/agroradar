"""Builds the 29-second AgroRadar demo video from the scene stills and the narration.

Run with the video tools environment (Pillow + imageio-ffmpeg):
    <venv>/bin/python -I build_video.py
Inputs:  frames/k*.png (from scenes.html via headless Chrome), audio/s1..s6.aiff (macOS `say`, see script.txt)
Output:  agroradar-demo.mp4 (1920x1080, 30 fps, H.264 + AAC)
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REEL = "reel" in sys.argv[1:]  # `build_video.py reel`: portrait 1080x1920 for Instagram/TikTok/Shorts
W, H, FPS, LENGTH = (1080, 1920, 30, 29.0) if REEL else (1920, 1080, 30, 29.0)
FRAMES = HERE / ("frames_reel" if REEL else "frames")
OUT = HERE / ("agroradar-reel.mp4" if REEL else "agroradar-demo.mp4")
FADE = 0.4  # cross-fade between stills, seconds
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# (group, still, start second); a group shares one slow zoom so stills inside it swap without a jump
# Narration: one ElevenLabs recording (voice "Zara"), 32.4 s, cut into the six script lines at its pauses
# (found with ffmpeg silencedetect) and played 1.1x faster (pitch kept) so it fits 29 s.
VOICE_FILE = HERE / "audio" / "voice_zara.mp3"
TEMPO = 1.10
LINES = [(0.00, 6.40), (6.80, 9.40), (9.78, 16.88), (17.22, 24.31), (24.66, 29.40), (29.80, 32.44)]  # seconds in the recording
LEAD, GAP = 0.15, 0.15
VOICE = []  # (start in recording, end in recording, start in video)
_t = LEAD
for a, b in LINES:
    VOICE.append((a, b, round(_t, 2)))
    _t += (b - a) / TEMPO + GAP
# line starts in the video: 0.15, 6.12, 8.63, 15.24, 21.83, 26.29 (last line ends at 28.69)

TIMELINE = [
    ("drought", "k1", 0.00),
    ("question", "k2", 5.95),
    ("how", "k3a", 8.45), ("how", "k3b", 10.20), ("how", "k3c", 12.00), ("how", "k3d", 13.60),
    ("nasa", "k4a", 15.05), ("nasa", "k4b", 17.75),
    ("vision", "k5a", 21.65), ("vision", "k5b", 23.35),  # "Tomorrow" starts about 1.7 s into line 5
    ("end", "k6", 26.10),
]
ZOOM = {"drought": 0.06, "question": 0.04, "how": 0.03, "nasa": 0.06, "vision": 0.07, "end": 0.02}

stills = {k: Image.open(FRAMES / f"{k}.png").convert("RGB") for _, k, _ in TIMELINE}
ends = [t for _, _, t in TIMELINE[1:]] + [LENGTH]
groups = {}
for (g, _, t), e in zip(TIMELINE, ends):
    s, _ = groups.get(g, (t, e))
    groups[g] = (min(s, t), e)


def watermark():
    """Space Apps rule: images and videos must carry a visible watermark saying they are AI-generated."""
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 30)
    text = "AI-generated"
    x0, y0, x1, y1 = font.getbbox(text)
    pad_x, pad_y = 26, 14
    w, h = x1 - x0 + 2 * pad_x, y1 - y0 + 2 * pad_y
    mark = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(mark)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(16, 32, 24, 170), outline=(255, 255, 255, 200), width=2)
    d.text((pad_x - x0, pad_y - y0), text, font=font, fill=(255, 255, 255, 240))
    # top-right corner, clear of captions and logos; the reel keeps it inside the area Reels leaves visible
    return mark, ((W - w) // 2, 40) if REEL else (W - w - 36, 32)


MARK, MARK_AT = watermark()

# Space Apps rule: SI-generated audio and video must be acknowledged in descriptive text and metadata.
SI_NOTE = ("AI-generated content: narration voice by ElevenLabs (voice Zara); script, scene graphics and editing made "
           "with Anthropic Claude. App screenshots are real captures of AgroRadar; backgrounds are NASA Blue Marble imagery.")
METADATA = ["-metadata", "title=AgroRadar — Adapting Cuzucos (NASA Space Apps 2026, Field Shift)",
            "-metadata", "artist=Adapting Cuzucos", "-metadata", f"comment={SI_NOTE}", "-metadata", f"description={SI_NOTE}"]


def render(i, t):
    """Still i at time t, with its group's slow zoom (Ken Burns) toward the centre."""
    g, k, _ = TIMELINE[i]
    s, e = groups[g]
    p = min(max((t - s) / (e - s), 0), 1)
    z = 1 + ZOOM[g] * p
    cw, ch = W / z, H / z
    box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
    return stills[k].resize((W, H), Image.BICUBIC, box=box)


def frame(t):
    i = max(j for j, (_, _, s) in enumerate(TIMELINE) if s <= t)
    img = render(i, t)
    nxt = i + 1
    if nxt < len(TIMELINE) and t > TIMELINE[nxt][2] - FADE:  # fading into the next still
        a = (t - (TIMELINE[nxt][2] - FADE)) / FADE
        img = Image.blend(img, render(nxt, t), a)
    if t < 0.3:  # fade in from black
        img = Image.blend(Image.new("RGB", (W, H)), img, t / 0.3)
    img.paste(MARK, MARK_AT, MARK)  # on every frame, including the fade-in
    return img


def narration(out):
    n = len(VOICE)
    chains = [f"[0:a]asplit={n}" + "".join(f"[in{i}]" for i in range(n))]
    for i, (a, b, at) in enumerate(VOICE):
        chains.append(f"[in{i}]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,atempo={TEMPO},"
                      f"afade=t=in:d=0.03,afade=t=out:st={(b - a) / TEMPO - 0.05:.3f}:d=0.05,adelay=delays={int(at * 1000)}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(n))
    # loudnorm: standard loudness for online video (-16 LUFS), so the voice is not quieter than other videos
    chains.append(f"{mix}amix=inputs={n}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=0:{LENGTH},"
                  "aformat=sample_rates=48000:channel_layouts=stereo[out]")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(VOICE_FILE), "-filter_complex", ";".join(chains),
                    "-map", "[out]", str(out)], check=True)


def main():
    wav = HERE / "audio" / "narration.wav"
    narration(wav)
    out = OUT
    enc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-t", str(LENGTH), *METADATA, "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE)
    n = int(LENGTH * FPS)
    for f in range(n):
        enc.stdin.write(frame(f / FPS).tobytes())
        if f % 150 == 0:
            print(f"frame {f}/{n}", file=sys.stderr)
    enc.stdin.close()
    if enc.wait():
        sys.exit("ffmpeg failed")
    print(out)


if __name__ == "__main__":
    main()
