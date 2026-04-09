@echo off
REM build_installer.bat
REM Full pipeline: PyInstaller build -> Inno Setup installer
REM Run from repo root.
REM Requirements:
REM   - Python 3.11+ on PATH  (or uses .venv if present)
REM   - Inno Setup 6 installed at default location

setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

REM ── Step 1: convert logo.png -> logo.ico (needed by Inno Setup) ────────────
echo [1/3] Converting logo.png to logo.ico ...

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

%PY% -c ^
"from PIL import Image; ^
img = Image.open('optimize/assets/logo.png'); ^
img.save('optimize/assets/logo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" ^
2>nul

if errorlevel 1 (
    echo   [WARN] Pillow not available or icon conversion failed.
    echo          Installing Pillow and retrying...
    %PY% -m pip install Pillow -q
    %PY% -c ^
"from PIL import Image; ^
img = Image.open('optimize/assets/logo.png'); ^
img.save('optimize/assets/logo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" ^
    2>nul
    if errorlevel 1 (
        echo   [WARN] Icon conversion still failed. Proceeding without custom icon.
        REM Remove SetupIconFile line won't affect build; Inno Setup will use default icon.
    )
)

REM ── Step 2: PyInstaller build ──────────────────────────────────────────────
echo [2/3] Running PyInstaller ...
powershell -ExecutionPolicy Bypass -File "%ROOT%build_windows.ps1"
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. Aborting.
    pause
    exit /b 1
)

REM ── Step 3: Inno Setup compile ─────────────────────────────────────────────
echo [3/3] Compiling Inno Setup installer ...

set "ISCC="
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P set "ISCC=%%~P"
)

if not defined ISCC (
    echo.
    echo [ERROR] Inno Setup 6 not found.
    echo         Download from: https://jrsoftware.org/isdl.php
    echo         Install, then re-run this script.
    pause
    exit /b 1
)

if not exist "installer_output" mkdir "installer_output"

"%ISCC%" "%ROOT%tgecase_installer.iss"
if errorlevel 1 (
    echo.
    echo [ERROR] Inno Setup compile failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Installer: installer_output\TNECase_Setup_1.0.0.exe
echo ============================================================
pause
