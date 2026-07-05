@echo off
setlocal enabledelayedexpansion
title YouTube Audio Downloader
cd /d "%~dp0"

REM ============================================
REM  Dependency checks (run once)
REM ============================================
where yt-dlp >nul 2>&1
if errorlevel 1 (
    echo [ERROR] yt-dlp was not found in PATH.
    echo Download it from: https://github.com/yt-dlp/yt-dlp/releases
    pause
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ffmpeg was not found in PATH.
    echo Download it from: https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)

if not exist "cookies.txt" (
    echo [ERROR] cookies.txt was not found in this folder.
    echo Export it first using the "Get cookies.txt LOCALLY" browser extension.
    pause
    exit /b 1
)

echo Checking for yt-dlp updates...
yt-dlp -U
echo.
pause

:download_loop
cls
echo ============================================
echo        YouTube Audio Downloader
echo ============================================
echo.

REM --- Ask for a link, with basic validation ---
:get_link
set "ytlink="
set /p ytlink="Enter YouTube link: "
echo.

set batchmode=0
set playlistflag=

if "!ytlink!"=="" (
    set batchmode=1
    if not exist "links.txt" (
        echo [ERROR] links.txt was not found in this folder.
        echo Create it and add one YouTube link per line, then run this again.
        echo.
        pause
        goto :download_loop
    )
    echo Batch mode detected, all links in links.txt will be downloaded.
    echo Note: pure playlist links are downloaded in full, regular video links are downloaded individually.
) else (
    echo !ytlink! | findstr /C:"youtube.com" >nul
    if errorlevel 1 (
        echo !ytlink! | findstr /C:"youtu.be" >nul
        if errorlevel 1 (
            echo [ERROR] That does not look like a valid YouTube link.
            echo.
            goto :get_link
        )
    )

    REM --- Auto-detect link type ---
    echo !ytlink! | findstr /C:"list=" >nul
    if not errorlevel 1 (
        echo !ytlink! | findstr /C:"watch?v=" >nul
        if not errorlevel 1 (
            echo This looks like a video inside a playlist.
            set /p plchoice="Download just this video, or the whole playlist? (single/S, all/A, Enter = single): "
            if /i "!plchoice!"=="a" (
                set playlistflag=--yes-playlist
                echo Downloading the entire playlist.
            ) else (
                set playlistflag=--no-playlist
                echo Downloading only this video.
            )
        ) else (
            set playlistflag=--yes-playlist
            echo Playlist link detected, downloading all videos.
        )
    ) else (
        set playlistflag=--no-playlist
        echo Regular video link detected.
    )
)
echo.

REM --- Choose audio format ---
echo Choose audio format:
echo   1. MP3  (default, works everywhere)
echo   2. FLAC (lossless, larger file size)
echo   3. WAV  (lossless, uncompressed)
set /p formatchoice="Choice (1/2/3, Enter = 1): "

if "%formatchoice%"=="2" (
    set audioformat=flac
) else if "%formatchoice%"=="3" (
    set audioformat=wav
) else (
    set audioformat=mp3
)
echo Format selected: %audioformat%
echo.
echo ============================================
echo Starting download...
echo ============================================
echo.

REM --- Run download ---
if "%batchmode%"=="1" (
    yt-dlp --remote-components ejs:github --cookies cookies.txt --batch-file links.txt ^
      --restrict-filenames ^
      --embed-thumbnail ^
      --embed-metadata ^
      --parse-metadata "%%(channel)s:%%(artist)s" ^
      --parse-metadata "%%(channel)s:%%(album_artist)s" ^
      -f bestaudio --extract-audio --audio-format %audioformat% --audio-quality 0 ^
      --retries 5 --sleep-requests 1 ^
      -o "%%(title)s.%%(ext)s" ^
      2>> download_log.txt
) else (
    yt-dlp --remote-components ejs:github --cookies cookies.txt !ytlink! !playlistflag! ^
      --restrict-filenames ^
      --embed-thumbnail ^
      --embed-metadata ^
      --parse-metadata "%%(channel)s:%%(artist)s" ^
      --parse-metadata "%%(channel)s:%%(album_artist)s" ^
      -f bestaudio --extract-audio --audio-format %audioformat% --audio-quality 0 ^
      --retries 5 --sleep-requests 1 ^
      -o "%%(title)s.%%(ext)s" ^
      2>> download_log.txt
)

echo.
echo ============================================
echo Done! Check this folder for your audio file(s).
echo If something went wrong, check download_log.txt for details.
echo ============================================
echo.

set /p again="Download another? (Y/n): "
if /i not "%again%"=="n" goto :download_loop

echo.
echo Goodbye!
pause
