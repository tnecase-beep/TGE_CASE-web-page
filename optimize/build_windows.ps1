$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ROOT = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$SCRIPT = Join-Path $ROOT "build_windows.ps1"

if (-not (Test-Path -LiteralPath $SCRIPT)) {
  throw "Repo-root build_windows.ps1 not found: $SCRIPT"
}

Set-Location $ROOT
& $SCRIPT
