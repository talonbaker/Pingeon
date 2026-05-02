# Pingeon -- One-time Worker deployment
# Run from the repo root: .\deploy.ps1

$ErrorActionPreference = 'Stop'
$WorkerConfig = Join-Path $PSScriptRoot 'cloudflare\wrangler.toml'

Write-Host ""
Write-Host "Pingeon -- Deploying Cloudflare Worker" -ForegroundColor Cyan
Write-Host ""

$ResendKey = Read-Host "Resend API key"
$FromEmail = Read-Host "Sending email address (e.g. onboarding@resend.dev)"

# Generate a random token -- stored only in Cloudflare secrets, never in the repo.
# The Worker injects it into setup.ps1 at serve-time so users get it automatically.
$NotifyToken = [System.Convert]::ToBase64String(
    [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)

Write-Host ""
Write-Host ">>> Setting secrets..." -ForegroundColor Cyan
$ResendKey   | npx wrangler secret put RESEND_API_KEY --config $WorkerConfig
$FromEmail   | npx wrangler secret put FROM_EMAIL     --config $WorkerConfig
$NotifyToken | npx wrangler secret put NOTIFY_TOKEN   --config $WorkerConfig

Write-Host ""
Write-Host ">>> Deploying worker..." -ForegroundColor Cyan
npx wrangler deploy --config $WorkerConfig

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Deployed!" -ForegroundColor Green
Write-Host "  irm `"https://pingeon.talonbaker.workers.dev`" | iex" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
