# YouTube Audio Downloader

A Windows batch script that downloads audio from YouTube and converts it to MP3, FLAC, or WAV, complete with embedded thumbnail art and artist metadata pulled from the channel name. Just double-click and go.

Built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Double-click to run, no command line typing needed
- Automatic dependency checks (yt-dlp, ffmpeg, cookies.txt)
- Auto-updates yt-dlp before every run
- Choose output format: MP3, FLAC, or WAV
- Embeds thumbnail as cover art
- Embeds metadata (title, artist/album artist from channel name)
- Single link or batch download from a `links.txt` file
- Optional full playlist download
- Automatic retries on failed requests
- Errors logged to `download_log.txt` for easier troubleshooting

## Requirements

1. **[yt-dlp](https://github.com/yt-dlp/yt-dlp/releases)** - added to your system PATH
2. **[FFmpeg](https://www.gyan.dev/ffmpeg/builds/)** - required for audio conversion and thumbnail embedding, also added to PATH
3. **[Deno](https://deno.com/)** - required for yt-dlp to solve YouTube's JavaScript challenges

Install Deno via winget:

```
winget install DenoLand.Deno
```

Restart your terminal after installing Deno so it's recognized. The script checks for yt-dlp and ffmpeg automatically and will tell you if either is missing.

## Setup

### 1. Get `cookies.txt`

YouTube requires sign-in verification for many downloads. Export your browser cookies:

1. Install the **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** extension (works on Chrome, Brave, Edge)
2. Go to [youtube.com](https://youtube.com) while logged into your account
3. Click the extension icon and export cookies for the current site
4. Save the exported file as `cookies.txt`

> **Note:** Chrome's built-in cookie decryption (`--cookies-from-browser`) is blocked by newer app-bound encryption on Windows. Exporting via extension avoids this issue entirely.

### 2. Place files together

```
your-folder/
├── run.bat
└── cookies.txt
```

### 3. (Optional) Batch downloads

To download multiple videos in one run, create a `links.txt` file in the same folder with one YouTube link per line:

```
https://www.youtube.com/watch?v=xxxxxxxxxxx
https://www.youtube.com/watch?v=yyyyyyyyyyy
https://www.youtube.com/watch?v=zzzzzzzzzzz
```

### 4. Run it

Double-click `run.bat` and follow the prompts:

1. Choose your audio format (MP3 / FLAC / WAV)
2. Choose single link or batch mode (`links.txt`)
3. Choose whether to download the full playlist if the link is a playlist
4. Paste your link (if single mode) and press Enter

Your finished audio files will appear in the same folder.

## Troubleshooting

| Error | Fix |
|---|---|
| `Sign in to confirm you're not a bot` | Your `cookies.txt` is missing, expired, or wasn't exported while logged in. Re-export it. |
| `Failed to decrypt with DPAPI` | Don't use `--cookies-from-browser` on Chrome; use the `cookies.txt` extension method instead. |
| `Could not copy Chrome cookie database` | Close the browser completely (check Task Manager for background processes), or just use `cookies.txt` instead. |
| `Signature solving failed` / `n challenge solving failed` | Deno isn't installed, or its solver script hasn't downloaded. Make sure `--remote-components ejs:github` is present and you restarted your terminal after installing Deno. |
| `HTTP Error 429: Too Many Requests` | You're being rate-limited. Wait a bit before retrying; the script already retries automatically and adds delays between requests. |
| Script exits immediately with a red `[ERROR]` message | Read the message — it tells you exactly which dependency or file is missing (yt-dlp, ffmpeg, or cookies.txt). |

Cookies expire periodically (typically after a few weeks to months, or if you log out of your browser). If downloads suddenly stop working, re-export `cookies.txt`. Check `download_log.txt` for detailed error output from any failed run.

## Disclaimer

This tool is intended for downloading content you have the right to download, such as your own uploads or content explicitly permitted for offline use. Respect YouTube's Terms of Service and copyright law in your jurisdiction.

## License

GPL
