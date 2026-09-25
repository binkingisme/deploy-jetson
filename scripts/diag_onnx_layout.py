"""Diagnostic: run det_10g.onnx directly on CPU (no DeepStream) and check
whether score/bbox/kps argmax rows are aligned with each other.

If the ONNX itself is self-consistent (score_argmax == bbox_argmaxrow),
then the export is fine and the DeepStream reading is the problem.
If they differ inside ONNX, the export itself flattened heads inconsistently.

Usage: python3 diag_onnx_layout.py /path/to/det_10g.onnx
"""
import sys

import numpy as np
import onnxruntime as ort


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "models/detector/det_10g.onnx"
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])

    iname = sess.get_inputs()[0].name
    ishape = sess.get_inputs()[0].shape
    print(f"input: {iname} {ishape}")

    size = 640
    if len(ishape) == 4:
        nchw = ishape[1] in (3, 1)
    else:
        nchw = True
    if nchw:
        dummy = np.zeros((1, 3, size, size), dtype=np.float32)
        dummy[:, :, 300:340, 300:340] = 1.0   # fake bright "face" patch
    else:
        dummy = np.zeros((1, size, size, 3), dtype=np.float32)
        dummy[:, 300:340, 300:340, :] = 1.0

    outs = sess.run(None, {iname: dummy})
    names = [o.name for o in sess.get_outputs()]
    assert len(names) == 9, f"expected 9 outputs, got {len(names)}"

    # order assumed: score/bbox/kps x (8, 16, 32), shapes [n,1]/[n,4]/[n,10]
    strides = (8, 16, 32)
    chunk = {"score": 1, "bbox": 4, "kps": 10}

    score_max_row = {}
    bbox_max_row = {}
    kps_max_row = {}
    ok = True
    for kind, ch in chunk.items():
        for i, st in enumerate(strides):
            arr = np.asarray(outs[i * 3 + (0 if kind == "score" else 1 if kind == "bbox" else 2)], np.float32)
            if arr.size == 0:
                print(f"{kind}_{st}: EMPTY")
                continue
            rows = arr.reshape(-1, ch)
            print(f"{kind}_{st}: shape={rows.shape} min={rows.min():.4f} max={rows.max():.4f}")
            if kind == "score":
                score_max_row[st] = int(np.argmax(rows.reshape(-1)))
                print(f"  score_argmax_row={score_max_row[st]} val={rows.reshape(-1)[score_max_row[st]]:.4f}")
            elif kind == "bbox":
                rowsum = rows.sum(axis=1)
                bbox_max_row[st] = int(np.argmax(rowsum))
                print(f"  bbox_argmax_row={bbox_max_row[st]} bbox={rows[bbox_max_row[st]]}")
            else:
                rowsum = rows.sum(axis=1)
                kps_max_row[st] = int(np.argmax(rowsum))
                print(f"  kps_argmax_row={kps_max_row[st]}")

    print("\n=== alignment check ===")
    for st in strides:
        s = score_max_row.get(st, -1)
        b = bbox_max_row.get(st, -1)
        k = kps_max_row.get(st, -1)
        same = s == b == k
        ok &= same
        print(f"stride {st}: score={s} bbox={b} kps={k} -> {'ALIGNED' if same else 'MISALIGNED'}")

    print("\nRESULT:", "ONNX-OK" if ok else "ONNX-MISALIGNED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())