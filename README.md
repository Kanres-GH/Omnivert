<div align="center">

<img src="icon.png" width="120" alt="Omnivert icon">

# Omnivert

**Paste a link → get the highest-quality, watermark-free video or audio.**

*omni + convert* — one tool for a lot of sites.

![License: MIT](https://img.shields.io/badge/License-MIT-7c5cff.svg)
![Platform: Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)

</div>

---

## Supported sites

Instagram · TikTok · YouTube (Shorts **and** regular) · Twitter / X · Reddit — plus any of [yt-dlp's 1000+ supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). Just paste the link.

## Features

- 🎬 **Highest quality** — grabs the best video + audio streams and merges them with ffmpeg.
- 🚫 **No watermark** — pulls the clean source (e.g. TikTok's no-watermark version).
- 🎵 **Audio extraction** — separate tab for audio-only with format (mp3 / m4a / opus / wav / flac) and bitrate.
- ⚙️ **Per-download options** — quality, codec (H.264 / VP9 / AV1), container (mp4 / mkv / webm), and custom file name.
- 📋 **Batch** — paste multiple links, one per line.
- 🔒 **Login fallback** — optional "use browser cookies" for private, blocked, or age-restricted content (handy for X).
- 📂 **Auto-reveal** — opens the output folder and highlights your files when done.
- 🪟 **Single instance** — re-launching brings the existing window to the front.
- 💾 **Remember folder** — pin a default output folder with one click.

## Download & run

Grab the latest **`Omnivert.exe`** from the [Releases](../../releases) page and double-click it — no install needed.

> Requires **ffmpeg** on your PATH for highest-quality merges (and for Reddit, which serves video/audio separately). Install it once with:
> ```
> winget install Gyan.FFmpeg
> ```

## Run from source

```bash
pip install -r requirements.txt
python omnivert.py
```

## Build the .exe yourself

```bash
python -m PyInstaller --noconfirm --windowed --onefile --clean ^
  --name Omnivert --icon icon.ico --add-data "icon.ico;." ^
  --collect-all customtkinter --hidden-import darkdetect omnivert.py
```

The result lands in `dist/Omnivert.exe`. (`build.bat` does this in one step.)

### Changing the icon

Replace `icon.png`, regenerate the multi-size `.ico`, then rebuild:

```bash
python make_icon.py   # icon.png -> icon.ico (16–256px)
```

## Tech

Python · [yt-dlp](https://github.com/yt-dlp/yt-dlp) (download engine) · ffmpeg (merge/convert) · [customtkinter](https://github.com/TomSchimansky/CustomTkinter) (UI) · PyInstaller (packaging).

## License

[MIT](LICENSE) — do whatever you want, just keep the copyright notice. *For downloading content you have the right to download.*
