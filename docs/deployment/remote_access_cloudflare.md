# Hướng dẫn Thiết lập Cloudflare Tunnel Truy Cập Từ Xa cho Jetson
**Theo đặc tả Spec v3 §FR-013 (Remote Access)**

Tài liệu này hướng dẫn cách kết nối và truy cập giao diện giám sát Web Dashboard trên **NVIDIA Jetson Orin Nano** từ bất kỳ đâu (ở nhà, quán cà phê, mạng 4G) mà **không cần mở cổng modem (Port Forwarding)** và **không cần IP tĩnh**.

---

## 1. Cài đặt `cloudflared` trên NVIDIA Jetson

Trên terminal của Jetson Orin Nano (kiến trúc ARM64):

```bash
# Tải bản cloudflared cho ARM64
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb

# Cài đặt
sudo dpkg -i cloudflared.deb
rm cloudflared.deb

# Kiểm tra phiên bản
cloudflared --version
```

---

## 2. Cách 1: Bật Tunnel Tạm Thời Nhanh (Dùng Thử trong 10 Giây)
*Không cần tạo tài khoản, không cần mua tên miền.*

Chỉ cần chạy lệnh sau trên Jetson:

```bash
cloudflared tunnel --url http://localhost:3000
```

Terminal sẽ in ra một đường link dạng:
```text
https://xxxx-xxxx-xxxx.trycloudflare.com
```
👉 Bạn mở điện thoại hoặc laptop ở nhà, dán link đó vào trình duyệt là có thể vào ngay Web Dashboard với kết nối bảo mật HTTPS!

---

## 3. Cách 2: Thiết lập Tunnel Cố Định Với Tên Miền Riêng (Khuyên Dùng cho Đồ Án)

### Bước 1: Đăng nhập Cloudflare
```bash
cloudflared tunnel login
```
Trình duyệt sẽ mở ra hoặc cung cấp link để bạn đăng nhập tài khoản Cloudflare miễn phí và chọn tên miền của bạn.

### Bước 2: Tạo Tunnel
```bash
cloudflared tunnel create jetson-camera
```
Lệnh này sẽ sinh ra một `Tunnel ID` (ví dụ: `a1b2c3d4-xxxx-...`) và file chứng chỉ lưu tại `~/.cloudflared/`.

### Bước 3: Cấu hình Tunnel (`~/.cloudflared/config.yml`)
Tạo file cấu hình:
```yaml
tunnel: a1b2c3d4-xxxx-... (ID tunnel vừa tạo)
credentials-file: /home/jetson/.cloudflared/a1b2c3d4-xxxx-....json

ingress:
  - hostname: camera.yourdomain.com
    service: http://localhost:3000
  - service: http_status:404
```

### Bước 4: Định tuyến DNS
```bash
cloudflared tunnel route dns jetson-camera camera.yourdomain.com
```

### Bước 5: Cài đặt chạy ngầm như một System Service
```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

Bây giờ, mỗi khi Jetson bật nguồn và có mạng, tunnel sẽ tự động chạy ngầm. Bạn chỉ cần truy cập `https://camera.yourdomain.com` từ bất kỳ đâu trên thế giới.

---

## 4. Kiểm tra hoạt động
1. **Giao diện Dashboard**: Tải đầy đủ qua HTTPS.
2. **REST API**: Các cuộc gọi `/api/...` được Nginx tự động chuyển hướng nội bộ tới Backend container.
3. **WebSocket**: Tự động nâng cấp sang `wss://` an toàn, cập nhật khung nhận diện và telemetry theo thời gian thực.