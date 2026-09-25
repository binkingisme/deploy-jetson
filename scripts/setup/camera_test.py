"""Quick camera sanity test (Phase 1).

Captures N frames from a CSI or RTSP source using OpenCV and reports FPS.
Verifies the camera source works before the DeepStream pipeline is built.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Camera sanity test")
    p.add_argument("--source", default="0", help="CSI index (int) or RTSP URI")
    p.add_argument("--frames", type=int, default=100)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--display", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    cap = cv2.VideoCapture(args.source, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"[camera_test] ERROR: cannot open source: {args.source}")
        return 1

    ok_count = 0
    start = time.perf_counter()
    for _ in range(args.frames):
        ret, frame = cap.read()
        if not ret:
            continue
        ok_count += 1
        if args.display:
            cv2.imshow("camera_test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    elapsed = time.perf_counter() - start
    cap.release()
    cv2.destroyAllWindows()

    fps = ok_count / elapsed if elapsed > 0 else 0.0
    print(f"[camera_test] captured {ok_count}/{args.frames} frames in {elapsed:.2f}s")
    print(f"[camera_test] FPS: {fps:.2f}")

    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
