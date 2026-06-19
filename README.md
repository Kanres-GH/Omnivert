<div align="center">

<img src="icon.png" width="120" alt="Converter icon">

# Converter

**Paste a link → get the highest-quality, watermark-free video or audio.**

Built for Instagram Reels and YouTube Shorts (and most other sites yt-dlp supports).

</div>

---

## Features

- 🎬 **Highest quality** — grabs the best video + audio streams and merges them with ffmpeg.
- 🚫 **No watermark** — pulls the original source file (Instagram/YouTube don't bake watermarks into the source).
- 🎵 **Audio extraction** — separate tab for audio-only with format (mp3 / m4a / opus / wav / flac) and bitrate.
- ⚙️ **Per-download options** — quality, codec (H.264 / VP9 / AV1), container (mp4 / mkv / webm), and custom file name.
- 📋 **Batch** — paste multiple links, one per line.
- 🔒 **Instagram login fallback** — optional "use browser cookies" for private or rate-limited reels.
- 📂 **Auto-reveal** — opens the output folder and highlights your files when done.
- 🪟 **Single instance** — re-launching brings the existing window to the front instead of opening a new one.
- 💾 **Remembers** your last-used output folder between launches.

## Download & run

Grab the latest **`Converter.exe`** from the [Releases](../../releases) page and double-click it — no install needed.

> Requires **ffmpeg** on your PATH for highest-quality merges. Install it once with:
> ```
> winget install Gyan.FFmpeg
> ```

## Run from source

```bash
pip install -r requirements.txt
python converter.py
```

## Build the .exe yourself

```bash
python -m PyInstaller --noconfirm --windowed --onefile --clean ^
  --name Converter --icon icon.ico --add-data "icon.ico;." ^
  --collect-all customtkinter --hidden-import darkdetect converter.py
```

The result lands in `dist/Converter.exe`. (`build.bat` does this in one step.)

### Changing the icon

Replace `icon.png`, regenerate the multi-size `.ico`, then rebuild:

```bash
python make_icon.py   # icon.png -> icon.ico (16–256px)
```

## Tech

Python · [yt-dlp](https://github.com/yt-dlp/yt-dlp) (download engine) · ffmpeg (merge/convert) · [customtkinter](https://github.com/TomSchimansky/CustomTkinter) (UI) · PyInstaller (packaging).

---

*Personal tool — for downloading content you have the right to download.*
