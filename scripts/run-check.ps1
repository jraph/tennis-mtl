$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "data"
$LogPath = Join-Path $LogDir "scheduled-check.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $Python)) {
  throw "Virtual environment not found at $Python. Run setup from README.md first."
}

Push-Location $ProjectRoot
try {
  & $Python -m tennis_booking.check_once | Tee-Object -FilePath $LogPath -Append
}
finally {
  Pop-Location
}
