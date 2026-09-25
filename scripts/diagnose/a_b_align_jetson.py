#!/usr/bin/env python3
"""Align A/B test on Jetson (read-only, repo-scoped).

Self-contained SCRFD decode (det_10g_4d) returning bboxes + kps, then for
each face compare gallery cosine via two embeddings of the SAME w600k model:
  RAW    = straight resize 112 (current runtime preprocess)
  ALIGN  = arcface 5-point warp (insightface norm_crop)
Measure which path lifts similarity to the PG gallery.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "services" / "face-ai"))

import numpy as np
import cv2
import onnxruntime as ort

from app.config.settings import GalleryConfig, PostgresConfig, load_settings
from app.gallery.manager import GalleryManager

ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

DET_INPUT = 640
STRIDES = [8, 16, 32]
NUM_ANCHORS = 2
SCORE_KEEP = 0.3
NMS_TH = 0.4


def distance2bbox(points, distance):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance2kps(points, distance):
    preds = []
    for i in range(0, distance.shape[1], 2):
        preds.append(points[:, 0] + distance[:, i])
        preds.append(points[:, 1] + distance[:, i + 1])
    return np.stack(preds, axis=-1)


def nms(boxes, scores, th=0.4):
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[np.where(ovr <= th)[0]]
    return np.array(keep, dtype=int)


def detect(sess, iname, img):
    h, w = img.shape[:2]
    blob = cv2.dnn.blobFromImage(img, 1.0 / 128.0, (DET_INPUT, DET_INPUT),
                                 (127.5, 127.5, 127.5), swapRB=True)
    outs = sess.run(None, {iname: blob})  # squash: [score x3, bbox x3, kps x3]

    scores_all, bboxes, kps_all = [], [], []
    for i, stride in enumerate(STRIDES):
        n_cells = (DET_INPUT // stride) ** 2
        n_anch = n_cells * NUM_ANCHORS
        score = outs[i][0].reshape(-1)
        bb = outs[i + 3][0].reshape(n_anch, 4)
        kp = outs[i + 6][0].reshape(n_anch, 10)

        h_cells = DET_INPUT // stride
        w_cells = DET_INPUT // stride
        anchor = np.mgrid[:h_cells, :w_cells][::-1]  # -> [xs, ys] each (h,w)
        anchor = np.stack(anchor, axis=-1).reshape(-1, 2).astype(np.float32) * stride  # y-major, like insightface
        if NUM_ANCHORS > 1:
            anchor = np.repeat(anchor, NUM_ANCHORS, axis=0)  # per-cell, per-anchor

        bb2 = bb * stride
        boxes = distance2bbox(anchor, bb2)
        kp2 = kp * stride
        kps = distance2kps(anchor, kp2)  # (n, 10)

        keep = np.where(score >= SCORE_KEEP)[0]
        if keep.size == 0:
            continue
        scores_all.append(score[keep])
        bboxes.append(boxes[keep])
        kps_all.append(kps[keep])

    if not scores_all:
        return [], [], []

    boxes = np.concatenate(bboxes)
    scores = np.concatenate(scores_all)
    kps = np.concatenate(kps_all)

    ##### 640 -> original coords (deepstream / _4d squash path) #####
    w, h = img.shape[1], img.shape[0]
    x_scale, y_scale = w / DET_INPUT, h / DET_INPUT

    boxes[:, [0, 2]] *= x_scale
    boxes[:, [1, 3]] *= y_scale
    kps = kps * np.array([x_scale, y_scale] * 5, dtype=np.float32)

    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h)

    keep = nms(boxes, scores, NMS_TH)
    return boxes[keep], scores[keep], kps[keep]


def embed(sess, iname, bgr112):
    rgb = cv2.cvtColor(bgr112, cv2.COLOR_BGR2RGB).astype(np.float32)
    x = (rgb - np.float32(127.5)) / np.float32(128.0)
    x = np.expand_dims(np.transpose(x, (2, 0, 1)), 0).astype(np.float32)
    e = sess.run(None, {iname: x})[0].flatten()
    n = np.linalg.norm(e)
    return e / n if n > 0 else e


def main() -> int:
    gal_lines = [
        ROOT / "gallery_dump_current.txt",
        ROOT / "raw_csi" / "gallery36.txt",
    ]
    gal_lookup = {}
    src = None
    for g in gal_lines:
        if g.exists():
            src = g
            for line in g.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split("|")
                if len(parts) < 5:
                    continue
                name = parts[0]
                vec = np.frombuffer(bytes.fromhex(parts[4]), dtype=np.float32)
                n = np.linalg.norm(vec)
                gal_lookup[name] = vec / n if n > 0 else vec
            break
    if not gal_lookup:
        print("[gallery] no gallery_dump_current.txt / gallery36.txt found in repo")
        return 2
    gal = np.stack(list(gal_lookup.values()))
    names = list(gal_lookup.keys())
    print(f"[gallery] vectors={gal.shape[0]} from {src.name}")

    det_sess = ort.InferenceSession(
        "models/detector/det_10g_4d.onnx", providers=["CPUExecutionProvider"]
    )
    det_iname = det_sess.get_inputs()[0].name
    emb_sess = ort.InferenceSession(
        "models/recognition/w600k_r50.onnx", providers=["CPUExecutionProvider"]
    )
    emb_iname = emb_sess.get_inputs()[0].name

    frames = []
    for cand in [
        "debug/face_dbg_raw.jpg",
        "scripts/diagnose/frame_030.jpg",
        "static/captures/20260604_120121.jpg",
    ]:
        if Path(cand).exists():
            frames.append(cand)
    if not frames:
        print("[frames] none in repo; nothing to test")
        return 0

    for fp in frames:
        img = cv2.imread(fp)
        if img is None:
            print(f"[skip] cannot read {fp}")
            continue
        print(f"\n== {fp} shape={img.shape} ==")
        boxes, scores, kps = detect(det_sess, det_iname, img)
        print(f"[detect] nfaces={len(boxes)}")
        for di in range(min(len(boxes), 4)):
            x1, y1, x2, y2 = (int(v) for v in boxes[di])
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(img.shape[1], x2), min(img.shape[0], y2)
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            k5 = kps[di].reshape(5, 2).astype(np.float32)

            raw112 = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_AREA)
            e_raw = embed(emb_sess, emb_iname, raw112)
            cubic112 = cv2.resize(crop, (112, 112), interpolation=cv2.INTER_CUBIC)
            e_cubic = embed(emb_sess, emb_iname, cubic112)

            M, inl = cv2.estimateAffinePartial2D(k5, ARCFACE_DST)
            e_align = None
            e_align_ok = False
            if M is not None and inl.sum() >= 2:
                align112 = cv2.warpAffine(img, M, (112, 112), borderValue=0.0)
                e_align = embed(emb_sess, emb_iname, align112)
                e_align_ok = True

            def show(tag, e):
                sims = gal @ e
                order = np.argsort(sims)[::-1][:3]
                print(f"   face{di} {tag}:")
                for j in order:
                    print(f"      {names[j]:12s} sim={sims[j]:.4f}")

            raw_f = e_raw.astype(np.float32)
            print(f"   face{di}: box=({x1},{y1},{x2},{y2}) score={scores[di]:.3f} "
                  f"crop={crop.shape[1]}x{crop.shape[0]} kps_inliers={int(inl.sum()) if M is not None else -1}")
            show("RAW", raw_f)
            show("CUBIC", e_cubic)
            if e_align_ok:
                show("ALIGN", e_align)
                self_sim = float(np.clip(float(raw_f @ e_align), -1.0, 1.0))
                print(f"      [self RAW.vs.ALIGN sim={self_sim:.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())