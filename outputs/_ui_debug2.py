import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 8024
BASE = f"http://127.0.0.1:{PORT}"
ROOT = pathlib.Path(__file__).resolve().parent.parent
tmp = pathlib.Path(tempfile.mkdtemp(prefix="uidebug2_"))
(tmp / "outputs").mkdir(parents=True)

for name, size, freq in (("sample_vert.mp4", "640x1136", 440), ("sample_land.mp4", "1280x720", 330)):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:d=2:rate=20",
                    "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(tmp / "outputs" / name)], check=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=size=640x1136:d=1:rate=1",
                "-frames:v", "1", str(tmp / "outputs" / "poster.png")], check=True)

env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp / 'dbg.db'}", STORAGE_DIR=str(tmp),
           SECRET_KEY="preview-secret-preview-secret-123", ADMIN_PASSWORD="adminpass123",
           REGISTER_PER_HOUR="100000")
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
                         "--host", "127.0.0.1", "--port", str(PORT)],
                        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        reqs, resps = [], []
        cons = []
        page.on("response", lambda r: resps.append((r.status, r.url)) if ".mp4" in r.url else None)
        page.on("requestfailed", lambda r: reqs.append((r.url, r.failure or "")))
        page.on("console", lambda m: cons.append(f"{m.type}: {m.text}"))
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        page.click("#tab-rg")
        page.fill("#a-u", "dbg2")
        page.fill("#a-e", "dbg2@example.com")
        page.fill("#a-p", "password123")
        page.click("#a-sub")
        page.wait_for_selector("#app-wrap:not(.hide)", timeout=15000)
        conn = sqlite3.connect(tmp / "dbg.db")
        uid = conn.execute("select id from users where username='dbg2'").fetchone()[0]
        for title, url in [("Doc 9:16", "/media/outputs/sample_vert.mp4"),
                           ("Land 16:9", "/media/outputs/sample_land.mp4")]:
            conn.execute(
                "insert into shared_video_library(title,category,base_video_url,preview_video_url,"
                "thumbnail_url,template_schema,status,creator_id,usage_count,created_at)"
                " values(?, 'full', ?, ?, '', '{\"aspect_ratio\": \"9:16\"}', 'publish', ?, 0, datetime('now'))",
                (title, url, url, uid))
        conn.commit(); conn.close()
        page.click('[data-nav="library"]')
        for tick in range(6):
            page.wait_for_timeout(1000)
            rs = page.evaluate("[...document.querySelectorAll('.tc video')].map(v => v.readyState)")
            print("readyState tick", tick, rs)
        print("CONSOLE:", cons)
        info = page.evaluate("""() => {
          const cards = [...document.querySelectorAll('.tc')].map(c => ({
            text: (c.querySelector('.tc-title')||{}).textContent,
            ratio: c.dataset.ratio,
            video: !!c.querySelector('video'),
            vsrc: (c.querySelector('video')||{}).src,
            nw: (c.querySelector('video')||{}).videoWidth,
            nh: (c.querySelector('video')||{}).videoHeight,
          }));
          return cards;
        }""")
        print("CARDS:", json.dumps(info, ensure_ascii=False))
        print("RESPS:", resps)
        print("FAILED:", reqs)
        b.close()
    print("done")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
