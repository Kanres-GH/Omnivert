"""
Omnivert
--------
Paste a link from Instagram, TikTok, YouTube (Shorts or regular), Twitter/X,
Reddit (or any of yt-dlp's 1000+ supported sites) and download the
highest-quality, watermark-free video — or extract just the audio.

Engine: yt-dlp  |  Merge/convert: ffmpeg  |  UI: customtkinter (cobalt-style dark)
"""

import os
import sys
import glob
import json
import queue
import shutil
import socket
import threading
import subprocess
from pathlib import Path

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except ImportError:
    print("Missing deps. Run:  python -m pip install -U customtkinter")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("yt-dlp is not installed. Run:  python -m pip install -U yt-dlp")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Resource / ffmpeg location
# --------------------------------------------------------------------------- #
def resource_path(name: str) -> str:
    """Path to a bundled resource, works in dev and in the PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def find_ffmpeg() -> str | None:
    """Return the folder containing ffmpeg.exe, or None."""
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

# Single-instance lock / IPC port, and persisted settings.
LOCK_PORT = 50573
DEFAULT_OUT = str(Path.home() / "Downloads" / "Omnivert")


def config_path() -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "Omnivert")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "settings.json")


def load_settings() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# --- Option tables --------------------------------------------------------- #
VIDEO_QUALITY = {"Best": None, "2160p": 2160, "1440p": 1440,
                 "1080p": 1080, "720p": 720, "480p": 480}
VIDEO_CODEC = {"Auto (best)": None, "H.264": "avc", "VP9": "vp9", "AV1": "av01"}
VIDEO_CONTAINER = ["mp4", "mkv", "webm"]

AUDIO_FORMAT = ["mp3", "m4a", "opus", "wav", "flac"]
AUDIO_BITRATE = ["320", "256", "192", "128"]

BROWSERS = ["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium"]

# Cobalt-ish palette.
BG = "#0d0d0f"
CARD = "#161618"
FIELD = "#202024"
BORDER = "#2a2a2e"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#6b4ce0"
SUBTLE = "#8a8a92"
TEXT = "#f0f0f2"


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
class OmnivertApp(ctk.CTk):
    def __init__(self, lock_sock: socket.socket | None = None):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Omnivert")
        self.geometry("720x680")
        self.minsize(620, 600)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.msg_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self._settings = load_settings()
        self._lock_sock = lock_sock

        saved = self._settings.get("out_dir")
        self.out_dir = ctk.StringVar(value=saved if saved else DEFAULT_OUT)
        self.v_quality = ctk.StringVar(value="Best")
        self.v_codec = ctk.StringVar(value="Auto (best)")
        self.v_container = ctk.StringVar(value="mp4")
        self.v_name = ctk.StringVar(value="")
        self.a_format = ctk.StringVar(value="mp3")
        self.a_bitrate = ctk.StringVar(value="320")
        self.a_name = ctk.StringVar(value="")
        self.use_cookies = ctk.BooleanVar(value=False)
        self.browser = ctk.StringVar(value="chrome")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self._lock_sock is not None:
            threading.Thread(target=self._listen, daemon=True).start()
        self.after(100, self._drain_queue)

    # ----- UI ------------------------------------------------------------- #
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        ctk.CTkLabel(header, text="Omnivert",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(header, text="  instagram · tiktok · youtube · twitter · reddit",
                     font=ctk.CTkFont(size=13), text_color=SUBTLE).pack(side="left",
                                                                        pady=(8, 0))

        # URL input card
        url_card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16,
                                border_width=1, border_color=BORDER)
        url_card.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        url_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(url_card, text="Paste links — one per line",
                     font=ctk.CTkFont(size=12), text_color=SUBTLE).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.url_box = ctk.CTkTextbox(url_card, height=72, fg_color=FIELD,
                                      corner_radius=10, border_width=0,
                                      font=ctk.CTkFont(size=13), text_color=TEXT)
        self.url_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 8))
        btnrow = ctk.CTkFrame(url_card, fg_color="transparent")
        btnrow.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkButton(btnrow, text="Paste", width=80, fg_color=FIELD,
                      hover_color=BORDER, text_color=TEXT,
                      command=self._paste).pack(side="left")
        ctk.CTkButton(btnrow, text="Clear", width=80, fg_color=FIELD,
                      hover_color=BORDER, text_color=TEXT,
                      command=lambda: self.url_box.delete("1.0", "end")).pack(
            side="left", padx=8)

        # Tabs: Video / Audio
        self.tabs = ctk.CTkTabview(self, fg_color=CARD, corner_radius=16,
                                   border_width=1, border_color=BORDER,
                                   segmented_button_selected_color=ACCENT,
                                   segmented_button_selected_hover_color=ACCENT_HOVER,
                                   text_color=TEXT)
        self.tabs.grid(row=2, column=0, sticky="ew", padx=24, pady=8)
        self.tabs.add("Video")
        self.tabs.add("Audio")
        self._build_video_tab(self.tabs.tab("Video"))
        self._build_audio_tab(self.tabs.tab("Audio"))

        # Save-to row
        save = ctk.CTkFrame(self, fg_color="transparent")
        save.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 4))
        save.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(save, text="Save to", text_color=SUBTLE,
                     width=60, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(save, textvariable=self.out_dir, fg_color=FIELD,
                     border_width=0, text_color=TEXT).grid(row=0, column=1,
                                                           sticky="ew", padx=8)
        ctk.CTkButton(save, text="Browse", width=90, fg_color=FIELD,
                      hover_color=BORDER, text_color=TEXT,
                      command=self._choose_folder).grid(row=0, column=2)
        self.btn_remember = ctk.CTkButton(
            save, text="Remember", width=100, fg_color=FIELD, hover_color=BORDER,
            text_color=TEXT, command=self._remember_path)
        self.btn_remember.grid(row=0, column=3, padx=(8, 0))

        # Progress + log
        self.progress = ctk.CTkProgressBar(self, height=8, corner_radius=4,
                                           progress_color=ACCENT, fg_color=FIELD)
        self.progress.grid(row=5, column=0, sticky="ew", padx=24, pady=(6, 0))
        self.progress.set(0)
        self.log = ctk.CTkTextbox(self, fg_color="#0a0a0c", corner_radius=12,
                                  border_width=1, border_color=BORDER,
                                  font=ctk.CTkFont(size=12, family="Consolas"),
                                  text_color="#cfcfd4")
        self.log.grid(row=4, column=0, sticky="nsew", padx=24, pady=(8, 4))
        self.status = ctk.CTkLabel(self, text="Ready", text_color=SUBTLE,
                                   font=ctk.CTkFont(size=12))
        self.status.grid(row=6, column=0, sticky="w", padx=24, pady=(2, 10))

        if not FFMPEG_DIR:
            self._log("WARNING: ffmpeg not found — install with: winget install Gyan.FFmpeg\n")

    def _build_video_tab(self, tab):
        tab.grid_columnconfigure((0, 1, 2), weight=1)
        self._opt(tab, "Quality", self.v_quality, list(VIDEO_QUALITY), 0, 0)
        self._opt(tab, "Codec", self.v_codec, list(VIDEO_CODEC), 0, 1)
        self._opt(tab, "Container", self.v_container, VIDEO_CONTAINER, 0, 2)
        ctk.CTkLabel(tab, text="File name (optional)", text_color=SUBTLE,
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=3,
                                                     sticky="w", padx=10, pady=(10, 0))
        ctk.CTkEntry(tab, textvariable=self.v_name, fg_color=FIELD, border_width=0,
                     placeholder_text="leave blank to use the video's title",
                     text_color=TEXT).grid(row=3, column=0, columnspan=3,
                                           sticky="ew", padx=10, pady=(2, 6))
        self._cookie_row(tab, 4)
        self.btn_video = ctk.CTkButton(
            tab, text="⬇  Download Video", height=44, corner_radius=12,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self._start("video"))
        self.btn_video.grid(row=5, column=0, columnspan=3, sticky="ew",
                            padx=10, pady=(8, 12))

    def _build_audio_tab(self, tab):
        tab.grid_columnconfigure((0, 1, 2), weight=1)
        self._opt(tab, "Format", self.a_format, AUDIO_FORMAT, 0, 0)
        self._opt(tab, "Bitrate (kbps)", self.a_bitrate, AUDIO_BITRATE, 0, 1)
        ctk.CTkLabel(tab, text="lossless for wav / flac", text_color=SUBTLE,
                     font=ctk.CTkFont(size=11)).grid(row=1, column=2, sticky="sw",
                                                     padx=10, pady=(0, 8))
        ctk.CTkLabel(tab, text="File name (optional)", text_color=SUBTLE,
                     font=ctk.CTkFont(size=12)).grid(row=2, column=0, columnspan=3,
                                                     sticky="w", padx=10, pady=(10, 0))
        ctk.CTkEntry(tab, textvariable=self.a_name, fg_color=FIELD, border_width=0,
                     placeholder_text="leave blank to use the track's title",
                     text_color=TEXT).grid(row=3, column=0, columnspan=3,
                                           sticky="ew", padx=10, pady=(2, 6))
        self._cookie_row(tab, 4)
        self.btn_audio = ctk.CTkButton(
            tab, text="♫  Download Audio", height=44, corner_radius=12,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self._start("audio"))
        self.btn_audio.grid(row=5, column=0, columnspan=3, sticky="ew",
                            padx=10, pady=(8, 12))

    def _opt(self, tab, label, var, values, row, col):
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.grid(row=row, column=col, sticky="ew", padx=10, pady=(12, 0))
        ctk.CTkLabel(wrap, text=label, text_color=SUBTLE,
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkOptionMenu(wrap, variable=var, values=values, fg_color=FIELD,
                          button_color=FIELD, button_hover_color=BORDER,
                          text_color=TEXT, dropdown_fg_color=CARD,
                          corner_radius=10).pack(fill="x", pady=(2, 0))

    def _cookie_row(self, tab, row):
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.grid(row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 0))
        ctk.CTkCheckBox(wrap, text="Use browser login (private / blocked / age-restricted)",
                        variable=self.use_cookies, text_color=SUBTLE,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkOptionMenu(wrap, variable=self.browser, values=BROWSERS, width=110,
                          fg_color=FIELD, button_color=FIELD,
                          button_hover_color=BORDER, text_color=TEXT,
                          dropdown_fg_color=CARD).pack(side="left", padx=10)

    # ----- small helpers -------------------------------------------------- #
    def _paste(self):
        try:
            txt = self.clipboard_get()
            self.url_box.insert("end", txt.strip() + "\n")
        except Exception:
            pass

    def _choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.home()))
        if d:
            self.out_dir.set(d)

    def _log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def _remember_path(self):
        """Pin the current folder as the default for future launches."""
        path = self.out_dir.get().strip()
        if not path:
            return
        self._settings["out_dir"] = path
        save_settings(self._settings)
        self.status.configure(text=f"Default folder set to {path}")
        self.btn_remember.configure(text="Saved ✓")
        self.after(1500, lambda: self.btn_remember.configure(text="Remember"))

    def _set_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_video.configure(state=state)
        self.btn_audio.configure(state=state)

    # ----- single-instance / lifecycle ----------------------------------- #
    def _listen(self):
        """Second launches connect to our lock port; we raise the window."""
        while True:
            try:
                conn, _ = self._lock_sock.accept()
                conn.close()
                self.msg_queue.put(("front", None))
            except OSError:
                break

    def _show_front(self):
        """Un-minimize and force this window above all others."""
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _on_close(self):
        if self._lock_sock is not None:
            try:
                self._lock_sock.close()
            except Exception:
                pass
        self.destroy()

    # ----- download orchestration ---------------------------------------- #
    def _start(self, mode):
        if self.worker and self.worker.is_alive():
            return
        urls = [u.strip() for u in self.url_box.get("1.0", "end").splitlines()
                if u.strip()]
        if not urls:
            messagebox.showinfo("No links", "Paste at least one link.")
            return
        out = self.out_dir.get().strip()
        os.makedirs(out, exist_ok=True)

        self._set_buttons(False)
        self.progress.set(0)
        self.status.configure(text=f"Downloading {len(urls)} item(s)…")
        self._log(f"\n=== {mode.upper()}: {len(urls)} item(s) ===\n")
        self.worker = threading.Thread(target=self._run, args=(mode, urls, out),
                                       daemon=True)
        self.worker.start()

    def _outtmpl(self, out_dir, custom_name, many):
        if custom_name.strip():
            base = custom_name.strip()
            if many:
                base += " %(autonumber)02d"
            return os.path.join(out_dir, base + ".%(ext)s")
        return os.path.join(out_dir, "%(title).80B [%(id)s].%(ext)s")

    def _build_opts(self, mode, out_dir, many):
        opts = {
            "outtmpl": self._outtmpl(
                out_dir, self.v_name.get() if mode == "video" else self.a_name.get(),
                many),
            "progress_hooks": [self._progress_hook],
            "logger": _QueueLogger(self.msg_queue),
            "noprogress": True,
            "noplaylist": False,
            "windowsfilenames": True,
            "ignoreerrors": False,
        }
        if FFMPEG_DIR:
            opts["ffmpeg_location"] = FFMPEG_DIR
        if self.use_cookies.get():
            opts["cookiesfrombrowser"] = (self.browser.get(),)

        if mode == "audio":
            opts["format"] = "bestaudio/best"
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": self.a_format.get()}
            if self.a_format.get() not in ("wav", "flac"):
                pp["preferredquality"] = self.a_bitrate.get()
            opts["postprocessors"] = [pp]
        else:
            height = VIDEO_QUALITY[self.v_quality.get()]
            vcodec = VIDEO_CODEC[self.v_codec.get()]
            filt = ""
            if height:
                filt += f"[height<={height}]"
            if vcodec:
                filt += f"[vcodec^={vcodec}]"
            fallback = "best" + (f"[height<={height}]" if height else "")
            opts["format"] = f"bestvideo{filt}+bestaudio/{fallback}/best"
            opts["merge_output_format"] = self.v_container.get()
        return opts

    def _run(self, mode, urls, out_dir):
        ok = fail = 0
        produced: list[str] = []
        for url in urls:
            self.msg_queue.put(("log", f"\n→ {url}\n"))
            try:
                with yt_dlp.YoutubeDL(self._build_opts(mode, out_dir,
                                                       len(urls) > 1)) as ydl:
                    info = ydl.extract_info(url, download=True)
                _collect_paths(info, produced)
                ok += 1
            except Exception as e:
                fail += 1
                msg = str(e)
                self.msg_queue.put(("log", f"  ERROR: {msg}\n"))
                low = msg.lower()
                if any(k in low for k in ("login", "rate-limit", "empty media",
                                          "private", "cookies")):
                    self.msg_queue.put(("log",
                        "  Tip: tick 'Use browser login' and pick your signed-in "
                        "browser, then retry.\n"))
        self.msg_queue.put(("done", (ok, fail, out_dir, produced)))

    def _progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                self.msg_queue.put(("progress",
                                    d.get("downloaded_bytes", 0) / total))
        elif d["status"] == "finished":
            self.msg_queue.put(("progress", 1.0))
            self.msg_queue.put(("log", "  processing…\n"))

    # ----- queue pump (GUI thread) --------------------------------------- #
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "front":
                    self._show_front()
                elif kind == "progress":
                    self.progress.set(payload)
                elif kind == "done":
                    ok, fail, out_dir, produced = payload
                    self._log(f"\n=== Done: {ok} ok, {fail} failed ===\n")
                    self.status.configure(text=f"Done — {ok} ok, {fail} failed")
                    self._set_buttons(True)
                    self.progress.set(0)
                    reveal_files(out_dir, produced)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #
def _collect_paths(info, acc):
    if not info:
        return
    entries = info.get("entries")
    if entries:
        for e in entries:
            _collect_paths(e, acc)
    for rd in info.get("requested_downloads", []) or []:
        fp = rd.get("filepath") or rd.get("_filename")
        if fp:
            acc.append(fp)
    if not info.get("requested_downloads") and info.get("filepath"):
        acc.append(info["filepath"])


def reveal_files(out_dir, paths):
    """Open the folder; highlight the file(s) when possible (Windows)."""
    existing = [os.path.normpath(p) for p in paths if p and os.path.exists(p)]
    try:
        if not existing:
            os.startfile(out_dir)
        elif len(existing) == 1:
            subprocess.run(f'explorer /select,"{existing[0]}"')
        else:
            # explorer highlights a single item; select the first, rest are visible.
            subprocess.run(f'explorer /select,"{existing[0]}"')
    except Exception:
        try:
            os.startfile(out_dir)
        except Exception:
            pass


class _QueueLogger:
    def __init__(self, q):
        self.q = q

    def debug(self, msg):
        if not msg.startswith("[debug] ") and msg.strip():
            self.q.put(("log", "  " + msg + "\n"))

    def info(self, msg):
        if msg.strip():
            self.q.put(("log", "  " + msg + "\n"))

    def warning(self, msg):
        self.q.put(("log", "  ! " + msg + "\n"))

    def error(self, msg):
        self.q.put(("log", "  ERROR: " + msg + "\n"))


def acquire_single_instance() -> socket.socket | None:
    """Bind the lock port. If already taken, ping the running instance and
    return None so this launch can exit."""
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


if __name__ == "__main__":
    lock = acquire_single_instance()
    if lock is None:
        sys.exit(0)  # another instance is already running and was brought forward
    OmnivertApp(lock).mainloop()
