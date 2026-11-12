---
name: video-editor
description: "Dựng/edit video final chất lượng cao cho pipeline VideoAI bằng ffmpeg: cắt ghép cảnh (clip phôi), chuyển cảnh xfade, cân bằng âm lượng loudnorm, xử lý clip ngắn/dài, kiểm tra thời lượng bằng ffprobe. Dùng khi sửa _run_editing, dựng video final, nối clip phôi, thêm transition, sửa lỗi final ngắn hơn yêu cầu (vd 20s trả về 8.5s), hoặc cần checklist chất lượng video trước khi trả về."
---

# Video Editor

IRON LAW: **Video final phải được đo bằng `ffprobe` và đạt đúng thời lượng người dùng yêu cầu (sai số ≤ 0.5s) trước khi trả về.** Không tin metadata API, không tin "pipeline chạy xong là xong".

## Workflow

```
Progress:
- [ ] 1. Đọc code edit hiện tại + xác định target (⚠️ REQUIRED)
- [ ] 2. Kiểm tra clip nguồn (video phôi)
- [ ] 3. Dựng final từ clip phôi — KHÔNG gọi API gen lại trừ khi user đồng ý
- [ ] 4. Verify final bằng ffprobe + tự edit lại nếu chưa đạt
- [ ] 5. Test không tốn API (clip giả lavfi) + pytest
- [ ] 6. Báo user: thời lượng thực, cách xử lý, chi phí phát sinh (nếu có)
```

### 1. Đọc code edit + xác định target ⚠️

- Hàm dựng video: `app/autopipeline.py::_run_editing`; clip phôi: `storage/outputs/pipe_<job>_scene_<i>.mp4` (tab "🎥 Video phôi").
- Target = `job.duration` (giây người dùng yêu cầu), tolerance 0.5s.
- Hỏi: nguồn clip có đủ mọi cảnh không? Cảnh nào lỗi (status failed) sẽ bị thiếu — báo rõ cho user.

### 2. Kiểm tra clip nguồn

Chạy: `python .claude/skills/video-editor/scripts/check_video.py <clip1> <clip2> ...`
→ JSON mỗi file: duration, width/height, fps, codec, has_audio, issues. Dùng số liệu thật để tính, không đoán.

### 3. Dựng final từ clip phôi

- Scale/pad mọi clip về cùng WxH (lấy từ clip đầu), `-r 30`, `-pix_fmt yuv420p`, audio `aresample=44100`.
- Chuẩn hóa âm lượng từng clip: `loudnorm=I=-16:TP=-1.5:LRA=11` (đều tiếng, tránh clip này to clip kia nhỏ).
- Thời lượng từng cảnh: scale thời lượng kế hoạch (`thời_lượng_giây`) để tổng khớp target. **Khi có chuyển cảnh xfade overlap T giây: tổng desired = target + T×(n−1).**
- Clip ngắn hơn desired: giãn chậm nhẹ trước (`setpts=PTS×f`, `atempo=1/f`, f ≤ 1.3), phần còn thiếu mới đóng băng khung cuối (`tpad=stop_mode=clone`). Không đóng băng > 1s/cảnh nếu còn giãn được.
- Cảnh gen video lỗi (không có clip) mà còn **ảnh keyframe**: không bỏ cảnh — dựng đoạn Ken Burns từ ảnh (`references/ffmpeg-recipes.md` mục 2b). Chỉ bỏ cảnh khi mất cả ảnh lẫn video.
- Clip dài hơn desired: cắt `-t desired`.
- Chuyển cảnh: `xfade` fade 0.3–0.5s + `acrossfade` audio, offset cộng dồn trừ overlap. Clip < 1s hoặc quá nhiều cảnh (>12) → nối cứng bằng concat demuxer.
- Công thức ffmpeg chi tiết: `references/ffmpeg-recipes.md`.

### 4. Verify + tự edit lại ⚠️ REQUIRED

```
if actual >= target - 0.5:  -> đạt
elif actual < target - 0.5: -> kéo dài clip cuối thêm (target - actual), dựng lại; lặp ≤ 3 lần
else (actual > target + 0.5): -> cắt -t target (re-encode)
```
- Ghi `final_duration` vào kết quả job; step hiển thị "Video final X.Xs (yêu cầu Ys)".
- Cập nhật `job.result` để UI/người dùng thấy số liệu thật.

### 5. Test không tốn API

- Tạo clip giả: `ffmpeg -f lavfi -i testsrc=duration=2:size=320x240:rate=30 -f lavfi -i sine=frequency=440:duration=2 -c:v libx264 -c:a aac -shortest out.mp4` (thêm `-pix_fmt yuv420p`).
- Test ít nhất: clip ngắn hơn target (kéo dài), clip dài hơn target (cắt), trộn có/không audio, khác kích thước.
- Chạy `python -m pytest tests/ -q` — không regression.
- Xoá file test trong `storage/outputs/` sau khi xong.

### 6. Báo user

Nêu: thời lượng thực đo được, thời lượng yêu cầu, cách chỉnh (giãn/đóng băng/cắt), có tốn credit hay không (mặc định KHÔNG).

## Anti-patterns — không làm

- ❌ Trả video final chỉ vì pipeline "done" mà chưa đo ffprobe.
- ❌ Gọi lại API gen video/cảnh khi user chưa đồng ý — tốn credit.
- ❌ Nối `-c copy` khi clip khác resolution/fps/pix_fmt/codec → file lỗi hoặc mất tiếng.
- ❌ Dùng `xfade` khi clip ngắn hơn ~2× thời lượng transition → lỗi filtergraph / mất cảnh.
- ❌ Đóng băng khung hình dài (>1s/cảnh) khi có thể giãn chậm nhẹ.
- ❌ Sửa code ngoài phạm vi edit (rendering/billing/UI) khi task chỉ là dựng final.
- ❌ Chỉ tăng `job.duration` hay sửa plan để "khớp" — phải khớp file thật.

## Pre-delivery checklist

- [ ] `ffprobe format=duration` của final ∈ [target − 0.5, target + 0.5]
- [ ] Final có cả stream video và audio (aac 44100, stereo)
- [ ] Độ phân giải/fps đồng nhất với clip đầu, `yuv420p`
- [ ] Cảnh lỗi (nếu có) được báo cho user, không im lặng
- [ ] `job.result["final_duration"]` được set
- [ ] pytest pass (125+), file test tạm đã xoá

## Resources

- `references/ffmpeg-recipes.md` — công thức ffmpeg chuẩn (normalize clip, xfade chain, verify, trim). Load khi viết/sửa lệnh ffmpeg.
- `scripts/check_video.py` — đo duration/resolution/fps/audio của file video, in JSON. Chạy trước và sau khi dựng.
