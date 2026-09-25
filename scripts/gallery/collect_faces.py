"""Automatically collect/capture face crops from a camera source.

Runs detection (when available) or captures raw frames to folder, for later
manual enrollment or automated gallery building.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect faces from camera")
    p.add_argument("--source", default="0", help="CSI index or RTSP URI")
    p.add_argument("--output-dir", default="collected_faces")
    p.add_argument("--count", type=int, default=50, help="frames to save")
    p.add_argument("--every", type=int, default=5, help="save every N frames")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.source, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"[collect_faces] ERROR: cannot open source: {args.source}")
        return 1

    saved = 0
    frame_idx = 0
    while saved < args.count:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % args.every == 0:
            path = outdir / f"face_{frame_idx:06d}.jpg"
            cv2.imwrite(str(path), frame)
            saved += 1
            print(f"[collect_faces] saved {path}")
        frame_idx += 1
        time.sleep(0.03)

    cap.release()
    print(f"[collect_faces] done: {saved} frames -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
