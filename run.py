#!/usr/bin/env python3
"""One-command launcher:  python run.py

First run: creates .env (random SECRET_KEY + admin password), checks FFmpeg, starts the app.
If Redis and MimicMotion are present it also starts the Celery worker for heavy renders.
"""
import argparse
import os
import secrets
import shutil
<<<<<<< HEAD
import signal
import socket
=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"


<<<<<<< HEAD
def port_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def probe_app(host: str, port: int) -> bool:
    try:
        import httpx
        r = httpx.get(f"http://{host}:{port}/openapi.json", timeout=2.5)
        return r.json().get("info", {}).get("title") == "Video Template SaaS"
    except Exception:
        return False


def process_cmdline(pid: int) -> str:
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
                text=True, errors="ignore")
            return out.strip()
        except Exception:
            return ""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except Exception:
        return ""


def looks_like_our_server(host: str, port: int, pid: int) -> bool:
    if probe_app(host, port):
        return True
    cmd = process_cmdline(pid).lower()
    root = str(ROOT).lower()
    return "run.py" in cmd and root in cmd.replace("/", "\\")


def find_pid_on_port(port: int) -> int | None:
    if os.name == "nt":
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
        except Exception:
            return None
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) >= 5 and parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    return int(parts[-1])
                except ValueError:
                    return None
        return None
    try:
        import psutil
        for c in psutil.net_connections(kind="tcp"):
            if c.status == psutil.CONN_LISTEN and c.laddr.port == port and c.pid:
                return c.pid
    except Exception:
        return None
    return None


def stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(30):
        if not Path(f"/proc/{pid}").exists():
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def ensure_port_available(host: str, port: int) -> bool:
    if not port_listening(host, port):
        return True
    pid = find_pid_on_port(port)
    if pid and pid != os.getpid() and looks_like_our_server(host, port, pid):
        print(f"  Port {port} dang bi chiem boi server cu cua tool (PID {pid})."
              f" Dang dung no va khoi dong lai ban moi...")
        stop_pid(pid)
        for _ in range(40):
            if not port_listening(host, port):
                return True
            time.sleep(0.2)
        print(f"  Khong dung duoc PID {pid}. Chay tay: taskkill /PID {pid} /F")
        return False
    owner = f"PID {pid}" if pid else "mot process khac"
    print(f"  Port {port} dang bi chiem boi {owner} (KHONG phai server cua tool — khong tu kill).")
    print(f"  Dung no nhu dang, hoac doi cong:  python run.py --port {port + 1}")
    return False


=======
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
def ensure_env() -> None:
    if ENV.exists():
        return
    text = (ROOT / ".env.example").read_text()
    admin_pw = secrets.token_urlsafe(12)
    text = text.replace("SECRET_KEY=\n", f"SECRET_KEY={secrets.token_urlsafe(48)}\n")
    text = text.replace("ADMIN_PASSWORD=\n", f"ADMIN_PASSWORD={admin_pw}\n")
    ENV.write_text(text)
    print(f"\n  Created .env\n  Admin login:  admin / {admin_pw}   (saved in .env)\n")


def env_value(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    for line in ENV.read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-worker", action="store_true", help="never start Redis/Celery")
    ap.add_argument("--init", action="store_true", help="only create .env (e.g. before docker compose up)")
    args = ap.parse_args()
    if args.init:
        ensure_env()
        return 0

    try:
        import fastapi, uvicorn, sqlalchemy, celery, alembic  # noqa: F401,E401
    except ImportError as e:
        print(f"Missing dependency ({e.name}). Run:  pip install -r requirements.txt")
        return 1
    if not shutil.which("ffmpeg"):
        print("FFmpeg not found. Install it (mac: brew install ffmpeg | ubuntu: apt install ffmpeg | "
              "windows: ffmpeg.org) and run again.")
        return 1

    ensure_env()
    os.chdir(ROOT)
<<<<<<< HEAD
    if not ensure_port_available(args.host, args.port):
        return 1
    if not (env_value("VILAO_BASE_URL") and env_value("VILAO_API_KEY")):
        print("  ! VILAO_BASE_URL / VILAO_API_KEY are empty in .env — AI features are off "
=======
    if not (env_value("INKSTONE_BASE_URL") and env_value("INKSTONE_API_KEY")):
        print("  ! INKSTONE_BASE_URL / INKSTONE_API_KEY are empty in .env — AI features are off "
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
              "(rendering and payments still work).")

    children: list[subprocess.Popen] = []
    mm = Path(env_value("MIMICMOTION_DIR") or "vendor/MimicMotion")
    mm = mm if mm.is_absolute() else ROOT / mm
    gpu_ready = (mm / "inference.py").exists()
    ai_ready = bool(env_value("MINIMAX_API_KEY"))
    celery = [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=warning"]
    if not args.no_worker and shutil.which("redis-server") and (gpu_ready or ai_ready):
        redis_url = env_value("REDIS_URL") or "redis://localhost:6379/0"
        port = redis_url.rsplit(":", 1)[-1].split("/")[0]
        children.append(subprocess.Popen(["redis-server", "--port", port, "--save", "", "--appendonly", "no"],
                                         stdout=subprocess.DEVNULL))
        time.sleep(1)
        if ai_ready:   # MiniMax jobs just wait on an API: run several at once
            children.append(subprocess.Popen(celery + ["-n", "ai@%h", "-Q", "ai", "-c", "4"]))
        if gpu_ready:  # MimicMotion: one job at a time on the GPU
            children.append(subprocess.Popen(celery + ["-n", "gpu@%h", "-Q", "gpu", "-c", "1"]))
        print(f"  Workers started: {'AI-video ' if ai_ready else ''}{'GPU(MimicMotion)' if gpu_ready else ''}")
    if not args.no_worker:
        if not ai_ready:
            print("  AI video (MiniMax-H3) is off: set MINIMAX_API_KEY in .env.")
        if not gpu_ready:
            print("  MimicMotion (dance / motion copy) is off: run scripts/setup_mimicmotion.sh to enable it.")
        if (ai_ready or gpu_ready) and not shutil.which("redis-server"):
            print("  redis-server not found: GPU jobs need it; AI video falls back to running inside the web app.")

    print(f"\n  Open http://{args.host}:{args.port}\n")
    try:
        import uvicorn
        uvicorn.run("app.main:app", host=args.host, port=args.port)
    finally:
        for c in children:
            c.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
