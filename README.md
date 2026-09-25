# Hệ thống Giám sát Camera AI (Dashboard) - Tài liệu Dự án Chi tiết

Tài liệu này cung cấp cái nhìn toàn diện về cơ sở hạ tầng, cấu trúc thư mục, cơ chế hoạt động và các tính năng của hệ thống Dashboard Giám sát Camera AI. Mục tiêu là giúp các thành viên trong đội ngũ phát triển (đồng nghiệp, lập trình viên mới) nhanh chóng nắm bắt kiến trúc và phát triển dự án một cách đồng bộ.

---

## 1. Tổng quan & Mục đích Dự án
Hệ thống **AI Camera Dashboard** được thiết kế để làm giao diện trung tâm điều phối, giám sát và quản lý các luồng dữ liệu camera an ninh được xử lý bởi các thiết bị biên (Edge Devices) như NVIDIA Jetson Nano.

### Mục tiêu chính:
*   **Giám sát thời gian thực:** Kết nối và hiển thị đồng thời hoặc chuyển đổi linh hoạt giữa các camera giám sát (hiện tại đang bật cấu hình cho 2 camera hoạt động thực tế).
*   **Đo lường hiệu năng biên (Edge Benchmarking):** Hiển thị trực quan tải lượng CPU, RAM, nhiệt độ của thiết bị xử lý Jetson và độ trễ mạng (ping) cùng tốc độ khung hình (FPS) thực tế của từng camera.
*   **Thu thập dữ liệu khuôn mặt (Local Dataset Registration):** Cho phép đăng ký thông tin nhân sự trực tiếp từ webcam cục bộ (laptop/PC) bằng cách chụp 3 góc độ (trước mặt, nghiêng trái, nghiêng phải) để phục vụ huấn luyện mô hình AI nhận diện khuôn mặt sau này.

---

## 2. Kiến trúc Hệ thống & Cơ sở Hạ tầng (Core Infrastructure)
Dự án được xây dựng dựa trên kiến trúc **Client-Server gọn nhẹ** nhưng tối ưu hóa hiệu năng truyền phát video và xử lý đa luồng.

```mermaid
graph TD
    subgraph Client [Trình duyệt / Frontend]
        UI[Giao diện Bootstrap 5]
        JS[JavaScript Logic]
        AJ[Ajax Polling - 1s/lần]
        VS[Thẻ img - Nhận luồng MJPEG]
    end

    subgraph Server [Flask Web Server / Backend]
        App[app.py - Flask Server]
        BG_Stats_Thread[Thread giám sát Jetson ngầm]
        BG_Cam_Threads[Các Thread đọc Camera ngầm]
        Cache[latest_frames - Cache khung hình RAM]
        Mutex[stats_lock & frame_locks - Khóa đồng bộ]
    end

    subgraph Edge [Thiết bị biên - Jetson Nano / Camera IP]
        JC[Các luồng Stream UDP/TCP/RTSP]
        JA[Jetson Stats API - Port 5001]
    end

    UI -->|Yêu cầu trang/API| App
    JS -->|Gọi API đăng ký/chụp ảnh| App
    AJ -->|Lấy stats hệ thống| App
    VS -->|Kết nối luồng MJPEG| App
    
    BG_Stats_Thread -->|Ping & Fetch Stats| JA
    BG_Cam_Threads -->|Giải mã liên tục| JC
    BG_Cam_Threads -.->|Cập nhật RAM Cache| Cache
    BG_Stats_Thread -.->|Cập nhật qua khóa| Mutex
    App -.->|Đọc RAM Cache & Đồng bộ dữ liệu| Mutex
```

### 2.1. Công nghệ Sử dụng (Tech Stack)
*   **Backend:** Python 3, Flask (Framework Web gọn nhẹ), OpenCV (xử lý khung hình, mã hóa JPEG, kết nối luồng camera).
*   **Frontend:** HTML5 (Cấu trúc ngữ nghĩa), Vanilla CSS (Tùy chỉnh giao diện chuyên sâu), Bootstrap 5 (Hệ thống lưới Responsive và các thành phần UI), FontAwesome 6 (Hệ thống biểu tượng trực quan).

### 2.2. Cơ chế Truyền phát Video (MJPEG Streaming)
Hệ thống sử dụng cơ chế phản hồi nhiều phần **Multipart Response (`multipart/x-mixed-replace; boundary=frame`)** qua giao thức HTTP:
*   Thay vì truyền tải video nặng nề hoặc dùng các giao thức phức tạp như WebRTC/HLS đòi hỏi thiết lập phức tạp, server Flask liên tục đọc các khung hình từ camera qua OpenCV, mã hóa chúng thành định dạng JPEG và gửi liên tiếp về trình duyệt.
*   Trình duyệt chỉ cần một thẻ `<img>` trỏ nguồn (`src`) vào route `/video_feed/<camera_id>` là có thể tự động giải mã hiển thị luồng video thời gian thực với độ trễ cực thấp.

### 2.3. Cơ chế Đa luồng (Multithreading) & Khóa Đồng bộ (Mutex Lock)
Để tránh tình trạng nghẽn hệ thống (blocking) khi xử lý các tác vụ I/O nặng và tối ưu hóa tốc độ chuyển đổi camera, dự án triển khai đa luồng:
1.  **Luồng chính (Main Thread):** Flask phục vụ các yêu cầu HTTP từ client (tải trang, stream video từ RAM cache, nhận diện API).
2.  **Luồng giám sát Jetson ngầm (Background Stats Thread - `update_jetson_stats_loop`):** Khởi chạy độc lập dưới dạng `daemon=True`. Cứ mỗi 2 giây, luồng này sẽ thực hiện gửi gói tin ping đo độ trễ và truy vấn HTTP GET tới API đo đạc phần cứng biên của Jetson (`http://192.168.31.102:5001/stats`).
3.  **Các luồng đọc Camera ngầm (Background Camera Reader Threads - `camera_reader_loop`):** Khởi chạy song song độc lập cho từng camera (`camera_1`, `camera_2`). Các luồng này kết nối liên tục tới nguồn camera, tự động thử lại khi mất kết nối, giải mã khung hình và tính toán FPS thực tế, sau đó cập nhật khung hình mới nhất vào RAM cache.
4.  **Khóa đồng bộ (`stats_lock` & `frame_locks`):** 
    *   `stats_lock` (Mutex): Bảo vệ dữ liệu benchmark dùng chung (`camera_stats`, `jetson_system_stats`) tránh lỗi tranh chấp dữ liệu (Race Condition).
    *   `frame_locks` (Mutex cho từng camera): Đảm bảo việc ghi khung hình mới của luồng đọc ngầm và việc đọc khung hình của Flask API phục vụ client không bị xung đột, giúp quá trình chuyển đổi camera trên giao diện web diễn ra **tức thì (độ trễ ~ 0 giây)**.

---

## 3. Cấu trúc Thư mục Dự án (Project Directory Structure)

Dưới đây là sơ đồ cấu trúc chi tiết của dự án `ai_camera_dashboard`:

```text
ai_camera_dashboard/
│
├── .venv/                      # Môi trường ảo chứa các thư viện Python (được cấu hình trong .gitignore)
├── .gitignore                  # Chỉ định các tệp tin và thư mục Git bỏ qua không theo dõi
├── README.md                   # Tài liệu hướng dẫn và mô tả dự án này
├── app.py                      # Tệp tin lập trình chính của Backend (Flask + OpenCV logic)
│
├── templates/
│   └── index.html              # Giao diện chính của hệ thống Dashboard
│
└── static/                     # Chứa các tài nguyên tĩnh phục vụ giao diện
    ├── css/
    │   └── style.css           # Các tùy chỉnh CSS riêng (nhấp nháy LIVE, hiệu ứng hover nút, bố cục video)
    │
    ├── captures/               # Thư mục tự động tạo để lưu ảnh chụp nhanh từ các camera giám sát
    │   └── camera_1_*.jpg      # Các ảnh chụp nhanh định dạng JPEG đặt tên theo mốc thời gian
    │
    └── face_registrations/     # Thư mục tự động lưu tập dữ liệu khuôn mặt phục vụ AI
        └── <ten_nhan_vien>/    # Thư mục riêng biệt của từng người, chứa 3 tư thế:
            ├── front.jpg       # Ảnh chụp thẳng trước mặt
            ├── left.jpg        # Ảnh chụp nghiêng sang trái
            └── right.jpg       # Ảnh chụp nghiêng sang phải
```

---

## 4. Các Tính năng Chính & Cách Hoạt Động (Key Features)

| Tính năng | Phía Frontend (Client) | Phía Backend (Server) |
| :--- | :--- | :--- |
| **Giám sát Camera Đa kênh** | Người dùng click chọn các camera (Camera 1 - 2) ở menu trái. Giao diện thay đổi nguồn phát tức thì mà không cần kết nối lại từ đầu. | Nhận request `/video_feed/<camera_id>`, trích xuất liên tục khung hình mới nhất từ RAM cache và mã hóa JPEG truyền đi. |
| **Đo lường Benchmark Hệ thống** | Cập nhật động mỗi 1 giây thông qua cơ chế Ajax polling. Hiển thị FPS thực tế, độ trễ Ping (ms), tải CPU (%), RAM (%), nhiệt độ (°C) thông qua các thanh tiến trình trực quan. | Luồng ngầm liên tục ping và truy vấn API giám sát phần cứng của Jetson. Cung cấp API endpoint `/api/stats` trả về JSON chứa toàn bộ dữ liệu mới nhất. |
| **Chụp ảnh Giám sát (Snapshot)** | Nút "Chụp ảnh" gửi yêu cầu POST đến hệ thống. Khi chụp thành công, hiển thị thông báo tên file ảnh đã lưu. | Endpoint `/capture/<camera_id>` sử dụng mô hình YOLOv8 ONNX (`detection_fp16.onnx`) để tìm khuôn mặt trên khung hình sạch. Nếu phát hiện thấy khuôn mặt, hệ thống tự động cắt và lưu riêng biệt các vùng khuôn mặt này (`face_<cam>_<time>_<idx>.jpg`). Nếu không phát hiện khuôn mặt, hệ thống tự động lưu toàn bộ khung hình làm phương án dự phòng (`full_<cam>_<time>.jpg`). |
| **Đăng ký Khuôn mặt cục bộ** | Nhập Họ & Tên nhân viên. Sử dụng Webcam cục bộ để hướng dẫn chụp 3 góc độ. Có ảnh xem trước (Preview) ở mỗi góc chụp. Cho phép nhấn vào để phóng to kiểm tra chất lượng. | Nhận gói dữ liệu JSON từ `/api/register_face` chứa chuỗi ảnh mã hóa Base64. Giải mã Base64 thành nhị phân, tự động làm sạch tên người dùng tạo thư mục và ghi các file `front.jpg`, `left.jpg`, `right.jpg`. |

---

## 5. Chi tiết Luồng xử lý Kỹ thuật (Technical Pipelines)

### 5.1. Luồng truyền tải khung hình Video (Video Pipeline)
1.  Trình duyệt yêu cầu luồng: `<img src="/video_feed/camera_1">`.
2.  Flask kích hoạt hàm generator `generate_frames("camera_1")`.
3.  Vòng lặp liên tục:
    *   Sử dụng khóa `frame_locks["camera_1"]` để lấy bản sao khung hình mới nhất từ `latest_frames["camera_1"]`.
    *   *Lưu ý về phát hiện khuôn mặt:* `latest_frames` được luồng xử lý AI chạy ngầm (`face_detection_loop`) cập nhật liên tục với các khung chữ nhật đỏ vẽ quanh khuôn mặt kèm nhãn "face" (tần suất ~ 10 FPS để tránh lag và tiết kiệm tài nguyên CPU).
    *   Mã hóa khung hình sang dạng nén `.jpg`.
    *   Truyền tải luồng byte qua lệnh `yield` định dạng MJPEG.
    *   *Lợi ích:* Độc lập hoàn toàn giữa luồng đọc camera (30 FPS), luồng chạy AI (10 FPS) và luồng phản hồi Flask giúp chuyển đổi camera tức thời và không bao giờ bị nghẽn camera.

### 5.2. Luồng đăng ký dữ liệu khuôn mặt (Face Dataset Pipeline)
1.  Người dùng điền tên "Nguyễn Văn A" và thực hiện chụp 3 ảnh trên giao diện.
2.  Trình duyệt sử dụng API Camera HTML5 để chụp ảnh từ thiết bị nội bộ, chuyển đổi dữ liệu thành các chuỗi **DataURL chứa mã hóa Base64**.
3.  Khi nhấn **"Lưu Bộ Ảnh"**, Frontend gửi yêu cầu `POST` dạng JSON tới `/api/register_face` chứa tên và 3 chuỗi Base64 đại diện cho 3 bức ảnh.
4.  Backend thực hiện:
    *   Chặn lọc tên thư mục bằng Regex để loại bỏ ký tự đặc biệt có hại cho hệ thống tệp tin (`\/*?:"<>|`).
    *   Tự động tạo thư mục: `static/face_registrations/Nguyen_Van_A/`.
    *   Bóc tách phần đầu dữ liệu Base64 (`data:image/jpeg;base64,...`), tiến hành giải mã chuỗi còn lại bằng thư viện `base64`.
    *   Ghi trực tiếp file ảnh nhị phân ra đĩa cứng dưới các tên `front.jpg`, `left.jpg`, `right.jpg`.

---

## 6. Hướng dẫn Cài đặt & Khởi chạy Dự án (dành cho Lập trình viên)

### Bước 1: Chuẩn bị Môi trường
Di chuyển vào thư mục dự án và tạo môi trường ảo Python nhằm tránh xung đột thư viện hệ thống:
```bash
# Di chuyển vào thư mục dự án
cd ai_camera_dashboard

# Tạo môi trường ảo (Virtual Environment)
python -m venv .venv

# Kích hoạt môi trường ảo:
# Trên Windows:
.venv\Scripts\activate
# Trên macOS/Linux:
source .venv/bin/activate
```

### Bước 2: Cài đặt các Thư viện cần thiết
```bash
pip install flask opencv-python onnxruntime numpy
```

### Bước 3: Cấu hình Địa chỉ IP Thiết bị Biên / Camera
Nếu địa chỉ IP của các Camera trong mạng LAN của bạn thay đổi, hãy mở file `app.py` và cập nhật cấu hình:
```python
# app.py (Dòng 18-21)
VIDEO_SOURCES = {
    "camera_1": "udp://@<IP_MỚI_CỦA_CAM>:5005",
    "camera_2": "udp://@<IP_MỚI_CỦA_CAM>:5006"
}
```
Và cập nhật địa chỉ IP của thiết bị Jetson trong hàm đo đạc hiệu năng:
```python
# app.py (Dòng 69)
req = urllib.request.Request("http://<IP_MỚI_CỦA_JETSON>:5001/stats")
```

### Bước 4: Khởi chạy Ứng dụng
```bash
python app.py
```
Mở trình duyệt và truy cập `http://localhost:5000` để trải nghiệm giao diện.

---

## 7. Các Lưu ý Quan trọng khi Làm việc Chung (Collaboration Rules)
Nhằm giữ cho mã nguồn luôn sạch, chạy ổn định và dễ bảo trì, các lập trình viên cần tuân thủ:

1.  **Cơ chế đa luồng an toàn:** Bất kỳ thay đổi nào liên quan đến đọc/ghi các biến toàn cục được chia sẻ giữa các luồng (`latest_frames`, `camera_stats`, `jetson_system_stats`) bắt buộc phải sử dụng các khóa tương ứng (`frame_locks` hoặc `stats_lock`) để đảm bảo an toàn luồng (thread safety).
2.  **Tránh chặn luồng chính:** Không thực hiện kết nối mạng hoặc các tác vụ I/O tốn thời gian (như mở video stream mới) trực tiếp bên trong các route của Flask. Sử dụng luồng chạy ngầm để thực hiện các tác vụ này.
3.  **Tối ưu hóa dung lượng truyền tải:** Tránh thực hiện các phép biến đổi ảnh phức tạp hoặc tính toán AI nặng nề trực tiếp trên luồng truyền phát video của Flask. Mọi tác vụ suy luận AI (Inference) nên được xử lý trực tiếp tại thiết bị biên trước khi đẩy luồng video về Dashboard.
4.  **Bảo mật dữ liệu đăng ký:** Ảnh đăng ký khuôn mặt chứa thông tin nhạy cảm của người dùng. Các thư mục ảnh được lưu trữ trong `static/face_registrations` cần được phân quyền đọc/ghi phù hợp trên môi trường production thực tế.

---
*Tài liệu được cập nhật và duy trì bởi Đội ngũ Phát triển Hệ thống Camera AI.*
