@echo off
setlocal enabledelayedexpansion
title YouTube Audio Downloader
cd /d "%~dp0"

echo ============================================
echo        YouTube Audio Downloader
echo ============================================
echo.

REM --- 1. Cek dependency ---
where yt-dlp >nul 2>&1
if errorlevel 1 (
    echo [ERROR] yt-dlp tidak ditemukan di PATH.
    echo Download dari: https://github.com/yt-dlp/yt-dlp/releases
    pause
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ffmpeg tidak ditemukan di PATH.
    echo Download dari: https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)

if not exist "cookies.txt" (
    echo [ERROR] cookies.txt tidak ditemukan di folder ini.
    echo Export dulu pakai ekstensi "Get cookies.txt LOCALLY" di browser.
    pause
    exit /b 1
)

REM --- 2. Auto-update yt-dlp ---
echo Mengecek update yt-dlp...
yt-dlp -U
echo.

REM --- 3. Minta link (Enter kosong = mode batch dari links.txt) ---
set /p ytlink="Link Youtube: "
echo.

set batchmode=0
set playlistflag=

if "!ytlink!"=="" (
    set batchmode=1
    if not exist "links.txt" (
        echo [ERROR] links.txt tidak ditemukan di folder ini.
        echo Buat file links.txt, isi satu link YouTube per baris.
        pause
        exit /b 1
    )
    echo Mode batch terdeteksi, akan download semua link dari links.txt.
    echo Catatan: link playlist murni otomatis didownload penuh, link video biasa didownload satu-satu sesuai defaultnya.
) else (
    REM --- Auto-deteksi jenis link ---
    echo !ytlink! | findstr /C:"list=" >nul
    if not errorlevel 1 (
        echo !ytlink! | findstr /C:"watch?v=" >nul
        if not errorlevel 1 (
            REM Link video yang ada di dalam playlist -> ambigu, tanya
            echo Link ini terdeteksi sebagai video di dalam sebuah playlist.
            set /p plchoice="Mau download videonya saja, atau semua isi playlist? (satu/S, semua/A, Enter = satu): "
            if /i "!plchoice!"=="a" (
                set playlistflag=--yes-playlist
                echo Oke, akan download semua video dalam playlist.
            ) else (
                set playlistflag=--no-playlist
                echo Oke, hanya video ini yang akan didownload.
            )
        ) else (
            REM Link playlist murni
            set playlistflag=--yes-playlist
            echo Link playlist terdeteksi, semua video akan didownload.
        )
    ) else (
        REM Link video biasa
        set playlistflag=--no-playlist
        echo Link video biasa terdeteksi.
    )
)
echo.

REM --- 4. Pilih format audio ---
echo Pilih format audio:
echo   1. MP3 (default, kompatibel semua device)
echo   2. FLAC (lossless, ukuran besar)
echo   3. WAV (lossless, tanpa kompresi)
set /p formatchoice="Pilihan (1/2/3, Enter = 1): "

if "%formatchoice%"=="2" (
    set audioformat=flac
) else if "%formatchoice%"=="3" (
    set audioformat=wav
) else (
    set audioformat=mp3
)
echo Format dipilih: %audioformat%
echo.

REM --- 5. Jalankan download ---
if "%batchmode%"=="1" (
    echo Mendownload semua link dari links.txt...
    echo.
    yt-dlp --remote-components ejs:github --cookies cookies.txt --batch-file links.txt ^
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
echo Selesai! Cek folder ini untuk file audionya.
echo Kalau ada error, cek download_log.txt untuk detailnya.
echo ============================================
pause
