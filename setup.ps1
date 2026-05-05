# Pingeon -- Calendar Monitor
# https://github.com/talonbaker/Pingeon
#
# One-liner install:
#   irm "https://pingeon.talonbaker.workers.dev" | iex

$ErrorActionPreference = 'Stop'

$GithubUser = 'talonbaker'
$GithubRepo = 'Pingeon'
$Branch     = 'main'
$RawBase    = "https://raw.githubusercontent.com/$GithubUser/$GithubRepo/$Branch"
$AppDir     = Join-Path $env:LOCALAPPDATA 'Pingeon'
$PkgDir     = Join-Path $AppDir 'pingeon'

function Write-Step([string]$msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    --  $msg" -ForegroundColor Yellow }

# -- Python -------------------------------------------------------------------

Write-Step "Checking for Python 3.8+..."
$PyExe = $null
foreach ($candidate in @('python', 'python3', 'py')) {
    try {
        $v = & $candidate --version 2>&1
        if ($v -match 'Python (\d+)\.(\d+)' -and [int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 8) {
            $PyExe = $candidate; break
        }
    } catch {}
}

if (-not $PyExe) {
    Write-Host "`nPython 3.8+ is required." -ForegroundColor Red
    Write-Host "Download: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Check 'Add Python to PATH' during install, then re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-OK "$(& $PyExe --version 2>&1)"

# -- Directories --------------------------------------------------------------

Write-Step "Creating application directory..."
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
New-Item -ItemType Directory -Path $PkgDir -Force | Out-Null
Write-OK $AppDir

# -- Download files -----------------------------------------------------------

Write-Step "Downloading Pingeon from GitHub..."
$Files = @(
    'pingeon/__init__.py',
    'pingeon/__main__.py',
    'pingeon/constants.py',
    'pingeon/logger.py',
    'pingeon/config.py',
    'pingeon/calendar_poller.py',
    'pingeon/notifier.py',
    'pingeon/service_manager.py',
    'pingeon/gui.py'
)

foreach ($f in $Files) {
    $url  = "$RawBase/$f"
    $dest = Join-Path $AppDir $f
    New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-OK $f
    } catch {
        Write-Host "    FAIL $f -- $_" -ForegroundColor Red
        exit 1
    }
}

# -- Dependencies -------------------------------------------------------------
# Pingeon is pure stdlib -- no third-party packages required.

# -- Launcher -----------------------------------------------------------------

Write-Step "Creating launcher..."
$LauncherPath = Join-Path $AppDir 'launch.ps1'
@"
Set-Location "$AppDir"
& "$PyExe" -m pingeon
"@ | Set-Content $LauncherPath -Encoding UTF8
Write-OK $LauncherPath

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Pingeon installed!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Launch: double-click 'Pingeon' on your Desktop"
Write-Host "  Or run: & '$LauncherPath'"
Write-Host ""

Write-Host "  To launch: open PowerShell and run: & '$LauncherPath'"
