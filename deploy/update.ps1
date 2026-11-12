param([switch]$NoBuild)

# Deploy code moi len domain studioai.id.vn.
# Code duoc COPY vao image -> phai build lai image roi recreate container.
# Du lieu (storage/: SQLite + uploads + outputs) KHONG bi anh huong.
#
# Chay:
#   powershell -ExecutionPolicy Bypass -File .\deploy\update.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Image = "dashboard-claude-wizardly-lamport-qfjxhi-web:latest"

if (-not $NoBuild) {
    Write-Host "== Build image (code moi)" -ForegroundColor Cyan
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "BUILD FAIL. Log o tren." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "== Restart container web" -ForegroundColor Cyan
docker compose up -d --no-build
if ($LASTEXITCODE -ne 0) { Write-Host "Compose up FAIL" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "== Cho app healthy" -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:8001/api/health" -TimeoutSec 5
        if ($h.ok) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 3
}
if (-not $ok) {
    Write-Host "App KHONG len. 40 dong log cuoi:" -ForegroundColor Red
    docker compose logs --tail 40 web
    exit 1
}
docker compose ps --format "table {{.Service}}`t{{.Status}}"

Write-Host ""
Write-Host "== Verify domain" -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest "https://studioai.id.vn/api/health" -TimeoutSec 15 -UseBasicParsing
    Write-Host "  https://studioai.id.vn -> $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  Domain loi: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Xong. Log: docker compose logs -f --tail 100 web"
