#!/usr/bin/env python
"""Đo thông số video bằng ffprobe — in JSON gọn cho từng file.

Dùng: python check_video.py <file1> [<file2> ...]
Output: JSON list, mỗi phần tử gồm duration_s, width, height, fps,
video_codec, audio_codec, has_audio, size_mb, issues[].
"""
import json
import subprocess
import sys
from pathlib import Path


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        return {"file": str(path), "error": (r.stderr or "ffprobe lỗi").strip()[:500]}
    data = json.loads(r.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    out: dict = {"file": path.name}
    try:
        out["duration_s"] = round(float(fmt.get("duration", 0)), 3)
    except (TypeError, ValueError):
        out["duration_s"] = None
    if video:
        out["width"] = video.get("width")
        out["height"] = video.get("height")
        out["video_codec"] = video.get("codec_name")
        out["pix_fmt"] = video.get("pix_fmt")
        num, _, den = (video.get("r_frame_rate") or "0/1").partition("/")
        try:
            out["fps"] = round(float(num) / float(den or 1), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            out["fps"] = None
    out["has_audio"] = audio is not None
    out["audio_codec"] = audio.get("codec_name") if audio else None
    try:
        out["size_mb"] = round(int(fmt.get("size", 0)) / 1_048_576, 2)
    except (TypeError, ValueError):
        out["size_mb"] = None

    issues = []
    if not video:
        issues.append("no_video_stream")
    if not audio:
        issues.append("no_audio_stream")
    if out.get("pix_fmt") and out["pix_fmt"] != "yuv420p":
        issues.append(f"pix_fmt={out['pix_fmt']} (should be yuv420p)")
    if out.get("fps") and abs(out["fps"] - 30) > 0.1:
        issues.append(f"fps={out['fps']} (should be 30)")
    if out.get("duration_s") is not None and out["duration_s"] < 0.5:
        issues.append("duration<0.5s")
    out["issues"] = issues
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    results = [probe(Path(p)) for p in sys.argv[1:]]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
