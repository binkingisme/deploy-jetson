"""Offline correction of threshold_table.json for the Jetson deployment.

Rule 7 compliant: fitting/correction happens offline in this script; the
running pipeline only reads threshold_table.json via dict lookup.

Background
----------
- The original table was fit on a workstation (calib_v1, 126k global
  impostor scores / ~3550 per identity, MLE/GPD). Those fits are stable and
  are PRESERVED for every identity.
- The exception is the Binh/Phuc pair: their gallery embeddings are
  exceptionally close (Binh <-> Phuc cosine = 0.442), which inflated the GPD
  tail (postive shape) and pushed identity thresholds to 0.4177 / 0.4640.
  Genuine live captures of these real people measure only ~0.30-0.33
  (verified-crop probe), so they can NEVER be recognized at runtime.
- Operator decision: cap Binh/Phuc so real people can be recognized again,
  accepting a cross-confusion risk (track voting: min_exceedances 30 helps).

Result: threshold_table.json with Binh/Phuc capped to 0.28; all other
identity thresholds and global_evt unchanged. Backup created.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GPD_LOWER_CAP = {"Binh": 0.28, "Phuc": 0.28}
CAP_REASON = (
    "capped offline: GPD inflated by Binh<->Phuc look-alike pair (0.442); "
    "genuine captures measure only ~0.30-0.33, threshold was unreachable. "
    "Capped per operator decision; cross-confusion mitigated by track voting."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--thr",
        default=str(ROOT / "thresholds" / "threshold_table.json"),
    )
    args = ap.parse_args()

    old_path = Path(args.thr)
    data = json.loads(old_path.read_text(encoding="utf-8"))

    identities = data.get("identities") or []
    changed = []
    for item in identities:
        ident = item.get("identity_id")
        cap = GPD_LOWER_CAP.get(ident)
        if cap is not None and item.get("threshold_value", 0) > cap:
            item["threshold_value"] = cap
            item["fit_status"] = "capped"
            item["refit_note"] = CAP_REASON
            changed.append((ident, item.get("gpd_shape"), item.get("gpd_scale")))

    metadata = dict(data.get("metadata") or {})
    metadata["refit_note"] = (
        "Preserved original GPD fits; capped only Binh/Phuc to 0.28 offline "
        "(operator-approved) so genuine captures can pass. "
        "See identity refit_note."
    )
    data["metadata"] = metadata

    bak = old_path.with_name(old_path.name + ".bak_refit")
    shutil.copy2(old_path, bak)
    old_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"changed: {changed}")
    print(f"wrote {old_path}  (backup: {bak})")
    if not changed:
        print("WARNING: no identity matched GPD_LOWER_CAP — nothing to cap!")
    return 0


if __name__ == "__main__":
    sys.exit(main())