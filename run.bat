@echo off
title YouTube to MP3 Downloader
cd /d "%~dp0"

set /p ytlink="YouTube link: "

yt-dlp --remote-components ejs:github --cookies cookies.txt %ytlink% --embed-thumbnail -f bestaudio --extract-audio --audio-format mp3 --audio-quality 0

echo.
echo Selesai! Cek folder ini untuk file mp3 nya.
pause