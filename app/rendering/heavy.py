"""Heavy render: MimicMotion (https://github.com/Tencent/MimicMotion) motion transfer.

Clone it with scripts/setup_mimicmotion.sh. We drive its inference.py through a
generated YAML config, as documented in the MimicMotion README.
"""
import subprocess
import tempfile
from pathlib import Path

from ..config import settings
<<<<<<< HEAD
from ..media import resolve, url_for, owner_dir_for_generation
=======
from ..media import resolve, url_for
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
from .fast import RenderError


def render(gen_id: int, base_video_url: str, values: dict) -> str:
    root = settings.mimicmotion_dir
    if not (root / "inference.py").exists():
        raise RenderError(f"Chưa cài MimicMotion tại {root}. Chạy scripts/setup_mimicmotion.sh")
    image = resolve(values.get("character_image", ""))
    video = resolve(base_video_url)
    if not image:
        raise RenderError("Thiếu ảnh nhân vật (character_image)")
    if not video:
        raise RenderError("Template không có video mẫu để sao chép chuyển động")

<<<<<<< HEAD
    out_root = owner_dir_for_generation(gen_id)
    out_dir = Path(tempfile.mkdtemp(prefix=f"mm_{gen_id}_", dir=out_root))
=======
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(tempfile.mkdtemp(prefix=f"mm_{gen_id}_", dir=settings.outputs_dir))
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    cfg = out_dir / "config.yaml"
    cfg.write_text(
        f"base_model_path: {settings.mimicmotion_base_model}\n"
        f"ckpt_path: {settings.mimicmotion_ckpt}\n"
        "test_case:\n"
        f"  - ref_video_path: {video}\n"
        f"    ref_image_path: {image}\n"
        f"    num_frames: {settings.mimicmotion_num_frames}\n    resolution: 576\n    frames_overlap: 6\n"
        "    num_inference_steps: 25\n    noise_aug_strength: 0\n    guidance_scale: 2.0\n"
        "    sample_stride: 2\n    fps: 15\n    seed: 42\n",
        encoding="utf-8")
    proc = subprocess.run(
        [settings.mimicmotion_python, "inference.py", "--inference_config", str(cfg),
         "--output_dir", str(out_dir)],
        cwd=root, capture_output=True, text=True, timeout=60 * 60)
    results = sorted(out_dir.glob("*.mp4"))
    if proc.returncode != 0 or not results:
        raise RenderError(f"MimicMotion lỗi: {(proc.stderr or proc.stdout)[-800:]}")
<<<<<<< HEAD
    final = out_root / f"gen_{gen_id}.mp4"
=======
    final = settings.outputs_dir / f"gen_{gen_id}.mp4"
>>>>>>> 822cff7506133e411f5ff03e99930c611a7a19fa
    results[0].replace(final)
    return url_for(final)
