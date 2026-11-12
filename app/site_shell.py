"""Shared page chrome for every public page (landing, pricing, docs, policy pages).

One design language, one header, one footer, one logo — so the site reads as a
single product instead of a pile of separate pages.
"""
from __future__ import annotations

import html
import os

SITE_NAME = os.getenv("SITE_NAME", "StudioAI")
DOMAIN = "studioai.id.vn"

LOGO_SVG = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">'
            '<path d="M8 5.5v13l11-6.5-11-6.5Z" fill="currentColor"/>'
            '<path d="M4.5 7.5v9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>')

NAV = [
    ("/", "Trang chủ"),
    ("/#features", "Tính năng"),
    ("/#docs", "Tài liệu"),
    ("/pricing", "Bảng giá"),
]

POLICY_LINKS = [
    ("/terms", "Điều khoản"),
    ("/privacy", "Bảo mật"),
    ("/acceptable-use", "Nội dung"),
    ("/refund", "Hoàn tiền"),
    ("/disclaimer", "Miễn trừ TNC"),
    ("/about", "Về chúng tôi"),
    ("/contact", "Liên hệ"),
]

BASE_CSS = """
:root{
  --bg:#0c0b09; --bg2:#141310; --card:#171613; --card2:#1d1b17;
  --tx:#f6f4ef; --tx2:#a8a094; --tx3:#7c756a;
  --gold:#d4af37; --gold-2:#f3d07a; --gold-soft:rgba(212,175,55,.13); --gold-line:rgba(212,175,55,.26);
  --grad:linear-gradient(135deg,#f3d07a 0%,#d4af37 55%,#a97e22 100%);
  --bd:rgba(255,255,255,.075);
  --r:16px; --r-sm:11px;
  --sh:0 24px 60px rgba(0,0,0,.55);
  --sans:'Plus Jakarta Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--bg);color:var(--tx);font-family:var(--sans);line-height:1.65;
  overflow-x:hidden;-webkit-font-smoothing:antialiased;
}
body::before{
  content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(1100px 720px at 82% -14%, rgba(212,175,55,.11), transparent 62%),
    radial-gradient(880px 620px at -14% 112%, rgba(124,92,255,.09), transparent 60%),
    radial-gradient(640px 520px at 42% 34%, rgba(255,255,255,.018), transparent 70%);
}
a{color:inherit;text-decoration:none}
.wrap{max-width:1140px;margin:0 auto;padding:0 22px}
::selection{background:rgba(212,175,55,.28);color:#fff}
:focus-visible{outline:2px solid var(--gold);outline-offset:3px;border-radius:6px}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.14);border-radius:99px}
::-webkit-scrollbar-thumb:hover{background:rgba(212,175,55,.45)}

/* ── animation ── */
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes glowPulse{0%,100%{box-shadow:0 10px 30px rgba(0,0,0,.45),0 0 0 0 rgba(212,175,55,.35)}
  70%{box-shadow:0 10px 30px rgba(0,0,0,.45),0 0 0 16px rgba(212,175,55,0)}}
.anim{animation:rise .55s cubic-bezier(.22,.9,.28,1) both}
.d1{animation-delay:.05s}.d2{animation-delay:.12s}.d3{animation-delay:.19s}
.d4{animation-delay:.26s}.d5{animation-delay:.33s}.d6{animation-delay:.4s}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation-duration:.01ms !important;animation-iteration-count:1 !important;transition-duration:.01ms !important}
}

/* ── header ── */
header.nav{
  position:sticky;top:0;z-index:40;backdrop-filter:blur(18px) saturate(160%);
  background:rgba(12,11,9,.80);border-bottom:1px solid var(--bd);
}
.nav-in{display:flex;align-items:center;justify-content:space-between;height:66px;gap:18px}
.brand{display:flex;align-items:center;gap:11px;font-weight:800;font-size:18px;letter-spacing:-.3px}
.brand .mark{
  width:34px;height:34px;border-radius:10px;background:var(--grad);display:flex;align-items:center;
  justify-content:center;color:#171307;box-shadow:0 8px 24px rgba(212,175,55,.28);
  transition:transform .2s ease;
}
.brand:hover .mark{transform:rotate(-6deg) scale(1.06)}
.brand span{background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.menu{display:flex;align-items:center;gap:4px}
.menu a{
  font-size:13.5px;font-weight:600;color:var(--tx2);padding:8px 12px;border-radius:9px;
  transition:color .16s ease,background .16s ease;
}
.menu a:hover{color:var(--tx);background:rgba(255,255,255,.05)}
.menu a.on{color:var(--gold-2)}
.menu a.cta{
  background:var(--grad);color:#191408;font-weight:800;padding:9px 17px;border-radius:11px;
  box-shadow:0 8px 22px rgba(212,175,55,.22);transition:transform .16s ease,filter .16s ease;
}
.menu a.cta:hover{filter:brightness(1.07);transform:translateY(-1px);background:var(--grad)}
.burger{display:none;background:none;border:1px solid var(--bd);color:var(--tx);font-size:18px;border-radius:9px;width:38px;height:38px;cursor:pointer}
.menu .link{font-size:13.5px;font-weight:600;color:var(--tx2);padding:8px 12px;border-radius:9px}
.menu .link:hover{color:var(--tx);background:rgba(255,255,255,.05)}
.nav-guest{display:flex;align-items:center;gap:8px}
.nav-guest a.ghost{border:1px solid var(--gold-line);color:var(--tx);padding:9px 15px;border-radius:11px;font-weight:700}
.nav-user{display:none;align-items:center;gap:10px;position:relative}
.nav-user.show{display:flex}
.nav-av{width:38px;height:38px;border-radius:50%;border:1px solid var(--gold-line);background:var(--grad);
  color:#191408;font-weight:800;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px;transition:transform .15s ease}
.nav-av:hover{transform:scale(1.08)}
.nav-menu{position:absolute;top:46px;right:0;min-width:236px;background:#171613;border:1px solid var(--gold-line);
  border-radius:14px;padding:10px;box-shadow:var(--sh);z-index:60;animation:rise .22s cubic-bezier(.22,.9,.28,1)}
.nav-menu.hide{display:none}
.nav-menu .who{padding:6px 8px 10px;border-bottom:1px solid var(--bd);margin-bottom:8px}
.nav-menu .who b{display:block;font-size:14px}
.nav-menu .who span{font-size:11.5px;color:var(--tx2)}
.nav-menu .who em{display:block;font-style:normal;font-size:11.5px;color:var(--gold-2);margin-top:2px}
.nav-menu button{display:flex;gap:10px;align-items:center;width:100%;background:none;border:0;color:var(--tx2);
  font-family:var(--sans);font-size:13px;font-weight:600;padding:9px 10px;border-radius:10px;cursor:pointer;text-align:left}
.nav-menu button:hover{background:rgba(255,255,255,.05);color:var(--tx)}
.nav-menu button.danger{color:#ff9c9c}
.nav-menu button.danger:hover{background:rgba(255,80,80,.12);color:#ffb4b4}
.pf-modal{position:fixed;inset:0;z-index:80;display:flex;align-items:center;justify-content:center;
  background:rgba(0,0,0,.62);backdrop-filter:blur(4px);animation:fadeIn .18s ease}
.pf-modal.hide{display:none}
.pf-card{width:min(430px,calc(100vw - 32px));background:var(--card);border:1px solid var(--gold-line);
  border-radius:18px;padding:22px;box-shadow:var(--sh);animation:rise .28s cubic-bezier(.22,.9,.28,1)}
.pf-card h3{margin:0 0 4px;font-size:17px}
.pf-card p{margin:0 0 14px;font-size:12.5px;color:var(--tx2)}
.pf-card label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--tx3);margin:10px 0 5px}
.pf-card input{width:100%;background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;
  color:var(--tx);font-family:var(--sans);font-size:14px}
.pf-card input:focus{outline:2px solid var(--gold);border-color:transparent}
.pf-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}
.pf-err{display:none;color:#ffb4b4;font-size:12.5px;margin-top:10px}
.pf-err.show{display:block}
@media(max-width:880px){
  .menu{position:absolute;top:66px;left:0;right:0;flex-direction:column;align-items:stretch;
    background:rgba(12,11,9,.97);border-bottom:1px solid var(--bd);padding:12px 22px 16px;display:none}
  .menu.open{display:flex;animation:fadeIn .2s ease}
  .menu a.cta{text-align:center;margin-top:6px}
  .nav-guest{flex-wrap:wrap;margin-top:4px}
  .nav-user{margin-top:6px}
  .nav-user .nav-menu{left:0;right:auto}
  .burger{display:block}
}

/* ── footer ── */
footer{border-top:1px solid var(--bd);padding:34px 0 40px;color:var(--tx2);font-size:12.5px;margin-top:20px}
.foot-in{display:flex;justify-content:space-between;gap:22px;flex-wrap:wrap;align-items:flex-start}
.foot-links{display:flex;gap:8px 16px;flex-wrap:max-width:640px}
.foot-links a{color:var(--tx2);transition:color .16s ease}
.foot-links a:hover{color:var(--gold-2)}
.foot-brand .brand{font-size:16px}
.foot-brand .mark{width:28px;height:28px;border-radius:8px}
.foot-brand p{margin:10px 0 0}

/* ── shared blocks ── */
.sec-head{text-align:center;max-width:62ch;margin:0 auto 30px}
.sec-head h2{font-size:clamp(24px,3vw,34px);letter-spacing:-.8px;margin:0 0 10px}
.sec-head p{color:var(--tx2);margin:0}
section{padding:52px 0}
h1{font-size:clamp(30px,5vw,52px);line-height:1.12;letter-spacing:-1.2px;margin:0 0 12px}
.lead{color:var(--tx2);font-size:clamp(15px,1.6vw,17.5px);max-width:70ch}
.card{background:linear-gradient(180deg,rgba(255,255,255,.03),transparent 55%),var(--card);
  border:1px solid var(--bd);border-radius:var(--r);padding:22px}
.btn{display:inline-flex;align-items:center;gap:9px;font-weight:800;font-size:14px;padding:12px 22px;
  border-radius:12px;border:1px solid transparent;transition:transform .16s ease,filter .16s ease,background .16s ease}
.btn:hover{transform:translateY(-2px)}
.btn-gold{background:var(--grad);color:#191408;box-shadow:0 14px 34px rgba(212,175,55,.24)}
.btn-gold:hover{filter:brightness(1.07)}
.btn-ghost{border-color:var(--gold-line);color:var(--tx);background:rgba(255,255,255,.03)}
.btn-ghost:hover{background:rgba(255,255,255,.07)}
"""


_ACCOUNT_MODAL = """
<div id="pf-modal" class="pf-modal hide" role="dialog" aria-modal="true" aria-labelledby="pf-title">
  <div class="pf-card">
    <h3 id="pf-title">✏️ Sửa thông tin tài khoản</h3>
    <p>Đổi tên đăng nhập, email hoặc mật khẩu của bạn.</p>
    <label for="pf-username">Tên đăng nhập</label>
    <input id="pf-username" autocomplete="username" spellcheck="false">
    <label for="pf-email">Email</label>
    <input id="pf-email" type="email" autocomplete="email" spellcheck="false">
    <label for="pf-cur">Mật khẩu hiện tại <span style="color:var(--tx3);text-transform:none;letter-spacing:0">(bắt buộc khi đổi mật khẩu)</span></label>
    <input id="pf-cur" type="password" autocomplete="current-password">
    <label for="pf-new">Mật khẩu mới <span style="color:var(--tx3);text-transform:none;letter-spacing:0">(bỏ trống nếu không đổi)</span></label>
    <input id="pf-new" type="password" autocomplete="new-password">
    <div class="pf-err" id="pf-err"></div>
    <div class="pf-actions">
      <button class="btn btn-ghost" id="pf-cancel" type="button">Huỷ</button>
      <button class="btn btn-gold" id="pf-save" type="button">Lưu thay đổi</button>
    </div>
  </div>
</div>"""

# Hiển thị trạng thái đăng nhập trên nav: chưa đăng nhập -> Đăng nhập/Đăng ký;
# đã đăng nhập -> Dashboard + avatar (bấm để sửa thông tin / đăng xuất).
_NAV_AUTH_SCRIPT = """
(function(){
  var token = '';
  try { token = localStorage.getItem('token') || ''; } catch (e) {}
  var guest = document.getElementById('nav-guest');
  var userBox = document.getElementById('nav-user');
  var av = document.getElementById('nav-av');
  var menu = document.getElementById('nav-menu');
  var me = null;

  function showGuest(){
    if (guest) guest.style.display = 'flex';
    if (userBox) userBox.classList.remove('show');
  }
  function showUser(u){
    me = u || {};
    if (guest) guest.style.display = 'none';
    if (!userBox) return;
    userBox.classList.add('show');
    var name = me.username || 'Tài khoản';
    av.textContent = (name.trim() || 'U')[0].toUpperCase();
    document.getElementById('nav-name').textContent = name;
    document.getElementById('nav-email').textContent = me.email || '';
    var cr = Number(me.credits_balance);
    document.getElementById('nav-cr').textContent =
      (isFinite(cr) ? cr.toLocaleString('vi-VN') : '0') + ' credit';
  }
  function errMsg(detail, fallback){
    if (!detail) return fallback;
    if (typeof detail === 'string') return detail;
    if (detail.message) return detail.message;
    try { return JSON.stringify(detail); } catch (e) { return fallback; }
  }

  if (token) {
    fetch('/api/auth/me', {headers: {Authorization: 'Bearer ' + token}})
      .then(function(r){ if (!r.ok) throw new Error('auth'); return r.json(); })
      .then(showUser)
      .catch(showGuest);
  } else {
    showGuest();
  }

  if (av && menu) {
    av.addEventListener('click', function(e){
      e.stopPropagation();
      var opening = menu.classList.contains('hide');
      menu.classList.toggle('hide', !opening);
      av.setAttribute('aria-expanded', opening ? 'true' : 'false');
    });
    document.addEventListener('click', function(){ menu.classList.add('hide'); });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') menu.classList.add('hide');
    });
  }

  var modal = document.getElementById('pf-modal');
  var errBox = document.getElementById('pf-err');
  function openModal(){
    if (!modal || !me) return;
    document.getElementById('pf-username').value = me.username || '';
    document.getElementById('pf-email').value = me.email || '';
    document.getElementById('pf-cur').value = '';
    document.getElementById('pf-new').value = '';
    errBox.classList.remove('show'); errBox.textContent = '';
    modal.classList.remove('hide');
    menu.classList.add('hide');
  }
  function closeModal(){ if (modal) modal.classList.add('hide'); }

  var bProfile = document.getElementById('nav-profile');
  if (bProfile) bProfile.addEventListener('click', openModal);
  var bLogout = document.getElementById('nav-logout');
  if (bLogout) bLogout.addEventListener('click', function(){
    try { localStorage.removeItem('token'); } catch (e) {}
    location.reload();
  });
  var bCancel = document.getElementById('pf-cancel');
  if (bCancel) bCancel.addEventListener('click', closeModal);
  if (modal) modal.addEventListener('click', function(e){ if (e.target === modal) closeModal(); });

  var bSave = document.getElementById('pf-save');
  if (bSave) bSave.addEventListener('click', function(){
    errBox.classList.remove('show');
    var payload = {};
    var username = document.getElementById('pf-username').value.trim();
    var email = document.getElementById('pf-email').value.trim();
    var cur = document.getElementById('pf-cur').value;
    var newP = document.getElementById('pf-new').value;
    if (username && username !== (me && me.username)) payload.username = username;
    if (email && email.toLowerCase() !== String((me && me.email) || '').toLowerCase()) payload.email = email;
    if (newP) { payload.current_password = cur; payload.new_password = newP; }
    if (!Object.keys(payload).length) { closeModal(); return; }
    bSave.disabled = true;
    fetch('/api/auth/me', {method: 'PUT',
        headers: {'Content-Type': 'application/json',
                  'Authorization': 'Bearer ' + (localStorage.getItem('token') || '')},
        body: JSON.stringify(payload)})
      .then(function(r){
        return r.json().then(function(data){
          if (!r.ok) throw new Error(errMsg(data && data.detail, 'Không lưu được'));
          return data;
        });
      })
      .then(function(u){ showUser(u); closeModal(); })
      .catch(function(e){ errBox.textContent = e.message || 'Có lỗi xảy ra'; errBox.classList.add('show'); })
      .finally(function(){ bSave.disabled = false; });
  });
})();"""


def _e(s: str) -> str:
    return html.escape(s or "", quote=True)


def header(active: str = "") -> str:
    links = "".join(
        f'<a href="{_e(href)}" class="{"on" if href == active else ""}">{_e(label)}</a>'
        for href, label in NAV)
    return f"""<header class="nav"><div class="wrap nav-in">
  <a class="brand" href="/">
    <span class="mark">{LOGO_SVG}</span>{_e(SITE_NAME)}<span>.</span>
  </a>
  <nav class="menu" id="site-menu">{links}
    <span class="nav-guest" id="nav-guest">
      <a class="ghost" href="/dashboard?login=1">Đăng nhập</a>
      <a class="cta" href="/dashboard?login=1&amp;tab=register">Đăng ký</a>
    </span>
    <span class="nav-user" id="nav-user">
      <a class="cta" href="/dashboard">Dashboard →</a>
      <button class="nav-av" id="nav-av" type="button" aria-haspopup="true" aria-expanded="false"
              aria-label="Tài khoản của bạn">?</button>
      <div class="nav-menu hide" id="nav-menu" role="menu">
        <div class="who"><b id="nav-name">…</b><span id="nav-email">…</span><em id="nav-cr">0 credit</em></div>
        <button id="nav-profile" type="button" role="menuitem">✏️ <span>Sửa thông tin</span></button>
        <button id="nav-logout" type="button" role="menuitem" class="danger">🚪 <span>Đăng xuất</span></button>
      </div>
    </span>
  </nav>
  <button class="burger" id="burger" aria-label="Menu">☰</button>
</div></header>"""


def footer(support: dict | None = None) -> str:
    links = "".join(f'<a href="{_e(h)}">{_e(l)}</a>' for h, l in POLICY_LINKS)
    sup = ""
    if support:
        chips = []
        if support.get("zalo"):
            chips.append(f'<a href="{_e(support["zalo"])}" target="_blank" rel="noopener">💬 Zalo</a>')
        if support.get("facebook"):
            chips.append(f'<a href="{_e(support["facebook"])}" target="_blank" rel="noopener">📘 Facebook</a>')
        if support.get("email"):
            chips.append(f'<a href="mailto:{_e(support["email"])}">✉️ { _e(support["email"]) }</a>')
        if chips:
            sup = '<div class="foot-links" style="margin-top:10px">' + "".join(chips) + "</div>"
    return f"""<footer><div class="wrap foot-in">
  <div class="foot-brand">
    <a class="brand" href="/"><span class="mark">{LOGO_SVG}</span>{_e(SITE_NAME)}<span>.</span></a>
    <p>© 2026 {_e(SITE_NAME)} · {_e(DOMAIN)} · Tất cả nội dung người dùng tạo thuộc trách nhiệm của người dùng.</p>
    {sup}
  </div>
  <div class="foot-links">{links}<a href="/#docs">Tài liệu</a><a href="/pricing">Bảng giá</a></div>
</div></footer>"""


def page(title: str, description: str, body: str, *, active: str = "",
         support: dict | None = None, extra_css: str = "") -> str:
    """Bọc trọn một trang công khai: head + header + body + footer + script menu."""
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<title>{_e(title)} — {_e(SITE_NAME)}</title>
<meta name="description" content="{_e(description)}">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>{BASE_CSS}{extra_css}</style>
</head>
<body>
{header(active)}
<main>{body}</main>
{footer(support)}
{_ACCOUNT_MODAL}
<script>
(function(){{
  const m=document.getElementById('site-menu'),b=document.getElementById('burger');
  if(b&&m)b.onclick=()=>m.classList.toggle('open');
  // hiệu ứng xuất hiện khi cuộn
  const io=new IntersectionObserver(es=>es.forEach(e=>{{
    if(e.isIntersecting){{e.target.classList.add('anim');io.unobserve(e.target);}}
 }}),{{threshold:.08}});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
}})();
</script>
<script>{_NAV_AUTH_SCRIPT}</script>
</body>
</html>"""
