#!/usr/bin/env bash
# Clone MimicMotion and print the remaining manual steps (weights are several GB).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor
[ -d vendor/MimicMotion ] || git clone https://github.com/Tencent/MimicMotion vendor/MimicMotion
cat <<'MSG'
Next, inside vendor/MimicMotion (needs an NVIDIA GPU, ~16GB VRAM):
  1. pip install -r requirements.txt  (use a dedicated venv and set MIMICMOTION_PYTHON to it)
  2. Download weights per the MimicMotion README:
       models/DWPose/{yolox_l.onnx,dw-ll_ucoco_384.onnx}
       models/MimicMotion_1-1.pth
       (SVD base model is downloaded from HuggingFace automatically on first run;
        or set MIMICMOTION_BASE_MODEL to a local path)
Then start the worker:  celery -A app.tasks.celery_app worker -c 1 -Q celery --loglevel=info
MSG
