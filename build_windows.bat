@echo off
REM build_windows.bat (wrapper)
REM Run from repo root:
REM   build_windows.bat
powershell -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
