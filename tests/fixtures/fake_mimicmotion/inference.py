"""Stand-in for Tencent/MimicMotion inference.py: same CLI, same output naming, no GPU."""
import argparse
import re
import subprocess
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--log_file")
ap.add_argument("--inference_config", default="configs/test.yaml")
ap.add_argument("--output_dir", default="outputs/")
a = ap.parse_args()
cfg = Path(a.inference_config).read_text()
for key in ("base_model_path", "ckpt_path", "ref_video_path", "ref_image_path", "num_frames"):
    assert re.search(rf"^\s*(- )?{key}:", cfg, re.M), f"missing {key}"   # real config keys
image = re.search(r"ref_image_path:\s*(.+)", cfg).group(1).strip()
video = re.search(r"ref_video_path:\s*(.+)", cfg).group(1).strip()
assert Path(image).exists() and Path(video).exists()
if not Path(image).read_bytes().startswith((b"\x89PNG", b"\xff\xd8")):   # PIL would raise on this
    raise SystemExit("cannot identify image file " + image)
Path(a.output_dir).mkdir(parents=True, exist_ok=True)
out = f"{a.output_dir}/{Path(video).stem}_{datetime.now():%Y%m%d%H%M%S}.mp4"
subprocess.run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-loop", "1", "-t", "1", "-i", image, "-vf",
                "scale=256:256,format=yuv420p", "-c:v", "libx264", out], check=True)
