# Open-Set Face Recognition — Jetson Edge Pipeline

Hệ thống nhận diện khuôn mặt **open-set** chạy real-time trên **NVIDIA Jetson (Orin Nano, JetPack 6.2.2)**.
Nhận diện được người đã đăng ký trong gallery (known identity), đồng thời giữ các khuôn mặt chưa biết (unknown) — không bị ép gắn nhãn sai.

---

## Mục lục

- [Kiến trúc](#kiến-trúc)
- [Các thành phần](#các-thành-phần)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Cài đặt & Môi trường](#cài-đặt--môi-trường)
- [Chuẩn bị Model (không commit vào Git)](#chuẩn-bị-model-không-commit-vào-git)
- [Chạy pipeline](#chạy-pipeline)
- [Cơ chế ngưỡng open-set](#cơ-chế-ngưỡng-open-set)
- [Kiểm thử](#kiểm-thử)
- [Quy tắc bảo tồn (Conservation Rules)](#quy-tắc-bảo-tồn-conservation-rules)

---

## Kiến trúc

```text
Camera (CSI/RTSP)
   │
   ▼
DeepStream pipeline (GStreamer) ─────────────► nvinfer (SCRFD det) → detection
   │
   ▼
Tracking (tracker.py) — giữ ID ổn định các khuôn mặt
   │
   ▼
Embedder (FaceEmbedder) — InsightFace w600k_r50 → vector 512D
   │
   ▼
Gallery (RAM, NumPy) — cosine search với toàn bộ embedding đã enroll
   │
   ▼
OpenSetRecognizer — quyết định KNOWN / UNKNOWN theo ngưỡng EVT/GPD
   │
   ├── KNOWN  → ghi sự kiện KNOWN vào PostgreSQL
   └── UNKNOWN → (tùy chọn) re-check lại ngưỡng, ghi sự kiện UNKNOWN
   │
   ▼
Web dashboard / Telemetry (backend)
```

Luồng xử lý chạy hoàn toàn trên Jetson. Gallery nạp vào RAM lúc khởi động
– **không có truy vấn PostgreSQL theo từng frame**.

---

## Các thành phần

| Thành phần | Chi tiết |
| :-- | :-- |
| **Detector** | DeepStream primary GIE — SCRFD (`det_10g`), engine TRT fp16 |
| **Embedding model** | InsightFace IR-SE50 `w600k_r50.onnx` (112×112), được cố định (conserved) |
| **Gallery** | PostgreSQL + RAM (NumPy matrix), cosine search |
| **Open-set** | EVT / POT / GPD thresholding theo từng identity |
| **DeepStream** | Pipeline GStreamer trên Jetson, dual camera |
| **Tracking** | Bộ tracker đa-dích, mỗi camera một engine/ID riêng |

Hạ tầng phụ trợ triển khai bằng Docker (backend + frontend + PostgreSQL + mediamtx),
nhưng **pipeline nhận diện chạy natively trên Jetson** (GPU tegra + camera CSI).

---

## Cấu trúc thư mục

```text
open-set-face-recognition/
├── services/face-ai/
│   └── app/
│       ├── pipeline/        # engine.py — vòng lặp chính DeepStream
│       ├── detection/       # detector (SCRFD)
│       ├── tracking/        # tracker.py — theo dõi khuôn mặt đa-dích
│       ├── recognition/     # embedder.py — InsightFace TRT
│       ├── gallery/         # manager.py — nạp gallery, cosine search
│       ├── openset/         # decision.py — ngưỡng EVT/GPD
│       ├── events/          # ghi sự kiện KNOWN/UNKNOWN
│       ├── config/          # settings (dataclass từ YAML)
│       ├── streaming/       # telemetry → backend
│       └── main.py          # entrypoint
├── configs/                 # YAML pipeline + DeepStream configs
├── database/migrations/     # SQL schema (setup_postgres.sh)
├── scripts/                 # setup / gallery / model / benchmark
├── thresholds/              # threshold_table.json + embeddings (fit offline)
├── models/                  # KHÔNG commit vào Git (xem dưới)
├── tests/                   # pytest
└── docs/                    # tài liệu kỹ thuật
```

---

## Cài đặt & Môi trường

- **Thiết bị:** NVIDIA Jetson **Orin Nano** (aarch64)
- **JetPack:** **6.2.2 (pinned, không nâng cấp)**
- **Yêu cầu:** DeepStream SDK, TensorRT, GStreamer, Python 3.10+

```bash
# Cài dependencies (nếu chưa có)
cd services/face-ai
pip install -r requirements.txt
```

Cấu hình qua YAML:

```bash
configs/app.yaml          # gallery, PostgreSQL, thresholds
configs/camera.yaml       # CSI/RTSP sources
configs/recognition.yaml  # engine path, recognition interval
configs/tracker.yaml      # tham số tracking
```

Database dùng **PostgreSQL** (mặc định docker `5432`, credential qua `.env`; `.env` không commit).

---

## Chuẩn bị Model (không commit vào Git)

Các model binary **bị loại khỏi Git** (`.gitignore` chặn `.engine`, `.onnx`, `.npz`, `.parquet`).
Chúng phải được đặt thủ công vào `models/` khi triển khai:

```text
models/
├── detector/det_10g_fp16_4d.engine      # SCRFD detector (DeepStream)
└── recognition/
    ├── face_recog_fp16.engine           # TRT engine embedding (runtime chính)
    ├── face_recog.engine                # bản dự phòng
    └── w600k_r50.onnx                   # nguồn ONNX (fit/offline)
```

> Lưu ý: `GALLERY_MODEL_VERSION` trong `.env` (mặc định `w600k_r50@1.0.0`)
> phải khớp version embedding trong gallery để vector so sánh đúng.

---

## Chạy pipeline

```bash
# Từ thư mục repo trên Jetson
cd ~/open-set-face-recognition

nohup python3 -m services.face-ai.app.main \
  --configs configs/app.yaml configs/camera.yaml configs/recognition.yaml \
  >> pipeline.log 2>&1 &

# Kiểm tra đã chạy (đợi ~40s cho load model)
sleep 40
pgrep -af 'services.face-ai.app.main'
tail -20 pipeline.log

# Tắt pipeline
pkill -f 'services.face-ai.app.main'
```

Dấu hiệu chạy tốt:

```text
Gallery: 36 vectors / 36 persons
KNOWN   track=25 person=Phuc (0.297 >= 0.280)
UNKNOWN track=43 sim=0.159 < thr=0.225
```

---

## Cơ chế ngưỡng open-set

Ba chế độ (cấu hình trong `configs/evt.yaml`):

| Mode | Ý nghĩa |
| :-- | :-- |
| `fixed` | Một ngưỡng cố định cho mọi khuôn mặt |
| `global_evt` | Một ngưỡng GPD/EVT chung cho toàn gallery |
| `identity_gpd` | **(Mặc định)** Ngưỡng riêng cho từng identity, top-k candidate, identity nào vượt được ngưỡng *của chính nó* thì thắng |

- Bảng ngưỡng `thresholds/threshold_table.json` được **fit offline** trên workstation
  (EVT/POT/GPD) — runtime chỉ tra cứu dict, **không fit tại runtime**.
- Nếu file JSON tồn tại, pipeline ưu tiên đọc JSON; ngược lại fallback đọc bảng
  `identity_thresholds` trong PostgreSQL.
- `min_threshold` (mặc định 0.15) là sàn ngưỡng tối thiểu để tránh nhận nhầm khi sim thấp.
- Format debug trong `pipeline.log`:
  `KNOWN person=<tên> (sim >= thr)` / `UNKNOWN sim=x < thr=y`.

---

## Kiểm thử

```bash
cd services/face-ai
pytest

# Kiểm tra cấu trúc import (không cần DeepStream)
python -m app.main --import-flag
```

---

## Quy tắc bảo tồn (Conservation Rules)

Các thành phần sau **không được thay thế** nếu không có phê duyệt:

1. **Face detector** — DeepStream primary GIE, SCRFD (`det_10g`)
2. **Embedding model** — InsightFace IR-SE50 (`w600k_r50.onnx`, 112×112)
3. **Gallery** — PostgreSQL-backed embedding gallery
4. **Pipeline** — DeepStream
5. **Thresholding** — Identity-wise EVT (POT/GPD)

Khác:

- **JetPack 6.2.2 được pinned** — không nâng cấp.
- **Rule 4 (Runtime efficiency):** gallery nạp RAM lúc khởi động, không query DB theo frame.
- **Rule 7 (Offline-fitting):** fit EVT/GPD chỉ ở workstation; runtime chỉ tra lookup từ
  `identity_thresholds` / `threshold_threshold.json`.

---

*Tài liệu pipeline nhận diện khuôn mặt open-set trên Jetson.*