"""OpenAI-compatible image generation and reference-image editing."""
import base64
import mimetypes
import time
from pathlib import Path

import httpx

from .config import settings

SIZE_BY_RATIO = {"9:16": "1024x1792", "16:9": "1792x1024", "1:1": "1024x1024"}


class ImageError(RuntimeError):
    pass


class ReferenceImageUnsupported(ImageError):
    pass


class MultiReferenceUnsupported(ImageError):
    """Gateway từ chối nhiều ảnh tham chiếu trong một request."""


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".gif": "image/gif"}


def _is_image(data: bytes) -> bool:
    return (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
            or data[:6] in (b"GIF87a", b"GIF89a") or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))


def gen_image(prompt: str, dest: Path, *, base_url: str | None = None, api_key: str | None = None,
              model: str | None = None, ratio: str = "9:16", timeout: float = 300,
              reference: Path | None = None,
              references: list[Path] | None = None) -> Path:
    """Gen ảnh. `references` cho phép gửi nhiều ảnh tham chiếu (nhân vật + bộ đồ...);
    `reference` giữ tương thích cho 1 ảnh. Nhiều ảnh -> field `image[]` kiểu OpenAI edits."""
    refs: list[Path] = [p for p in (references or []) if p is not None]
    if reference is not None and reference not in refs:
        refs.insert(0, reference)
    for p in refs:
        if not p.is_file():
            raise ImageError(f"Không tìm thấy ảnh tham chiếu: {p.name}")
    base = (base_url or settings.vilao_base_url).rstrip("/")
    key = api_key or settings.vilao_api_key
    if base_url and not api_key:
        raise ImageError("Model chưa có API key riêng; vui lòng nhập API key trong Quản lý Model")
    if not base or not key:
        raise ImageError("Chưa cấu hình base_url / api_key cho model ảnh")
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {key}"}
    body = {"model": model or "", "prompt": prompt, "n": 1,
            "size": SIZE_BY_RATIO.get(ratio, settings.vilao_image_size)}
    try:
        with httpx.Client(timeout=timeout) as client:
            for attempt in range(3):
                if not refs:
                    r = client.post(base + "/images/generations", headers=headers, json=body)
                else:
                    field = "image" if len(refs) == 1 else "image[]"
                    files = []
                    try:
                        for p in refs:
                            mime = _MIME.get(p.suffix.lower(),
                                             mimetypes.guess_type(p.name)[0] or "image/png")
                            files.append((field, (p.name, p.read_bytes(), mime)))
                        r = client.post(base + "/images/edits", headers=headers,
                                        data={**body, "response_format": "b64_json"},
                                        files=files)
                    finally:
                        files.clear()
                    if r.status_code in (404, 405):
                        if len(refs) > 1:
                            raise MultiReferenceUnsupported(
                                "Model ảnh không hỗ trợ /images/edits với nhiều ảnh tham chiếu")
                        raise ReferenceImageUnsupported("Model ảnh không hỗ trợ /images/edits")
                    if len(refs) > 1 and r.status_code in (400, 422):
                        raise MultiReferenceUnsupported(
                            f"Gateway từ chối nhiều ảnh tham chiếu (HTTP {r.status_code}): {r.text[:200]}")
                if r.status_code not in (429, 502, 503, 504) or attempt == 2:
                    break
                time.sleep(5 * (attempt + 1))
            if r.status_code >= 400:
                raise ImageError(f"Gateway ảnh lỗi HTTP {r.status_code}: {r.text[:300]}")
            item = ((r.json().get("data") or [{}])[0]) or {}
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"], validate=True)
            elif item.get("url"):
                rr = client.get(item["url"], timeout=timeout, follow_redirects=True)
                if rr.status_code >= 400:
                    raise ImageError(f"Tải ảnh lỗi HTTP {rr.status_code}")
                raw = rr.content
            else:
                raise ImageError("Gateway ảnh không trả url/b64_json")
    except httpx.HTTPError as e:
        raise ImageError(f"Lỗi mạng khi gọi gateway ảnh: {e}") from e
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
        raise ImageError("Gateway trả dữ liệu ảnh không hợp lệ") from e
    if not raw or not _is_image(raw):
        raise ImageError("Dữ liệu trả về không phải ảnh hợp lệ")
    dest.write_bytes(raw)
    return dest
