#Requires -Version 5.1
<#
.SYNOPSIS
    One-liner installer for Photographer Monitor.

.DESCRIPTION
    Downloads the application from GitHub, checks for Python, installs
    dependencies, and creates a desktop shortcut. Nothing is sent to any
    external service during setup except the GitHub download.

    Run with:
        irm "https://raw.githubusercontent.com/<user>/Pingeon/main/setup.ps1" | iex

.NOTES
    All configuration data stays on your machine. The only external connections
    made by the application itself are to Google Calendar ICS feeds and Gmail SMTP.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoUrl   = "https://github.com/<user>/Pingeon"   # UPDATE before hosting
$RawBase   = "https://raw.githubusercontent.com/<user>/Pingeon/main"
$AppDir    = Join-Path $env:LOCALAPPDATA "PhotographerMonitor"
$DataDir   = Join-Path $AppDir "data"
$PkgDir    = Join-Path $AppDir "photographer_monitor"
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Photographer Monitor.lnk"

# ── Helpers ────────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host ">>> $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "    OK: $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "    FAIL: $msg" -ForegroundColor Red
    exit 1
}

function Get-PythonExe {
    foreach ($candidate in @("python", "python3", "py")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 8) {
                    return $candidate
                }
            }
        } catch { }
    }
    return $null
}

# ── Step 1: Python check ────────────────────────────────────────────────────────

Write-Step "Checking for Python 3.8+..."
$PythonExe = Get-PythonExe
if (-not $PythonExe) {
    Write-Host ""
    Write-Host "Python 3.8 or newer is required but was not found." -ForegroundColor Yellow
    Write-Host "Download it from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during install, then re-run this script." -ForegroundColor Yellow
    exit 1
}
$VersionStr = & $PythonExe --version 2>&1
Write-OK "Found $VersionStr"

# ── Step 2: Create directories ─────────────────────────────────────────────────

Write-Step "Creating application directory..."
New-Item -ItemType Directory -Path $AppDir  -Force | Out-Null
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path $PkgDir  -Force | Out-Null
Write-OK $AppDir

# ── Step 3: Download application files ────────────────────────────────────────

Write-Step "Downloading application files from GitHub..."

$Files = @(
    "photographer_monitor/__init__.py",
    "photographer_monitor/__main__.py",
    "photographer_monitor/constants.py",
    "photographer_monitor/logger.py",
    "photographer_monitor/config.py",
    "photographer_monitor/calendar_poller.py",
    "photographer_monitor/email_notifier.py",
    "photographer_monitor/service_manager.py",
    "photographer_monitor/gui.py",
    "requirements.txt"
)

foreach ($RelPath in $Files) {
    $Url  = "$RawBase/$RelPath"
    $Dest = Join-Path $AppDir $RelPath

    # Ensure subdirectory exists
    $DestDir = Split-Path $Dest -Parent
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

    try {
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
        Write-OK $RelPath
    } catch {
        Write-Fail "Could not download $RelPath from $Url`nError: $_"
    }
}

# ── Step 4: Install Python dependencies ────────────────────────────────────────

Write-Step "Installing Python dependencies..."
$ReqFile = Join-Path $AppDir "requirements.txt"
try {
    & $PythonExe -m pip install --quiet --require-virtualenv 2>$null
    # If require-virtualenv is unsupported (older pip), fall back to user install
} catch { }

$PipResult = & $PythonExe -m pip install -r $ReqFile --user --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Warning: pip install returned non-zero. Output:" -ForegroundColor Yellow
    Write-Host $PipResult -ForegroundColor Yellow
} else {
    Write-OK "Dependencies installed."
}

# ── Step 5: Create launch script ──────────────────────────────────────────────

Write-Step "Creating launcher..."
$LauncherPath = Join-Path $AppDir "launch.ps1"
@"
Set-Location "$AppDir"
& "$PythonExe" -m photographer_monitor
"@ | Set-Content $LauncherPath -Encoding UTF8
Write-OK $LauncherPath

# ── Step 6: Desktop shortcut ──────────────────────────────────────────────────

Write-Step "Creating desktop shortcut..."
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments  = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LauncherPath`""
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.Description = "Photographer Monitor — Check for cancellations"
$Shortcut.Save()
Write-OK "Shortcut created on Desktop."

# ── Done ────────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Photographer Monitor installed successfully!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To launch: double-click 'Photographer Monitor' on your Desktop."
Write-Host "  Or run:    & '$LauncherPath'"
Write-Host ""
Write-Host "  Privacy note: all your data stays on this machine."
Write-Host "  Only Google Calendar ICS feeds and Gmail SMTP are contacted."
Write-Host ""

$Launch = Read-Host "Launch the app now? (y/n)"
if ($Launch -eq "y" -or $Launch -eq "Y") {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$LauncherPath`""
}
