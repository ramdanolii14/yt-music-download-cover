# YouTube Audio Downloader With Cover Included

A native Windows desktop app for downloading audio from YouTube as MP3, FLAC, or WAV, with embedded cover art and artist metadata pulled from the channel name. No browser, no terminal, just a proper Windows application.

Built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp), with [ffmpeg](https://ffmpeg.org/) and [Deno](https://deno.com/) handled automatically.

![status](https://img.shields.io/badge/version-2.0-blue)

## What's new in v2.0

v2.0 is a full rework from the original batch script into a proper GUI application:

- Sidebar navigation (Home / Settings), like a typical Windows app
- Home screen kept minimal: link input, preview, progress bar, and log
- One-click **Auto Setup** that installs yt-dlp, ffmpeg, and Deno automatically, no PATH editing required
- Live progress bar instead of raw scrolling text
- Cancel button to stop an in-progress download
- Metadata preview (title, channel, duration) before committing to a download
- Windows tray notification when a download finishes or is cancelled
- Dark mode
- Automatic update check against this repository's GitHub releases

## Features

- Paste one or many links (one per line) and download them all in sequence
- Auto-detects single video vs. playlist links; manual override available
- Choose output format: MP3, FLAC, or WAV
- Embeds thumbnail as cover art
- Embeds metadata (title, artist / album artist from the channel name)
- Safe filenames on Windows (`--restrict-filenames`)
- Settings (output folder, cookies path, format, etc.) persist across restarts
- All external tools (ffmpeg, Deno) are installed portably next to the app; nothing is written to your system PATH or environment variables

## Requirements

The app manages its own dependencies via **Settings > Auto Setup**, which installs:

- **yt-dlp** (via pip)
- **ffmpeg** (portable build, downloaded automatically)
- **Deno** (portable build, downloaded automatically, needed for yt-dlp to solve YouTube's JavaScript challenges)

You only need Python and pip available on the machine you use to *build* the app (see below). End users running the packaged `.exe` don't need Python installed at all.

## Setup

### 1. Get `cookies.txt`

YouTube requires sign-in verification for many downloads. Export your browser cookies:

1. Install the **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** extension (works on Chrome, Brave, Edge)
2. Go to [youtube.com](https://youtube.com) while logged into your account
3. Click the extension icon and export cookies for the current site
4. Save the exported file as `cookies.txt` in the same folder as the app, or point to it from **Settings**

> **Note:** Chrome's built-in cookie decryption (`--cookies-from-browser`) is blocked by newer app-bound encryption on Windows. Exporting via extension avoids this issue entirely.

### 2. Run Auto Setup

Open the app, go to **Settings**, and click **Auto Setup (yt-dlp + ffmpeg + Deno)**. Watch the log on the Home screen for progress. At the end, each tool is verified by actually running it, not just checking that a file exists.

### 3. Download

Go back to **Home**, paste your link(s), optionally click **Preview** to confirm the video before downloading, then click **Download**. Progress shows live in the progress bar and log. You can cancel at any time.

## Building from source

This app is a Python/Tkinter script (`gui_downloader.py`) packaged into a standalone `.exe` with PyInstaller.

```
pip install pyinstaller
```

Prepare an icon (`.ico` format, not `.png`) named `icon.ico` in the same folder as the script. If you only have a PNG:

```
pip install pillow
python -c "from PIL import Image; Image.open('icon.png').save('icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

Build:

```
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name "YouTubeDownloader" gui_downloader.py
```

The finished executable is at `dist\YouTubeDownloader.exe`. It's fully standalone; copy it anywhere.

## Updating

The app checks this repository's [releases page](https://github.com/ramdanolii14/yt-music-download-cover/releases/) automatically on startup and shows a note in **Settings** if a newer version is available. You can also check manually anytime via **Settings > Check for updates**.

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| "Missing: yt-dlp, ffmpeg" on startup | Run **Settings > Auto Setup** |
| "Sign in to confirm you're not a bot" | `cookies.txt` is missing, expired, or wasn't exported while logged in. Re-export it. |
| Update yt-dlp fails with "You installed yt-dlp with pip..." | Handled automatically — the app falls back to `pip install --upgrade yt-dlp` on its own |
| Signature / JS challenge solving failed | Deno is missing. Run Auto Setup, or check **Settings** to confirm a Deno path was found |
| A console window flashes briefly | Should not happen in this version; all subprocess calls are run with no console window and unbuffered output |
| App looks blurry on a HiDPI display | Should not happen in this version; the app declares DPI awareness on startup |
| Notification doesn't appear, or looks like it came from another app | Notifications are sent directly from the app's own window handle via the Win32 API, not through an external process |

## Disclaimer

This tool is intended for downloading content you have the right to download, such as your own uploads or content explicitly permitted for offline use. Respect YouTube's Terms of Service and copyright law in your jurisdiction.

## License

GPL
