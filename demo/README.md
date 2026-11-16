# AgroRadar demo video (29 s)

`agroradar-demo.mp4`: 1920×1080, 30 fps, English narration (ElevenLabs voice "Zara", `audio/voice_zara.mp3`), burned-in captions.
The 32.4 s recording is cut into the six lines at its pauses and played 1.1× faster (pitch kept) to fit 29 s;
`build_video.py` holds those cut points (`LINES`) and the scene timings that follow them. A new recording needs new cut points.
Every frame carries a visible "AI-generated" watermark (top-right), as Space Apps requires for images and videos.

`agroradar-reel.mp4`: the same 29 s story laid out for Reels / TikTok / Shorts (1080×1920). Text stays out of the
bottom ~350 px and right ~140 px that those apps cover; the watermark sits top-centre. Stills: `scenes.html?reel#k1` …
rendered at 1080×1920 into `frames_reel/`; build with `build_video.py reel`.

## Story

| Time | Scene | Narration |
|---|---|---|
| 0:00–0:05 | **Problem**: canícula, dry cracked field | This year, a long canícula dried El Salvador's fields, and our farmers lost much of their harvest. |
| 0:05–0:08 | **Question** | What if they could see that risk before planting? |
| 0:08–0:15 | **How it works**: real app screens on a phone | With AgroRadar, a farmer marks the plot, answers three questions, and sees which rotation is most likely to succeed. |
| 0:15–0:21 | **NASA data** over a NASA Blue Marble image of El Salvador | It runs on NASA's free, open data: 35 years of climate, plus satellite greenness, slope and soil moisture. |
| 0:21–0:26 | **Vision**: zoom out to the Americas | Today, El Salvador. Tomorrow, every farm facing a changing climate. |
| 0:26–0:29 | **End card**: Adapting Cuzucos, challenge, members, agroradar.space | AgroRadar, by Adapting Cuzucos. |

## Files

- `script.txt`: spoken text (with phonetic spellings for the English voice) and on-screen captions.
- `scenes.html`: every still of the video as a 1920×1080 page (`scenes.html#k1` … `#k6`), in the AgroRadar design system.
- `screens/`: real captures of the app at phone size. `assets/`: NASA GIBS Blue Marble mosaics (`fetch_imagery.py`).
- `build_video.py`: timing, slow zoom, cross-fades, narration mix and encoding.

## Rebuild

```bash
# once: tools outside the project
python3 -m venv /tmp/videotools && /tmp/videotools/bin/pip install pillow imageio-ffmpeg
# stills
for k in k1 k2 k3a k3b k3c k3d k4a k4b k5a k5b k6; do "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars --allow-file-access-from-files --window-size=1920,1080 --virtual-time-budget=8000 --screenshot=frames/$k.png "file://$PWD/scenes.html#$k"; done
# video
/tmp/videotools/bin/python -I build_video.py
```

To use another recording: save it as `audio/voice_zara.mp3` (or change `VOICE_FILE`), find its pauses with
`ffmpeg -i <file> -af silencedetect=noise=-35dB:d=0.25 -f null -`, update `LINES` (and `TEMPO` if it is longer or
shorter than 32 s) in `build_video.py`, then run the last command. `script.txt` has the text of each line.

## Credits

Imagery: NASA Blue Marble via NASA GIBS. App data: NASA POWER, MODIS (Terra), NASADEM, SMAP, NASA GIBS; NOAA ONI; Open-Meteo; MAG El Salvador harvest records.
Map tiles in the app screens: © OpenStreetMap contributors.
