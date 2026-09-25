"""Capture raw frames from a camera (RTSP URI, CSI/GStreamer string, or webcam index).

Shows a live preview; press 's' (or wait --interval) to save full frames to disk.
Pass a number of frames to auto-capture and exit (no GUI), e.g. --auto 10 --interval 2.

Examples:
  # RTSP (runs on PC or Jetson)
  python3 capture_frames.py --source "rtsp://admin:Nckh%402025@10.39.4.64:554/stream" --out raw_rtsp --auto 10 --interval 1

  # CSI on Jetson (stop the face-ai pipeline first so the sensor is free)
  python3 capture_frames.py --
    source "nvarguscamerasrc sensor-id=0 ... ! video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1 ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink" --out raw_csi --auto 10 --interval 1
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2


def open_capture(source: str):
    if source.startswith(("nvarguscamerasrc", "v4l2")):
        return cv2.VideoCapture(source, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(source)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture raw frames from a camera")
    p.add_argument("--source", required=True, help="RTSP URI / CSI gst string / index")
    p.add_argument("--out", default="captured_frames")
    p.add_argument("--auto", type=int, default=0, help="number of frames to save then exit (0 = interactive)")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between saves")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    cap = open_capture(args.source)
    if not cap.isOpened():
        print(f"[capture_frames] ERROR: cannot open source: {args.source}")
        return 1

    saved = 0
    last_save = 0.0
    import time as _t

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("[capture_frames] frame read failed")
            break

        now = _t.time()
        if args.auto > 0:
            if saved >= args.auto:
                break
            if now - last_save >= args.interval:
                path = outdir / f"frame_{saved:03d}.jpg"
                cv2.imwrite(str(path), frame)
                saved += 1
                last_save = now
                print(f"[capture_frames] saved {path}")
        else:
            cv2.imshow("capture_frames - press 's' to save, ESC to quit", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if key == ord("s") and now - last_save >= 0.5:
                path = outdir / f"manual_{saved:03d}.jpg"
                cv2.imwrite(str(path), frame)
                saved += 1
                last_save = now
                print(f"[capture_frames] saved {path}")
        time.sleep(0.02)

    cap.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    print(f"[capture_frames] done: {saved} frames -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())