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
$BUILD_NAME = "TNECase"
$LEGACY_NAME = "TGECase"

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
Write-Host "Stopping any running $BUILD_NAME/$LEGACY_NAME process..."
try { Get-Process $BUILD_NAME -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
try { Get-Process $LEGACY_NAME -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue } catch { }
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

$SC1_PARQUET = Join-Path $OPT "parquet\sc1\Array_100pct.parquet"
$SC2_PARQUET = Join-Path $OPT "parquet\sc2\100pct.parquet"
if (-not (Test-Path -LiteralPath $SC1_PARQUET)) {
  throw "SC1 Parquet payload missing before build: $SC1_PARQUET"
}
if (-not (Test-Path -LiteralPath $SC2_PARQUET)) {
  throw "SC2 Parquet payload missing before build: $SC2_PARQUET"
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
  "--name", $BUILD_NAME,
  "--distpath", $DISTPATH,
  "--workpath", $WORKPATH,

  "--collect-all", "streamlit",
  "--collect-all", "plotly",
  "--collect-all", "altair",
  "--collect-all", "pydeck",
  "--collect-all", "pandas",
  "--collect-all", "pyarrow",
  "--collect-all", "numpy",
  "--collect-all", "scipy",
  "--collect-all", "geopy",

  "--collect-all", "gurobipy",
  "--collect-binaries", "gurobipy",
  "--collect-submodules", "gurobipy",

  "--hidden-import", "_socket",
  "--hidden-import", "socket",
  "--hidden-import", "select",
  "--hidden-import", "_multiprocessing",
  "--hidden-import", "multiprocessing",
  "--hidden-import", "_queue",
  "--hidden-import", "_overlapped",

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
$EXE = Join-Path $DISTPATH "$BUILD_NAME\$BUILD_NAME.exe"
if (-not (Test-Path -LiteralPath $EXE)) {
  throw "Build finished but exe not found at: $EXE"
}

# PyInstaller should place --add-data optimize -> app under _internal\app
# in onedir builds. Make it explicit as a safety net so the distributed zip
# never relies on a local repo fallback such as .\optimize\Total.py.
$APP_PAYLOAD = Join-Path $DISTPATH "$BUILD_NAME\_internal\app"
if (Test-Path -LiteralPath $APP_PAYLOAD) {
  Remove-Item -Recurse -Force -LiteralPath $APP_PAYLOAD
}
Copy-Item -Recurse -Force -LiteralPath $OPT -Destination $APP_PAYLOAD

$TOTAL_PY = Join-Path $APP_PAYLOAD "Total.py"
if (-not (Test-Path -LiteralPath $TOTAL_PY)) {
  throw "Build payload is incomplete. Total.py not found at: $TOTAL_PY"
}

$PAYLOAD_SC1_PARQUET = Join-Path $APP_PAYLOAD "parquet\sc1\Array_100pct.parquet"
$PAYLOAD_SC2_PARQUET = Join-Path $APP_PAYLOAD "parquet\sc2\100pct.parquet"
if (-not (Test-Path -LiteralPath $PAYLOAD_SC1_PARQUET)) {
  throw "Build payload is incomplete. SC1 Parquet not found at: $PAYLOAD_SC1_PARQUET"
}
if (-not (Test-Path -LiteralPath $PAYLOAD_SC2_PARQUET)) {
  throw "Build payload is incomplete. SC2 Parquet not found at: $PAYLOAD_SC2_PARQUET"
}

$ZIP = Join-Path $DISTPATH "$BUILD_NAME-Windows.zip"
if (Test-Path -LiteralPath $ZIP) {
  Remove-Item -Force -LiteralPath $ZIP
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
  (Join-Path $DISTPATH $BUILD_NAME),
  $ZIP
)

Write-Host ""
Write-Host "Build finished."
Write-Host ("Run: " + $EXE)
Write-Host ("Zip: " + $ZIP)
Write-Host "Logs and crash reports are written under: %APPDATA%\TGECase (compat path)"
Write-Host "Optional remote reporting env vars: TGECASE_ERROR_REPORT_URL / _TOKEN / _SECRET"
Write-Host ("PyInstaller output: " + $PYI_LOG)
