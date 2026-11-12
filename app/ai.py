"""Thin OpenAI-compatible client used by the pipeline's LLM step.

Models are managed by an admin through the UI (app/adminmodels.py); this module just
provides the generic chat() helper that works with any OpenAI-compatible gateway
(vilao.ai, OpenAI, ...). Old Inkstone/MiniMax built-in models have been removed.
"""
import httpx

from .config import settings


class AIError(RuntimeError):
    pass


FAST, HEAVY = "fast_remotion", "heavy_mimicmotion"
AI_VIDEO, AI_DANCE = "ai_video", "ai_dance"


def chat(model: str, messages: list[dict], *, json_mode: bool = False,
         tools: list[dict] | None = None, timeout: float | None = None,
         base_url: str | None = None, api_key: str | None = None) -> dict:
    """OpenAI-compatible chat. base_url/api_key default to the vilao settings."""
    # An admin-added model with a custom base_url must carry its own key — never
    # fall back to the global VILAO key (would leak it to a foreign gateway).
    if base_url and not api_key:
        raise AIError("Model chưa có API key riêng; vui lòng nhập API key trong Quản lý Model")
    base = (base_url or settings.vilao_base_url).rstrip("/")
    key = api_key or settings.vilao_api_key
    if not base or not key:
        raise AIError("Chưa cấu hình base_url / api_key cho model này")
    if timeout is None:
        timeout = 300
    body: dict = {"model": model, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
    try:
        r = httpx.post(f"{base}/chat/completions", json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]
    except httpx.HTTPError as e:
        raise AIError(f"Lỗi gọi API model {model}: {e}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise AIError(f"Lỗi gọi API model {model}: {e}") from e


def _text(model: str, system: str, user: str) -> str:
    return chat(model, [{"role": "system", "content": system},
                        {"role": "user", "content": user}]).get("content") or ""


DANCE_RULES = "full body visible from head to toe, plain simple background, static camera."


def optimize_video_prompt(idea: str, *, dance: bool = False, allow_llm: bool = True) -> str:
    """Turn a short idea into a prompt a video model handles well."""
    idea = idea.strip()
    text = idea
    if configured() and allow_llm:
        try:
            text = _text("vilao-script", "You write prompts for a text-to-video model. Rewrite the user's idea "
                         "(any language) as ONE concise English paragraph: subject, action, setting, lighting, "
                         "camera. No lists, no preamble." + (" The clip is a dance reference: one performer, the "
                         "dance style described precisely." if dance else ""), idea).strip() or idea
        except AIError:
            text = idea
    return (f"{text} {DANCE_RULES}" if dance else text)[:2000]


def configured() -> bool:
    return bool(settings.vilao_api_key and settings.vilao_base_url)


def decide_render_type_ex(category: str, template_schema: dict,
                          input_data: dict, use_model: bool = True) -> tuple[str, bool]:
    """Heuristic render-type router (no LLM call). Returns (render_type, model_was_called)."""
    motion = bool((template_schema or {}).get("motion_transfer"))
    wants_motion = motion or bool(input_data.get("character_image"))
    return HEAVY if (wants_motion and input_data.get("character_image")) else FAST, False
