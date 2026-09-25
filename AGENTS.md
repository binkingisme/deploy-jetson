# AGENTS.md — open-set-face-recognition

Guidance for AI agents working in this repository. Derived from the thesis
specification's conservation rules (Spec Section 36).

## Conventions & rules (MUST follow)

1. **Conservation principles (do NOT replace without approval):**
   - Face detector (DeepStream primary GIE, YOLOv12n)
   - Embedding model: InsightFace IR-SE50 (`w600k_r50.onnx`, 112x112)
   - PostgreSQL-backed embedding gallery
   - DeepStream pipeline
   - Identity-wise EVT (POT/GPD) thresholding

2. **JetPack 6.2.2 is pinned. Do NOT upgrade.**
   The environment must stay at the verified L4T/JetPack/CUDA versions.

3. **Runtime efficiency rules (Spec Rule 4):**
   - Gallery loads into RAM at startup (NumPy matrix), exact cosine search.
   - No PostgreSQL queries per frame. DB writes only on decision events.

4. **Offline-fitting rule (Spec Rule 7):**
   - EVT / GPD fitting happens ONLY on a workstation, offline.
   - Runtime reads thresholds via dict lookup from `identity_thresholds` /
     `thresholds/threshold_table.json`. Never fit distributions at runtime.

## Layout

- `services/face-ai/app/` — Python service modules
- `configs/` — YAML + DeepStream configs
- `database/migrations/` — schema SQL, applied by `setup_postgres.sh`
- `scripts/` — setup / gallery / model / benchmark helpers

## Commands

```bash
# Tests
cd services/face-ai && pytest

# Import-only structural check (no DeepStream)
cd services/face-ai && python -m app.main --import-flag

# Benchmarks
python3 scripts/benchmark/benchmark_gallery.py
```

## Notes for agents

- Type hints everywhere; use dataclasses for configs.
- Do not add code that queries the DB per frame.
- Preserve model asset hashes; do not swap embedding models silently.
- Threshold table updates originate from the offline fit pipeline, not runtime.
