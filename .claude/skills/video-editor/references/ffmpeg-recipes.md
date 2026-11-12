# FFmpeg recipes — pipeline VideoAI

Mục lục:
1. Đo clip
2. Chuẩn hóa 1 clip về desired duration (giãn chậm + đóng băng + loudnorm)
3. Nối cứng (concat demuxer)
4. Nối có chuyển cảnh (xfade + acrossfade)
5. Verify + trim final

## 1. Đo clip

```
ffprobe -v error -show_entries format=duration -of csv=p=0 clip.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 clip.mp4
ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 clip.mp4
```

## 2. Chuẩn hóa 1 clip (nguồn `video`, audio riêng `audio` có thể None)

Biến: `src_dur`, `desired`, `W`, `H` (canonical), `slow = min(desired/src_dur, 1.3)` khi `src_dur < desired`; `freeze = desired - src_dur*slow` nếu > 0.02.

Video chain:
```
scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30
```
- Nếu giãn chậm: thêm `setpts=PTS*<slow>`
- Nếu còn thiếu: thêm `tpad=stop_mode=clone:stop_duration=<freeze>`

Audio chain (bắt buộc output 44100 stereo):
```
aresample=44100,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100
```
- Nếu giãn: `<...>,atempo=<1/slow>`
- Cuối: `apad=whole_duration=<desired>`

Lệnh đầy đủ (trường hợp audio riêng):
```
ffmpeg -y -i video.mp4 -i audio.mp3 \
  -filter_complex "[0:v]scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS*SLOW,tpad=stop_mode=clone:stop_duration=FREEZE[v];[1:a]aresample=44100,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,atempo=ATEMPO,apad=whole_duration=DESIRED[a]" \
  -map "[v]" -map "[a]" -t DESIRED \
  -c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p -r 30 \
  -c:a aac -ar 44100 -ac 2 scene_i.mp4
```
Trường hợp clip không có audio: thêm input `-f lavfi -i anullsrc=r=44100:cl=stereo` và map `[2:a]` (đánh lại chỉ số input).

Lưu ý: `setpts` **không** tự đổi audio; thời lượng output vẫn bị `-t desired` chặn trên.

## 2b. Cảnh lỗi (gen video fail nhưng có ảnh keyframe) — đoạn Ken Burns từ ảnh tĩnh

Khi cảnh không có clip mà chỉ còn ảnh keyframe, KHÔNG bỏ cảnh — dựng đoạn zoom/pan từ ảnh:

```
ffmpeg -y -i kf.png -vf "scale=W*2:H*2:force_original_aspect_ratio=increase,crop=W*2:H*2,zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=<frames>:s=WxH:fps=30,setsar=1" -c:v libx264 -pix_fmt yuv420p -r 30 still.mp4
```

- `frames = want * 30`; image làm input đơn, KHÔNG `-loop 1` (loop khiến zoompan nhân khung → video 400s).
- Sau đó normalize clip như cảnh video thường (Ken Burns dur = want nên không cần giãn/đóng băng).
- Nếu cảnh mất cả ảnh lẫn video thì mới bỏ và cảnh báo trong `step`.

## 3. Nối cứng

```
printf "file 'scene_0.mp4'\nfile 'scene_1.mp4'\n" > concat.txt
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy out.mp4   # cwd = thư mục chứa clip
```
Chỉ dùng khi mọi clip đã chuẩn hóa cùng W/H/fps/pix_fmt/codec. Đo lại duration sau khi nối.

## 4. Nối có chuyển cảnh (n clip, overlap T=0.4)

`d_i` = duration clip i. Offset cho cặp k (0-based, bắt đầu từ 1):
```
off_k = (d_0 + ... + d_{k-1}) - k*T
```
Filter graph:
```
[0:v][1:v]xfade=transition=fade:duration=0.4:offset=OFF_1[v1];
[v1][2:v]xfade=transition=fade:duration=0.4:offset=OFF_2[v2]; ... [vN-1]
[0:a][1:a]acrossfade=d=0.4:c1=tri:c2=tri[a1];
[a1][2:a]acrossfade=d=0.4:c1=tri:c2=tri[a2]; ... [aN-1]
```
Lệnh:
```
ffmpeg -y -i s0.mp4 -i s1.mp4 -i s2.mp4 \
  -filter_complex "<graph trên>" \
  -map "[vN-1]" -map "[aN-1]" \
  -c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p -r 30 \
  -c:a aac -ar 44100 -ac 2 out.mp4
```
Tổng thời lượng = Σd − T×(n−1). Vì vậy khi chuẩn hóa: Σdesired = target + T×(n−1).

Điều kiện an toàn: mọi clip phải dài > 2×T; nếu không → quay về nối cứng (mục 3).

## 5. Verify + trim final

```
ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp4
```
- Thiếu: kéo dài clip cuối thêm `target-actual` bằng `tpad=stop_mode=clone:stop_duration=<delta>` rồi dựng lại toàn bộ.
- Thừa: `ffmpeg -y -i out.mp4 -t <target> -c:v libx264 -preset ultrafast -crf 23 -c:a aac -ar 44100 -ac 2 out_trim.mp4` (re-encode, không `-c copy` để cắt chính xác).
