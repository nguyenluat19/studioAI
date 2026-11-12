@echo off
REM Chay cloudflared tunnel cho studioai.id.vn -> http://127.0.0.1:8001
REM Dung cho Task Scheduler (ONSTART, SYSTEM) — thay the Windows Service bi crash.
REM Vong lap: neu tunnel chet, tu khoi dong lai sau 5 giay.
:loop
"C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "C:\Users\Admin\.cloudflared\config.yml" tunnel run studioai
echo [run-tunnel] cloudflared ket thuc, khoi dong lai sau 5 giay...
timeout /t 5 /nobreak >nul
goto loop
