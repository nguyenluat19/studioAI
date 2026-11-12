"""Pipeline: yêu cầu văn bản -> storyboard -> ảnh từng cảnh -> video từng cảnh -> dựng thành phẩm.

Mỗi bước dùng MỘT model do người dùng chọn (theo model registry), không tự chuyển model khi lỗi.
"""
import json
import math
import re

from . import ai
from .modelregistry import get_model


<<<<<<< HEAD
def _extract_storyboard_text(message: dict) -> str:
    """Normalize OpenAI-compatible and block-based gateway message content to text."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                value = block.get("text") or block.get("content")
                if isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, list):
                    parts.extend(str(x.get("text", "")) for x in value if isinstance(x, dict))
        return "\\n".join(p for p in parts if p).strip()
    if isinstance(content, dict):
        for key in ("text", "json", "output"):
            value = content.get(key)
            if isinstance(value, (str, dict, list)):
                return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value.strip()
    for key in ("output_text", "text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _parse_storyboard_json(text: str) -> dict:
    """Parse one JSON object from gateway output, including fenced/prefixed responses.

    Some OpenAI-compatible gateways ignore response_format=json_object. A balanced
    decoder avoids the previous greedy-regex failure when prose or another object
    appears after the actual storyboard.
    """
    text = (text or "").strip()
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("LLM không trả về JSON object hợp lệ")


_PHASE_ALIASES = {
    "hook": "hook",
    "mở đầu": "hook",
    "mo dau": "hook",
    "intro": "hook",
    "biến hình": "bien_hinh",
    "bien hinh": "bien_hinh",
    "bien_hinh": "bien_hinh",
    "transformation": "bien_hinh",
    "transform": "bien_hinh",
    "review": "review",
    "đánh giá": "review",
    "danh gia": "review",
    "chi tiết sản phẩm": "chi_tiet_san_pham",
    "chi tiet san pham": "chi_tiet_san_pham",
    "chi_tiet_san_pham": "chi_tiet_san_pham",
    "product close-up": "chi_tiet_san_pham",
    "detail": "chi_tiet_san_pham",
}


def _normalize_phase(raw: object, idx: int, total: int) -> str:
    # Review phases are position-locked by the application, not trusted from LLM JSON.
    if idx == 0:
        return "hook"
    if total >= 3 and idx == 1:
        return "bien_hinh"
    if total >= 3 and idx == total - 1:
        return "chi_tiet_san_pham"
    return "review"


def plan_storyboard(topic: str, model_id: str, duration_seconds: int,
                    aspect_ratio: str, character_image_url: str | None = None,
                    max_retries: int = 2, creds: dict | None = None,
                    language: str = "vi", mode: str = "standard",
                    outfit_image_url: str | None = None,
                    hook_seconds: int = 3,
                    clip_steps: list[int] | None = None,
                    preset: dict | None = None,
                    product: str = "") -> dict:
    """Tạo storyboard JSON từ yêu cầu; các reference ảnh thật chỉ được xử lý ở keyframe stage."""
    review_mode = str(mode) == "review_outfit"
    hook_seconds = max(1, min(int(hook_seconds or 3), 10))
    steps = sorted({int(s) for s in (clip_steps or []) if 0 < int(s) <= 120})
    if steps:
        hook_seconds = min(steps, key=lambda s: (abs(s - hook_seconds), s))
=======
def plan_storyboard(topic: str, model_id: str, duration_seconds: int,
                    aspect_ratio: str, character_image_url: str | None = None,
                    max_retries: int = 2) -> dict:
    """Tạo storyboard JSON từ yêu cầu văn bản bằng model LLM đã chọn.

    Không tự đổi model khi lỗi: thử lại chính model đó tối đa `max_retries` lần.
    """
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    model = get_model(model_id)
    if not model or model.step != "llm":
        raise ValueError(f"Model {model_id} không phải model kịch bản (LLM)")
    if not model.enabled:
        raise ValueError(f"Model {model_id} đang bị tắt")

<<<<<<< HEAD
    # Số cảnh suy ra từ tổng thời lượng và độ dài mỗi shot (mặc định 2-6s tự nhiên; nếu biết mốc giây model → dùng mốc đó)
    min_per_scene = steps[0] if steps else 2
    max_per_scene = steps[-1] if steps else 6
    clip_count = max(1, math.ceil(duration_seconds / max_per_scene))  # số clip ước tính (model limit handled in rendering)

    # Ngôn ngữ thoại: vi = Tiếng Việt, en = English
    lang = "en" if str(language).strip().lower() in ("en", "eng", "english", "tiếng anh", "tieng anh") else "vi"
    dialogue_word = "tiếng Việt" if lang == "vi" else "English"
    lang_example = "Meo meo, hôm nay trời đẹp quá!" if lang == "vi" else "Meow meow, the weather is lovely today!"

    sys_prompt = (
        "Detailed storyboard as pure JSON (never wrap in markdown code blocks, "
        "no explanation before/after the JSON).\n"
        "Mandatory JSON schema:\n"
        "{\n"
        '  "character_bible": {"mô_tả": "...", "khuôn_mặt": "face shape, eyes, nose, mouth, skin, distinguishing traits (must NOT change between scenes)", "tóc": "...", "trang_phúc": "...", "tuổi": "...", "tính_diện": "...", "ghi_chú_không_thay_đổi": "..."},\n'
        '  "nhân_vật": [{"tên": "Character name", "giới_tính": "nam or nữ", "mô_tả": "..."}],\n'
=======
    min_per_scene = max(1, duration_seconds // 5)
    clip_count = max(1, math.ceil(duration_seconds / min_per_scene))

    sys_prompt = (
        "storyboard chi tiết dưới dạng JSON thuần túy (KHÔNG bọc trong markdown code block, "
        "KHÔNG giải thích thêm ngoài JSON).\n"
        "Schema JSON bắt buộc:\n"
        "{\n"
        '  "character_bible": {"mô_tả": "...", "trang_phúc": "...", "tuổi": "...", "tính_diện": "...", "ghi_chú_không_thay_đổi": "..."},\n'
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        '  "style_bible": {"ánh_sáng": "...", "tông_màu": "...", "ống_kính": "...", "tỉ_lệ_khung_hình": "...", "phong_cách": "..."},\n'
        '  "location_bible": {"bối_cảnh": "...", "tái_sử_dụng": true},\n'
        '  "các_cảnh": [\n'
        "    {\n"
        '      "stt": 1,\n'
<<<<<<< HEAD
        '      "thời_lượng_giây": 4,\n'
        '      "loại_shot": "WS wide shot",\n'
        '      "góc_máy": "low angle",\n'
        '      "chuyển_động_camera": "pan right",\n'
        '      "hành_động": "...",\n'
        '      "biểu_cảm": "<một tag cảm xúc>",\n'
        '      "nhân_vật_nói": "Speaker name (must match nhân_vật list)",\n'
        '      "thoại": "...",\n'
        '      "ghi_chú_âm_thanh": "...",\n'
        '      "ghi_chú_liên_tục": "...",\n'
        '      "image_prompt": "detailed English prompt for this scene (character bible + style + location + action)",\n'
        '      "video_prompt": "detailed English prompt for this scene (action + camera + lighting + style)"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Each scene is a short cut, never a long take that is chopped.\n"
        f"- Total duration of all scenes equals {duration_seconds} seconds.\n"
        + (
            f"- Every scene duration MUST be exactly one of: {' / '.join(str(s) for s in steps)} seconds — the video model only accepts those clip lengths. "
            f"Total must come as close as possible to {duration_seconds}s using ONLY those lengths.\n"
            if steps else
            "- Each scene is 2-6 seconds (natural shot length).\n"
        ) +
        "- ABSOLUTELY diverse: at least 4 shot types (WS/MS/CU/insert...), at least 3 different camera angles, camera movement in most scenes. Two consecutive scenes must not share both shot type and camera angle.\n"
            "- Dialogue is REQUIRED in every character-on-camera scene in the selected language; lip-sync only the exact provided line, one visible speaker, face/mouth clearly visible, no extra words or off-script audio. Product-only scenes have no visible speaker and use voiceover/CTA only, never lip-sync.\n"
        "- character_bible must clearly describe face, eyes, nose, mouth, skin tone, hair, outfit and fixed identity.\n"
        "- biểu_cảm MUST be exactly one of these emotion tags (in the guest's language or English): "
        "vui vẻ | hào hứng | phấn khích | lạc quan | tự tin | nghiêm túc | bình thường | bình thản | nũng nịu | ngọt ngào | cảm động | cảm thông | "
        "buồn bã | thất vọng | chán nản | tức giận | giận dữ | sợ hãi | hoảng loạn | ngạc nhiên | sốc | thì thầm | khóc | thút thít | thông thái | cao hứng "
        "(English equivalents: happy | excited | joyful | optimistic | confident | serious | neutral | calm | sweet | empathetic | sad | disappointed | angry | furious | scared | surprised | whisper | crying | wise).\n"
        "- EVERY line of thoại carries the biểu_cảm tag that matches its mood — NEVER default the whole scene set to 'bình thường'. "
        "Vary the tags across scenes (hook = curious/hào hứng, review = sincere/tự tin, product CTA = hào hứng). "
        "The tag drives the TTS voice delivery (rate/pitch/volume) and the video model's lip-sync acting — an untagged or wrong tag makes the line sound robotic.\n"
        "- If there are multiple characters, each has their own character_bible/nhân_vật entry; never mix their features.\n"
        '- List ALL characters appearing in "nhân_vật", each with explicit "giới_tính" (nam/nữ). Each scene records "nhân_vật_nói" matching that name so the system can pick a gender-appropriate voice.\n'
        "- image_prompt: detailed ENGLISH prompt for the image model including character bible + style + location + action.\n"
        "- video_prompt: detailed ENGLISH prompt for the video model including action + camera + lighting + style.\n"
        "- All prompts (image_prompt/video_prompt) are always written in English.\n"
        f"- All human-readable values in the JSON (ví dụ: thoại, hành_động, biểu_cảm, mô_tả, ghi_chú...) are written in {dialogue_word} — that is the guest's chosen language.\n"
        "- NO SUBTITLES, captions, watermarks, letters, graphics or on-screen text anywhere in any scene; the guest adds subtitles later in their own editor. Video prompts must never ask for text/captions overlay.\n"
        "- If a character reference image is provided, use that exact character in every scene.\n"
        "- Quality: photorealistic, 8K, ultra sharp, modern cinematic style, professional lighting, high detail, no blur, no artifacts. Characters must look real, expressions natural.\n"
    )
    if review_mode:
        sys_prompt += (
            "STRICT PRODUCT-REFERENCE LOCK: the uploaded product/garment photo is the only source of truth for the item. Never substitute, redesign, recolor, embellish, simplify, or infer a different product from the text, outfit_bible, or genre conventions. Never invent blazer, buttons, collar, sleeves, pattern, logo, or accessories unless clearly visible in that uploaded photo. If a property is not visible, do not claim it. The character photo is the only source of truth for face, hair, skin tone, and body; preserve that same person in every character shot.\n"
            "REVIEW PRODUCT MODE — mandatory:\n"
            "- Use phase tags: hook | bien_hinh | review | chi_tiet_san_pham.\n"
            f"- Hook ({hook_seconds}s): the same character already wears the exact user-supplied item.\n"
            "- Reveal scene is camera/light reveal only; no product morph. Review scenes keep the exact same product design.\n"
            "- Product-only scene has no person; CTA is voiceover only.\n"
            "- outfit_bible contains only cautious visual notes and can never override the source image.\n"


            '- Each scene MUST include "giai_đoạn" being EXACTLY one of: "hook" | "bien_hinh" | "review" | "chi_tiet_san_pham".\n'
            f"- Scene 1 (hook, exactly {hook_seconds} seconds): the same character already wears the exact user-supplied product/garment from the start.\n"
            "- Scene 2 (bien_hinh, 2-4 seconds): start with the character already wearing the exact reviewing product from the reference; use a simple flash/camera reveal only. Do not morph, redesign, or change garment details within this independently generated shot.\n"
            "- Middle scenes (review): character wears the EXACT REVIEWING PRODUCT from the uploaded image. Do not replace it with a generic item or the original outfit. Give sincere review; only discuss visible/provided product facts.\n"
            "- Final scene (chi_tiet_san_pham): exact product close-up using the uploaded reference. No invented seam, tag, accessory, logo, or product feature. Voiceover/CTA only; no visible speaker required.\n"
            "- Preserve product design and character identity through all scenes. Pose, framing, and background may change; the item itself may not.\n"
        )
    else:
        sys_prompt += (
            'Each scene may optionally include "giai_đoạn".\n'
        )

    if preset:
        from .presets import build_prompt_block
        sys_prompt += (
            "SALES PRESET (B2C selling video) — mandatory, follow the industry angle exactly:\n"
            + build_prompt_block(preset, product) + "\n"
            "- The dialogue must sound like a real seller talking to the camera about THIS product.\n"
        )

    user_msg = (
        f"Video request: {topic}\n"
        f"Total duration: {duration_seconds} seconds\n"
        f"Aspect ratio: {aspect_ratio}\n"
        f"Dialogue language (reply language): {dialogue_word}\n"
        f"Estimated clip count: {clip_count}\n"
        f"{'Character reference image: ' + character_image_url if character_image_url else ''}"
        + (f"\nGarment/product reference image (reference 2): {outfit_image_url}"
           if review_mode and outfit_image_url else "")
=======
        '      "thời_lượng_giây": 10,\n'
        '      "loại_shot": "...",\n'
        '      "góc_máy": "...",\n'
        '      "chuyển_động_camera": "...",\n'
        '      "hành_động": "...",\n'
        '      "biểu_cảm": "...",\n'
        '      "thoại": "...",\n'
        '      "ghi_chú_âm_thanh": "...",\n'
        '      "ghi_chú_liên_tục": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Quy tắc:\n"
        "- Mỗi cảnh là một cú quay ngắn, cắt theo hành động (không quay dài liền bị cắt khúc).\n"
        f"- Tổng độ dài các cảnh bằng {duration_seconds} giây.\n"
        f"- Mỗi cảnh <= {min_per_scene} giây (giới hạn clip của model video đã chọn).\n"
        "- Lời thoại phải vừa độ dài cảnh (tiếng Việt).\n"
        "- Nhân vật giữ nhất quán qua mọi cảnh (mặt, tóc, dáng, trang phục khoá).\n"
        "- Nếu có ảnh nhân vật tham chiếu, dùng đúng nhân vật đó trong mọi cảnh.\n"
    )

    user_msg = (
        f"Yêu cầu video: {topic}\n"
        f"Tổng độ dài: {duration_seconds} giây\n"
        f"Tỉ lệ khung hình: {aspect_ratio}\n"
        f"Số clip ước tính: {clip_count}\n"
        f"{'Ảnh nhân vật tham chiếu: ' + character_image_url if character_image_url else ''}"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    )

    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
<<<<<<< HEAD
            msg = ai.chat((creds or {}).get("model_name") or model_id, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ], json_mode=True, timeout=30,
                base_url=(creds or {}).get("base_url"),
                api_key=(creds or {}).get("api_key"))
            text = _extract_storyboard_text(msg)
            if not text:
                # Keep only a safe structural diagnostic; never log prompts or secrets.
                keys = sorted(str(k) for k in msg.keys()) if isinstance(msg, dict) else []
                raise ValueError(f"Gateway trả content rỗng/không phải text (message keys: {keys})")
            data = _parse_storyboard_json(text)
=======
            msg = ai.chat(model_id, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ], json_mode=True, timeout=30)
            text = (msg.get("content") or "").strip()
            m = re.search(r"\{.*\}", text or "", re.DOTALL)
            if not m:
                raise ValueError("LLM không trả về JSON hợp lệ")
            data = json.loads(m.group(0))
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa

            scenes = data.get("các_cảnh", [])
            if not scenes:
                raise ValueError("Storyboard không có cảnh nào")

<<<<<<< HEAD
            characters = data.get("nhân_vật", [])
            normalized = []
            for i, scene in enumerate(scenes):
                dur = int(scene.get("thời_lượng_giây", 4))
                if steps:
                    dur = min(steps, key=lambda s: (abs(s - dur), s))
                else:
                    dur = max(2, min(dur, 6))  # shot tự nhiên 2-6s
                try:
                    stt = int(scene.get("stt", i + 1))
                except (TypeError, ValueError):
                    stt = i + 1
                if review_mode and i == 0:
                    dur = hook_seconds  # hook đúng số giây người dùng chọn (đã snap về mốc model nếu cần)
                normalized.append({
                    "stt": stt,
=======
            normalized = []
            for i, scene in enumerate(scenes):
                dur = int(scene.get("thời_lượng_giây", min_per_scene))
                dur = max(1, min(dur, min_per_scene if min_per_scene > 0 else duration_seconds))
                normalized.append({
                    "stt": scene.get("stt", i + 1),
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
                    "thời_lượng_giây": dur,
                    "loại_shot": str(scene.get("loại_shot", "MS")),
                    "góc_máy": str(scene.get("góc_máy", "mặt đã")),
                    "chuyển_động_camera": str(scene.get("chuyển_động_camera", "tĩnh")),
                    "hành_động": str(scene.get("hành_động", "")),
                    "biểu_cảm": str(scene.get("biểu_cảm", "bình thường")),
                    "thoại": str(scene.get("thoại", "")),
<<<<<<< HEAD
                    "nhân_vật_nói": str(scene.get("nhân_vật_nói", "")),
                    "ghi_chú_âm_thanh": str(scene.get("ghi_chú_âm_thanh", "")),
                    "ghi_chú_liên_tục": str(scene.get("ghi_chú_liên_tục", "")),
                    "giai_đoạn": _normalize_phase(scene.get("giai_đoạn"), i, len(scenes)) if review_mode else "",
                    "tỉ_lệ_khung_hình": aspect_ratio,
                    "image_prompt": str(scene.get("image_prompt", "")),
                    "video_prompt": str(scene.get("video_prompt", "")),
                })

            # Đảm bảo tổng ≈ duration_seconds (bám sát mốc giây model nếu có)
            lo = steps[0] if steps else 2
            hi = steps[-1] if steps else 6
            unit = steps[0] if steps else 1
            total = sum(s["thời_lượng_giây"] for s in normalized)
            if total != duration_seconds and normalized:
                diff = duration_seconds - total
                # Hook (cảnh 1) giữ đúng thời lượng người dùng chọn -> chỉ phân bổ vào các cảnh còn lại.
                start = 1 if (review_mode and len(normalized) > 1) else 0
                span = max(1, len(normalized) - start)
                # Phân bổ diff vào các cảnh (theo bước mốc, cố định giới hạn [lo, hi])
                i = 0
                while diff != 0 and i < span * 30:
                    idx = start + (i % span)
                    cur = normalized[idx]["thời_lượng_giây"]
                    if diff > 0 and cur + unit <= hi:
                        normalized[idx]["thời_lượng_giây"] = cur + unit
                        diff -= unit
                    elif diff < 0 and cur - unit >= lo:
                        normalized[idx]["thời_lượng_giây"] = cur - unit
                        diff += unit
                    i += 1

            # No visual model sees either image in this LLM call. Never use LLM-invented visual facts
            # as prompt truth; the image editor/video model receives the actual user reference later.
            outfit_bible = {
                "source_of_truth": "user-uploaded product/garment image only",
                "rule": "preserve the exact visible item; do not infer or invent details",
            }
            return {
                "model_used": model_id,
                "language": lang,
                "mode": "review_outfit" if review_mode else str(mode or "standard"),
                "preset": (preset or {}).get("id", ""),
                "nhân_vật": characters,
                "tổng_số_cảnh": len(normalized),
                "tổng_thời_lượng": sum(s["thời_lượng_giây"] for s in normalized),
                "character_bible": data.get("character_bible", {}),
                "outfit_bible": outfit_bible if review_mode else {},
=======
                    "ghi_chú_âm_thanh": str(scene.get("ghi_chú_âm_thanh", "")),
                    "ghi_chú_liên_tục": str(scene.get("ghi_chú_liên_tục", "")),
                    "tỉ_lệ_khung_hình": aspect_ratio,
                })

            # Đảm bảo tổng ≈ duration_seconds
            total = sum(s["thời_lượng_giây"] for s in normalized)
            if total != duration_seconds and normalized:
                diff = duration_seconds - total
                normalized[0]["thời_lượng_giây"] = max(1, normalized[0]["thời_lượng_giây"] + diff)

            return {
                "model_used": model_id,
                "tổng_số_cảnh": len(normalized),
                "tổng_thời_lượng": sum(s["thời_lượng_giây"] for s in normalized),
                "character_bible": data.get("character_bible", {}),
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
                "style_bible": data.get("style_bible", {}),
                "location_bible": data.get("location_bible", {}),
                "các_cảnh": normalized,
            }
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(f"Không tạo được storyboard sau {max_retries + 1} lần thử ({model_id}): {last_error}")


<<<<<<< HEAD
def expand_single_prompt(idea: str, model_id: str, *, creds: dict | None = None,
                         language: str = "vi", max_retries: int = 2) -> str:
    """Mở rộng ý tưởng ngắn thành 1 prompt video hoàn chỉnh (tiếng Anh, cinematic) cho Veo.

    Dùng cho mode Text→Video / Ảnh→Video: chỉ cần 1 clip, không cần storyboard/keyframe.
    Lỗi LLM → trả về ý tưởng gốc; KHÔNG làm hỏng pipeline.
    """
    idea = (idea or "").strip()
    if not idea:
        return idea
    model = get_model(model_id)
    if not model or model.step != "llm" or not model.enabled:
        return idea
    lang = "en" if str(language).strip().lower() in ("en", "eng", "english", "tiếng anh", "tieng anh") else "vi"
    dialogue_word = "tiếng Việt" if lang == "vi" else "English"
    system = (
        "You are a world-class cinematic prompt writer for Veo video generation. "
        "Expand the guest's brief into ONE rich video prompt in ENGLISH: describe subject, precise action, "
        "camera movement, lighting, color grading, lens, mood, style, and IF appropriate include ONE short spoken "
        f"dialogue line in {dialogue_word}. Output ONLY the final prompt text — no explanation, no quotes, "
        "no preamble. Keep it under 110 words. Absolutely no subtitles, captions, text or watermarks in frame."
    )
    user = f"Brief: {idea}\nAspect: 9:16"
    for _ in range(max_retries + 1):
        try:
            resp = ai.chat(
                (creds or {}).get("model_name") or model_id,
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                timeout=30,
                base_url=(creds or {}).get("base_url"),
                api_key=(creds or {}).get("api_key"))
            text = (resp.get("content") or "").strip()
            text = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", text).strip().strip('"')
            if len(text) >= 20:
                return text
        except Exception:
            pass
    return idea


def identity_lock(character_bible: dict, characters: list[dict] | None = None,
                  allow_outfit_change: bool = False) -> str:
    if allow_outfit_change:
        wardrobe = ("Wardrobe is scripted: the character wears the ORIGINAL outfit in the hook scene, "
                   "then changes into the REVIEWING OUTFIT for all later scenes. "
                   "Never revert to the original outfit after the transformation.")
    else:
        wardrobe = "preserve each named character's face, hair, skin tone, body proportions and wardrobe"
    return (
        f"IDENTITY LOCK: {wardrobe} across all scenes. "
        "Never swap identities or mix their features. "
        "Only characters present in this scene should appear; do not add the entire cast. "
        f"CHARACTER BIBLE: {json.dumps(character_bible or {}, ensure_ascii=False)}. "
        f"NAMED CHARACTERS: {json.dumps(characters or [], ensure_ascii=False)}. "
        "The visual reference takes precedence over conflicting appearance descriptions."
    )


def gen_keyframe_prompt(scene: dict, character_bible: dict, style_bible: dict,
                        character_image_url: str | None = None,
                        characters: list[dict] | None = None,
                        location_bible: dict | None = None,
                        *, phase: str = "",
                        outfit_bible: dict | None = None,
                        has_outfit_reference: bool = False) -> str:
    """Sinh prompt ảnh với identity lock cố định cho mọi cảnh."""
    if phase == "chi_tiet_san_pham":
        # Cận cảnh sản phẩm: không có nhân vật — chỉ giữ đúng sản phẩm/bộ đồ.
        parts = [
            f"PRODUCT CLOSE-UP SHOT: {json.dumps(outfit_bible or {}, ensure_ascii=False)}",
            f"Hành động: {scene.get('hành_động', '')}",
            f"Loại shot: {scene.get('loại_shot', '')}",
            f"Góc máy: {scene.get('góc_máy', '')}",
            f"STYLE: {json.dumps(style_bible, ensure_ascii=False)}",
            f"LOCATION: {json.dumps(location_bible or {}, ensure_ascii=False)}",
            f"Tỉ lệ: {scene.get('tỉ_lệ_khung_hình', '9:16')}",
            "PRODUCT REFERENCE LOCK: recreate only the visible garment/product from the supplied reference image, matching silhouette, color, neckline, straps, seams, pattern and fit as far as visible. Do not substitute another garment or invent hidden details. The exact supplied product reference outranks any textual description. No people in frame. Extreme close-up of visible product details only. Studio lighting, macro detail, photorealistic, 8K.",
            "No on-screen text, no letters, no watermark, no subtitles or captions in frame.",
        ]
        if has_outfit_reference:
            parts.append("The reference image is the exact product/garment — preserve its color, material, pattern, stitching and shape exactly.")
        return ". ".join(parts)

    is_review = bool(phase)
    parts = [
        identity_lock(character_bible, characters, allow_outfit_change=is_review),
        f"Hành động: {scene.get('hành_động', '')}",
        f"Biểu cảm: {scene.get('biểu_cảm', 'bình thường')}",
        f"Loại shot: {scene.get('loại_shot', '')}",
        f"Góc máy: {scene.get('góc_máy', '')}",
        f"Chuyển động camera: {scene.get('chuyển_động_camera', 'tĩnh')}",
        f"STYLE: {json.dumps(style_bible, ensure_ascii=False)}",
        f"LOCATION: {json.dumps(location_bible or {}, ensure_ascii=False)}",
        f"Tỉ lệ: {scene.get('tỉ_lệ_khung_hình', '9:16')}",
        "Scene details may change pose, expression, framing and background, but must not override the identity lock. Preserve the specified shot and camera angle.",
        "No on-screen text, no letters, no watermark, no subtitles or captions in frame.",
    ]
    if is_review:
        parts.append("PRODUCT IMAGE LOCK: the uploaded product image, not text or generated descriptions, determines the exact item. Match only its visible color, silhouette, neckline, straps/sleeves, seams, pattern and fit; do not add/replace design features.")
    if phase == "hook":
        parts.append("The person must match the supplied character reference photo exactly: face, hair, skin tone, and body. The review garment already worn must match the separate product reference exactly; do not use the character photo's clothing as a substitute.")
        if has_outfit_reference:
            parts.append("Use the second supplied product reference as the exact review item already worn by the character. Preserve its visible design, color, silhouette and details; do not substitute or invent garment features.")
    elif phase in ("bien_hinh", "review"):
        parts.append(f"OUTFIT BIBLE (reference constraint only, not a source of invented product facts): {json.dumps(outfit_bible or {}, ensure_ascii=False)}")
        parts.append("The user-uploaded garment photo is authoritative. Reproduce the exact visible item: same silhouette, color, neckline, straps/sleeves, seam placement, pattern and fit. Never substitute or add product details. Preserve the exact same face, hair, skin tone and body from the character reference. Pose/background can change; garment design cannot.")
        if phase == "bien_hinh":
            parts.append("Reveal-only beat: simple camera/light reveal while preserving the exact product design. No wardrobe morph, redesign, added or removed details.")
    if character_image_url:
        parts.append("Use the supplied character reference image as the primary identity reference. Preserve the same identities; change only pose, expression, camera angle and background.")
    if has_outfit_reference:
        parts.append("A second reference image shows the exact garment/product — match it exactly (color, material, pattern, cut, stitching). Do not output a split screen.")
=======
def gen_keyframe_prompt(scene: dict, character_bible: dict, style_bible: dict,
                        character_image_url: str | None = None) -> str:
    """Sinh prompt ảnh cho một cảnh từ storyboard + bible."""
    parts = [
        f"Hành động: {scene['hành_động']}",
        f"Biểu cảm: {scene['biểu_cảm']}",
        f"Góc máy: {scene['góc_máy']}",
        f"Chuyển động camera: {scene['chuyển_động_camera']}",
        f"Ánh sáng: {style_bible.get('ánh_sáng', 'ánh sáng tự nhiên')}",
        f"Tông màu: {style_bible.get('tông_màu', 'tự nhiên')}",
        f"Phong cách: {style_bible.get('phong_cách', 'cinematic')}",
        f"Tỉ lệ: {scene['tỉ_lệ_khung_hình']}",
    ]
    if character_image_url:
        parts.append(f"Ảnh nhân vật tham chiếu: {character_image_url}")
    cb = character_bible
    parts.append(f"Nhân vật: {cb.get('mô_tả', '')} | Trang phục: {cb.get('trang_phúc', '')} | Tuổi: {cb.get('tuổi', '')}")
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    return ". ".join(parts)


def scene_clip_count(scene: dict, video_model_id: str) -> int:
    """Số clip cần gen cho một cảnh dựa trên giới hạn của model video đã chọn."""
    model = get_model(video_model_id)
    if not model or model.max_clip_seconds <= 0:
        return 1
    dur = scene.get("thời_lượng_giây", 10)
    return math.ceil(dur / model.max_clip_seconds)


def estimated_cost(selections: dict, duration_seconds: int,
                   num_scenes: int, images_per_scene: int = 1,
                   db=None) -> dict:
    """Ước tính chi phí trước khi bấm Gen (dựa trên model đã chọn)."""
    from . import pricing
    details = {}
    total = 0.0

    # LLM: 1 lần gọi
    llm_id = selections.get("llm")
    if llm_id:
<<<<<<< HEAD
        llm_price_key = f"m.{llm_id}" if f"m.{llm_id}" in pricing.catalog() else None
=======
        llm_price_key = f"ai.{llm_id}" if f"ai.{llm_id}" in pricing.catalog() else None
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        llm_price = pricing.price(db, llm_price_key) if llm_price_key else 0.0
        details["llm"] = {"model": llm_id, "unit": "lần gọi", "số_lượng": 1, "giá": llm_price}
        total += llm_price

    # Images: 1 ảnh × số cảnh
    img_id = selections.get("image_generate")
    if img_id:
        img_price_key = f"m.{img_id}" if f"m.{img_id}" in pricing.catalog() else None
        img_price = pricing.price(db, img_price_key) if img_price_key else 0.0
        img_cost = round(img_price * num_scenes * images_per_scene, 2)
        details["image"] = {"model": img_id, "unit": "ảnh",
                            "số_lượng": num_scenes * images_per_scene, "giá": img_price,
                            "tổng": img_cost}
        total += img_cost

<<<<<<< HEAD
    # Video: 1 clip = 1 request (vilao tính theo request, vd Veo 3000đ/request)
    vid_id = selections.get("video_i2v")
    if vid_id:
        vid_price_key = pricing.video_pricing_key(vid_id)
        vid_price_key = vid_price_key if vid_price_key in pricing.catalog() else None
        vid_price = pricing.price(db, vid_price_key) if vid_price_key else 0.0
        video_cost = round(num_scenes * vid_price, 2)
        details["video"] = {"model": vid_id, "unit": "request", "số_lượng": num_scenes,
                            "giá": vid_price, "tổng": video_cost}
=======
    # Video: tổng giây × giá/giây
    vid_id = selections.get("video_i2v")
    if vid_id:
        vid_price_key = f"m.{vid_id}" if f"m.{vid_id}" in pricing.catalog() else None
        vid_price = pricing.price(db, vid_price_key) if vid_price_key else 0.0
        total_sec = duration_seconds
        video_cost = round(total_sec * vid_price, 2)
        details["video"] = {"model": vid_id, "unit": "giây",
                            "số_lượng": total_sec, "giá_đơn_vị": vid_price,
                            "tổng_giây": total_sec, "tổng": video_cost}
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
        total += video_cost

    details["tổng_credit"] = round(total, 2)
    return details
