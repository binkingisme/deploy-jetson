# DEPLOY JETSON — Face Recognition trên Jetson Orin Nano (Phase 0-5)

Hướng dẫn deploy hệ thống open-set face recognition (deepstream pipeline)
lên **Jetson Orin Nano + JetPack 6.2.2**.

> ⚠️ **Bắt buộc:** TensorRT engine phải được build **trên chính Jetson**.
> Không thể build `.engine` trên Windows rồi copy qua. Script dưới đây chạy
> ngay trên Jetson.

---

## 1. Chuẩn bị trước

### 1.1 Trên PC (Windows)
```powershell
# Copy toàn bộ project sang USB hoặc scp đến Jetson
# Ví dụ scp từ PowerShell (nếu có OpenSSH):
scp -r "C:\Users\M S I\Desktop\dt-jetson\open-set-face-recognition" jetson@<JETSON_IP>:/home/jetson/
```

Hoặc dùng ổ USB copy thư mục `open-set-face-recognition` sang Jetson.

### 1.2 Trên Jetson
```bash
# Chuyển vào thư mục project
cd ~/open-set-face-recognition

# Xác minh environment (Phase 0)
bash scripts/setup/environment_report.sh
```

✅ **Kiểm tra output:** đảm bảo peak:
- JetPack 6.2.2 (không nâng cấp)
- DeepStream 6.4+
- TensorRT ≥ 8.6
- CUDA 12.x

---

## 2. Cài đặt dependencies

```bash
# System + Python deps (script trên Jetson)
bash scripts/setup/install_deps.sh

# Xác nhận pyarrow để đọc parquet
python3 -c "import pyarrow; print('pyarrow OK')"
```

---

## 3. Build TensorRT engines (Quan trọng nhất)

```bash
# Chạy NGAY TRÊN JETSON — convert ONNX -> engine
bash scripts/model/build_engines.sh
```

Output mong đợi:
```
models/detector/detector_fp16.engine        (từ yolov12n_face.onnx)
models/recognition/face_recog_fp16.engine   (từ w600k_r50.onnx)
```

> **Thời gian build:** mỗi engine ~1-3 phút (fp16).
> Nếu không muốn fp16, mở `build_engines.sh` và bỏ cờ `--fp16`.

### Verify engine
```bash
# Kiểm tra engine đọc được
trtexec --loadEngine=models/detector/detector_fp16.engine \
  --shapes=images:1x3x640x640 \
  --verbose 2>&1 | tail -20
```

---

## 4. Cài đặt PostgreSQL + tạo schema

```bash
# Cài Postgres + tạo user/db + chạy migrations (Phase 0/5)
bash scripts/setup/setup_postgres.sh
```

### Biến môi trường cần thiết
```bash
export POSTGRES_HOST=localhost
export POSTGRES_USER=open_set_fr
export POSTGRES_PASSWORD=your_password
export POSTGRES_DB=open_set_fr
```

---

## 5. Import gallery (parquet → PostgreSQL)

```bash
# Copy parquet nếu chưa có trong project (đang ở jetson_deploy_v2)
cp /path/to/jetson_deploy_v2/known_embeddings.parquet ./jetson_deploy_v2/

# Import embedding gallery
python3 scripts/gallery/build_gallery.py \
  --input jetson_deploy_v2/known_embeddings.parquet

# (Có thể pass tên cho label số, ví dụ)
python3 scripts/gallery/build_gallery.py \
  --input jetson_deploy_v2/known_embeddings.parquet \
  --names '{"3137841":"An"}'
```

### Import threshold table (kết quả EVT/GPD offline)
```bash
# Copy threshold table về đúng vị trí runtime sẽ load
cp /path/to/jetson_deploy_v2/threshold_table.json ./thresholds/threshold_table.json
```

### Verify gallery
```bash
python3 scripts/gallery/validate_gallery.py \
  --parquet jetson_deploy_v2/known_embeddings.parquet
```

---

## 6. Cấu hình camera

Sửa `configs/camera.yaml`:
```yaml
camera:
  source_type: "csi"     # csi hoặc rtsp
  sensor_id: 0
  width: 1920
  height: 1080
  fps: 30
```
Hoặc RTSP:
```yaml
camera:
  source_type: "rtsp"
  uri: "rtsp://user:pass@ip:554/stream"
```

Test nhanh camera:
```bash
python3 scripts/setup/camera_test.py --source 0 --frames 100
```

---

## 7. Chạy pipeline

```bash
# Import-only check (xác minh toàn bộ module load được)
cd services/face-ai
python3 -m app.main --import-flag

# Test unit (verify logic không lỗi)
python3 -m pytest tests -q

# Chạy pipeline chính (DeepStream runtime — Phase 1-3)
# Lưu ý: hiện engine.py mới dựng skeleton; phần DeepStream loop
# sẽ được lắp trong bước tích hợp tiếp theo (xem "Ghi chú" bên dưới).
cd ../..
python3 -m services.face-ai.app.main
```

---

## 8. Benchmark (tùy chọn)

```bash
# Đo latency search 53k embeddings trong RAM
python3 scripts/benchmark/benchmark_gallery.py --vectors 53149
```

---

## 9. Checklist hoàn tất

- [ ] `environment-report.txt` chạy OK, đúng JetPack 6.2.2 / DeepStream
- [ ] ONNX → engine build xong (detector + recognition) trên Jetson
- [ ] PostgreSQL có schema `persons`, `face_embeddings`, ... 
- [ ] parquet đã import: đủ 36 embeddings / 36 labels (hoặc số thực của bạn)
- [ ] threshold_table.json đặt tại `thresholds/threshold_table.json`
- [ ] camera test ≥ 25 FPS
- [ ] Unit tests pass

---

## Ghi chú triển khai tiếp theo

Trạng thái hiện tại là **skeleton** (theo kế hoạch Phase 0-5 đã duyệt):
- `app/pipeline/engine.py` có wiring components nhưng **chưa lắp GStreamer
  loop DeepStream thực tế** (primary GIE → tracker → secondary GIE → OSD).
- `app/recognition/embedder.py` đã có preprocessing InsightFace đúng
  (112×112, (x-127.5)/128, L2) — sẵn sàng dùng cho ONNX Runtime.
- Engine DeepStream dùng trong `configs/deepstream/*.txt` tham chiếu
  `detector_fp16.engine` + `face_recog_fp16.engine` — đúng file build mục 3.

Khi bạn sẵn sàng lắp pipeline DeepStream thực tế (camera → OSD → events),
tôi sẽ implement phần **engine.py** hoàn chỉnh theo kiến trúc
`run_inference.py` cũ + state machine tracking + threshold decision.