"""
=============================================================
SNIPPET ĐỂ THÊM VÀO SCRIPT JETSON (chạy trên Jetson Nano)
=============================================================

Hướng dẫn tích hợp:
1. Copy các biến global và hàm update_faces_cache() vào script Jetson
2. Trong vòng lặp phát hiện khuôn mặt, gọi update_faces_cache() TRƯỚC KHI vẽ khung đỏ
3. Thêm route /api/faces vào Flask app trên Jetson (cùng app đang chạy /stats)

Ví dụ tích hợp vào vòng lặp detection:
    
    # ... (code detection đã có sẵn) ...
    # Sau khi detect được face_boxes từ model YOLO:
    
    # ★ GỌI HÀM NÀY TRƯỚC KHI VẼ KHUNG ĐỎ ★
    update_faces_cache("camera_1", frame.copy(), face_boxes)
    
    # Sau đó mới vẽ khung đỏ lên frame để stream
    for (x1, y1, x2, y2) in face_boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
"""

import cv2
import base64
import time
import threading
from flask import jsonify

# ==========================================
# BIẾN GLOBAL - Thêm vào đầu script Jetson
# ==========================================
_faces_lock = threading.Lock()
_latest_faces_data = {}  # Cache khuôn mặt mới nhất, key = camera_id


def update_faces_cache(camera_id, clean_frame, face_boxes):
    """
    Cập nhật cache khuôn mặt. Gọi hàm này TRƯỚC KHI vẽ annotation lên frame.
    
    Args:
        camera_id: str - ID camera, ví dụ "camera_1"
        clean_frame: numpy array - Frame GỐC chưa vẽ khung đỏ
        face_boxes: list - Danh sách bounding box [[x1,y1,x2,y2], ...]
    """
    faces = []
    h, w = clean_frame.shape[:2]
    
    for box in face_boxes:
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        # Clamp tọa độ về trong frame
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)
        
        if x2 > x1 and y2 > y1:
            face_crop = clean_frame[y1:y2, x1:x2]
            ret, buffer = cv2.imencode('.jpg', face_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ret:
                b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
                faces.append({
                    "data": f"data:image/jpeg;base64,{b64}",
                    "box": [x1, y1, x2, y2]
                })
    
    with _faces_lock:
        _latest_faces_data[camera_id] = {
            "faces": faces,
            "count": len(faces),
            "timestamp": time.time()
        }


# ==========================================
# ROUTE API - Thêm vào Flask app trên Jetson
# ==========================================
# Thêm 2 route này vào Flask app đang chạy trên port 5001

# @app.route('/api/faces')
# @app.route('/api/faces/<camera_id>')
def api_faces(camera_id=None):
    """
    API trả về danh sách khuôn mặt đã crop từ frame sạch.
    Dashboard server sẽ gọi endpoint này khi user bấm "Chụp ảnh".
    """
    with _faces_lock:
        if camera_id:
            data = _latest_faces_data.get(camera_id)
            if data and (time.time() - data["timestamp"]) < 5.0:
                return jsonify({
                    "status": "success",
                    "faces": data["faces"],
                    "count": data["count"]
                })
            else:
                return jsonify({
                    "status": "success",
                    "faces": [],
                    "count": 0,
                    "message": "Không có dữ liệu khuôn mặt hoặc dữ liệu đã cũ"
                })
        else:
            # Trả về tất cả camera
            result = {}
            for cam_id, data in _latest_faces_data.items():
                if (time.time() - data["timestamp"]) < 5.0:
                    result[cam_id] = data
            return jsonify({"status": "success", "cameras": result})
