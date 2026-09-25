"""Demo (1 phút): so sánh threshold cố định vs bảng EVT trên cùng một query set.

Dùng đúng code production (OpenSetRecognizer + ThresholdTable + GalleryManager)
trong decision.py — không reinvent. Mỗi ảnh đầu vào được embed → gallery search
→ decide theo 3 chế độ:
  - fixed        : một ngưỡng chung (--fixed, mặc định 0.5)
  - global_evt   : một ngưỡng EVT toàn cục từ threshold_table (0.4119)
  - identity_gpd : mỗi identity một ngưỡng riêng trong bảng (xét top-k)

In ra từng query theo dạng bảng và tóm tắt chỗ KHÁC NHAU giữa các chế độ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))


def load_env_file(env_path: Path) -> None:
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


DEFAULT_IMAGES = [
    "/home/jetson/dt/capture/Hoang_Nhat_Nam/Hoang_Nhat_Nam_20260731_134746_1.jpg",
    "/home/jetson/dt/capture/Le_Thien_Phuc/Le_Thien_Phuc_20260731_134746_2.jpg",
    "/home/jetson/dt/capture/Le_Thien_Phuc/Le_Thien_Phuc_20260731_135429_2.jpg",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="fixed vs EVT threshold demo")
    parser.add_argument("images", nargs="*", help="path to query face images")
    parser.add_argument("--fixed", type=float, default=0.5, help="fixed threshold")
    args = parser.parse_args()

    load_env_file(_ROOT / ".env")
    from app.config.settings import RecognitionConfig, load_settings
    from app.gallery.manager import GalleryManager
    from app.openset.decision import OpenSetRecognizer, ThresholdTable
    from app.recognition.embedder import FaceEmbedder

    settings = load_settings([_ROOT / "configs" / "app.yaml"])

    th_table = ThresholdTable()
    th_table.load_from_json(_ROOT / "thresholds" / "threshold_table.json")

    gallery = GalleryManager(settings.postgresql, settings.gallery)
    gallery.load()

    rec_cfg = RecognitionConfig()
    embedder = FaceEmbedder(rec_cfg)

    images = args.images or [p for p in DEFAULT_IMAGES if Path(p).is_file()]
    if not images:
        print("No query images given and default captures not found.")
        return 2

    fixed = OpenSetRecognizer(gallery, th_table, settings.gallery, mode="fixed", fixed_threshold=args.fixed)
    global_evt = OpenSetRecognizer(gallery, th_table, settings.gallery, mode="global_evt", fixed_threshold=args.fixed)
    identity_gpd = OpenSetRecognizer(gallery, th_table, settings.gallery, mode="identity_gpd", fixed_threshold=args.fixed)

    import cv2

    print(f"[demo] gallery={gallery.n_persons} persons, "
          f"{len(images)} queries, fixed={args.fixed}")
    print(f"{'query':<46} | {'sim(top-1)':>10} | {'FIXED':<26} | {'GLOBAL_EVT':<26} | {'IDENTITY_GPD':<26}")

    diffs = []

    for img_path in images:
        img = cv2.imread(img_path)
        if img is None:
            print(f"[demo] cannot read {img_path}")
            continue
        res = embedder.extract(img)
        if res is None:
            print(f"[demo] no face/embedding in {img_path}")
            continue
        q = res.embedding

        d_f = fixed.decide(q, top_k=5)
        d_g = global_evt.decide(q, top_k=5)
        d_i = identity_gpd.decide(q, top_k=5)

        row_f = f"{d_f.person_name if d_f.is_known else 'UNKNOWN'}(thr={d_f.threshold:.3f})"
        row_g = f"{d_g.person_name if d_g.is_known else 'UNKNOWN'}(thr={d_g.threshold:.3f})"
        row_i = f"{d_i.person_name if d_i.is_known else 'UNKNOWN'}(thr={d_i.threshold:.3f})"

        short = img_path.split("/")[-1] if "/" in img_path else img_path
        print(f"{short:<46} | {d_i.similarity:>10.3f} | {row_f:<26} | {row_g:<26} | {row_i:<26}")

        labels = {d_f.is_known: "FIXED", d_g.is_known: "GLOBAL_EVT", d_i.is_known: "IDENTITY_GPD"}
        names = {
            "FIXED": d_f.person_name if d_f.is_known else None,
            "GLOBAL_EVT": d_g.person_name if d_g.is_known else None,
            "IDENTITY_GPD": d_i.person_name if d_i.is_known else None,
        }
        uniq = {names[k] for k in names}
        if len(uniq) > 1 or set(labels) != {True} and all(labels.values()) is False:
            diffs.append((short, d_i.similarity, d_f, d_g, d_i))

    # nhóm "tất cả đúng FIXED" không tính là khác biệt
    real_diffs = [
        (s, sim, a, b, c) for s, sim, a, b, c in diffs
        if {(a.person_name if a.is_known else None),
            (b.person_name if b.is_known else None),
            (c.person_name if c.is_known else None)} != {None}
    ]

    print("\n[summary] khác biệt giữa các chế độ:")
    if not real_diffs:
        print("  (không có khác biệt nào trong query set này)")
    fixed_d = {s: (d.person_name, d.similarity, d.threshold) for s, _, d, _, _ in real_diffs}
    evt_d = {s: (d.person_name, d.similarity, d.threshold) for s, _, _, d, _ in real_diffs}
    gpd_d = {s: (d.person_name, d.similarity, d.threshold) for s, _, _, _, d in real_diffs}
    for s, sim, d_f, d_g, d_i in real_diffs:
        print(f"  {s} (sim={sim:.3f}):")
        print(f"    fixed        -> {fixed_d[s][0] or 'UNKNOWN'} (thr {fixed_d[s][2]:.3f})")
        print(f"    global_evt   -> {evt_d[s][0] or 'UNKNOWN'} (thr {evt_d[s][2]:.3f})")
        print(f"    identity_gpd -> {gpd_d[s][0] or 'UNKNOWN'} (thr {gpd_d[s][2]:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())