"""Public landing page for the domain root.

Shares the same chrome (header/footer/tokens) as every other public page
(app/site_shell.py). The product itself lives at /dashboard.
"""
from __future__ import annotations

from .site_shell import SITE_NAME, page

FEATURES = [
    ("🎬", "Tạo video AI 1-click",
     "Viết ý tưởng — AI tạo kịch bản theo cảnh, dựng ảnh keyframe, gen clip phôi và lưu dự án "
     "vào thư viện của bạn. Có chế độ chỉ-gen-ảnh, Text→Video và Ảnh→Video."),
    ("👗", "Biến hình trang phục",
     "Upload ảnh nhân vật + ảnh bộ đồ, chọn thời lượng hook. Kịch bản tự động theo chuỗi "
     "Hook → Biến hình → Review → Chi tiết sản phẩm, giữ nhất quán khuôn mặt."),
    ("📰", "Bài viết → video 60s",
     "Dán link bài viết — AI tự đọc, viết lời dẫn, tạo ảnh minh hoạ và đọc thành tiếng. "
     "Ra video hoàn chỉnh kèm phụ đề, hợp tin tức, tài chính, sức khoẻ, giáo dục."),
    ("🛍️", "Bán hàng theo ngành",
     "16 ngành hàng có sẵn (thời trang, mỹ phẩm, gia dụng, mẹ & bé…). Kịch bản lấy đúng "
     "đối tượng, nỗi đau và lời kêu gọi của ngành đó."),
    ("📦", "Gen hàng loạt",
     "Một ảnh nhân vật + 20 ảnh sản phẩm (hoặc 1 file ZIP). Hệ thống xử lý tuần tự, có ETA, "
     "tự lưu từng sản phẩm và cho phép thử lại riêng các mục lỗi."),
    ("🎙️", "Dịch & thêm phụ đề",
     "Phiên âm tự động, tự bịt các đoạn bị bỏ sót, dịch 12 ngôn ngữ theo ngữ cảnh, render phụ đề "
     "đúng khung hình, làm mờ vùng nhạy cảm và lồng tiếng có cảm xúc."),
    ("📥", "Tải video mạng xã hội",
     "TikTok, YouTube, Facebook Reels, X, Pinterest… Tải được cả video lẫn post ảnh, "
     "tải hàng loạt, có thanh tiến độ, ETA và chặn sẵn file quá dung lượng."),
    ("🤖", "Trợ lý AI hỗ trợ",
     "Chat ngay trong ứng dụng để hỏi cách dùng từng tính năng. Lịch sử chat lưu riêng cho "
     "từng tài khoản, không dùng chung."),
    ("💎", "Tính tiền minh bạch",
     "1 credit = 1.000đ. Xem ước tính chi phí trước khi tạo, lịch sử dòng tiền cá nhân, "
     "mã khuyến mãi nhiều mức và chính sách hoàn credit rõ ràng."),
    ("🗂️", "Dữ liệu riêng tư",
     "Mỗi tài khoản có thư mục lưu trữ riêng cho ảnh, video, giọng đọc và lịch sử chat — "
     "không trộn lẫn giữa các tài khoản."),
]

STEPS = [
    ("1", "Đăng ký tài khoản",
     "Tạo tài khoản miễn phí. Nạp tiền qua QR VietQR — credit cộng tự động."),
    ("2", "Chọn model & viết ý tưởng",
     "Chọn model kịch bản, ảnh và video. Hệ thống báo trước số credit sẽ trừ."),
    ("3", "Nhận kết quả",
     "Kịch bản, ảnh phân cảnh và clip phôi trong “Template của tôi”. Tải clip về tự dựng."),
]

CSS = """
.hero{padding:72px 0 54px;text-align:center}
.kicker{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:700;
  color:var(--gold-2);background:var(--gold-soft);border:1px solid var(--gold-line);
  padding:7px 14px;border-radius:999px}
.hero h1{margin-top:22px}
.hero h1 em{font-style:normal;background:var(--grad);-webkit-background-clip:text;
  background-clip:text;-webkit-text-fill-color:transparent}
.cta-row{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:28px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:52px}
.stat{background:var(--card);border:1px solid var(--bd);border-radius:var(--r);padding:18px 16px;text-align:center}
.stat b{display:block;font-size:24px;font-weight:800;letter-spacing:-.5px;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.stat span{font-size:12px;color:var(--tx2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:16px}
.feat{background:linear-gradient(180deg,rgba(255,255,255,.028),transparent 55%),var(--card);
  border:1px solid var(--bd);border-radius:var(--r);padding:22px;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
.feat:hover{transform:translateY(-4px);border-color:var(--gold-line);box-shadow:var(--sh)}
.feat .ic{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:21px;background:var(--gold-soft);border:1px solid var(--gold-line);margin-bottom:14px}
.feat h3{font-size:16.5px;margin:0 0 7px;letter-spacing:-.2px}
.feat p{font-size:13.5px;color:var(--tx2);margin:0}
.steps{display:grid;gap:14px;max-width:820px;margin:0 auto}
.step{display:flex;gap:16px;align-items:flex-start;background:var(--card);border:1px solid var(--bd);border-radius:var(--r);padding:20px 22px}
.step .n{width:36px;height:36px;flex-shrink:0;border-radius:11px;background:var(--grad);color:#191408;font-weight:800;display:flex;align-items:center;justify-content:center}
.step h3{font-size:16px;margin:2px 0 5px}
.step p{margin:0;font-size:13.5px;color:var(--tx2)}
.pol-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.pol{background:var(--card);border:1px solid var(--bd);border-radius:var(--r);padding:18px 20px;display:block;transition:transform .16s ease,border-color .16s ease}
.pol:hover{transform:translateY(-3px);border-color:var(--gold-line)}
.pol h3{font-size:15px;margin:0 0 6px;color:var(--gold-2)}
.pol p{font-size:12.8px;color:var(--tx2);margin:0 0 10px}
.pol .go{font-size:12.5px;font-weight:700;color:var(--gold)}
.cta-band{background:linear-gradient(135deg,rgba(212,175,55,.15),rgba(212,175,55,.04));
  border:1px solid var(--gold-line);border-radius:22px;padding:46px 30px;text-align:center}
.cta-band h2{font-size:clamp(22px,2.6vw,30px);margin:0 0 10px;letter-spacing:-.6px}
.cta-band p{color:var(--tx2);margin:0 0 22px}
@media(max-width:880px){.stats{grid-template-columns:repeat(2,1fr)}.hero{padding:52px 0 40px}}
@media(max-width:520px){.stats{grid-template-columns:1fr 1fr;gap:10px}}
"""

POLICIES = [
    ("/terms", "Điều khoản dịch vụ", "Quyền và nghĩa vụ của hai bên, quy tắc credit, giới hạn trách nhiệm."),
    ("/privacy", "Chính sách bảo mật", "Dữ liệu thu thập, mục đích sử dụng, thời hạn lưu trữ và quyền của bạn."),
    ("/acceptable-use", "Chính sách nội dung", "Nội dung được phép và bị cấm, trách nhiệm của người tạo."),
    ("/refund", "Chính sách hoàn tiền", "Điều kiện hoàn credit chưa sử dụng và thời gian xử lý."),
    ("/disclaimer", "Miễn trừ trách nhiệm", "AI có thể sai; bạn chịu trách nhiệm cho nội dung mình xuất bản."),
    ("/contact", "Liên hệ", "Kênh hỗ trợ, báo lỗi và yêu cầu gỡ nội dung."),
]


def render(support: dict | None = None) -> str:
    feats = "".join(
        f'<article class="feat reveal d{i+1}"><div class="ic">{ic}</div>'
        f'<h3>{t}</h3><p>{d}</p></article>'
        for i, (ic, t, d) in enumerate(FEATURES))
    steps = "".join(
        f'<div class="step reveal d{i+1}"><span class="n">{n}</span>'
        f'<div><h3>{t}</h3><p>{d}</p></div></div>'
        for i, (n, t, d) in enumerate(STEPS))
    pol = "".join(
        f'<a class="pol reveal" href="{h}"><h3>{t}</h3><p>{d}</p><span class="go">Xem →</span></a>'
        for h, t, d in POLICIES)

    body = f"""
<section class="hero"><div class="wrap">
  <span class="kicker anim">✦ Nền tảng tạo video AI cho người bán hàng &amp; content Việt Nam</span>
  <h1 class="anim d1">Tạo video AI <em>nhanh hơn</em> — kịch bản,<br>ảnh, clip, dịch phụ đề trong 1 nơi</h1>
  <p class="lead anim d2">Một ý tưởng là ra kịch bản và clip phôi. Biến hình trang phục, gen hàng loạt cho cả chợ sản phẩm, dịch và thêm phụ đề 12 ngôn ngữ, tải video từ mạng xã hội. Tính tiền theo credit, thấy giá trước khi tạo.</p>
  <div class="cta-row anim d3">
    <a class="btn btn-gold" href="/dashboard?login=1">🚀 Bắt đầu tạo video</a>
    <a class="btn btn-ghost" href="/#docs">📚 Xem tài liệu &amp; hướng dẫn</a>
  </div>
  <div class="stats anim d4">
    <div class="stat"><b>12</b><span>ngôn ngữ dịch phụ đề</span></div>
    <div class="stat"><b>1-click</b><span>ý tưởng → clip phôi</span></div>
    <div class="stat"><b>20</b><span>sản phẩm/lô gen hàng loạt</span></div>
    <div class="stat"><b>1.000đ</b><span>cho 1 credit</span></div>
  </div>
</div></section>

<section id="features"><div class="wrap">
  <div class="sec-head"><h2>Tính năng nổi bật</h2><p>Một bộ công cụ cho cả quy trình làm nội dung — không phải nhiều phần mềm rời rạc.</p></div>
  <div class="grid">{feats}</div>
</div></section>

<section id="how"><div class="wrap">
  <div class="sec-head"><h2>Ba bước để có video</h2><p>Không cần biết dựng video. Sản phẩm luôn được tách thành clip phôi để bạn tự chỉnh.</p></div>
  <div class="steps">{steps}</div>
</div></section>

<section id="docs"><div class="wrap">
  <div class="sec-head"><h2>Tài liệu &amp; chính sách</h2><p>Mỗi trang có đường dẫn riêng — thuận tiện chia sẻ và tra cứu.</p></div>
  <div class="pol-grid">{pol}</div>
</div></section>

<section><div class="wrap"><div class="cta-band anim">
  <h2>Sẵn sàng tạo video đầu tiên?</h2>
  <p>Đăng ký tài khoản miễn phí và chạy pipeline đầu tiên trong vài phút.</p>
  <div class="cta-row" style="margin-top:0">
    <a class="btn btn-gold" href="/dashboard?login=1">Vào Dashboard →</a>
    <a class="btn btn-ghost" href="/pricing">Xem bảng giá</a>
  </div>
</div></div></section>
"""
    return page(
        title=f"{SITE_NAME} — Tạo video AI, dịch & thêm phụ đề",
        description="Tạo video AI 1-click, biến hình trang phục, gen hàng loạt, dịch và thêm phụ đề 12 ngôn ngữ, tải video mạng xã hội. Tính tiền theo credit minh bạch.",
        body=body, active="/", support=support, extra_css=CSS)


# ─────────────────────────── BẢNG GIÁ ĐỒNG BỘ VỚI TAB GIÁ ADMIN ────────────────
PRICING_CSS = """
.rate{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.rate b{font-size:clamp(38px,5vw,54px);font-weight:800;letter-spacing:-1.6px;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.price-group{background:var(--card);border:1px solid var(--bd);border-radius:var(--r);padding:22px;margin-bottom:16px}
.price-group h3{margin:0 0 4px;font-size:16px}
.price-group > p{margin:0 0 14px;font-size:12.8px;color:var(--tx2)}
.ptable{width:100%;border-collapse:collapse}
.ptable th{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--tx3);text-align:left;
  padding:8px 10px;border-bottom:1px solid var(--bd)}
.ptable td{padding:12px 10px;border-bottom:1px solid rgba(255,255,255,.045);font-size:13.5px;vertical-align:middle}
.ptable tr:last-child td{border-bottom:none}
.ptable tr{transition:background .16s ease}
.ptable tbody tr:hover{background:rgba(212,175,55,.05)}
.pname{font-weight:700}
.punit{color:var(--tx2);font-size:12.5px}
.pprice{font-weight:800;color:var(--gold-2);white-space:nowrap}
.pvnd{color:var(--tx2);font-size:12px;white-space:nowrap}
.chip{display:inline-block;font-size:11px;padding:3px 9px;border-radius:99px;border:1px solid var(--bd);
  color:var(--tx2)}
.rule-list{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.rule-list li{display:flex;gap:10px;align-items:flex-start;font-size:13.5px;color:var(--tx2)}
.rule-list li b{color:var(--tx)}
.note{font-size:12.5px;color:var(--tx3);margin-top:12px}
"""

_STEP_LABEL = {
    "llm": "Mô hình ngôn ngữ — viết kịch bản, sửa thoại, dịch phụ đề",
    "image_generate": "Tạo ảnh — ảnh nhân vật và ảnh phân cảnh",
    "video_i2v": "Tạo video — clip phôi theo từng cảnh",
}
_STEP_UNIT = {"llm": "lần gọi", "image_generate": "ảnh", "video_i2v": "clip"}


def _model_rows(db, step: str) -> list[tuple[str, float, bool]]:
    """(tên model, giá credit, đang bật) — lấy đúng giá admin đặt trong tab Bảng giá."""
    from . import pricing as _pricing
    from .modelregistry import all_models
    snap = _pricing.snapshot(db)
    out = []
    for m in all_models():
        if m.step != step:
            continue
        key = f"m.{m.id}"
        row = snap.get(key)
        price = row.price if row is not None else _pricing.price(db, key)
        enabled = row.enabled if row is not None else True
        if not enabled:
            continue
        out.append((m.name, float(price), True))
    return out


def render_pricing(db=None, support: dict | None = None) -> str:
    """Bảng giá công khai — đọc thẳng giá admin đặt (bảng pricing_items)."""
    from . import pricing as _pricing
    vnd_per_credit = _pricing.get_setting(db, "vnd_per_credit", 1000) if db is not None else 1000
    try:
        vnd_per_credit = float(vnd_per_credit)
    except (TypeError, ValueError):
        vnd_per_credit = 1000
    if vnd_per_credit <= 0:
        vnd_per_credit = 1000

    groups = []
    for step in ("video_i2v", "image_generate", "llm"):
        rows = _model_rows(db, step) if db is not None else []
        if not rows:
            continue
        trs = "".join(
            f'<tr><td class="pname">{name}</td>'
            f'<td class="punit">{_STEP_UNIT.get(step, "lần")}</td>'
            f'<td class="pprice">{price:g} credit</td>'
            f'<td class="pvnd">{int(round(price * vnd_per_credit)):,}đ</td></tr>'
            for name, price, _ in rows)
        groups.append(
            f'<div class="price-group reveal"><h3>{_STEP_LABEL.get(step, step)}</h3>'
            f'<p>Giá tính theo {_STEP_UNIT.get(step, "lần")} — đồng bộ với giá quản trị viên đang đặt.</p>'
            f'<table class="ptable"><thead><tr><th>Model</th><th>Đơn vị tính</th>'
            f'<th>Giá bán</th><th>Quy đổi</th></tr></thead><tbody>{trs}</tbody></table></div>')

    body = f"""
<section style="padding-top:44px"><div class="wrap">
  <div class="sec-head"><h1>Bảng giá</h1>
    <p>Tất cả tính năng dùng chung một đơn vị: <b>credit</b>. Nạp tiền một lần, dùng dần cho tới khi hết credit.</p>
  </div>
  <div class="card anim" style="text-align:center;margin-bottom:18px">
    <div class="rate" style="justify-content:center"><b>1 credit</b>
      <span class="lead" style="font-size:15px">= {int(vnd_per_credit):,}đ</span></div>
    <p class="lead" style="margin:12px auto 0;max-width:64ch">Trước khi tạo, hệ thống luôn hiển thị
      <b>ước tính chi phí</b> để bạn biết chính xác số credit sẽ bị trừ — không có phí ẩn.</p>
  </div>
</div></section>

<section style="padding-top:0"><div class="wrap">
  <div class="sec-head"><h2>Giá từng model</h2>
    <p>Giá bán do quản trị viên đặt trong tab <b>Bảng giá &amp; Model</b> và hiển thị đồng bộ tại đây.</p></div>
  {''.join(groups) if groups else '<div class="card"><p class="lead">Đang cập nhật danh mục model…</p></div>'}
</div></section>

<section style="padding-top:0"><div class="wrap">
  <div class="price-group reveal">
    <h3>Cách tính credit</h3>
    <ul class="rule-list" style="margin-top:12px">
      <li><b>Video — tính theo clip (request):</b> mỗi clip phôi sinh ra là 1 lần gọi model video. Không tính theo giây.</li>
      <li><b>Ảnh — tính theo ảnh:</b> mỗi ảnh phân cảnh (hoặc ảnh nhân vật) là 1 lần gọi model ảnh.</li>
      <li><b>Kịch bản / sửa thoại / dịch — tính theo lần gọi LLM:</b> 1 lần cho mỗi kịch bản, 1 lần cho mỗi lần sửa hoặc dịch phụ đề.</li>
      <li><b>Giọng đọc (TTS) — tính theo câu thoại:</b> mỗi câu trong kịch bản là 1 lần.</li>
      <li><b>Cảnh lỗi:</b> chỉ trừ credit cho cảnh tạo thành công; cảnh lỗi không tính phí.</li>
    </ul>
  </div>
  <div class="price-group reveal">
    <h3>Nạp tiền &amp; hoàn tiền</h3>
    <ul class="rule-list" style="margin-top:12px">
      <li>Nạp qua QR VietQR — credit cộng tự động khi webhook ngân hàng trả về.</li>
      <li>Nạp trong khung giờ khuyến mãi được thưởng thêm credit.</li>
      <li>Credit <b>chưa sử dụng</b> được hoàn trong 7 ngày; credit đã dùng để tạo nội dung không hoàn lại.</li>
      <li>Xem lịch sử cộng/trừ credit (dòng tiền cá nhân) ngay trong tab Nạp credit.</li>
    </ul>
    <p class="note">Chi tiết điều khoản: <a href="/refund" style="color:var(--gold-2)">Chính sách hoàn tiền</a> ·
      <a href="/terms" style="color:var(--gold-2)">Điều khoản dịch vụ</a></p>
  </div>
  <div class="cta-row" style="justify-content:flex-start;margin-top:6px">
    <a class="btn btn-gold" href="/dashboard?login=1">Bắt đầu với Dashboard →</a>
    <a class="btn btn-ghost" href="/#docs">Đọc tài liệu</a>
  </div>
</div></section>
"""
    return page(
        title="Bảng giá",
        description="Giá từng model AI, cách tính credit và chính sách hoàn tiền.",
        body=body, active="/pricing", support=support, extra_css=PRICING_CSS)
