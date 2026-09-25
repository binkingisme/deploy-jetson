"""Export / convert model assets — RUN ON THE JETSON (Phase 0/2/4).

Converts ONNX detection/recognition models to TensorRT engines using trtexec.
Engines are device-specific and MUST be built on the target Jetson.

Equivalent shell workflow:
    bash scripts/model/build_engines.sh
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def trtexec_convert(
    onnx_path: Path,
    engine_path: Path,
    input_name: str,
    input_shape: str,
    fp16: bool = True,
) -> int:
    """Convert ONNX to TensorRT engine using trtexec (run on Jetson)."""
    if not onnx_path.exists():
        print(f"[export] ERROR: ONNX not found: {onnx_path}")
        return 1

    shapes = f"--{input_name}={input_shape}"
    cmd = [
        "trtexec",
        f"--onnx={onnx_path}",
        f"--saveEngine={engine_path}",
        f"--minShapes={shapes}",
        f"--optShapes={shapes}",
        f"--maxShapes={shapes}",
        "--workspace=1024",
    ]
    if fp16:
        cmd.append("--fp16")

    print(f"[export] running:\n    {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build TensorRT engines on the Jetson")
    ap.add_argument("--fp16", action="store_true", default=True, help="build FP16 engine (default)")
    ap.add_argument("--no-fp16", dest="fp16", action="store_false", help="build FP32 engine")
    sub = ap.add_subparsers(dest="cmd")

    det = sub.add_parser("detector")
    det.add_argument("--onnx", default="models/detector/yolov12n_face.onnx")
    det.add_argument("--engine", default="models/detector/detector_fp16.engine")
    det.add_argument("--input-name", default="images")

    rec = sub.add_parser("recognition")
    rec.add_argument("--onnx", default="models/recognition/w600k_r50.onnx")
    rec.add_argument("--engine", default="models/recognition/face_recog_fp16.engine")
    rec.add_argument("--input-name", default="input.1")

    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 1

    if args.cmd == "detector":
        input_shape = "1x3x640x640"
    else:
        input_shape = "1x3x112x112"

    return trtexec_convert(
        Path(args.onnx),
        Path(args.engine),
        args.input_name,
        input_shape,
        fp16=args.fp16,
    )


if __name__ == "__main__":
    sys.exit(main())