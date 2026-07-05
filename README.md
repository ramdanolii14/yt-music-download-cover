# YouTube to MP3 Downloader

A simple Windows batch script that downloads audio from YouTube videos and converts them to MP3, with embedded thumbnail art. Just double-click, paste a link, and get your MP3.

Built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Double-click to run, no command line typing needed
- Downloads best available audio quality
- Automatically converts to MP3
- Embeds thumbnail as cover art
- Uses browser cookies to bypass YouTube's bot detection

## Requirements

Before using this script, make sure you have the following installed:

1. **[yt-dlp](https://github.com/yt-dlp/yt-dlp/releases)** - added to your system PATH
2. **[FFmpeg](https://www.gyan.dev/ffmpeg/builds/)** - required for audio conversion and thumbnail embedding, also added to PATH
3. **[Deno](https://deno.com/)** - required for yt-dlp to solve YouTube's JavaScript challenges

Install Deno easily via winget:

```
winget install DenoLand.Deno
```

Restart your terminal after installing Deno so it's recognized.

## Setup

### 1. Get `cookies.txt`

YouTube requires sign-in verification for many downloads. You need to export your browser cookies:

1. Install the **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** extension (works on Chrome, Brave, Edge)
2. Go to [youtube.com](https://youtube.com) while logged into your account
3. Click the extension icon and export cookies for the current site
4. Save the exported file as `cookies.txt`

> **Note:** Chrome's built-in cookie decryption (`--cookies-from-browser`) is blocked by newer app-bound encryption on Windows. Exporting via extension avoids this issue entirely.

### 2. Place files together

Put these three files in the same folder:

```
your-folder/
├── run.bat
└── cookies.txt
```

### 3. Run it

Double-click `run.bat`, paste the YouTube link when prompted, press Enter, and wait for the download to finish. Your MP3 will appear in the same folder.

## The Script

`run.bat`:

```bat
@echo off
title YouTube to MP3 Downloader
cd /d "%~dp0"

set /p ytlink="Masukin link YouTube: "

yt-dlp --remote-components ejs:github --cookies cookies.txt %ytlink% --embed-thumbnail -f bestaudio --extract-audio --audio-format mp3 --audio-quality 0

echo.
echo Selesai! Cek folder ini untuk file mp3 nya.
pause
```

## Troubleshooting

| Error | Fix |
|---|---|
| `Sign in to confirm you're not a bot` | Your `cookies.txt` is missing, expired, or wasn't exported while logged in. Re-export it. |
| `Failed to decrypt with DPAPI` | Don't use `--cookies-from-browser` on Chrome; use the `cookies.txt` extension method instead. |
| `Could not copy Chrome cookie database` | Close the browser completely (check Task Manager for background processes) before trying `--cookies-from-browser`, or just use `cookies.txt` instead. |
| `Signature solving failed` / `n challenge solving failed` | Deno isn't installed, or its solver script hasn't been downloaded. Make sure `--remote-components ejs:github` is in the command and that you restarted your terminal after installing Deno. |
| `HTTP Error 429: Too Many Requests` | You're being rate-limited. Wait a bit before retrying, or add `--sleep-requests 2` to the command. |

Cookies expire periodically (typically after a few weeks to months, or if you log out of your browser). If downloads suddenly stop working, re-export `cookies.txt`.

## Disclaimer

This tool is intended for downloading content you have the right to download, such as your own uploads or content explicitly permitted for offline use. Respect YouTube's Terms of Service and copyright law in your jurisdiction.

## License

GPL
