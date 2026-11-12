# Publish dự án lên domain — `studioai.id.vn` (máy nhà làm VPS)

Trạng thái: **đang chạy** tại <https://studioai.id.vn> (2026-11-11).

```
Internet → Cloudflare (DNS + TLS + WAF) → Tunnel (cloudflared, Task Scheduler / SYSTEM)
        → http://127.0.0.1:8001 → Docker: web (FastAPI) + redis
                                   └── dữ liệu: ./storage (SQLite + outputs) — mount từ host
```

- Không mở port nào trên router. IP nhà không bị lộ.
- HTTPS do Cloudflare cấp, miễn phí, tự renew.
- Tunnel tự lên lại khi máy khởi động (Task Scheduler `ONSTART`, quyền SYSTEM).

---

## 1. DNS: đưa domain về Cloudflare

Domain `studioai.id.vn` do iNET quản lý (panel OnePortal `inet.vn`).

1. <https://dash.cloudflare.com> → **Add a site** → gõ `studioai.id.vn` → gói **Free**.
   - Nếu hỏi setup: chọn **Full setup** (Partial/CNAME chỉ có ở Business).
   - Cloudflare Free vẫn nhận subdomain làm zone riêng — không cần domain cha trên Cloudflare.
2. Cloudflare hiện 2 nameserver (lần này: `celine.ns.cloudflare.com`, `jimmy.ns.cloudflare.com`).
3. OnePortal → **Cập nhật DNS** → thay 2 NS cũ (`laocai/sapa.vclouddns.com`) bằng 2 NS của Cloudflare → **Cập nhật DNS**.
4. Chờ lan truyền (vài phút đến vài giờ):

```powershell
nslookup -type=NS studioai.id.vn 8.8.8.8
```

Phải thấy `*.ns.cloudflare.com`. Hỏi thẳng zone cha cho chắn:

```powershell
nslookup -type=NS studioai.id.vn a.dns-servers.vn
```

> NS của `studioai.id.vn` nằm ở zone cha `id.vn` (VNNIC quản lý, NS `*.dns-servers.vn`), nên việc đổi NS do iNET gửi lên zone cha — có thộng chờ.

## 2. Chứng chỉ HTTPS

Sau khi zone **Active**, tab **SSL/TLS → Edge Certificates** sẽ hiện Universal cert ở trạng thái **Pending Validation (TXT)**.
Nguyên nhân pending: Cloudflare xác thực bằng cách gọi `http://studioai.id.vn/.well-known/pki-validation/...` — request đó đi qua tunnel về app (app trả 404) nên validation fail.

Cách sửa (mở đúng dòng Universal → copy 2 giá trị):

| Trường | Giá trị |
|---|---|
| Type | TXT |
| Name | `_acme-challenge` (Cloudflare tự nối thành `_acme-challenge.studioai.id.vn`) |
| Content | chuỗi token ở cột "Certificate validation TXT value" (2 bản ghi, cùng Name) |
| TTL / Proxy | Auto / DNS only |

Chờ 5–15 phút → trạng thái chuyển **Active**.

> **Giữ lại 2 bản ghi TXT** — Cloudflare dùng chúng để renew cert.
> Custom certificate (upload của riêng bạn) **chỉ có ở gói Business+** → không dùng được với Free.

## 3. Tunnel

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel login
```

Mở link trình duyệt → chọn account + zone → Authorize (lưu `cert.pem` vào `%USERPROFILE%\.cloudflared\`).

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel create studioai
```

Ghi `config.yml` vào `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: C:\Users\Admin\.cloudflared\<TUNNEL_UUID>.json

ingress:
  - hostname: studioai.id.vn
    service: http://127.0.0.1:8001
  - service: http_status:404
```

Tạo bản ghi DNS trỏ domain về tunnel:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns --overwrite-dns studioai studioai.id.vn
```

Chạy thử (foreground) để kiểm tra:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "C:\Users\Admin\.cloudflared\config.yml" tunnel run studioai
```

> Cờ `--config` phải đặt **trước** subcommand, không phải sau `tunnel run`.

## 4. Chạy 24/7: Task Scheduler (KHÔNG dùng Windows Service)

⚠️ `cloudflared service install` **không dùng được** với tunnel tạo bằng `tunnel create`:
service luôn chạy `cloudflared.exe` **không tham số** (`Cloudflared service arguments: [...cloudflared.exe]`),
nên nó không biết chạy tunnel nào → thoát ngay → **crash-loop** (SCM restart mỗi 20s, Event ID 7031).
`--config` truyền lúc install không được ghi vào args; `--token-file` chỉ dành cho *remotely-managed* tunnel.

Giải pháp: Task Scheduler chạy lúc boot dưới **SYSTEM** (tương đương service, không cần đăng nhập).

[deploy/run-tunnel.cmd](run-tunnel.cmd) — vòng lặp tự restart tunnel nếu chết:

```bat
:loop
"C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "C:\Users\Admin\.cloudflared\config.yml" tunnel run studioai
timeout /t 5 /nobreak >nul
goto loop
```

Tạo task (PowerShell **Run as administrator**):

```powershell
schtasks /Create /TN "VideoAI-Cloudflared" /TR "D:\...\deploy\run-tunnel.cmd" /SC ONSTART /RU SYSTEM /F
```

Chạy thử ngay:

```powershell
schtasks /Run /TN "VideoAI-Cloudflared"
```

Kiểm tra:

```powershell
schtasks /Query /TN "VideoAI-Cloudflared" /V
Get-Process cloudflared   # SessionId 0 = chạy dưới SYSTEM
```

> `schtasks` và `service install` đều bị từ chối nếu PowerShell **không elevated** — phải Run as administrator.

## 5. App trong Docker

```powershell
docker build -t dashboard-claude-wizardly-lamport-qfjxhi-web:latest .
docker compose up -d
```

> `docker compose build` bị BuildKit chặn quyền đọc Dockerfile (exit 0 nhưng **không tạo image**) → build bằng `docker build` rồi `compose up -d`.

Kiểm tra:

```powershell
docker compose ps
curl http://127.0.0.1:8001/api/health
```

**Port 8001 phải trống** — nếu server dev (`python run.py --port 8001`) đang chạy thì Docker không bind được.

## 6. Lệnh duy trì

| Việc | Lệnh |
|---|---|
| Bật lại toàn bộ (sau reboot) | [deploy/start-server.ps1](start-server.ps1) (admin) — Docker engine → containers → service → verify domain |
| Trạng thái app | `docker compose ps` |
| Log app | `docker compose logs -f --tail 100 web` |
| Deploy code mới | `docker compose up -d --build` |
| Tunnel còn sống? | `Get-Process cloudflared` (SessionId 0) · `schtasks /Query /TN "VideoAI-Cloudflared" /V` |
| Chạy tay tunnel (debug) | `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "$env:USERPROFILE\.cloudflared\config.yml" tunnel run studioai` |
| Restart tunnel | `schtasks /Run /TN "VideoAI-Cloudflared"` |

## 7. Sau khi reboot máy

| Việc | Cần làm |
|---|---|
| Tunnel | ✅ tự lên (Task Scheduler ONSTART / SYSTEM) |
| Containers | ⚠️ Docker Desktop mặc định **chỉ chạy khi bạn đăng nhập Windows** → bật Docker Desktop → Settings → General → **Start Docker Desktop when you sign in**. Muốn sống cả khi không đăng nhập: bật auto-login Windows. |
| Không ngủ | Settings → System → Power → **Sleep: Never** (tắt màn hình thì OK) |
| Windows Update | có thể reboot → downtime vài phút cho tới khi Docker Desktop lên lại |

## 8. Giới hạn cần biết

- **Cloudflare Free giới hạn upload ~100MB/request** → upload video >100MB vào tab Dịch & Phụ đề sẽ trả `413`. Tải MXH (server tự tải) và xuất video không vướng.
- **Bot protection chặn User-Agent lạ** (vd `python-httpx` bị 403) → nếu cần gọi API từ script/mobile app thì tắt Bot Fight Mode / Browser Integrity Check trong Security.
- **Job pipeline nằm trong RAM** → restart container là mất job đang chạy (file đã sinh vẫn còn trong `storage/outputs`).
- **SQLite + 1 web container** → không scale `web` lên ≥2 replica.
- `REGISTER_PER_HOUR=20` → ai cũng tự đăng ký; cân nhắc khoá đăng ký khi mở bán public.
- Sao lưu: copy thư mục `storage/` (SQLite + uploads + outputs). Chưa tự động hoá.

## 9. Phương án thay thế (nếu cần)

- **VPS Linux thật** (mục 7 của `fix_bug`): ổn định hơn, không phụ thuộc nhà/mạng, nhưng tốn tiền.
- **Port forwarding + Caddy**: mở port 80/443 trên router, Caddy tự cấp Let's Encrypt. Cần IP tĩnh/DDNS và Viettel có thể chặn inbound.
- **Remotely-managed tunnel + token**: `cloudflared service install <TOKEN>` chạy đúng như service thật (token lấy ở Zero Trust dashboard); đổi lại ingress cấu hình trên web, không sửa file local.
