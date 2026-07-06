"""
YouTube Audio Downloader - GUI version
Wraps yt-dlp in a native Windows desktop application using Tkinter.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

APP_VERSION = "1.0.0"
GITHUB_REPO = "ramdanolii14/yt-music-download-cover"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _base_dir():
    """Folder next to the exe when frozen by PyInstaller, otherwise the script's folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return APP_DIR


BASE_DIR = _base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "settings.json")

# Prevent a console window from popping up for each subprocess call on Windows
_NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_PROGRESS_RE = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d)?)%")


def _popen(cmd):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_NO_WINDOW_FLAGS,
        env=env,
    )


def _fix_windows_dpi_blur():
    """Tell Windows this app is DPI-aware so it isn't upscaled/blurred on HiDPI displays."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _resource_path(filename):
    """Resolve a bundled resource whether running as a script or a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", APP_DIR)
    return os.path.join(base, filename)


def _show_windows_notification(hwnd, title, message):
    """Show a Windows tray balloon notification attributed to this app's own window,
    using the Win32 API directly instead of spawning a separate PowerShell process
    (which would otherwise show up as the notification's source)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        import time

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
            ]

        NIF_ICON = 0x00000002
        NIF_TIP = 0x00000004
        NIF_INFO = 0x00000010
        NIM_ADD = 0x00000000
        NIM_DELETE = 0x00000002
        NIIF_INFO = 0x00000001
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040

        hicon = 0
        icon_path = _resource_path("icon.ico")
        if os.path.isfile(icon_path):
            hicon = ctypes.windll.user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = wintypes.HWND(hwnd)
        nid.uID = 1
        nid.uFlags = NIF_TIP | NIF_INFO | (NIF_ICON if hicon else 0)
        nid.hIcon = hicon
        nid.szTip = "YouTube Audio Downloader"
        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = NIIF_INFO

        ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        time.sleep(6)
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    except Exception:
        pass


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Audio Downloader")
        self.root.geometry("760x600")
        self.root.resizable(False, False)

        # State
        self.log_queue = queue.Queue()
        self.output_dir = tk.StringVar(value=BASE_DIR)
        self.cookies_path = tk.StringVar(value=os.path.join(BASE_DIR, "cookies.txt"))
        self.audio_format = tk.StringVar(value="mp3")
        self.video_resolution = tk.StringVar(value="Best available")
        self.playlist_mode = tk.StringVar(value="auto")
        self.restrict_filenames = tk.BooleanVar(value=True)
        self.ffmpeg_path = tk.StringVar(value="")
        self.deno_path = tk.StringVar(value="")
        self.dark_mode = tk.BooleanVar(value=False)
        self.is_downloading = False
        self.cancel_event = threading.Event()
        self.current_process = None

        self.preview_title = tk.StringVar(value="")
        self.preview_channel = tk.StringVar(value="")
        self.preview_duration = tk.StringVar(value="")

        self._load_settings()
        self._build_ui()
        self._on_format_change()
        self._apply_theme()
        self._check_dependencies_ui()
        self._show_page("home")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_log_queue)
        self._check_for_updates(silent=True)

    # ---------- Settings persistence ----------

    def _load_settings(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        out_dir = data.get("output_dir", "")
        if out_dir and os.path.isdir(out_dir):
            self.output_dir.set(out_dir)

        cookies = data.get("cookies_path", "")
        if cookies and os.path.isfile(cookies):
            self.cookies_path.set(cookies)

        if data.get("audio_format") in ("mp3", "flac", "wav", "mp4"):
            self.audio_format.set(data["audio_format"])

        if data.get("video_resolution"):
            self.video_resolution.set(data["video_resolution"])

        if data.get("playlist_mode") in ("auto", "single video only", "full playlist"):
            self.playlist_mode.set(data["playlist_mode"])

        if isinstance(data.get("restrict_filenames"), bool):
            self.restrict_filenames.set(data["restrict_filenames"])

        ffmpeg_path = data.get("ffmpeg_path", "")
        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            self.ffmpeg_path.set(ffmpeg_path)

        deno_path = data.get("deno_path", "")
        if deno_path and os.path.isfile(deno_path):
            self.deno_path.set(deno_path)

        if isinstance(data.get("dark_mode"), bool):
            self.dark_mode.set(data["dark_mode"])

    def _save_settings(self):
        data = {
            "output_dir": self.output_dir.get(),
            "cookies_path": self.cookies_path.get(),
            "audio_format": self.audio_format.get(),
            "video_resolution": self.video_resolution.get(),
            "playlist_mode": self.playlist_mode.get(),
            "restrict_filenames": self.restrict_filenames.get(),
            "ffmpeg_path": self.ffmpeg_path.get(),
            "deno_path": self.deno_path.get(),
            "dark_mode": self.dark_mode.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _on_close(self):
        self._save_settings()
        self.root.destroy()

    # ---------- UI construction ----------

    def _build_ui(self):
        self._build_sidebar()

        self.content = tk.Frame(self.root)
        self.content.pack(side="left", fill="both", expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        self.home_frame = ttk.Frame(self.content)
        self.settings_frame = ttk.Frame(self.content)
        self.home_frame.grid(row=0, column=0, sticky="nsew")
        self.settings_frame.grid(row=0, column=0, sticky="nsew")

        self._build_home_page(self.home_frame)
        self._build_settings_page(self.settings_frame)

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.root, width=170)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        title_lbl = ttk.Label(
            self.sidebar, text="YT Audio\nDownloader", font=("Segoe UI", 12, "bold"),
            anchor="w", justify="left"
        )
        title_lbl.pack(fill="x", padx=14, pady=(20, 24))

        self.nav_home_btn = ttk.Button(self.sidebar, text="Home", command=lambda: self._show_page("home"))
        self.nav_home_btn.pack(fill="x", padx=12, pady=4)

        self.nav_settings_btn = ttk.Button(
            self.sidebar, text="Settings", command=lambda: self._show_page("settings")
        )
        self.nav_settings_btn.pack(fill="x", padx=12, pady=4)

        spacer = ttk.Frame(self.sidebar)
        spacer.pack(fill="both", expand=True)

        self.version_lbl = ttk.Label(self.sidebar, text=f"v{APP_VERSION}", foreground="gray")
        self.version_lbl.pack(pady=10)

    def _show_page(self, name):
        if name == "home":
            self.home_frame.tkraise()
        else:
            self.settings_frame.tkraise()

    # ---------- Home page ----------

    def _build_home_page(self, parent):
        pad = {"padx": 14, "pady": 8}

        link_frame = ttk.LabelFrame(parent, text="Link(s)")
        link_frame.pack(fill="x", **pad)

        ttk.Label(link_frame, text="One link per line. A single line = single download.").pack(
            anchor="w", padx=8, pady=(6, 0)
        )
        self.links_text = tk.Text(link_frame, height=5, wrap="none")
        self.links_text.pack(fill="x", padx=8, pady=6)

        btn_row = ttk.Frame(link_frame)
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_row, text="Load from links.txt", command=self._load_links_file).pack(side="left")
        ttk.Button(btn_row, text="Clear", command=lambda: self.links_text.delete("1.0", tk.END)).pack(
            side="left", padx=6
        )
        ttk.Button(btn_row, text="Preview", command=self._preview_link).pack(side="left", padx=6)

        preview_frame = ttk.LabelFrame(parent, text="Preview")
        preview_frame.pack(fill="x", **pad)
        ttk.Label(preview_frame, textvariable=self.preview_title, wraplength=680).pack(anchor="w", padx=8, pady=(6, 0))
        ttk.Label(preview_frame, textvariable=self.preview_channel).pack(anchor="w", padx=8)
        ttk.Label(preview_frame, textvariable=self.preview_duration).pack(anchor="w", padx=8, pady=(0, 6))

        action_frame = ttk.Frame(parent)
        action_frame.pack(fill="x", **pad)
        self.download_btn = ttk.Button(action_frame, text="Download", command=self._start_download)
        self.download_btn.pack(side="left")
        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self._cancel_download, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)

        progress_frame = ttk.Frame(parent)
        progress_frame.pack(fill="x", **pad)
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = ttk.Label(progress_frame, text="0%", width=6)
        self.progress_label.pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(parent, text="Checking dependencies...", foreground="gray")
        self.status_label.pack(anchor="w", padx=14)

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=6)

    # ---------- Settings page ----------

    def _build_settings_page(self, parent):
        pad = {"padx": 14, "pady": 8}

        out_frame = ttk.LabelFrame(parent, text="Output folder")
        out_frame.pack(fill="x", **pad)
        row = ttk.Frame(out_frame)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._browse_output_dir).pack(side="left", padx=(6, 0))
        ttk.Button(out_frame, text="Open output folder", command=self._open_output_dir).pack(
            anchor="w", padx=8, pady=(0, 8)
        )

        cookies_frame = ttk.LabelFrame(parent, text="cookies.txt")
        cookies_frame.pack(fill="x", **pad)
        row2 = ttk.Frame(cookies_frame)
        row2.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row2, textvariable=self.cookies_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Browse...", command=self._browse_cookies).pack(side="left", padx=(6, 0))

        opt_frame = ttk.LabelFrame(parent, text="Download options")
        opt_frame.pack(fill="x", **pad)
        row3 = ttk.Frame(opt_frame)
        row3.pack(fill="x", padx=8, pady=6)
        ttk.Label(row3, text="Format:").pack(side="left")
        self.format_combo = ttk.Combobox(
            row3, textvariable=self.audio_format, values=["mp3", "flac", "wav", "mp4"], width=8, state="readonly"
        )
        self.format_combo.pack(side="left", padx=(6, 20))
        self.format_combo.bind("<<ComboboxSelected>>", self._on_format_change)
        ttk.Label(row3, text="Playlist:").pack(side="left")
        ttk.Combobox(
            row3, textvariable=self.playlist_mode,
            values=["auto", "single video only", "full playlist"], width=18, state="readonly"
        ).pack(side="left", padx=6)

        row3b = ttk.Frame(opt_frame)
        row3b.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row3b, text="Resolution:").pack(side="left")
        self.resolution_combo = ttk.Combobox(
            row3b, textvariable=self.video_resolution, values=["Best available"], width=16, state="disabled"
        )
        self.resolution_combo.pack(side="left", padx=6)
        self.resolution_hint = ttk.Label(
            row3b, text="(MP4 only — click Preview on Home to load resolutions for that video)",
            foreground="gray"
        )
        self.resolution_hint.pack(side="left", padx=(8, 0))

        row4 = ttk.Frame(opt_frame)
        row4.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Checkbutton(
            row4, text="Restrict filenames (safer for Windows)", variable=self.restrict_filenames
        ).pack(side="left")

        tools_frame = ttk.LabelFrame(parent, text="Tools")
        tools_frame.pack(fill="x", **pad)
        row5 = ttk.Frame(tools_frame)
        row5.pack(fill="x", padx=8, pady=8)
        self.setup_btn = ttk.Button(
            row5, text="Auto Setup (yt-dlp + ffmpeg + Deno)", command=self._auto_setup
        )
        self.setup_btn.pack(side="left")
        ttk.Button(row5, text="Update yt-dlp", command=self._update_ytdlp).pack(side="left", padx=6)

        appearance_frame = ttk.LabelFrame(parent, text="Appearance")
        appearance_frame.pack(fill="x", **pad)
        ttk.Checkbutton(
            appearance_frame, text="Dark mode", variable=self.dark_mode, command=self._toggle_dark_mode
        ).pack(anchor="w", padx=8, pady=8)

        update_frame = ttk.LabelFrame(parent, text="Updates")
        update_frame.pack(fill="x", **pad)
        row6 = ttk.Frame(update_frame)
        row6.pack(fill="x", padx=8, pady=8)
        ttk.Button(row6, text="Check for updates", command=lambda: self._check_for_updates(silent=False)).pack(
            side="left"
        )
        self.update_status_label = ttk.Label(update_frame, text=f"Current version: v{APP_VERSION}", foreground="gray")
        self.update_status_label.pack(anchor="w", padx=8, pady=(0, 8))

    # ---------- Theme ----------

    def _on_format_change(self, event=None):
        if self.audio_format.get() == "mp4":
            self.resolution_combo.config(state="readonly")
        else:
            self.resolution_combo.config(state="disabled")
        self._save_settings()

    def _toggle_dark_mode(self):
        self._save_settings()
        self._apply_theme()

    def _apply_theme(self):
        style = ttk.Style()
        dark = self.dark_mode.get()

        if dark:
            style.theme_use("clam")
            bg, fg, field_bg, btn_bg, btn_active = "#1e1e1e", "#e6e6e6", "#2b2b2b", "#333333", "#3f3f3f"
        else:
            try:
                style.theme_use("vista")
            except tk.TclError:
                style.theme_use("clam")
            bg, fg, field_bg, btn_bg, btn_active = "#f0f0f0", "#000000", "#ffffff", "#e1e1e1", "#d0d0d0"

        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TButton", background=btn_bg, foreground=fg)
        style.map("TButton", background=[("active", btn_active)])
        style.configure("TCombobox", fieldbackground=field_bg, foreground=fg)
        style.configure("TEntry", fieldbackground=field_bg, foreground=fg)

        self.root.configure(background=bg)
        if hasattr(self, "sidebar"):
            self.sidebar.configure(background=bg)
        if hasattr(self, "content"):
            self.content.configure(background=bg)
        if hasattr(self, "links_text"):
            self.links_text.configure(bg=field_bg, fg=fg, insertbackground=fg)
        if hasattr(self, "log_text"):
            self.log_text.configure(bg=field_bg, fg=fg, insertbackground=fg)

    # ---------- Dependency checks ----------

    def _has_ffmpeg(self):
        if shutil.which("ffmpeg") is not None:
            return True
        path = self.ffmpeg_path.get()
        return bool(path) and os.path.isfile(path)

    def _has_deno(self):
        if shutil.which("deno") is not None:
            return True
        path = self.deno_path.get()
        return bool(path) and os.path.isfile(path)

    def _download_portable_tool(self, url, subfolder, exe_name, label):
        target_dir = os.path.join(BASE_DIR, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        zip_path = os.path.join(target_dir, f"{subfolder}_download.zip")

        last_percent = {"value": -10}

        def _progress(count, block_size, total_size):
            if total_size <= 0:
                return
            percent = int(count * block_size * 100 / total_size)
            if percent - last_percent["value"] >= 10:
                last_percent["value"] = percent
                self._log(f"Downloading {label}... {min(percent, 100)}%\n")

        self._log(f"Downloading {label}...\n")
        urllib.request.urlretrieve(url, zip_path, reporthook=_progress)
        self._log(f"{label} download complete. Extracting...\n")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        os.remove(zip_path)

        for root_dir, _dirs, files in os.walk(target_dir):
            if exe_name in files:
                return os.path.join(root_dir, exe_name)
        return None

    def _check_dependencies_ui(self):
        missing = []
        if shutil.which("yt-dlp") is None:
            missing.append("yt-dlp")
        if not self._has_ffmpeg():
            missing.append("ffmpeg")

        if missing:
            msg = f"Missing: {', '.join(missing)}. Go to Settings > Auto Setup to install automatically."
            self.status_label.config(text=msg, foreground="red")
            self.download_btn.config(state="disabled")
        elif not self._has_deno():
            self.status_label.config(
                text="Ready, but Deno is missing (some formats may be limited). See Settings > Auto Setup.",
                foreground="#b8860b",
            )
            self.download_btn.config(state="normal")
        else:
            self.status_label.config(text="Ready. All tools verified.", foreground="green")
            self.download_btn.config(state="normal")

    # ---------- File dialogs ----------

    def _load_links_file(self):
        path = filedialog.askopenfilename(
            initialdir=BASE_DIR, title="Select links.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.links_text.delete("1.0", tk.END)
        self.links_text.insert("1.0", content)

    def _browse_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir.get())
        if path:
            self.output_dir.set(path)
            self._save_settings()

    def _browse_cookies(self):
        path = filedialog.askopenfilename(
            initialdir=BASE_DIR, title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self.cookies_path.set(path)
            self._save_settings()

    def _open_output_dir(self):
        path = self.output_dir.get()
        if os.path.isdir(path):
            os.startfile(path)  # noqa: Windows-only, intentional
        else:
            messagebox.showerror("Error", "Output folder does not exist.")

    # ---------- Logging ----------

    def _log(self, text):
        self.log_queue.put(("log", text))

    def _set_progress(self, percent):
        self.log_queue.put(("progress", percent))

    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self.log_text.insert(tk.END, payload)
                    self.log_text.see(tk.END)
                    match = _PROGRESS_RE.search(payload)
                    if match:
                        self._update_progress_widgets(float(match.group(1)))
                elif kind == "progress":
                    self._update_progress_widgets(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _update_progress_widgets(self, percent):
        percent = max(0, min(100, percent))
        self.progress_bar["value"] = percent
        self.progress_label.config(text=f"{percent:.0f}%")

    # ---------- Preview ----------

    def _preview_link(self):
        links = self._get_links()
        if not links:
            messagebox.showwarning("No link", "Enter a link first.")
            return
        link = links[0]
        if "youtube.com" not in link and "youtu.be" not in link:
            messagebox.showerror("Error", "That doesn't look like a valid YouTube link.")
            return

        self.preview_title.set("Fetching info...")
        self.preview_channel.set("")
        self.preview_duration.set("")
        threading.Thread(target=self._preview_worker, args=(link,), daemon=True).start()

    def _preview_worker(self, link):
        cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--skip-download", "--no-warnings"]
        cookies = self.cookies_path.get()
        if os.path.isfile(cookies):
            cmd += ["--cookies", cookies]
        cmd.append(link)

        try:
            process = _popen(cmd)
            output, _ = process.communicate(timeout=30)
            process.wait()
            first_line = output.strip().splitlines()[0] if output and output.strip() else ""
            data = json.loads(first_line)
            title = data.get("title", "Unknown title")
            channel = data.get("channel") or data.get("uploader") or "Unknown channel"
            duration = data.get("duration_string") or ""

            heights = set()
            for fmt in data.get("formats", []):
                h = fmt.get("height")
                vcodec = fmt.get("vcodec")
                if h and vcodec and vcodec != "none":
                    heights.add(int(h))
            resolution_labels = ["Best available"] + [f"{h}p" for h in sorted(heights, reverse=True)]

            def update_ui():
                self.preview_title.set(f"Title: {title}")
                self.preview_channel.set(f"Channel: {channel}")
                self.preview_duration.set(f"Duration: {duration}" if duration else "")

                if hasattr(self, "resolution_combo"):
                    self.resolution_combo["values"] = resolution_labels
                    if self.video_resolution.get() not in resolution_labels:
                        self.video_resolution.set(resolution_labels[0])
                    if self.audio_format.get() == "mp4":
                        self.resolution_combo.config(state="readonly")
                    if len(resolution_labels) > 1 and hasattr(self, "resolution_hint"):
                        self.resolution_hint.config(
                            text=f"({len(resolution_labels) - 1} resolutions available for this video)"
                        )

            self.root.after(0, update_ui)
        except Exception as e:
            def update_ui_err():
                self.preview_title.set("Could not fetch preview info.")
                self.preview_channel.set(str(e))
                self.preview_duration.set("")

            self.root.after(0, update_ui_err)

    # ---------- Download logic ----------

    def _get_links(self):
        raw = self.links_text.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _playlist_flag(self, link):
        mode = self.playlist_mode.get()
        if mode == "single video only":
            return "--no-playlist"
        if mode == "full playlist":
            return "--yes-playlist"
        if "list=" in link and "watch?v=" in link:
            return "--no-playlist"
        if "list=" in link:
            return "--yes-playlist"
        return "--no-playlist"

    def _build_command(self, link):
        cookies = self.cookies_path.get()
        out_dir = self.output_dir.get()
        audioformat = self.audio_format.get()

        cmd = ["yt-dlp", "--remote-components", "ejs:github", link]

        if os.path.isfile(cookies):
            cmd += ["--cookies", cookies]

        if shutil.which("ffmpeg") is None and self.ffmpeg_path.get():
            cmd += ["--ffmpeg-location", os.path.dirname(self.ffmpeg_path.get())]

        if shutil.which("deno") is None and self.deno_path.get():
            cmd += ["--js-runtimes", f"deno:{self.deno_path.get()}"]

        cmd += [self._playlist_flag(link)]

        if self.restrict_filenames.get():
            cmd += ["--restrict-filenames"]

        cmd += [
            "--newline",
            "--embed-thumbnail",
            "--embed-metadata",
            "--parse-metadata", "%(channel)s:%(artist)s",
            "--parse-metadata", "%(channel)s:%(album_artist)s",
        ]

        if audioformat == "mp4":
            cmd += [
                "-f", self._video_format_selector(),
                "--merge-output-format", "mp4",
            ]
        else:
            cmd += [
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", audioformat,
                "--audio-quality", "0",
            ]

        cmd += [
            "--retries", "5",
            "--sleep-requests", "1",
            "-o", os.path.join(out_dir, "%(title)s.%(ext)s"),
        ]
        return cmd

    def _video_format_selector(self):
        """Build a yt-dlp format selector from the resolution the user picked after
        previewing the actual video. Never hardcodes a resolution — if nothing has
        been fetched yet, or 'Best available' is selected, it just asks for the best."""
        label = self.video_resolution.get()
        if not label or label == "Best available":
            return "bestvideo+bestaudio/best"
        height = "".join(ch for ch in label if ch.isdigit())
        if not height:
            return "bestvideo+bestaudio/best"
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"

    def _start_download(self):
        if self.is_downloading:
            return

        links = self._get_links()
        if not links:
            messagebox.showwarning("No links", "Enter at least one YouTube link.")
            return

        valid_links = [l for l in links if "youtube.com" in l or "youtu.be" in l]
        if len(valid_links) != len(links):
            if not messagebox.askyesno(
                "Invalid links found",
                "Some entries don't look like YouTube links. Continue anyway with only the valid ones?"
            ):
                return
        if not valid_links:
            messagebox.showerror("Error", "No valid YouTube links found.")
            return

        self.is_downloading = True
        self.cancel_event.clear()
        self.download_btn.config(state="disabled", text="Downloading...")
        self.cancel_btn.config(state="normal")
        self._update_progress_widgets(0)
        self._log(f"\n=== Starting download of {len(valid_links)} link(s) ===\n")
        thread = threading.Thread(target=self._run_downloads, args=(valid_links,), daemon=True)
        thread.start()

    def _cancel_download(self):
        if not self.is_downloading:
            return
        self.cancel_event.set()
        self._log("\n[!] Cancelling after the current file...\n")
        if self.current_process is not None and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
            except Exception:
                pass
        self.cancel_btn.config(state="disabled")

    def _run_downloads(self, links):
        total = len(links)
        cancelled = False
        for i, link in enumerate(links, start=1):
            if self.cancel_event.is_set():
                cancelled = True
                break

            self._log(f"\n=== [{i}/{total}] Downloading: {link} ===\n")
            self._update_progress_widgets(0)
            cmd = self._build_command(link)
            try:
                process = _popen(cmd)
                self.current_process = process
                for line in process.stdout:
                    self._log(line)
                    if self.cancel_event.is_set():
                        break
                process.wait()
                self.current_process = None
                if self.cancel_event.is_set():
                    cancelled = True
                    self._log("\n[!] Download cancelled by user.\n")
                    break
                if process.returncode != 0:
                    self._log(f"\n[WARNING] Link finished with errors (exit code {process.returncode})\n")
            except FileNotFoundError:
                self._log("\n[ERROR] yt-dlp not found. Make sure it's installed and in PATH.\n")
                break
            except Exception as e:
                import traceback
                self._log(f"\n[ERROR] {type(e).__name__}: {e}\n")
                self._log(traceback.format_exc() + "\n")

        if cancelled:
            self._log("\n=== Download cancelled ===\n")
        else:
            self._log("\n=== All downloads finished ===\n")
        self.root.after(0, lambda: self._download_finished(cancelled))

    def _download_finished(self, cancelled=False):
        self.is_downloading = False
        self.current_process = None
        self.download_btn.config(state="normal", text="Download")
        self.cancel_btn.config(state="disabled")
        self._update_progress_widgets(100 if not cancelled else 0)

        hwnd = self.root.winfo_id()
        if cancelled:
            threading.Thread(
                target=lambda: _show_windows_notification(hwnd, "Download Cancelled", "The download was cancelled."),
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=lambda: _show_windows_notification(
                    hwnd, "Download Complete", "All downloads finished successfully."
                ),
                daemon=True,
            ).start()

    # ---------- Auto Setup ----------

    def _auto_setup(self):
        self._show_page("home")
        self._log("\n=== Starting Auto Setup ===\n")
        self.setup_btn.config(state="disabled", text="Setting up...")
        threading.Thread(target=self._auto_setup_worker, daemon=True).start()

    def _auto_setup_worker(self):
        if shutil.which("yt-dlp") is None:
            self._log("yt-dlp not found. Installing via pip...\n")
            try:
                process = _popen(["pip", "install", "--upgrade", "yt-dlp"])
                for line in process.stdout:
                    self._log(line)
                process.wait()
                if process.returncode == 0:
                    self._log("yt-dlp installed successfully.\n")
                else:
                    self._log(f"[WARNING] pip exited with code {process.returncode}\n")
            except FileNotFoundError:
                self._log("[ERROR] pip not found. Install Python from python.org first (it includes pip).\n")
            except Exception as e:
                self._log(f"[ERROR] Failed to install yt-dlp: {e}\n")
        else:
            self._log("yt-dlp already installed, skipping.\n")

        if self._has_ffmpeg():
            self._log("ffmpeg already available, skipping.\n")
        else:
            self._log("ffmpeg not found. Downloading a portable build (this can take a few minutes)...\n")
            try:
                found = self._download_portable_tool(FFMPEG_URL, "ffmpeg", "ffmpeg.exe", "ffmpeg")
                if found:
                    self.ffmpeg_path.set(found)
                    self._save_settings()
                    self._log(f"ffmpeg is ready at: {found}\n")
                else:
                    self._log("[ERROR] Downloaded ffmpeg but couldn't locate ffmpeg.exe inside it.\n")
            except Exception as e:
                self._log(f"[ERROR] Failed to set up ffmpeg: {e}\n")
                self._log("You can still install ffmpeg manually from https://www.gyan.dev/ffmpeg/builds/\n")

        if self._has_deno():
            self._log("Deno already available, skipping.\n")
        else:
            self._log("Deno not found. Downloading a portable build...\n")
            try:
                found = self._download_portable_tool(DENO_URL, "deno", "deno.exe", "Deno")
                if found:
                    self.deno_path.set(found)
                    self._save_settings()
                    self._log(f"Deno is ready at: {found}\n")
                else:
                    self._log("[ERROR] Downloaded Deno but couldn't locate deno.exe inside it.\n")
            except Exception as e:
                self._log(f"[ERROR] Failed to set up Deno: {e}\n")
                self._log("You can still install Deno manually: winget install DenoLand.Deno\n")

        self._log("\n--- Verifying setup ---\n")
        self._verify_tool("yt-dlp", shutil.which("yt-dlp") or "yt-dlp")
        self._verify_tool("ffmpeg", shutil.which("ffmpeg") or self.ffmpeg_path.get())
        self._verify_tool("Deno", shutil.which("deno") or self.deno_path.get())

        self._log("=== Auto Setup finished ===\n")
        self.root.after(0, self._auto_setup_done)

    def _verify_tool(self, label, path_or_cmd):
        if not path_or_cmd:
            self._log(f"[ERROR] {label}: not available, setup did not succeed.\n")
            return
        try:
            process = _popen([path_or_cmd, "--version"])
            output, _ = process.communicate(timeout=20)
            process.wait()
            first_line = (output or "").strip().splitlines()[0] if output and output.strip() else ""
            if process.returncode == 0 or first_line:
                self._log(f"[OK] {label}: {first_line if first_line else 'responded successfully'}\n")
            else:
                self._log(f"[WARNING] {label}: exited with code {process.returncode}, might not be working correctly.\n")
        except FileNotFoundError:
            self._log(f"[ERROR] {label}: executable not found at '{path_or_cmd}'.\n")
        except subprocess.TimeoutExpired:
            self._log(f"[ERROR] {label}: did not respond in time.\n")
        except Exception as e:
            self._log(f"[ERROR] {label}: verification failed ({e}).\n")

    def _auto_setup_done(self):
        self.setup_btn.config(state="normal", text="Auto Setup (yt-dlp + ffmpeg + Deno)")
        self._check_dependencies_ui()

    def _update_ytdlp(self):
        self._show_page("home")
        self._log("\n=== Updating yt-dlp ===\n")

        def run_update():
            pip_needed = False
            try:
                process = _popen(["yt-dlp", "-U"])
                for line in process.stdout:
                    self._log(line)
                    if "installed yt-dlp with pip" in line.lower():
                        pip_needed = True
                process.wait()
            except Exception as e:
                self._log(f"\n[ERROR] {e}\n")
                return

            if pip_needed:
                self._log("\nDetected a pip installation, switching to pip upgrade...\n")
                try:
                    process = _popen(["pip", "install", "--upgrade", "yt-dlp"])
                    for line in process.stdout:
                        self._log(line)
                    process.wait()
                    if process.returncode == 0:
                        self._log("\nyt-dlp updated successfully via pip.\n")
                    else:
                        self._log(f"\n[WARNING] pip upgrade finished with exit code {process.returncode}\n")
                except FileNotFoundError:
                    self._log("\n[ERROR] pip not found. Make sure Python and pip are installed and in PATH.\n")
                except Exception as e:
                    self._log(f"\n[ERROR] {e}\n")

        threading.Thread(target=run_update, daemon=True).start()

    # ---------- Self-update check ----------

    def _check_for_updates(self, silent=True):
        def to_tuple(version_str):
            parts = []
            for p in version_str.split("."):
                num = "".join(ch for ch in p if ch.isdigit())
                parts.append(int(num) if num else 0)
            return tuple(parts)

        def worker():
            try:
                req = urllib.request.Request(
                    GITHUB_API_LATEST, headers={"User-Agent": "YT-Audio-Downloader"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                latest_tag = data.get("tag_name", "").lstrip("vV")
                current = APP_VERSION.lstrip("vV")
                is_newer = bool(latest_tag) and to_tuple(latest_tag) > to_tuple(current)

                def update_ui():
                    if not hasattr(self, "update_status_label"):
                        return
                    if is_newer:
                        self.update_status_label.config(
                            text=f"New version available: v{latest_tag} (current: v{APP_VERSION})",
                            foreground="#b8860b",
                        )
                        if not silent:
                            if messagebox.askyesno(
                                "Update available",
                                f"A new version (v{latest_tag}) is available. Open the releases page?"
                            ):
                                webbrowser.open(RELEASES_PAGE)
                    else:
                        self.update_status_label.config(
                            text=f"You're using the latest version (v{APP_VERSION}).", foreground="green"
                        )
                        if not silent:
                            messagebox.showinfo("Up to date", "You're using the latest version.")

                self.root.after(0, update_ui)
            except Exception as e:
                def update_ui_err():
                    if hasattr(self, "update_status_label"):
                        self.update_status_label.config(text="Could not check for updates.", foreground="gray")
                    if not silent:
                        messagebox.showerror("Error", f"Could not check for updates: {e}")

                self.root.after(0, update_ui_err)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    _fix_windows_dpi_blur()
    root = tk.Tk()
    try:
        root.iconbitmap(_resource_path("icon.ico"))
    except Exception:
        pass
    app = DownloaderApp(root)
    root.mainloop()
