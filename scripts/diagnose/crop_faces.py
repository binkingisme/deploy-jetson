"""Detect and crop faces from a camera/RTSP/CSI source with the project's
SCRFD face detector (det_10g.onnx) run raw via onnxruntime + OpenCV,
not DeepStream. Lets us test whether the detector itself works on a
camera before blaming the pipeline.

Replicates the DeepStream preprocessing exactly:
    Input : 640x640 RGB, NCHW, scale (x - 127.5) / 128
    Output: score_8/16/32, bbox_8/16/32, kps_8/16/32
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

DET_INPUT = 640


def load_session(model_path: str):
    import onnxruntime as ort

    providers = []
    for p in ("CUDAExecutionProvider", "CPUExecutionProvider"):
        try:
            if p in ort.get_available_providers():
                providers.append(p)
        except Exception:
            pass
    if not providers:
        providers = ["CPUExecutionProvider"]
    sess = ort.InferenceSession(model_path, providers=providers)
    iname = sess.get_inputs()[0].name
    print(
        f"[crop_faces] session loaded: {Path(model_path).name} "
        f"providers={sess.get_providers()} input={iname}"
    )
    return sess, iname, sess.get_outputs()


def preprocess(img_bgr: np.ndarray) -> np.ndarray:
    img = cv2.resize(img_bgr, (DET_INPUT, DET_INPUT))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = (img.astype(np.float32) - 127.5) / 128.0
    img = img.transpose(2, 0, 1)[None]  # 1x3x640x640
    return img


def decode(outs, img_h: int, img_w: int, thr: float) -> list[np.ndarray]:
    def arr(i):
        a = np.asarray(outs[i], np.float32).reshape(-1)
        return a

    dets: list[np.ndarray] = []
    strides = (8, 16, 32)
    for si, st in enumerate(strides):
        fmap = DET_INPUT // st
        scores = arr(si)  # SCRFD score head is already sigmoid (0..1)
        boxes = arr(3 + si).reshape(-1, 4)
        step = fmap * fmap
        for i in range(step):
            s = float(scores[i])
            if s < thr:
                continue
            r, c = divmod(i, fmap)
            cx = (c + 0.5) * st
            cy = (r + 0.5) * st
            x1 = max(0, cx - boxes[i, 0] * st) / DET_INPUT * img_w
            y1 = max(0, cy - boxes[i, 1] * st) / DET_INPUT * img_h
            x2 = min(DET_INPUT, cx + boxes[i, 2] * st) / DET_INPUT * img_w
            y2 = min(DET_INPUT, cy + boxes[i, 3] * st) / DET_INPUT * img_h
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            dets.append(np.array([x1, y1, x2, y2, s], np.float32))
    if not dets:
        return []
    dets = np.array(dets, np.float32)
    box = dets[:, :4]
    scores = dets[:, 4]
    keep = cv2.dnn.NMSBoxes(
        box.tolist(), scores.tolist(), thr, 0.4
    )
    keep = np.asarray(keep).reshape(-1)
    return [dets[k] for k in keep]


def detect(sess, iname, img_bgr: np.ndarray, thr: float) -> list[list[int]]:
    h, w = img_bgr.shape[:2]
    blob = preprocess(img_bgr)
    outs = sess.run(None, {iname: blob})
    return [[int(x1), int(y1), int(x2), int(y2)] for x1, y1, x2, y2, _ in decode(outs, h, w, thr)]


def open_camera(source: str, width: int, height: int):
    if source.startswith("nvarguscamerasrc") or source.startswith("v4l2"):
        return cv2.VideoCapture(source, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(source)


def run_source(sess, iname, cap, label: str, out_dir: Path, frames: int, thr: float, save_frames: bool):
    face_dir = out_dir / label
    face_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / f"{label}_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    total_faces = 0
    t0 = time.time()
    for i in range(frames):
        ret, frame = cap.read()
        if not ret or frame is None:
            print(f"[crop_faces] {label}: frame {i} read failed")
            break
        if save_frames:
            cv2.imwrite(str(raw_dir / f"frame_{i:04d}.jpg"), frame)
        boxes = detect(sess, iname, frame, thr)
        total_faces += len(boxes)
        print(f"[crop_faces] {label}: frame {i:04d} detections={len(boxes)}")
        for j, (x1, y1, x2, y2) in enumerate(boxes):
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            cv2.imwrite(str(face_dir / f"frame_{i:04d}_face_{j:02d}.jpg"), crop)
    dt = time.time() - t0
    print(
        f"[crop_faces] {label}: done {frames} frames, "
        f"{total_faces} faces, {dt:.1f}s"
    )
    return total_faces


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crop faces with SCRFD via OpenCV")
    p.add_argument("--model", default="models/detector/det_10g_4d.onnx")
    p.add_argument("--out", default="crop_faces_out")
    p.add_argument("--frames", type=int, default=30)
    p.add_argument("--thr", type=float, default=0.5)
    p.add_argument("--save-frames", action="store_true")
    p.add_argument("--source", nargs="+", required=True, help="camera URI or CSI gst string or video file")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    sess, iname, _ = load_session(args.model)

    total = 0
    for si, src in enumerate(args.source):
        grain = src if len(src) < 60 else src[:57] + "..."
        print(f"[crop_faces] opening source {si}: {grain}")
        cap = open_camera(src, DET_INPUT, DET_INPUT)
        if not cap.isOpened():
            print(f"[crop_faces] ERROR: cannot open source {si}")
            return 1
        label = f"cam{si}"
        total += run_source(
            sess, iname, cap, label, out_dir, args.frames, args.thr, args.save_frames
        )
        cap.release()

    print(f"[crop_faces] TOTAL faces: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())