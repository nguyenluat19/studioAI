import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 8023
BASE = f"http://127.0.0.1:{PORT}"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="uiprev5_"))
(tmp / "outputs").mkdir(parents=True)

def mkvideo(name, size, freq):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:d=2:rate=20",
                    "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(tmp / "outputs" / name)], check=True)
mkvideo("sample_vert.mp4", "640x1136", 440)
mkvideo("sample_land.mp4", "1280x720", 330)
mkvideo("sample_sq.mp4", "720x720", 550)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=size=640x1136:d=1:rate=1",
                "-frames:v", "1", str(tmp / "outputs" / "poster.png")], check=True)

env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp / 'prev.db'}", STORAGE_DIR=str(tmp),
           SECRET_KEY="preview-secret-preview-secret-123", ADMIN_PASSWORD="adminpass123",
           REGISTER_PER_HOUR="100000")
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
                         "--host", "127.0.0.1", "--port", str(PORT)],
                        cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("server did not start")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        page.click("#tab-rg")
        page.fill("#a-u", "ratio_user")
        page.fill("#a-e", "ratio@example.com")
        page.fill("#a-p", "password123")
        page.click("#a-sub")
        page.wait_for_selector("#app-wrap:not(.hide)", timeout=15000)
        conn = sqlite3.connect(tmp / "prev.db")
        uid = conn.execute("select id from users where username='ratio_user'").fetchone()[0]
        rows = [
            ("Video doc 9:16", "/media/outputs/sample_vert.mp4", "9:16", "publish"),
            ("Video ngang 16:9", "/media/outputs/sample_land.mp4", "16:9", "publish"),
            ("Anh vuong 1:1", "/media/outputs/sample_sq.mp4", "1:1", "publish"),
        ]
        for title, url, ratio, status in rows:
            conn.execute(
                "insert into shared_video_library(title,category,base_video_url,preview_video_url,"
                "thumbnail_url,template_schema,status,creator_id,usage_count,created_at)"
                " values(?, 'full', ?, ?, ?, ?, ?, ?, 0, datetime('now'))",
                (title, url, url, "", json.dumps({"aspect_ratio": ratio}), status, uid))
        conn.commit(); conn.close()

        page.click('[data-nav="library"]')
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "ui_ratio_library.png"))
        # click 16:9 pill if present
        btn = page.locator(".ratio-pills [data-ratio='16:9']")
        if btn.count():
            btn.click()
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "ui_ratio_library_169.png"))
        b.close()
    print("done")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
