"""Gọi provider gateway chuẩn OpenAI/NewAPI (GET {base_url}/models).

Dùng chung cho:
- admin "☁️ Giá gốc API" (kéo giá provider mỗi tab admin)
- pipeline storyboard (lấy `model_options.seconds` để viết kịch bản theo đúng mốc giây của model)
"""
import httpx


def fetch_models(base_url: str, api_key: str, timeout: float = 15.0) -> list[dict]:
    r = httpx.get(base_url.rstrip("/") + "/models",
                  headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Gateway trả HTTP {r.status_code}")
    data = r.json().get("data", [])
    if not isinstance(data, list):
        raise RuntimeError("Gateway trả về không đúng định dạng /models")
    return data


def match_model(data: list[dict], model_name: str | None) -> dict | None:
    """Khớp model_name với danh sách gateway: exact → bỏ prefix provider (vd 'vid/Veo-3.1' → 'Veo-3.1') → substring 2 chiều."""
    mn = (model_name or "").strip().lower()
    suf = mn.split("/", 1)[1] if "/" in mn else mn
    for m in data:
        mid = str(m.get("id") or "").lower()
        if mn and (mid == mn or mid == suf or mid in mn or mn in mid):
            return m
    return None


def clip_seconds(data: list[dict], model_name: str | None) -> list[int] | None:
    """Trả về danh sách mốc giây mỗi clip mà model hỗ trợ (vd Veo [4,6,8]); None nếu không có."""
    m = match_model(data, model_name)
    if not m:
        return None
    vals = [int(s) for s in (m.get("model_options") or {}).get("seconds") or []
            if str(s).isdigit()]
    return sorted(set(vals)) or None


def clip_steps_for_model(base_url: str, api_key: str | None, model_name: str | None) -> list[int] | None:
    """Bước cao để storyboard chỉ viết cảnh theo mốc giây model chấp nhận; None = không tra được (LLM tự do 2-6s)."""
    if not api_key:
        return None
    try:
        data = fetch_models(base_url, api_key, timeout=15)
    except Exception:
        return None
    return clip_seconds(data, model_name)
