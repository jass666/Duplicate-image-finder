@echo off
setlocal EnableExtensions
title Folder-trained image classifier
cd /d "%~dp0"
if errorlevel 1 (
    echo Could not switch to the project folder.
    pause
    exit /b 1
)
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "PY=py -3"
%PY% -c "import sys" >nul 2>&1
if errorlevel 1 set "PY=python"
%PY% -u "%~dp0train_from_folders.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Classifier exited with code %RC%.
    pause
)
exit /b %RC%
