"""
Omnivert
--------
Paste a link from Instagram, TikTok, YouTube (Shorts or regular), Twitter/X,
Reddit (or any of yt-dlp's 1000+ supported sites) and download the
highest-quality, watermark-free video — or extract just the audio.

UI: web front-end (web/) rendered in a native window via pywebview.
Engine: yt-dlp   |   Merge/convert: ffmpeg
"""

import os
import sys
import json
import glob
import queue
import shutil
import socket
import threading
import subprocess
from pathlib import Path

import webview
# yt_dlp is imported lazily (inside probe/_download) so the window paints
# immediately on launch instead of waiting for its heavy import.


APP_NAME = "Omnivert"
LOCK_PORT = 50573
DEFAULT_OUT = str(Path.home() / "Downloads" / "Omnivert")


# --------------------------------------------------------------------------- #
# Paths / ffmpeg
# --------------------------------------------------------------------------- #
def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    candidates = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates += glob.glob(
            os.path.join(local, "Microsoft", "WinGet", "Packages",
                         "Gyan.FFmpeg*", "**", "ffmpeg.exe"), recursive=True)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates += glob.glob(os.path.join(here, "**", "ffmpeg.exe"), recursive=True)
    for c in candidates:
        if os.path.isfile(c):
            return str(Path(c).parent)
    return None


FFMPEG_DIR = find_ffmpeg()


# --------------------------------------------------------------------------- #
# Settings persistence
# --------------------------------------------------------------------------- #
DEFAULT_SETTINGS = {
    "theme": "dark",
    "out_dir": DEFAULT_OUT,
    "subtitles": "none",       # "none" or a language code
    "disable_metadata": False,
}


def config_path() -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "settings.json")


def load_settings() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Option maps + format-string builders
# --------------------------------------------------------------------------- #
QUALITY_HEIGHT = {"best": None, "2160": 2160, "1440": 1440,
                  "1080": 1080, "720": 720, "480": 480}
CODEC_PREFIX = {"auto": None, "h264": "avc", "vp9": "vp9", "av1": "av01"}


def _audio_selector(track: str) -> str:
    """bestaudio, optionally preferring a language; always falls back."""
    if track and track.lower() not in ("origin", "original", "", "auto"):
        return f"(bestaudio[language^={track}]/bestaudio)"
    return "bestaudio"


def video_format(opts: dict) -> str:
    height = QUALITY_HEIGHT.get(str(opts.get("quality", "best")), None)
    vcodec = CODEC_PREFIX.get(opts.get("codec", "auto"), None)
    vfilt = ""
    if height:
        vfilt += f"[height<={height}]"
    if vcodec:
        vfilt += f"[vcodec^={vcodec}]"
    abest = _audio_selector(opts.get("audio_track", "origin"))
    fallback = "best" + (f"[height<={height}]" if height else "")
    return f"bestvideo{vfilt}+{abest}/{fallback}/best"


def audio_format(opts: dict) -> str:
    return f"{_audio_selector(opts.get('audio_track', 'origin'))}/best"


class _Cancelled(Exception):
    pass


class _Paused(Exception):
    pass


def _friendly_error(msg: str) -> str:
    """Map yt-dlp's noisy errors to a short, user-facing message."""
    low = (msg or "").lower()
    if any(k in low for k in ("not exist", "unavailable", "no video", "not found",
                              "removed", "incorrect", "unsupported url", "is not a valid url",
                              "404")):
        return "Video doesn't exist. Please put in a valid link."
    if "private" in low:
        return "This video is private."
    if "drm" in low:
        return "This video is DRM-protected and can't be downloaded."
    if any(k in low for k in ("sign in", "login", "age", "confirm your age")):
        return "This video requires sign-in (age-restricted or private)."
    if any(k in low for k in ("timed out", "timeout", "connection", "network",
                              "getaddrinfo", "resolve")):
        return "Network error. Check your connection and the link."
    return "Download failed. Please check the link."


# --------------------------------------------------------------------------- #
# JS-facing API + download worker
# --------------------------------------------------------------------------- #
class Api:
    def __init__(self):
        self.window = None
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}      # id -> state
        self.q: queue.Queue = queue.Queue()
        self.cancelled: set[str] = set()
        self.paused: set[str] = set()
        self.probe_cache: dict[str, dict] = {}
        self.info_cache: dict[str, dict] = {}
        self.settings = load_settings()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- lifecycle --------------------------------------------------------- #
    def warm_up(self):
        """Front-load the heavy yt-dlp import while the loader is showing, so the
        first download starts quickly. Runs on a worker thread (non-blocking)."""
        try:
            import yt_dlp  # noqa: F401
        except Exception:
            pass
        return True

    # ---- settings ---------------------------------------------------------- #
    def get_settings(self):
        return self.settings

    def save_settings(self, patch):
        self.settings.update(patch or {})
        save_settings(self.settings)
        return self.settings

    def choose_folder(self):
        try:
            res = self.window.create_file_dialog(webview.FOLDER_DIALOG,
                                                 directory=self.settings.get("out_dir", ""))
        except Exception:
            res = None
        if res:
            path = res[0] if isinstance(res, (list, tuple)) else res
            self.settings["out_dir"] = path
            save_settings(self.settings)
            return path
        return None

    # ---- probe (called on paste) ------------------------------------------ #
    def probe(self, url):
        import yt_dlp
        url = (url or "").strip()
        if not url:
            return {"ok": False, "error": "empty"}
        if url in self.probe_cache:
            return self.probe_cache[url]
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "noplaylist": True, "socket_timeout": 15,
                "retries": 1, "extractor_retries": 1, "fragment_retries": 1}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info.get("entries"):
                entries = [e for e in info["entries"] if e]
                info = entries[0] if entries else info
            self.info_cache[url] = info     # reused to resolve the output filename
            # Collapse language variants (en-US -> en) and de-duplicate, so a
            # single-language video doesn't look like it has multiple tracks.
            formats = info.get("formats") or []
            bases, seen = [], set()
            has_video = False
            for f in formats:
                if f.get("vcodec") not in (None, "none"):
                    has_video = True
                lang = f.get("language")
                if f.get("acodec") not in (None, "none") and lang:
                    base = lang.split("-")[0].lower()
                    if base not in seen:
                        seen.add(base)
                        bases.append(base)
            # Audio-only source (SoundCloud, Bandcamp, podcasts, …): no video stream.
            is_audio = bool(formats) and not has_video
            result = {
                "ok": True,
                "url": url,
                "title": info.get("title") or url,
                "thumbnail": info.get("thumbnail"),
                "extractor": (info.get("extractor_key") or info.get("extractor") or ""),
                "duration": info.get("duration"),
                "audio_tracks": bases if len(bases) > 1 else [],
                "is_audio": is_audio,
            }
            self.probe_cache[url] = result
            return result
        except Exception as e:
            return {"ok": False, "url": url, "error": _friendly_error(str(e))}

    # ---- queue ------------------------------------------------------------- #
    def add_job(self, job):
        jid = job["id"]
        with self.lock:
            job.setdefault("status", "queued")
            job.setdefault("downloaded", 0)
            job.setdefault("total", None)
            self.jobs[jid] = job
        # Fill missing title/thumb from probe cache or a background probe.
        if not job.get("title") or job.get("title") == job.get("url"):
            threading.Thread(target=self._fill_meta, args=(jid, job.get("url")),
                             daemon=True).start()
        self.q.put(jid)
        return True

    def _fill_meta(self, jid, url):
        info = self.probe_cache.get(url) or self.probe(url)
        if info.get("ok"):
            with self.lock:
                j = self.jobs.get(jid)
                if j:
                    j["title"] = info.get("title") or j.get("title")
                    j["thumbnail"] = info.get("thumbnail") or j.get("thumbnail")

    def remove_job(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            status = j.get("status") if j else None
        if status == "downloading":
            # Let the worker stop, delete partial files, and drop the job.
            self.cancelled.add(jid)
            self.paused.discard(jid)
            return True
        # Not actively downloading: drop now; clean partials unless it finished.
        if j and status in ("queued", "paused", "error"):
            self._cleanup_partials(j)
        with self.lock:
            self.jobs.pop(jid, None)
        self.cancelled.discard(jid)
        self.paused.discard(jid)
        return True

    def clear(self):
        with self.lock:
            items = list(self.jobs.items())
        for jid, j in items:
            if j.get("status") == "downloading":
                self.cancelled.add(jid)
            elif j.get("status") != "done":
                self._cleanup_partials(j)
        with self.lock:
            # keep jobs the worker still needs to clean up (downloading -> cancelled)
            self.jobs = {jid: j for jid, j in self.jobs.items()
                         if jid in self.cancelled}
        return True

    def pause_job(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            if not j:
                return False
            if j.get("status") == "downloading":
                self.paused.add(jid)          # worker stops, keeps the .part file
            elif j.get("status") == "queued":
                j["status"] = "paused"         # never started; just hold it
        return True

    def resume_job(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
            if not j or j.get("status") != "paused":
                return False
            j["status"] = "queued"
        self.paused.discard(jid)
        self.q.put(jid)                        # continuedl resumes from the .part
        return True

    def _cleanup_partials(self, job):
        """Delete any partial/temp files this job created (.part, .ytdl, frags)."""
        targets = set()
        for p in job.get("partials", set()):
            if not p:
                continue
            targets.update(glob.glob(glob.escape(p) + "*"))
            if p.endswith(".part"):
                targets.add(p[:-5] + ".ytdl")
        for p in targets:
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass

    def poll(self):
        keys = ("status", "title", "thumbnail", "downloaded", "total",
                "speed", "pct", "error", "ext", "quality", "mode")
        with self.lock:
            return {jid: {k: j.get(k) for k in keys} for jid, j in self.jobs.items()}

    def reveal(self, jid):
        with self.lock:
            j = self.jobs.get(jid)
        path = j.get("filepath") if j else None
        try:
            if path and os.path.exists(path):
                subprocess.run(f'explorer /select,"{os.path.normpath(path)}"')
            else:
                os.startfile(self.settings.get("out_dir", DEFAULT_OUT))
        except Exception:
            pass
        return True

    # ---- worker ------------------------------------------------------------ #
    def _worker(self):
        while True:
            jid = self.q.get()
            with self.lock:
                job = self.jobs.get(jid)
                if not job or jid in self.cancelled:
                    self.cancelled.discard(jid)
                    if job is None:
                        continue
                    self._cleanup_partials(job)
                    self.jobs.pop(jid, None)
                    continue
                if jid in self.paused or job.get("status") == "paused":
                    continue           # held; resume_job will re-queue it
                job["status"] = "downloading"
            try:
                self._download(job)
                with self.lock:
                    if self.jobs.get(jid):
                        self.jobs[jid]["status"] = "done"
                        self.jobs[jid]["pct"] = 100
            except _Paused:
                with self.lock:
                    if self.jobs.get(jid):
                        self.jobs[jid]["status"] = "paused"   # keep the .part file
                self.paused.discard(jid)
            except _Cancelled:
                self._cleanup_partials(job)                    # delete partials
                with self.lock:
                    self.jobs.pop(jid, None)
                self.cancelled.discard(jid)
            except Exception as e:
                with self.lock:
                    if self.jobs.get(jid):
                        self.jobs[jid]["status"] = "error"
                        self.jobs[jid]["error"] = _friendly_error(str(e))

    def _build_opts(self, job):
        o = job.get("opts", {}) or {}
        out = self.settings.get("out_dir", DEFAULT_OUT)
        os.makedirs(out, exist_ok=True)
        common = {
            "outtmpl": os.path.join(out, "%(title).80B [%(id)s].%(ext)s"),
            "progress_hooks": [lambda d: self._hook(job, d)],
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "windowsfilenames": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 2,
            "fragment_retries": 3,
            "extractor_retries": 1,
            "continuedl": True,        # resume from .part on a re-queue (pause/continue)
        }
        if FFMPEG_DIR:
            common["ffmpeg_location"] = FFMPEG_DIR
        pps = []
        if not self.settings.get("disable_metadata"):
            pps.append({"key": "FFmpegMetadata"})
        if job.get("mode") == "audio":
            container = (o.get("container") or "mp3").lstrip(".")
            common["format"] = audio_format(o)
            extract = {"key": "FFmpegExtractAudio", "preferredcodec": container}
            if container not in ("wav", "flac"):
                extract["preferredquality"] = str(o.get("quality", "256"))
            pps.insert(0, extract)
        else:
            container = (o.get("container") or "mp4").lstrip(".")
            common["format"] = video_format(o)
            common["merge_output_format"] = container
            subs = self.settings.get("subtitles", "none")
            if subs and subs != "none":
                common["writesubtitles"] = True
                common["writeautomaticsub"] = True       # fall back to auto-captions
                common["subtitleslangs"] = [subs]
                # Embedded as a selectable soft track (not burned into the picture).
                pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
        if pps:
            common["postprocessors"] = pps
        return common

    def _apply_unique_name(self, opts, job):
        """If the target file already exists in the output folder, append
        ' (1)', ' (2)', … to the template so we never overwrite a download."""
        # Reuse a name already chosen for this job (e.g. pause -> resume).
        if job.get("resolved_outtmpl"):
            opts["outtmpl"] = job["resolved_outtmpl"]
            return
        try:
            import yt_dlp
            tmpl = opts.get("outtmpl")
            if not isinstance(tmpl, str) or not tmpl.endswith(".%(ext)s"):
                return
            info = self.info_cache.get(job["url"])
            name_opts = {"outtmpl": tmpl, "quiet": True, "no_warnings": True,
                         "windowsfilenames": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(name_opts) as ydl:
                if info is None:                       # only if probe didn't cache it
                    info = ydl.extract_info(job["url"], download=False)
                stem = os.path.splitext(ydl.prepare_filename(info))[0]
            o = job.get("opts", {}) or {}
            ext = (o.get("container")
                   or ("mp3" if job.get("mode") == "audio" else "mp4")).lstrip(".")
            if os.path.exists(f"{stem}.{ext}"):
                n = 1
                while os.path.exists(f"{stem} ({n}).{ext}"):
                    n += 1
                opts["outtmpl"] = tmpl[:-len(".%(ext)s")] + f" ({n}).%(ext)s"
        except Exception:
            pass
        job["resolved_outtmpl"] = opts.get("outtmpl")

    def _download(self, job):
        import yt_dlp
        opts = self._build_opts(job)
        self._apply_unique_name(opts, job)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job["url"], download=True)
        except (_Cancelled, _Paused):
            raise
        except Exception:
            # Subtitles are best-effort: if they break the download, retry without.
            if not opts.get("writesubtitles"):
                raise
            opts = dict(opts)
            for k in ("writesubtitles", "writeautomaticsub", "subtitleslangs"):
                opts.pop(k, None)
            opts["postprocessors"] = [p for p in opts.get("postprocessors", [])
                                      if p.get("key") != "FFmpegEmbedSubtitle"]
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job["url"], download=True)
        # Record final filepath for "reveal".
        try:
            fp = None
            for rd in (info.get("requested_downloads") or []):
                fp = rd.get("filepath") or fp
            with self.lock:
                if self.jobs.get(job["id"]) and fp:
                    self.jobs[job["id"]]["filepath"] = fp
        except Exception:
            pass

    def _hook(self, job, d):
        jid = job["id"]
        if jid in self.cancelled:
            raise _Cancelled()
        if jid in self.paused:
            raise _Paused()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            with self.lock:
                j = self.jobs.get(jid)
                if j:
                    j["downloaded"] = done
                    j["total"] = total
                    j["speed"] = d.get("speed")
                    j["pct"] = (done / total * 100) if total else None
                    # Track temp files so we can delete them on cancel.
                    parts = j.setdefault("partials", set())
                    if d.get("tmpfilename"):
                        parts.add(d["tmpfilename"])
                    if d.get("filename"):
                        parts.add(d["filename"])
        elif d["status"] == "finished":
            with self.lock:
                j = self.jobs.get(job["id"])
                if j:
                    j["pct"] = 100


# --------------------------------------------------------------------------- #
# Single instance
# --------------------------------------------------------------------------- #
def acquire_single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen()
        return s
    except OSError:
        try:
            with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=1) as c:
                c.sendall(b"show")
        except OSError:
            pass
        s.close()
        return None


def _raise_existing_window():
    """Bring our window to the front with Win32 only. Must NOT call pywebview
    window methods here — doing so from this background thread deadlocks the
    GUI thread (freezes the app)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, APP_NAME)
        if hwnd:
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE (un-minimize)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _instance_listener(sock):
    while True:
        try:
            conn, _ = sock.accept()
            conn.close()
        except OSError:
            break
        _raise_existing_window()


def _unblock_bundle():
    """Strip 'Mark of the Web' (Zone.Identifier) from our bundled files so .NET
    can load Python.Runtime.dll even when the app was extracted from a
    downloaded zip. Without this, pywebview's pythonnet backend fails with
    'Failed to resolve Python.Runtime.Loader.Initialize'. Frozen .exe only."""
    if not getattr(sys, "frozen", False):
        return
    base = os.path.dirname(os.path.abspath(sys.executable))   # the app folder
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                os.remove(os.path.join(root, name) + ":Zone.Identifier")
            except OSError:
                pass


def main():
    _unblock_bundle()
    lock = acquire_single_instance()
    if lock is None:
        sys.exit(0)

    api = Api()
    window = webview.create_window(
        APP_NAME,
        url=resource_path(os.path.join("web", "index.html")),
        js_api=api,
        width=520, height=820, min_size=(440, 680),
        background_color="#0e0e10",     # dark while WebView2 warms up (no white flash)
    )
    api.window = window
    threading.Thread(target=_instance_listener, args=(lock,), daemon=True).start()
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
