"""Model registry: one record per AI model the user can pick for a pipeline step.

Each model declares capabilities (max clip seconds, resolution, aspect ratios, supports
first/last frame, reference image, audio, TTS, etc.) so the system adapts to whichever
model the user chose without hard-coding provider logic.

Models are now managed entirely through the admin UI (app/adminmodels.py) — built-in
catalogues for Inkstone/MiniMax/local GPU have been removed; only admin-added models
(app_models table) are available.
"""
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ModelSpec:
    id: str
    name: str
    step: str            # llm | image_generate | image_edit | video_i2v | video_t2v | tts | lipsync | music | vlm
    provider: str        # vilao | custom | external
    kind: str            # api | local_gpu
    desc: str = ""
    strengths: str = ""
    weaknesses: str = ""
    enabled: bool = True
    max_clip_seconds: int = 10
    min_clip_seconds: int = 1
    resolutions: list[str] = field(default_factory=lambda: ["768P"])
    aspect_ratios: list[str] = field(default_factory=lambda: ["9:16", "16:9", "1:1"])
    supported_durations: list[int] = field(default_factory=list)
    supports_first_frame: bool = True
    supports_last_frame: bool = False
    supports_reference_image: bool = False
    supports_audio: bool = False
    supports_voice_clone: bool = False
    supports_vietnamese: bool = True
    max_reference_images: int = 0
    price_unit: str = "call"
    default_price: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# Models an admin added through the UI (app/adminmodels.py keeps this in sync with the DB).
_DYNAMIC_MODELS: list[ModelSpec] = []


def set_dynamic_models(specs: list[ModelSpec]) -> None:
    global _DYNAMIC_MODELS
    _DYNAMIC_MODELS = list(specs)


def _all_models() -> list[ModelSpec]:
    return list(_DYNAMIC_MODELS)


def all_models() -> list[ModelSpec]:
    return list(_all_models())


STEPS = {
    "llm": "Tạo prompt/kịch bản/storyboard",
    "image_generate": "Tạo ảnh nhân vật / ảnh từng cảnh",
    "image_edit": "Sửa ảnh theo tham chiếu",
    "video_i2v": "Gen video (image-to-video)",
    "video_t2v": "Gen video (text-to-video)",
    "tts": "Giọng đọc (TTS)",
    "lipsync": "Ghép khẩu hình",
    "music": "Nhạc nền",
    "vlm": "Chấm chất lượng (VLM)",
}


def models_for_step(step: str) -> list[ModelSpec]:
    return [m for m in _all_models() if m.step == step and m.enabled]


def get_model(model_id: str) -> ModelSpec | None:
    for m in _all_models():
        if m.id == model_id:
            return m
    return None


def clip_count_for_duration(model: ModelSpec, total_seconds: int) -> int:
    if model.max_clip_seconds <= 0:
        return 1
    import math
    return math.ceil(total_seconds / model.max_clip_seconds)


def validate_selections(selections: dict, required: list[str] | None = None) -> list[str]:
    errors = []
    if required is None:
        required = ["llm", "image_generate", "video_i2v"]
    for step in required:
        mid = selections.get(step)
        if not mid:
            errors.append(f"Chưa chọn model cho bước: {STEPS.get(step, step)}")
            continue
        m = get_model(mid)
        if not m:
            errors.append(f"Model không tồn tại: {mid}")
            continue
        if m.step != step:
            errors.append(f"Model {mid} không thuộc bước {step}")
            continue
        if not m.enabled:
            errors.append(f"Model {mid} đang bị tắt")
    return errors
