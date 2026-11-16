"""Builds the 30-second "my first hackathon" reel (1080x1920, text only) from the journey.html stills.

Run with the video tools environment (Pillow + imageio-ffmpeg):
    <venv>/bin/python -I build_journey.py
Inputs:  frames/j1..j11.png (journey.html#j1 … via headless Chrome)
Output:  agroradar-journey-reel.mp4 (H.264, silent AAC track so every platform accepts it; add music in the app)
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H, FPS, LENGTH = 1080, 1920, 30, 30.0
FADE = 0.35
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# (still, start second): ~2.6 s per milestone, a longer hold on the end card
TIMELINE = [("j1", 0.0), ("j2", 2.8), ("j3", 5.4), ("j4", 8.0), ("j5", 10.6), ("j6", 13.2), ("j7", 15.8),
            ("j8", 18.4), ("j9", 21.0), ("j10", 23.6), ("j11", 26.2)]
ZOOM = 0.035  # gentle push-in on every still

SI_NOTE = ("AI-generated content: scene graphics and editing made with Anthropic Claude. "
           "App screens are real captures of AgroRadar's versions during the hackathon.")
METADATA = ["-metadata", "title=AgroRadar — my first hackathon (Adapting Cuzucos, NASA Space Apps 2026)",
            "-metadata", "artist=Adapting Cuzucos", "-metadata", f"comment={SI_NOTE}", "-metadata", f"description={SI_NOTE}"]

stills = {k: Image.open(HERE / "frames" / f"{k}.png").convert("RGB") for k, _ in TIMELINE}
ends = [t for _, t in TIMELINE[1:]] + [LENGTH]


def watermark():
    """Space Apps rule: images and videos must carry a visible watermark saying they are AI-generated."""
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 30)
    text = "AI-generated"
    x0, y0, x1, y1 = font.getbbox(text)
    w, h = x1 - x0 + 52, y1 - y0 + 28
    mark = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(mark)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(16, 32, 24, 170), outline=(255, 255, 255, 200), width=2)
    d.text((26 - x0, 14 - y0), text, font=font, fill=(255, 255, 255, 240))
    return mark, ((W - w) // 2, 40)  # top-centre: clear of titles and of the icons Reels puts at the corners


MARK, MARK_AT = watermark()


def render(i, t):
    k, s = TIMELINE[i]
    p = min(max((t - s) / (ends[i] - s), 0), 1)
    z = 1 + ZOOM * p
    cw, ch = W / z, H / z
    return stills[k].resize((W, H), Image.BICUBIC, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))


def frame(t):
    i = max(j for j, (_, s) in enumerate(TIMELINE) if s <= t)
    img = render(i, t)
    if i + 1 < len(TIMELINE) and t > TIMELINE[i + 1][1] - FADE:
        img = Image.blend(img, render(i + 1, t), (t - (TIMELINE[i + 1][1] - FADE)) / FADE)
    if t < 0.25:
        img = Image.blend(Image.new("RGB", (W, H)), img, t / 0.25)
    img.paste(MARK, MARK_AT, MARK)
    return img


def main():
    out = HERE / "agroradar-journey-reel.mp4"
    enc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-c:v", "libx264", "-preset", "medium",
                            "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-t", str(LENGTH), *METADATA,
                            "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(LENGTH * FPS)
    for f in range(n):
        enc.stdin.write(frame(f / FPS).tobytes())
    enc.stdin.close()
    if enc.wait():
        sys.exit("ffmpeg failed")
    print(out)


if __name__ == "__main__":
    main()
