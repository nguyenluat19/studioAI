"""Browser smoke journeys through the real UI (Liquid Glass redesign 2026-11-05+).

Self-contained: starts one uvicorn subprocess (no Redis/Celery needed — the app runs
in-process without them). Verifies: register/login, every sidebar tab renders without
page errors, the VietQR top-up flow, and the admin tabs.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

USER_TABS = ["library", "mytemplates", "ai", "sales", "article", "batch", "download", "subtitles", "history", "activity", "topup"]
ADMIN_TABS = ["analytics", "users", "adm", "pricing", "promos"]
TAB_ANCHOR = {"library": "Thư viện", "mytemplates": "Template của tôi", "ai": "Trợ lý AI", "sales": "Bán hàng", "article": "Bài viết",
              "batch": "Gen hàng loạt", "download": "Tải Video", "subtitles": "Phụ đề",
              "history": "Lịch sử", "activity": "Nhật ký", "topup": "Tạo mã VietQR",
              "analytics": "Analytics", "users": "Quản lý tài khoản", "adm": "Quản trị", "pricing": "Bảng giá", "promos": "Khuyến mãi"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Web:
    def __init__(self, tmp):
        self.tmp, self.port = tmp, free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/ui.db", "STORAGE_DIR": str(tmp),
                    "SECRET_KEY": "ui-secret-ui-secret-ui-secret-12", "ADMIN_PASSWORD": "adminpass123",
                    "SEPAY_API_KEY": "sepay-key", "REGISTER_PER_HOUR": "1000",
                    "VILAO_BASE_URL": "", "VILAO_API_KEY": "", "MINIMAX_API_KEY": "",
                    "ELEVENLABS_API_KEY": "", "HUGGINGFACE_API_KEY": "", "PYTHONPATH": str(ROOT)}
        self.log = open(tmp / "web.log", "w")

    def start(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port)],
                                     cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        end = time.time() + 30
        while time.time() < end:
            try:
                if httpx.get(self.base + "/api/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError(f"web did not come up:\n{self.log_text()}")

    def log_text(self):
        return (Path(self.tmp) / "web.log").read_text()[-1500:]

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture(scope="module")
def web(tmp_path_factory):
    st = Web(tmp_path_factory.mktemp("ui"))
    st.start()
    try:
        yield st
    finally:
        st.stop()


@pytest.fixture(scope="module")
def browser():
    import glob
    pre = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))   # pre-installed build
    exe = next((p for p in (os.environ.get("CHROMIUM_PATH"), *pre, shutil.which("chromium"),
                            shutil.which("google-chrome")) if p), None)
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(headless=True, **({"executable_path": exe} if exe else {}))
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"no chromium available: {e}")
        yield b
        b.close()


def watch(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    return errors


def test_register_and_every_user_tab_renders(web, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = watch(page)
    page.goto(web.base + "/dashboard?login=1")
    page.click("#tab-rg")
    page.fill("#a-u", "uiuser"); page.fill("#a-e", "ui@x.io"); page.fill("#a-p", "password123")
    page.click("#a-sub")
    page.wait_for_selector("#u-name:has-text('uiuser')")
    assert "0 credit" in page.inner_text("#u-cr")

    for tab in USER_TABS:
        page.click(f".ni[data-nav={tab}]")
        page.wait_for_selector(f"#page:has-text('{TAB_ANCHOR[tab]}')", timeout=15000)
    assert not errors, errors
    ctx.close()


def test_my_template_details_stay_open_during_auto_refresh(web, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = watch(page)
    page.goto(web.base + "/dashboard?login=1")
    page.fill("#a-u", "admin")
    page.fill("#a-p", "adminpass123")
    page.click("#a-sub")
    page.wait_for_selector("#u-name:has-text('admin')")
    page.click(".ni[data-nav=mytemplates]")
    page.locator("#my-detail").wait_for(state="attached")
    page.wait_for_function("typeof pgMyTemplates === 'function' && typeof render === 'function'")
    page.evaluate("""() => {
      window.localStorage.setItem('tab', 'mytemplates');
      window.tab = 'mytemplates';
      window.mineTpls = [{id: 987654, title: 'Test project', category: 'full', base_video_url: '',
        thumbnail_url: '', created_at: '', template_schema: {status: 'rendering', progress: 30,
          step: 'Rendering test', source_feature: 'standard', keyframes: []}}];
      const oldApi = window.api;
      window.api = async (path) => path === '/api/generations' ? [] : path === '/api/generations/categories' ? [] : path === '/api/templates' ? [] : path === '/api/templates?mine=1' ? window.mineTpls : oldApi(path);
      return pgMyTemplates();
    }""")
    page.wait_for_selector('[data-tpl-detail="987654"]')
    page.click('[data-tpl-detail="987654"]')
    page.wait_for_selector("#my-detail .card")
    page.wait_for_timeout(3500)
    assert page.locator("#my-detail .card").count() == 1
    assert page.locator("#my-detail .card").inner_text().find("Rendering test") >= 0
    assert not errors, errors
    ctx.close()


def test_topup_qr_flow_in_ui(web, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = watch(page)
    page.goto(web.base + "/dashboard?login=1")
    page.click("#tab-rg")
    page.fill("#a-u", "qruser"); page.fill("#a-e", "qr@x.io"); page.fill("#a-p", "password123")
    page.click("#a-sub")
    page.wait_for_selector("#u-name:has-text('qruser')")
    page.click(".ni[data-nav=topup]")
    page.wait_for_selector("#amt")
    page.fill("#amt", "50000")
    page.wait_for_selector("#conv:has-text('credit')")
    page.click("#qr-go")
    page.wait_for_selector("#qr-box img", timeout=15000)
    src = page.get_attribute("#qr-box img", "src")
    assert src.startswith("https://img.vietqr.io/image/") and "amount=50000" in src
    page.wait_for_selector("#qr-time:has-text('Còn')")                    # 5-minute countdown
    assert "NAP" in page.inner_text("#qr-box")                             # transaction code shown
    assert not errors, errors
    ctx.close()


def test_admin_tabs_render(web, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = watch(page)
    page.goto(web.base + "/dashboard?login=1")
    page.fill("#a-u", "admin"); page.fill("#a-p", "adminpass123")
    page.click("#a-sub")
    page.wait_for_selector("#u-name:has-text('admin')")
    for tab in ADMIN_TABS:
        page.click(f".ni[data-nav={tab}]")
        page.wait_for_selector(f"#page:has-text('{TAB_ANCHOR[tab]}')", timeout=15000)
    assert not errors, errors
    ctx.close()
