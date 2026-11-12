param([switch]$Watch, [int]$Interval = 3)

# Trang thai server cua may nay: containers, app, tunnel, domain, tai nguyen.
# Chay:  powershell -ExecutionPolicy Bypass -File .\deploy\status.ps1
#       powershell -ExecutionPolicy Bypass -File .\deploy\status.ps1 -Watch

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Line([string]$label, [string]$value, [string]$color = "Gray") {
    Write-Host ("{0,-14}" -f $label) -NoNewline
    Write-Host $value -ForegroundColor $color
}

function Check {
    Clear-Host
    Write-Host "=== VIDEOAI SERVER - $(Get-Date -Format 'HH:mm:ss dd/MM/yyyy') ===" -ForegroundColor Cyan
    Write-Host ""

    # Containers
    $rows = docker compose ps --format '{{.Service}}|{{.Status}}' 2>$null
    foreach ($r in $rows) {
        $p = $r -split '\|'
        $ok = $p[1] -match 'healthy|Up'
        Line $p[0] $p[1] $(if ($ok) { 'Green' } else { 'Red' })
    }
    if (-not $rows) { Line 'containers' 'KHONG chay (docker desktop chua mo?)' 'Red' }

    # App local
    try {
        $h = Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 5
        Line 'app local' 'OK  http://127.0.0.1:8001' 'Green'
    } catch { Line 'app local' "LOI: $($_.Exception.Message)" 'Red' }

    # Tunnel (SYSTEM = session 0)
    $t = Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 }
    if ($t) { Line 'tunnel' "OK (PID $($t.Id), SYSTEM)" 'Green' }
    else { Line 'tunnel' 'KHONG chay -> schtasks /Run /TN "VideoAI-Cloudflared"' 'Red' }

    # Domain
    try {
        $r = Invoke-WebRequest 'https://studioai.id.vn/api/health' -TimeoutSec 12 -UseBasicParsing
        Line 'domain' "OK  https://studioai.id.vn ($($r.StatusCode))" 'Green'
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        Line 'domain' "LOI$code`: $($_.Exception.Message.Split([char]10)[0])" 'Yellow'
    }

    # Tai nguyen
    try {
        $used = [math]::Round(((Get-ChildItem "$Root\storage" -Recurse -File -ErrorAction SilentlyContinue |
                Measure-Object Length -Sum).Sum / 1MB), 1)
        $free = [math]::Round((Get-PSDrive -Name ($Root.Substring(0,1))).Free / 1GB, 1)
        Line 'storage' "$used MB da dung | dia D: con $free GB" 'Gray'
    } catch {}

    # CPU / RAM container
    $st = docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' 2>$null
    foreach ($s in $st) {
        $p = $s -split '\|'
        Line 'cpu/ram' "$($p[0]): $($p[1]) CPU, $($p[2]) RAM" 'Gray'
    }
    Write-Host ""
}

if ($Watch) {
    while ($true) { Check; Start-Sleep -Seconds $Interval }
} else {
    Check
    Write-Host 'Them -Watch de theo doi lien tuc. Log app: docker compose logs -f --tail 100 web'
}
