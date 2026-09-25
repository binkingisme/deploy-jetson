"""CSI 1080p capability test (IMX219 sensor-mode=1).

Probes the nvarguscamerasrc at the requested resolution and reports the
actual captured frame size and FPS. Tests a single mode, e.g. sensor-mode=1
for 1920x1080@30.
"""
from __future__ import annotations

import argparse
import sys
import time

import cv2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--sensor-id", type=int, default=0)
    p.add_argument("--mode", type=int, default=1, help="IMX219 sensor mode")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--frames", type=int, default=90)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    pipeline = (
        f"nvarguscamerasrc sensor-id={args.sensor_id} "
        f"sensor-mode={args.mode} ! "
        f"video/x-raw(memory:NVMM), width={args.width}, height={args.height}, "
        f"framerate={args.fps}/1 ! "
        f"nvvidconv ! video/x-raw, format=BGRx ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink"
    )
    print(f"[csi1080p] pipeline: {pipeline}")

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print("[csi1080p] ERROR: cannot open CSI pipeline")
        return 1

    # First frame carries the real negotiated size.
    ret, frame = cap.read()
    if not ret or frame is None:
        print("[csi1080p] ERROR: no frame captured")
        return 1

    w, h = frame.shape[1], frame.shape[0]
    print(f"[csi1080p] captured size: {w}x{h}")

    ok = 1
    start = time.perf_counter()
    for _ in range(args.frames - 1):
        ret, f = cap.read()
        if not ret or f is None:
            continue
        ok += 1
    elapsed = time.perf_counter() - start

    fps = ok / elapsed if elapsed > 0 else 0.0
    cap.release()

    target = (args.width, args.height)
    actual = (w, h)
    status = "MATCH" if actual == target else "MISMATCH"
    print(f"[csi1080p] frames={ok}/{args.frames} elapsed={elapsed:.2f}s fps={fps:.2f}")
    print(f"[csi1080p] requested {target} -> actual {actual} : {status}")
    print(f"[csi1080p] RESULT={status} RESOLUTION={w}x{h} FPS={fps:.2f}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())