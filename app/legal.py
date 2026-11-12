"""Public legal / policy pages (Terms, Privacy, Refund, Acceptable use, About, Contact, Disclaimer).

Served as standalone HTML at fixed paths so they can be linked from the footer and
referenced in any dispute.  Content is Vietnamese, scoped to the operator (studioai.id.vn).
"""
from __future__ import annotations

import html
import os

from .site_shell import SITE_NAME as _SITE, page as _page

SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@studioai.id.vn")
SITE_NAME = "StudioAI"
SITE_URL = os.getenv("PUBLIC_SITE_URL", "https://studioai.id.vn")
DOMAIN = "studioai.id.vn"
UPDATED = "11/11/2026"


def _e(s: str) -> str:
    return html.escape(s or "", quote=True)


# (slug, [(heading, [paragraphs]), ...])
PAGES: dict[str, tuple[str, list[tuple[str, list[str]]]]] = {
    "terms": ("Điều khoản dịch vụ", [
        ("Đối tượng sử dụng", [
            f"{SITE_NAME} (\"chúng tôi\") là nền tảng tạo nội dung bằng trí tuệ nhân tạo tại {SITE_URL}. "
            "Bằng việc tạo tài khoản, bạn xác nhận mình từ đủ 18 tuổi hoặc có người đại diện hợp pháp, và đồng ý tuân thủ toàn bộ các điều khoản này.",
            "Chúng tôi có quyền từ chối cung cấp dịch vụ, khoá tài khoản hoặc vô hiệu hoá credit nếu bạn vi phạm các điều khoản này hoặc pháp luật hiện hành."]),
        ("Tài khoản", [
            "Bạn chịu trách nhiệm bảo mật mật khẩu và mọi hoạt động phát sinh từ tài khoản của mình.",
            "Không chia sẻ tài khoản, không bán lại tài khoản, không dùng tài khoản chung với nhiều người.",
            "Tài khoản giả mạo, spam đăng ký hoặc lạm dụng credit sẽ bị khoá vĩnh viễn và credit trong tài khoản không được hoàn lại."]),
        ("Credits và thanh toán", [
            "Mỗi thao tác tạo nội dung (tạo video, ảnh, giọng đọc, dịch...) đều trừ credit theo bảng giá được công bố tại trang bảng giá trong ứng dụng.",
            "Credit đã dùng không được hoàn lại. Credit chưa dùng chỉ được hoàn lại theo Chính sách hoàn tiền.",
            "Giá và mô hình credit có thể thay đổi. Chúng tôi sẽ thông báo trước ít nhất 7 ngày đối với thay đổi bất lợi.",
            "Thanh toán qua VietQR/ngân hàng. Mã giao dịch được ghi nhận tự động qua webhook; nếu tiền đã chuyển mà credit chưa cộng, liên hệ hỗ trợ kèm ảnh chụp biên lai."]),
        ("Sở hữu trí tuệ", [
            "Nội dung bạn tạo ra bằng công cụ (video, ảnh, phụ đề, giọng đọc) thuộc quyền sử dụng của bạn, không phải quyền sở hữu của chúng tôi.",
            "Bạn KHÔNG có quyền sở hữu mô hình, mã nguồn, thuật toán hay tài sản thương hiệu của chúng tôi.",
            "Bạn không được sao chép, reverse-engineer, hay phân phối lại hệ thống của chúng tôi."]),
        ("Trách nhiệm về nội dung", [
            "AI có thể tạo ra nội dung sai, thiếu chính xác hoặc không phù hợp. Bạn là người chịu trách nhiệm duy nhất cho nội dung mình đăng tải, xuất bản hoặc sử dụng.",
            "Bạn không được dùng công cụ để tạo nội dung vi phạm pháp luật Việt Nam hoặc pháp luật quốc tế.",
            "Bạn không được dùng công cụ để tạo nội dung vi phạm quyền con người, danh dự, nhân phẩm hoặc đời tư của bất kỳ ai.",
            "Chúng tôi không chịu trách nhiệm pháp lý phát sinh từ nội dung mà người dùng tạo ra, bao gồm thiệt hại tài chính, danh tiếng hoặc quan hệ thương mại."]),
        ("Nội dung bị cấm", [
            "Khiêu dâm, nội dung 18+ mang tính tình dục, hoặc hình ảnh trẻ em trong bối cảnh không phù hợp.",
            "Nội dung kích động thù hằn, bạo lực, khủng bố, kỳ thị chủng tộc/tôn giáo/giới tính.",
            "Tin giả, lừa đảo, mạo danh cá nhân/tổ chức khác nhằm trục lợi.",
            "Vi phạm bản quyền: dùng nhạc, hình ảnh, video, giọng nói của người khác mà không có quyền.",
            "Bất kỳ nội dung nào vi phạm pháp luật Việt Nam, Bộ luật Dân sự, Luật Sở hữu trí tuệ, Luật An ninh mạng."]),
        ("Giới hạn trách nhiệm", [
            "Dịch vụ được cung cấp \"nguyên trạng\" (as-is) và \"có sẵn\" (as available). Chúng tôi không đảm bảo dịch vụ hoạt động liên tục, không gián đoạn hay không có lỗi.",
            "Trong phạm vi pháp luật cho phép, tổng trách nhiệm của chúng tôi đối với một tài khoản không vượt quá tổng số tiền đã thanh toán cho tài khoản đó trong 12 tháng gần nhất.",
            "Chúng tôi không chịu trách nhiệm cho mất dữ liệu, mất nguồn thu, mất cơ hội kinh doanh hoặc bất kỳ tổn thất gián tiếp, đặc biệt hay ngẫu nhiên nào."]),
        ("Thay đổi điều khoản", [
            "Chúng tôi có thể cập nhật điều khoản này bất kỳ lúc nào. Bản mới có hiệu lực ngay khi được đăng tải.",
            "Việc bạn tiếp tục sử dụng dịch vụ sau khi điều khoản thay đổi được coi là chấp nhận điều khoản mới."]),
    ]),
    "privacy": ("Chính sách bảo mật", [
        ("Chúng tôi thu thập dữ liệu gì", [
            "Thông tin tài khoản: tên đăng nhập, email, mật khẩu (được mã hoá một chiều, chúng tôi không lưu mật khẩu dạng chữ).",
            "Dữ liệu thao tác: lượt tạo nội dung, số credit, lịch sử giao dịch, nhật ký hoạt động (activity log).",
            "File bạn upload: ảnh, video, âm thanh — được lưu trong thư mục lưu trữ của dịch vụ và phục vụ trực tiếp cho việc tạo nội dung bạn yêu cầu.",
            "Dữ liệu kỹ thuật: địa chỉ IP, trình duyệt, thời gian truy cập — dùng để bảo trì hệ thống và ngăn lạm dụng."]),
        ("Chúng tôi dùng dữ liệu để làm gì", [
            "Cung cấp dịch vụ: xử lý yêu cầu tạo video/ảnh/phụ đề/giọng đọc.",
            "Quản trị tài khoản: xác thực, tính credit, hoàn tiền, giải quyết khiếu nại.",
            "Cải thiện sản phẩm: phân tích xu hướng sử dụng, phát hiện lỗi.",
            "Tuân thủ pháp luật: phản hồi yêu cầu hợp pháp của cơ quan chức năng."]),
        ("Chia sẻ dữ liệu", [
            "Chúng tôi KHÔNG bán dữ liệu cá nhân của bạn.",
            "Chúng tôi chỉ chia sẻ dữ liệu với nhà cung cấp kỹ thuật khi cần thiết để vận hành (lưu trữ, cổng thanh toán, máy chủ AI) theo hợp đồng bảo mật.",
            "Chúng tôi có thể tiết lộ dữ liệu nếu có yêu cầu hợp pháp từ cơ quan nhà nước hoặc để bảo vệ quyền lợi của chúng tôi, người dùng hoặc bên thứ ba."]),
        ("Lưu trữ và xoá dữ liệu", [
            "Dữ liệu được lưu trong phạm vi cần thiết; file media của bạn có thể được xoá theo yêu cầu hoặc khi tài khoản bị xoá.",
            "Bạn có quyền yêu cầu xoá tài khoản và toàn bộ dữ liệu liên quan bằng cách liên hệ hỗ trợ.",
            "Một số dữ liệu có thể được giữ lại để đáp ứng nghĩa vụ pháp lý (kế toán, chống gian lận)."]),
        ("Bảo mật", [
            "Mật khẩu được băm; API key của hệ thống được lưu trong biến môi trường, không lưu trong cơ sở dữ liệu dạng chữ.",
            "Kết nối tới dịch vụ được mã hoá bằng HTTPS/TLS.",
            "Không có hệ thống nào an toàn tuyệt đối; bạn cần tự bảo vệ mật khẩu và thiết bị."]),
        ("Quyền của bạn", [
            f"Bạn có quyền truy cập, chỉnh sửa dữ liệu cá nhân, yêu cầu xoá tài khoản và khiếu nại về cách chúng tôi xử lý dữ liệu qua email {SUPPORT_EMAIL}.",
            "Bạn có quyền từ chối nhận email marketing; email giao dịch vẫn được gửi."]),
        ("Cookies", [
            "Dịch vụ lưu token đăng nhập và một số tuỳ chọn giao diện trong bộ nhớ trình duyệt (localStorage). Chúng tôi không dùng cookie quảng cáo bên thứ ba."]),
    ]),
    "refund": ("Chính sách hoàn tiền", [
        ("Nguyên tắc", [
            "Credit đã phát sinh từ việc tạo nội dung (LLM, ảnh, video, TTS) KHÔNG được hoàn lại.",
            "Credit chưa sử dụng có thể được hoàn lại theo các điều kiện dưới đây.",
            "Hoàn tiền được thực hiện thủ công qua VietQR/chuyển khoản ngân hàng theo đúng kênh bạn đã thanh toán."]),
        ("Điều kiện hoàn tiền", [
            "Yêu cầu hoàn tiền cần được gửi trong vòng 7 ngày kể từ ngày nạp.",
            "Chỉ phần credit CHƯA SỬ DỤNG mới được hoàn; phần đã dùng không được hoàn.",
            "Số tiền hoàn tối đa bằng số tiền thực nạp, trừ phí ngân hàng (nếu có).",
            "Credit từ khuyến mãi/thưởng không thể quy đổi sang tiền mặt.",
            f"Gửi yêu cầu kèm mã giao dịch và ảnh chụp biên lai tới {SUPPORT_EMAIL}."]),
        ("Không hoàn tiền", [
            "Lỗi do phía bạn (prompt sai, file upload hỏng, tự xoá dữ liệu).",
            "Nội dung vi phạm Điều khoản sử dụng hoặc Chính sách nội dung.",
            "Tài khoản bị khoá do vi phạm.",
            "Nội dung đã tạo ra dù không hài lòng — AI có thể tạo kết quả khác nhau, không đảm bảo đúng ý từng lần.",
            "Credit đã dùng gần hết."]),
        ("Thời gian xử lý", [
            "Yêu cầu hoàn tiền được xử lý trong 3–7 ngày làm việc kể từ khi chúng tôi nhận đủ thông tin.",
            "Nếu bạn đã nạp tiền mà credit chưa được cộng, chúng tôi sẽ cộng bù trong vòng 24 giờ sau khi xác nhận."]),
        ("Sự cố kỹ thuật", [
            "Nếu hệ thống lỗi khiến bạn mất credit mà không tạo được kết quả (ví dụ: server lỗi giữa chừng), chúng tôi hoàn lại credit cho lần tạo đó.",
            "Chụp màn hình lỗi hoặc sao chép mã lỗi và gửi cho hỗ trợ kèm thời gian xảy ra sự cố."]),
    ]),
    "acceptable-use": ("Chính sách nội dung & sử dụng chấp nhận được", [
        ("Phạm vi áp dụng", [
            "Áp dụng cho tất cả nội dung bạn tạo, lưu, chia sẻ hoặc xuất bản qua dịch vụ.",
            "Chúng tôi có quyền tự động quét và xử lý nội dung vi phạm."]),
        ("Nội dung bị cấm tuyệt đối", [
            "Nội dung khiêu dâm, hở hang mang tính tình dục, đặc biệt chứa trẻ vị thành niên — báo cáo ngay cho cơ quan chức năng.",
            "Nội dung kích động bạo lực, khủng bố, thù hằn chủng tộc, tôn giáo, giới tính, dân tộc.",
            "Mạo danh cá nhân, tổ chức hoặc thương hiệu thật nhằm lừa đảo.",
            "Nội dung giả mạo tin tức/cơ quan nhà nước nhằm gây hoang mang.",
            "Lừa đảo, đa cấp, bán hàng giả, quảng cáo sản phẩm bị cấm.",
            "Vi phạm bản quyền hoặc quyền sở hữu trí tuệ."]),
        ("Nội dung bị hạn chế", [
            "Video/ảnh/giọng nói của người thật mà không có sự đồng ý: bạn cần có quyền đối với hình ảnh và giọng nói đó.",
            "Nội dung chính trị, tôn giáo nhạy cảm có thể bị giới hạn phân phối tuỳ nền tảng.",
            "Nội dung AI cần được ghi rõ là nội dung do AI tạo ra nếu có thể gây hiểu nhầm."]),
        ("Trách nhiệm của bạn", [
            "Bạn đảm bảo ảnh, video, giọng nói bạn tải lên thuộc quyền sử dụng hợp pháp của bạn.",
            "Bạn chịu trách nhiệm pháp lý cho mọi nội dung bạn tạo và cách bạn sử dụng nó.",
            "Bạn không được dùng công cụ để vi phạm bản quyền, xoá watermark hay tái xuất bản nội dung của người khác."]),
        ("Hậu quả vi phạm", [
            "Chúng tôi có thể xoá nội dung, khoá tính năng hoặc khoá tài khoản.",
            "Credit trong tài khoản vi phạm không được hoàn lại.",
            "Chúng tôi có thể báo cáo vi phạm cho cơ quan chức năng hoặc nền tảng liên quan."]),
        ("Báo cáo vi phạm", [
            f"Nếu phát hiện nội dung vi phạm trên dịch vụ, gửi email {SUPPORT_EMAIL} kèm link hoặc bằng chứng. Chúng tôi xử lý trong vòng 72 giờ."]),
    ]),
    "disclaimer": ("Miễn trừ trách nhiệm nội dung do người dùng tạo", [
        ("Nguyên tắc", [
            f"{SITE_NAME} là công cụ tạo nội dung; mọi nội dung do người dùng tạo ra là trách nhiệm của người dùng đó.",
            "Chúng tôi không kiểm duyệt trước nội dung bạn tạo, và không thể kiểm duyệt hết nội dung của mọi người dùng.",
            "Việc bạn thấy nội dung nào đó trên dịch vụ không có nghĩa là chúng tôi endorse nội dung đó."]),
        ("AI có thể sai", [
            "Kịch bản, giọng đọc, phụ đề, hình ảnh và video đều có thể chứa lỗi nhận dạng, dịch thuật sai hoặc chi tiết không có thật (ảo giác AI).",
            "Bạn cần kiểm tra nội dung trước khi đăng tải, phát sóng hoặc dùng cho mục đích thương mại."]),
        ("Bản quyền và giọng nói, hình ảnh", [
            "Nhân vật, thương hiệu, bài hát, hình ảnh người thật bạn dùng trong nội dung đều thuộc quyền của chủ sở hữu tương ứng.",
            "Bạn cần có quyền đồng ý của người xuất hiện trong ảnh/video/giọng nói; chúng tôi không chịu trách nhiệm nếu bạn không có quyền đó."]),
        ("Không tư vấn chuyên môn", [
            "Nội dung trong công cụ không phải tư vấn pháp lý, y tế, tài chính, đầu tư, tâm lý hoặc chuyên môn khác.",
            "Hãy tham vấn chuyên gia có chuyên môn trước khi dùng nội dung cho các quyết định quan trọng."]),
        ("Hệ quả trên nền tảng", [
            "Nội dung do AI tạo có thể không phù hợp với chính sách của TikTok, YouTube, Facebook, Instagram; các nền tảng có quyền gỡ, giới hạn phân phối hoặc cấm tài khoản của bạn.",
            "Chúng tôi không chịu trách nhiệm cho việc tài khoản nền tảng của bạn bị xử lý vì nội dung bạn đăng."]),
        ("Liên hệ", [
            f"Mọi câu hỏi về điều khoản này xin gửi tới {SUPPORT_EMAIL}."]),
    ]),
    "about": ("Về chúng tôi", [
        (f"{SITE_NAME}", [
            f"{SITE_NAME} là nền tảng tạo video và hình ảnh bằng trí tuệ nhân tạo dành cho người làm nội dung Việt Nam, tại {SITE_URL}.",
            "Chúng tôi cung cấp: tạo video từ ảnh/prompt, kịch bản AI, tạo ảnh AI, dịch và thêm phụ đề đa ngôn ngữ, lồng tiếng, tải video mạng xã hội, và thư viện template.",
            "Mục tiêu của chúng tôi là mang công nghệ AI tạo video đến với người bán hàng, content creator và doanh nghiệp nhỏ với chi phí minh bạch theo credit."]),
        ("Giá trị", [
            "Minh bạch: bảng giá rõ ràng, ước tính chi phí trước khi tạo, lịch sử dòng tiền cá nhân.",
            "Tôn trọng quyền sở hữu: nội dung bạn tạo là của bạn.",
            "Bảo vệ nội dung: công cụ giúp bạn tạo nội dung gốc, không khuyến khích re-up nội dung của người khác."]),
        ("Thông tin đơn vị vận hành", [
            f"Tên dịch vụ: {SITE_NAME}",
            f"Website: {SITE_URL}",
            f"Email hỗ trợ: {SUPPORT_EMAIL}",
            "Thời gian hỗ trợ: 8:00–22:00, Thứ 2 – Chủ nhật (GMT+7)."]),
    ]),
    "contact": ("Liên hệ", [
        ("Hỗ trợ kỹ thuật", [
            f"Email: {SUPPORT_EMAIL}",
            "Zalo và Facebook: nút hỗ trợ ở chân trang và góc trên thanh điều hướng — bấm để mở chat trực tiếp.",
            "Thời gian hỗ trợ: 8:00–22:00 (GMT+7), phản hồi trong vòng 24 giờ ngày làm việc."]),
        ("Báo lỗi và phản hồi", [
            "Mô tả lỗi kèm ảnh chụp màn hình, thông báo lỗi và thời gian xảy ra.",
            f"Gửi tới {SUPPORT_EMAIL} hoặc chat trực tiếp trong ứng dụng."]),
        ("Yêu cầu pháp lý", [
            "Yêu cầu gỡ nội dung vi phạm bản quyền hoặc báo cáo nội dung: gửi kèm URL nội dung, bằng chứng quyền sở hữu và thông tin liên hệ của bạn.",
            f"Email {SUPPORT_EMAIL}, tiêu đề \"YÊU CẦU GỠ NỘI DUNG\"."]),
        ("Hợp tác và quảng cáo", [
            f"Liên hệ {SUPPORT_EMAIL} với tiêu đề \"HỢP TÁC\"."]),
    ]),
}




_LEGAL_CSS = """
main.wrap{padding:34px 0 56px;max-width:900px}
.crumbs{font-size:12.5px;color:var(--tx3);margin-bottom:14px}
.crumbs a{color:var(--tx2);text-decoration:none}
.crumbs a:hover{color:var(--gold-2)}
.page-title{font-size:clamp(26px,3.4vw,36px);letter-spacing:-.8px;margin:6px 0 4px}
.updated{color:var(--tx2);font-size:12.5px}
h2{font-size:18px;margin:30px 0 8px;color:var(--gold-2)}
p{color:#e8e5df;font-size:14.5px;margin:8px 0}
section{border-bottom:1px solid rgba(255,255,255,.05);padding-bottom:16px}
section:last-of-type{border-bottom:none}
.doc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:14px}
.doc-card{display:block;text-decoration:none;background:var(--card);border:1px solid var(--bd);
  border-radius:var(--r);padding:18px;transition:transform .16s ease,border-color .16s ease}
.doc-card:hover{transform:translateY(-3px);border-color:var(--gold-line)}
.doc-card h3{margin:0 0 6px;font-size:15px;color:var(--gold-2)}
.doc-card p{margin:0 0 10px;font-size:12.5px;color:var(--tx2);line-height:1.6}
.doc-card .go{font-size:12.5px;color:var(--gold);font-weight:700}
"""


def render(slug: str, support: dict | None = None) -> str | None:
    page = PAGES.get(slug)
    if not page:
        return None
    title, sections = page
    body = ['<main class="wrap">',
            f'<div class="crumbs"><a href="/#docs">Tài liệu</a> &nbsp;›&nbsp; {_e(title)}</div>',
            f'<h1 class="page-title">{_e(title)}</h1>',
            f'<div class="updated">Cập nhật lần cuối: {_e(UPDATED)}</div>']
    for heading, paragraphs in sections:
        body.append(f"<section><h2>{_e(heading)}</h2>")
        for p in paragraphs:
            body.append(f"<p>{_e(p)}</p>")
        body.append("</section>")
    body.append("</main>")

    return _page(title=title,
                 description=f"{title} của {SITE_NAME}",
                 body="".join(body),
                 active="/#docs", support=support, extra_css=_LEGAL_CSS)


def all_routes() -> list[str]:
    return list(PAGES)
