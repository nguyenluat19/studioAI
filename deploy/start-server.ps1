#Requires -RunAsAdministrator
# Khởi động toàn bộ "VPS" trên máy này: Docker engine -> containers -> cloudflared service -> verify domain.
# Chạy khi: mới reboot, Docker Desktop bị tắt, domain trả 502/530.
#   powershell -ExecutionPolicy Bypass -File .\deploy\start-server.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Step([string]$Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }

# 1) Docker engine
Step "Docker engine"
$engine = $null
try { $engine = docker info --format '{{.ServerVersion}}' 2>$null } catch {}
if (-not $engine) {
    $exe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $exe) {
        Write-Host "  Docker chua chay, dang khoi dong Docker Desktop..."
        Start-Process $exe | Out-Null
    } else {
        Write-Host "  KHONG tim thay Docker Desktop.exe" -ForegroundColor Red
    }
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 3
        try { $engine = docker info --format '{{.ServerVersion}}' 2>$null } catch {}
        if ($engine) { break }
        Write-Host "  ... doi Docker engine ($($i * 3)s)"
    }
}
if (-not $engine) { Write-Host "  Docker engine KHONG len duoc. Mo Docker Desktop bang tay roi chay lai script." -ForegroundColor Red; exit 1 }
Write-Host "  Engine OK: $engine"

# 2) Containers
Step "Containers (web + redis)"
docker compose up -d | Out-Null
docker compose ps --format "table {{.Service}}`t{{.Status}}"

# 3) Cho app healthy
Step "Cho app san sang"
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" -TimeoutSec 5
        if ($r.ok) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 3
}
if ($ok) { Write-Host "  App local OK: http://127.0.0.1:8001" -ForegroundColor Green }
else { Write-Host "  App KHONG tra loi. Xem log: docker compose logs --tail 100 web" -ForegroundColor Red }

# 4) cloudflared tunnel (Task Scheduler, quyen SYSTEM — KHONG dung Windows Service,
#    service luon chay cloudflared.exe khong tham so nen crash-loop)
Step "cloudflared tunnel"
schtasks /Query /TN "VideoAI-Cloudflared" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Chua co task VideoAI-Cloudflared. Tao bang lenh (admin):" -ForegroundColor Red
    Write-Host "  schtasks /Create /TN `"VideoAI-Cloudflared`" /TR `"$Root\deploy\run-tunnel.cmd`" /SC ONSTART /RU SYSTEM /F"
} else {
    $tunnel = Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 }
    if (-not $tunnel) {
        Write-Host "  Tunnel chua chay -> dang khoi dong task..."
        schtasks /Run /TN "VideoAI-Cloudflared" | Out-Null
        Start-Sleep -Seconds 10
    }
    $tunnel = Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 }
    if ($tunnel) { Write-Host "  Tunnel OK (PID $($tunnel.Id), session 0 = SYSTEM)" -ForegroundColor Green }
    else { Write-Host "  Tunnel KHONG len. Chay tay de xem loi: $Root\deploy\run-tunnel.cmd" -ForegroundColor Red }
}

# 5) Verify domain
Step "Verify domain"
try {
    $r = Invoke-WebRequest -Uri "https://studioai.id.vn/api/health" -TimeoutSec 20 -UseBasicParsing
    Write-Host "  https://studioai.id.vn -> $($r.StatusCode) $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  Domain loi: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  - 530: cloudflared chua ket noi (xem: Get-WinEvent -LogName Application -ProviderName Cloudflared -MaxEvents 10)"
    Write-Host "  - 502: cloudflared OK nhung app chet (xem: docker compose logs web)"
}

Write-Host ""
Write-Host "Xong. Log app: docker compose logs -f --tail 100 web"
