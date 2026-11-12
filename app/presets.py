"""Preset bán hàng theo ngành hàng.

Mỗi preset là một "khung kịch bản" dùng để LLM viết kịch bản bán hàng đúng ngành:
đối tượng, giọng văn, kiểu hook, nỗi đau, điểm bán, lời kêu gọi và phong cách hình ảnh.

Dùng chung tài nguyên sẵn có (LLM + ảnh + video của admin) — không cần model mới.
"""
from __future__ import annotations

PRESETS: list[dict] = [
    {
        "id": "fashion",
        "label": "Thời trang",
        "icon": "👗",
        "audience": "phụ nữ 20-40, thích ăn mặc đẹp nhưng sợ mua nhầm size",
        "tone": "gợi ý thân thiện, đẹp mà không khoe khoang",
        "hook": "cảnh người mẫu khoác thử, kéo dài để lộ form đẹp",
        "pain": "sợ size không vừa, chất vải xấu hơn hình",
        "proof": "chất liệu, form đẹp, cách phối đồ, có size cho mỗi người",
        "cta": "khoe bảng size và bảo khách nhắn để được tư vấn",
        "visual": "studio sáng, nền trung tính, chuyển động chậm, cận cảnh chất liệu",
    },
    {
        "id": "beauty",
        "label": "Mỹ phẩm",
        "icon": "💄",
        "audience": "nữ 18-35, quan tâm da, makeup, chất lượng và giá",
        "tone": "nhẹ nhàng, có chuyên môn, không nói quá",
        "hook": "cận cảnh vùng da trước và sau khi dùng",
        "pain": "da dầu, dị ứng, mờ đốm, sản phẩm không hợp",
        "proof": "thành phần, kết quả thật, hợp với loại da",
        "cta": "mời đặt lịch tư vấn theo loại da",
        "visual": "ánh sáng mềm, màu nude, cận cảnh texture sản phẩm",
    },
    {
        "id": "food",
        "label": "Đồ ăn vặt",
        "icon": "🍜",
        "audience": "người bận rộn, thích ăn vặt, dễ bị mê bởi hình ảnh món ăn",
        "tone": "gợi ý thèm ăn, nhanh, súc tích",
        "hook": "cận cảnh món ăn đang nóng/chiên xèo xèo",
        "pain": "đói, không có thời gian nấu, ăn ngoài không ngon",
        "proof": "vị, thành phần, cách bảo quản, sẵn sàng trong 3 phút",
        "cta": "nhắn để đặt giao nhanh trong ngày",
        "visual": "food styling sẵn sàng nhà hàng, hơi nước, màu ấm",
    },
    {
        "id": "grocery",
        "label": "Hàng tiêu dùng",
        "icon": "🛒",
        "audience": "người nội trợ, mua sắm theo tuần, giá là quan trọng nhất",
        "tone": "thực tế, rõ ràng, nói thẳng giá trị",
        "hook": "bày sản phẩm thành mẫu 1 tuần ăn",
        "pain": "mất thời gian đi chợ, hàng không đúng ý, tốn tiền",
        "proof": "thành phần, hương vị, số lượng, giá so với siêu thị",
        "cta": "đặt hộp giao định kỳ, đổi vị miễn phí",
        "visual": "bàn ăn sáng, sản phẩm xếp gọn, nhẹ nhàng",
    },
    {
        "id": "appliance",
        "label": "Gia dụng",
        "icon": "🏠",
        "audience": "gia đình 2-4 người, quan tâm tiện lợi, tiết kiệm thời gian",
        "tone": "thực tế, demo rõ tác dụng",
        "hook": "before/after khi dùng thiết bị",
        "pain": "mất thời gian, dọn dẹp vất vả, tiền điện",
        "proof": "công suất, tiết kiệm điện, bảo hành, bảo trì",
        "cta": "nhắn để xem thông số và nhận ưu đãi lắp đặt",
        "visual": "không gian nhà Việt Nam sáng sạch, cận cảnh nút bấm",
    },
    {
        "id": "baby",
        "label": "Mẹ & Bé",
        "icon": "🍼",
        "audience": "mẹ bỉm sữa, ưu tiên an toàn và thành phần",
        "tone": "ấm áp, đáng tin cậy, tuyệt đối không hoa mỹ",
        "hook": "khoảnh khắc mẹ và bé cười",
        "pain": "lo ngại chất liệu, hết mùi, sổ bụng, khó sử dụng",
        "proof": "chất liệu, chứng nhận, tuổi phù hợp, cách dùng",
        "cta": "nhắn để được tư vấn theo tháng tuổi bé",
        "visual": "sáng, màu pastel, cận cảnh chất liệu mềm",
    },
    {
        "id": "tech",
        "label": "Đồ công nghệ",
        "icon": "📱",
        "audience": "dân văn phòng, sinh viên, người đam mê công nghệ",
        "tone": "nói thẳng tính năng, không hoa mỹ",
        "hook": "cận cảnh thao tác nhanh nhất của thiết bị",
        "pain": "loại chính hãng, bảo hành, hiệu năng thật",
        "proof": "cấu hình thật, đo benchmark, bảo hành, phụ kiện đi kèm",
        "cta": "nhắn để nhận báo giá + tặng phụ kiện",
        "visual": "nền tối, ánh sáng viền xanh, chuyển động mượt",
    },
    {
        "id": "accessory",
        "label": "Phụ kiện",
        "icon": "👜",
        "audience": "người thích đồ xịn giá rẻ, nữ trẻ",
        "tone": "thời trang, gợi ý phối đồ",
        "hook": "cận cảnh chi tiết phụ kiện độc đáo",
        "pain": "đồ rẻ nhìn không xịn, dễ bị xước",
        "proof": "chất liệu, đường may, phối đồ, bảo hành",
        "cta": "nhắn để chọn màu phù hợp",
        "visual": "nền sạch, sản phẩm xoay nhẹ, ánh sáng mềm",
    },
    {
        "id": "shoes",
        "label": "Giày dép",
        "icon": "👟",
        "audience": "người đi nhiều, cần giày bền, phù hợp công việc",
        "tone": "thẳng thắn, nói về độ bền và thoải mái",
        "hook": "bước chân đầu tiên sau khi thay giày",
        "pain": "đau chân, xuống cỡ, mẩm mồ hôi",
        "proof": "đế, lót, size, chống trơn, độ bền",
        "cta": "nhắn số đo chân để được tư vấn size",
        "visual": "quay chân, cận cảnh đế giày, ánh sáng ban ngày",
    },
    {
        "id": "decor",
        "label": "Decor",
        "icon": "🪴",
        "audience": "chủ nhà, người thích không gian xinh",
        "tone": "thư giãn, cảm hứng",
        "hook": "cảnh phòng trước/sau khi thêm decor",
        "pain": "phòng chật, tối, thiếu điểm nhấn",
        "proof": "kích thước, chất liệu, cách treo, phối màu",
        "cta": "nhắn để được gợi ý set theo không gian",
        "visual": "nhà ấm, ánh sáng chiều, không gian sống",
    },
    {
        "id": "stationery",
        "label": "Đồ dùng học tập",
        "icon": "✏️",
        "audience": "học sinh sinh viên, phụ huynh",
        "tone": "vui, gần gũi, tập trung vào sự tiện lợi",
        "hook": "cảnh mở cặp sách đầy màu sắc",
        "pain": "đồ hết hàng giữa kỳ, không tiện mua lẻ",
        "proof": "chất lượng giấy, số lượng, giá theo bộ",
        "cta": "nhắn để đặt trọn bộ theo lớp",
        "visual": "màu sắc tươi, góc nhìn từ trên xuống",
    },
    {
        "id": "supplement",
        "label": "Thực phẩm chức năng",
        "icon": "🫐",
        "audience": "người 30-55, quan tâm sức khỏe",
        "tone": "khoa học, trung thực, không hứa hẹn quá mức",
        "hook": "cận cảnh thành phần nổi bật",
        "pain": "mệt mỏi, thiếu vitamin, không tiện ăn đủ",
        "proof": "hàm lượng hoạt chất, nguồn gốc, chứng nhận",
        "cta": "nhắn để nhận hướng dẫn dùng đúng cách",
        "visual": "sạch, tươi, đồng hồ cát, ánh sáng trắng",
    },
    {
        "id": "toy",
        "label": "Đồ chơi",
        "icon": "🧸",
        "audience": "phụ huynh có con 3-10 tuổi, tặng quà",
        "tone": "vui vẻ, an toàn, đáng tin",
        "hook": "trẻ em chơi với món đồ chơi",
        "pain": "đồ chơi nhanh vỡ, không an toàn, khó vệ sinh",
        "proof": "chất liệu, độ bền, tuổi phù hợp, tiêu chuẩn",
        "cta": "nhắn để chọn quà theo lứa tuổi",
        "visual": "màu sắc tươi, không gian gia đình, tay chơi",
    },
    {
        "id": "vehicle",
        "label": "Xe cộ",
        "icon": "🛵",
        "audience": "người chạy xe ôm, giao hàng, đi làm xa",
        "tone": "thực dụng, bền bỉ, nói về giá trị sử dụng",
        "hook": "cảnh lên xe và chạy trên đường",
        "pain": "xe yếu, chạy xa mệt, bảo trì tốn",
        "proof": "động cơ, dung tích, phạm vi, bảo hành",
        "cta": "nhắn để được gửi báo giá tại chỗ",
        "visual": "đường phố Việt Nam, ánh sáng chiều, chuyển động mượt",
    },
    {
        "id": "pet",
        "label": "Phụ kiện thú cưng",
        "icon": "🐶",
        "audience": "chủ nuôi chó mèo, coi thú cưng như con",
        "tone": "ấm áp, vui, có chút hài",
        "hook": "thú cưng phản ứng với món đồ mới",
        "pain": "thú cưng không thích, đồ dễ bị phá, vệ sinh khó",
        "proof": "chất liệu an toàn, kích thước, khả năng giặt",
        "cta": "nhắn để được tư vấn theo giống thú cưng",
        "visual": "sáng, ấm, thú cưng ở tiền cảnh",
    },
    {
        "id": "general",
        "label": "Mọi sản phẩm",
        "icon": "📦",
        "audience": "khách lướt nhanh trên mạng xã hội, chưa biết mình cần gì",
        "tone": "gọn, dễ hiểu, có lời động viên hành động rõ",
        "hook": "cảnh sản phẩm xuất hiện đầy màn hình kèm câu hỏi chặn scroll",
        "pain": "không biết chọn loại nào, sợ mua nhầm",
        "proof": "điểm nổi bật nhất + cam kết dễ dàng",
        "cta": "nhắn để được tư vấn nhanh",
        "visual": "sạch, tối giản, sản phẩm nổi bật",
    },
]

_BY_ID = {p["id"]: p for p in PRESETS}


def get_preset(preset_id: str | None) -> dict | None:
    """Preset theo id; trả None nếu rỗng/không hợp lệ."""
    if not preset_id:
        return None
    return _BY_ID.get(str(preset_id).strip().lower())


def list_presets() -> list[dict]:
    """Danh sách preset cho UI (id, label, icon, mô tả ngắn)."""
    return [{"id": p["id"], "label": p["label"], "icon": p["icon"],
             "audience": p["audience"], "tone": p["tone"],
             "hook": p["hook"], "pain": p["pain"], "proof": p["proof"],
             "cta": p["cta"], "visual": p["visual"]} for p in PRESETS]


def build_prompt_block(preset: dict, product: str = "") -> str:
    """Đoạn chỉ dẫn thêm vào prompt kịch bản — định dạng theo từng ngành."""
    lines = [
        f"- Ngành hàng: {preset.get('label', '')}.",
        f"- Đối tượng khách hàng: {preset.get('audience', '')}.",
        f"- Giọng văn kể: {preset.get('tone', '')}.",
        f"- Cảnh hook (3 giây đầu, phải chặn được ngón tay): {preset.get('hook', '')}.",
        f"- Nỗi đau khách đang gặp: {preset.get('pain', '')} — kịch bản phải chạm đúng nỗi đau này.",
        f"- Điểm bán (proof) cần nêu: {preset.get('proof', '')}.",
        f"- Lời kêu gọi hành động ở cảnh cuối: {preset.get('cta', '')}.",
        f"- Phong cách hình ảnh: {preset.get('visual', '')}.",
        "- Kịch bản phải giống một video bán hàng thật: có hook, có vấn đề, có giải pháp, có CTA.",
    ]
    if product:
        lines.insert(1, f"- Sản phẩm đang bán: {product}.")
    return "\n".join(lines)
