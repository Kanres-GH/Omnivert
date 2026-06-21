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

Instagram · TikTok · YouTube (Shorts **and** regular) · Twitter / X · Reddit · SoundCloud — plus any of [yt-dlp's 1000+ supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). Just paste the link.

## Features

- 🎬 **Highest quality, no watermark** — grabs the best video + audio streams and merges them with ffmpeg; pulls the clean source.
- 🧺 **Download queue** — paste, hit download, and items stack into a live queue with progress and a finished **Done** state.
- ⏯️ **Pause / continue / cancel** — pause a download and resume it later from where it left off; cancelling cleans up partial files.
- 🎵 **Audio mode** — extract audio as mp3 / m4a / opus / wav / flac at your chosen bitrate. Music links (SoundCloud, etc.) are detected and steered to the Audio tab.
- ⚙️ **Per-download options** — quality, codec (H.264 / VP9 / AV1), and container (mp4 / mkv / webm).
- 💬 **Soft subtitles** — optionally embed a selectable subtitle track (not burned in).
- 🔢 **Never overwrites** — a second download of the same file is saved as `name (1)`, `name (2)`, …
- 🌗 **Light & dark themes** with a modern, animated UI.
- 📂 **Open-folder button** on every item · 🪟 **single-instance** window · 💾 **remembered** output folder.

## Download & run

Grab the latest **`Omnivert.exe`** from the [Releases](../../releases) page and double-click it — no install needed.

> Requires **ffmpeg** on your PATH for highest-quality merges (and for Reddit, which serves video/audio separately). Install it once with:
> ```
> winget install Gyan.FFmpeg
> ```
> The app uses the built-in **WebView2** runtime (preinstalled on Windows 10/11).

## Run from source

```bash
pip install -r requirements.txt
python omnivert.py
```

## Build the .exe yourself

```bash
python -m PyInstaller --noconfirm --windowed --onefile --clean ^
  --name Omnivert --icon icon.ico ^
  --add-data "icon.ico;." --add-data "web;web" ^
  --collect-all webview omnivert.py
```

The result lands in `dist/Omnivert.exe`. (`build.bat` does this in one step.)

### Changing the icon

Replace `ico_test.png` (the icon art), then regenerate the multi-size `.ico`:

```bash
python make_icon.py   # ico_test.png -> icon.ico (dark tile + mark, 16–256px)
```

## Tech

Python · [yt-dlp](https://github.com/yt-dlp/yt-dlp) (download engine) · ffmpeg (merge/convert) · [pywebview](https://github.com/r0x0r/pywebview) + a small HTML/CSS/JS front-end (`web/`) · PyInstaller (packaging).

## License

[MIT](LICENSE) — do whatever you want, just keep the copyright notice. *For downloading content you have the right to download.*
