@echo off
setlocal EnableExtensions
title Image organizer

rem ============================================================
rem  Launcher for image_organizer.py (keep both files in one folder,
rem  the "profiles" folder sits next to them)
rem
rem  Double-click          -> guided menu (organize, edit profiles, undo)
rem  Drag folder(s) onto   -> organizes those folders (preview, then asks before moving)
rem  Command line          -> run_image_organizer.bat "D:\photos" --apply
rem                           (any image_organizer.py option works)
rem ============================================================

set "SCRIPT=%~dp0image_organizer.py"
if not exist "%SCRIPT%" (
    echo Cannot find image_organizer.py next to this file:
    echo   %SCRIPT%
    echo.
    pause
    exit /b 1
)

chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

rem ---- find Python: local venv first, then py launcher, then python
set "PY="
set "VENV_PY=%~dp0finder-env\Scripts\python.exe"
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>&1 && set PY="%VENV_PY%"
)
if not defined PY (
    py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python 3 was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

rem ---- check the packages, offer to install them
%PY% -c "import open_clip, torch, PIL, numpy, openpyxl, imagehash" >nul 2>&1
if errorlevel 1 (
    echo Required packages are missing: open_clip_torch torch pillow numpy openpyxl imagehash
    echo This is a one-time download of several hundred MB.
    choice /c YN /n /m "Install them now? [Y/N] "
    if errorlevel 2 (
        pause
        exit /b 1
    )
    %PY% -m pip install open_clip_torch torch pillow numpy openpyxl imagehash
    if errorlevel 1 (
        echo.
        echo Install failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
    echo.
)

rem ---- run
%PY% "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"

rem Guided menu has its own prompts; when started with arguments keep the window open here
if not "%~1"=="" (
    echo.
    pause
)
exit /b %RC%
