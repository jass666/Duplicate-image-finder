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

if "%~1"=="" goto menu

%PY% -u "%~dp0train_from_folders.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Classifier exited with code %RC%.
    pause
)
exit /b %RC%

:menu
echo.
echo Folder-trained image classifier
echo.
echo   1^) Train from the showroom dataset
echo   2^) Classify a new image folder
echo   Q^) Quit
echo.
choice /c 12Q /n /m "Choose: "
if errorlevel 3 exit /b 0
if errorlevel 2 goto classify

if not exist "%~dp0Showroom Media (For everyone)\" (
    echo.
    echo Could not find the showroom dataset next to this launcher.
    pause
    exit /b 1
)
echo.
%PY% -u "%~dp0train_from_folders.py" train "%~dp0Showroom Media (For everyone)" --output "%~dp0trained_models\showroom"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Training exited with code %RC%.
    pause
)
exit /b %RC%

:classify
echo.
set "INPUT="
set /p "INPUT=Path to the new image folder: "
if not defined INPUT exit /b 0
%PY% -u "%~dp0train_from_folders.py" classify "%INPUT%" --model-dir "%~dp0trained_models\showroom"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Classification exited with code %RC%.
    pause
)
exit /b %RC%
