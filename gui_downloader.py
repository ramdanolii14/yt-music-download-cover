"""
YouTube Audio Downloader - GUI version
Wraps yt-dlp in a native Windows desktop application using Tkinter.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _base_dir():
    """Folder next to the exe when frozen by PyInstaller, otherwise the script's folder.
    Used for settings.json and as a sensible default output/cookies location.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return APP_DIR


BASE_DIR = _base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "settings.json")

# Prevent a console window from popping up for each subprocess call on Windows
_NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


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
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
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


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Audio Downloader")
        self.root.geometry("640x560")
        self.root.resizable(False, False)

        self.log_queue = queue.Queue()
        self.log_window = None
        self.log_text = None
        self.output_dir = tk.StringVar(value=BASE_DIR)
        self.cookies_path = tk.StringVar(value=os.path.join(BASE_DIR, "cookies.txt"))
        self.audio_format = tk.StringVar(value="mp3")
        self.playlist_mode = tk.StringVar(value="auto")
        self.restrict_filenames = tk.BooleanVar(value=True)
        self.is_downloading = False

        self._load_settings()
        self._build_ui()
        self._check_dependencies_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_log_queue)

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

        if data.get("audio_format") in ("mp3", "flac", "wav"):
            self.audio_format.set(data["audio_format"])

        if data.get("playlist_mode") in ("auto", "single video only", "full playlist"):
            self.playlist_mode.set(data["playlist_mode"])

        if isinstance(data.get("restrict_filenames"), bool):
            self.restrict_filenames.set(data["restrict_filenames"])

    def _save_settings(self):
        data = {
            "output_dir": self.output_dir.get(),
            "cookies_path": self.cookies_path.get(),
            "audio_format": self.audio_format.get(),
            "playlist_mode": self.playlist_mode.get(),
            "restrict_filenames": self.restrict_filenames.get(),
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
        pad = {"padx": 10, "pady": 6}

        # Link input
        link_frame = ttk.LabelFrame(self.root, text="Link(s)")
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

        # Options
        opt_frame = ttk.LabelFrame(self.root, text="Options")
        opt_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(opt_frame)
        row1.pack(fill="x", padx=8, pady=6)
        ttk.Label(row1, text="Format:").pack(side="left")
        ttk.Combobox(
            row1, textvariable=self.audio_format, values=["mp3", "flac", "wav"],
            width=8, state="readonly"
        ).pack(side="left", padx=(6, 20))

        ttk.Label(row1, text="Playlist:").pack(side="left")
        ttk.Combobox(
            row1, textvariable=self.playlist_mode,
            values=["auto", "single video only", "full playlist"],
            width=18, state="readonly"
        ).pack(side="left", padx=6)

        row2 = ttk.Frame(opt_frame)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Checkbutton(
            row2, text="Restrict filenames (safer for Windows)", variable=self.restrict_filenames
        ).pack(side="left")

        # Output folder
        out_frame = ttk.LabelFrame(self.root, text="Output folder")
        out_frame.pack(fill="x", **pad)
        row3 = ttk.Frame(out_frame)
        row3.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row3, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row3, text="Browse...", command=self._browse_output_dir).pack(side="left", padx=(6, 0))

        # Cookies
        cookies_frame = ttk.LabelFrame(self.root, text="cookies.txt")
        cookies_frame.pack(fill="x", **pad)
        row4 = ttk.Frame(cookies_frame)
        row4.pack(fill="x", padx=8, pady=6)
        ttk.Entry(row4, textvariable=self.cookies_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row4, text="Browse...", command=self._browse_cookies).pack(side="left", padx=(6, 0))

        # Actions
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", **pad)
        self.download_btn = ttk.Button(action_frame, text="Download", command=self._start_download)
        self.download_btn.pack(side="left")
        ttk.Button(action_frame, text="Update yt-dlp", command=self._update_ytdlp).pack(side="left", padx=6)
        ttk.Button(action_frame, text="Open output folder", command=self._open_output_dir).pack(
            side="left", padx=6
        )
        ttk.Button(action_frame, text="Show Log", command=self._open_log_window).pack(side="left", padx=6)

        self.status_label = ttk.Label(self.root, text="Checking dependencies...", foreground="gray")
        self.status_label.pack(anchor="w", padx=12, pady=(0, 12))

    # ---------- Dependency checks ----------

    def _check_dependencies_ui(self):
        missing = []
        if shutil.which("yt-dlp") is None:
            missing.append("yt-dlp")
        if shutil.which("ffmpeg") is None:
            missing.append("ffmpeg")

        if missing:
            msg = f"Missing: {', '.join(missing)}. Install and add to PATH, then restart this app."
            self.status_label.config(text=msg, foreground="red")
            self.download_btn.config(state="disabled")
        else:
            self.status_label.config(text="Ready.", foreground="green")

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

    # ---------- Log window ----------

    def _open_log_window(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force()
            return

        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Download Log")
        self.log_window.geometry("640x400")
        try:
            self.log_window.iconbitmap(_resource_path("icon.ico"))
        except Exception:
            pass

        self.log_text = scrolledtext.ScrolledText(self.log_window, state="normal", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text.insert(tk.END, "Log window ready.\n")

        def on_close():
            self.log_window.destroy()
            self.log_window = None
            self.log_text = None

        self.log_window.protocol("WM_DELETE_WINDOW", on_close)

    def _log(self, text):
        self.log_queue.put(text)

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if self.log_text is not None and self.log_window is not None and self.log_window.winfo_exists():
                    self.log_text.insert(tk.END, line)
                    self.log_text.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    # ---------- Download logic ----------

    def _get_links(self):
        raw = self.links_text.get("1.0", tk.END)
        links = [line.strip() for line in raw.splitlines() if line.strip()]
        return links

    def _playlist_flag(self, link):
        mode = self.playlist_mode.get()
        if mode == "single video only":
            return "--no-playlist"
        if mode == "full playlist":
            return "--yes-playlist"
        # auto
        if "list=" in link and "watch?v=" in link:
            return "--no-playlist"  # ambiguous case defaults to single video in GUI mode
        if "list=" in link:
            return "--yes-playlist"
        return "--no-playlist"

    def _build_command(self, link):
        cookies = self.cookies_path.get()
        out_dir = self.output_dir.get()
        audioformat = self.audio_format.get()

        cmd = [
            "yt-dlp",
            "--remote-components", "ejs:github",
            link,
        ]
        if os.path.isfile(cookies):
            cmd += ["--cookies", cookies]

        cmd += [self._playlist_flag(link)]

        if self.restrict_filenames.get():
            cmd += ["--restrict-filenames"]

        cmd += [
            "--newline",
            "--embed-thumbnail",
            "--embed-metadata",
            "--parse-metadata", "%(channel)s:%(artist)s",
            "--parse-metadata", "%(channel)s:%(album_artist)s",
            "-f", "bestaudio",
            "--extract-audio",
            "--audio-format", audioformat,
            "--audio-quality", "0",
            "--retries", "5",
            "--sleep-requests", "1",
            "-o", os.path.join(out_dir, "%(title)s.%(ext)s"),
        ]
        return cmd

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
        self.download_btn.config(state="disabled", text="Downloading...")
        self._open_log_window()
        self._log(f"\n=== Starting download of {len(valid_links)} link(s) ===\n")
        thread = threading.Thread(target=self._run_downloads, args=(valid_links,), daemon=True)
        thread.start()

    def _run_downloads(self, links):
        total = len(links)
        for i, link in enumerate(links, start=1):
            self._log(f"\n=== [{i}/{total}] Downloading: {link} ===\n")
            cmd = self._build_command(link)
            try:
                process = _popen(cmd)
                for line in process.stdout:
                    self._log(line)
                process.wait()
                if process.returncode != 0:
                    self._log(f"\n[WARNING] Link finished with errors (exit code {process.returncode})\n")
            except FileNotFoundError:
                self._log("\n[ERROR] yt-dlp not found. Make sure it's installed and in PATH.\n")
                break
            except Exception as e:
                import traceback
                self._log(f"\n[ERROR] {type(e).__name__}: {e}\n")
                self._log(traceback.format_exc() + "\n")

        self._log("\n=== All downloads finished ===\n")
        self.root.after(0, self._download_finished)

    def _download_finished(self):
        self.is_downloading = False
        self.download_btn.config(state="normal", text="Download")

    def _update_ytdlp(self):
        self._open_log_window()
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


if __name__ == "__main__":
    _fix_windows_dpi_blur()
    root = tk.Tk()
    try:
        root.iconbitmap(_resource_path("icon.ico"))
    except Exception:
        pass
    app = DownloaderApp(root)
    root.mainloop()
