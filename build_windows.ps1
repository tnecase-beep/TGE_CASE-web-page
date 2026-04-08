# build_windows.ps1 — stable build script for TGECase (Windows)
# Fixes PowerShell NativeCommandError by running PyInstaller via cmd.exe and redirecting output to file.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- Paths ---
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

$LAUNCHER = Join-Path $ROOT "launcher.py"
if (-not (Test-Path -LiteralPath $LAUNCHER)) {
  throw "launcher.py not found in repo root: $ROOT"
}

$REQ = Join-Path $ROOT "optimize\requirements.txt"
if (-not (Test-Path -LiteralPath $REQ)) { $REQ = Join-Path $ROOT "requirements.txt" }
if (-not (Test-Path -LiteralPath $REQ)) {
  throw "requirements.txt not found at optimize\requirements.txt or requirements.txt"
}

$VENV_PY = Join-Path $ROOT ".venv\Scripts\python.exe"
$PYI_LOG = Join-Path $ROOT "pyinstaller_output.txt"

# --- Ensure venv ---
if (-not (Test-Path -LiteralPath $VENV_PY)) {
  Write-Host "Creating venv at .venv ..."
  $created = $false
  try { py -3 -m venv .venv; $created = $true } catch { }
  if (-not $created) { python -m venv .venv; $created = $true }
  if (-not (Test-Path -LiteralPath $VENV_PY)) {
    throw "Failed to create venv. Could not find: $VENV_PY"
  }
}
$PY = $VENV_PY

# --- Install deps ---
Write-Host "Installing dependencies..."
& $PY -m pip install --upgrade pip setuptools wheel | Out-Host
& $PY -m pip install -r $REQ | Out-Host
& $PY -m pip install --upgrade pyinstaller | Out-Host

# Ensure gurobipy exists in this venv
try { & $PY -m pip show gurobipy | Out-Null } catch {
  Write-Host "gurobipy not found in venv. Installing..."
  & $PY -m pip install gurobipy | Out-Host
}

# --- Stop running app (so dist/ isn't locked) ---
Write-Host "Stopping any running TGECase process..."
try { Get-Process TGECase -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
Start-Sleep -Milliseconds 300

# --- Clean old build outputs ---
foreach ($p in @("build", "dist")) {
  $full = Join-Path $ROOT $p
  if (Test-Path -LiteralPath $full) {
    Write-Host "Removing $p/ ..."
    try {
      Remove-Item -Recurse -Force -LiteralPath $full
    } catch {
      throw "Could not remove $full. It may be in use. Close the app and retry. Details: $($_.Exception.Message)"
    }
  }
}

# --- PyInstaller args ---
$OPT = Join-Path $ROOT "optimize"
if (-not (Test-Path -LiteralPath $OPT)) {
  throw "optimize folder not found at: $OPT"
}

$DISTPATH = Join-Path $ROOT "dist"
$WORKPATH = Join-Path $ROOT "build"

# Helper: quote for cmd.exe
function Quote-CmdArg([string]$a) {
  if ($a -match '[\s"]') { return '"' + $a.Replace('"','""') + '"' }
  return $a
}

$pyiArgs = @(
  "--noconfirm",
  "--clean",
  "--onedir",
  "--noconsole",
  "--name", "TGECase",
  "--distpath", $DISTPATH,
  "--workpath", $WORKPATH,

  "--collect-all", "streamlit",
  "--collect-all", "plotly",
  "--collect-all", "altair",
  "--collect-all", "pydeck",
  "--collect-all", "pandas",
  "--collect-all", "numpy",
  "--collect-all", "scipy",
  "--collect-all", "geopy",

  "--collect-all", "gurobipy",
  "--collect-binaries", "gurobipy",
  "--collect-submodules", "gurobipy",

  "--copy-metadata", "streamlit",

  "--add-data", ("$OPT;app"),

  $LAUNCHER
)

# --- Run PyInstaller via cmd.exe (prevents NativeCommandError killing the script) ---
if (Test-Path -LiteralPath $PYI_LOG) { Remove-Item -Force -LiteralPath $PYI_LOG }

Write-Host ""
Write-Host "Running PyInstaller... (output -> $PYI_LOG)"

$argLine = ($pyiArgs | ForEach-Object { Quote-CmdArg $_ }) -join " "
$cmdLine = Quote-CmdArg $PY
$fullCmd = "$cmdLine -m PyInstaller $argLine > " + (Quote-CmdArg $PYI_LOG) + " 2>&1"

cmd /c $fullCmd
$exit = $LASTEXITCODE

if ($exit -ne 0) {
  Write-Host ""
  Write-Host "PyInstaller FAILED (exit code $exit). Last lines from log:"
  try {
    Get-Content -LiteralPath $PYI_LOG -Tail 120 | ForEach-Object { Write-Host $_ }
  } catch { }
  throw "PyInstaller failed. See: $PYI_LOG"
}

# --- Verify output exists ---
$EXE = Join-Path $DISTPATH "TGECase\TGECase.exe"
if (-not (Test-Path -LiteralPath $EXE)) {
  throw "Build finished but exe not found at: $EXE"
}

Write-Host ""
Write-Host "Build finished."
Write-Host ("Run: " + $EXE)
Write-Host "Logs and crash reports are written under: %APPDATA%\TGECase"
Write-Host "Optional remote reporting env vars: TGECASE_ERROR_REPORT_URL / _TOKEN / _SECRET"
Write-Host ("PyInstaller output: " + $PYI_LOG)
