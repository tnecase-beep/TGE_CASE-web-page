@echo off
REM Delegates to the repo-root build script.
powershell -ExecutionPolicy Bypass -File "%~dp0..\build_windows.ps1"
