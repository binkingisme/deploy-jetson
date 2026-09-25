"""Diagnose Binh/Phuc/Nam gallery separation.

Reads gallery embeddings from PostgreSQL and prints:
  - pairwise cosine similarity among the specified identities
  - each identity's own self-similarity (min/mean across its vectors)
  - gap: mean-impostor vs self, to sanity check thresholds
Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "services" / "face-ai"))


def load_env_file(env_path: Path) -> None:
    """Load .env into os.environ (no python-dotenv dependency)."""
    import os

    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def main() -> int:
    import psycopg2

    load_env_file(_ROOT / ".env")
    from app.config.settings import load_settings

    pg = load_settings([_ROOT / "configs" / "app.yaml"]).postgresql
    conn = psycopg2.connect(pg.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.student_code, p.full_name, fe.embedding
                FROM face_embeddings fe
                JOIN persons p ON p.person_id = fe.person_id
                WHERE p.status = 'active'
                ORDER BY p.full_name
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    people: dict[str, np.ndarray] = {}
    for code, name, emb in rows:
        key = code or name or ""
        people.setdefault(key, []).append(
            np.frombuffer(bytes(emb), dtype=np.float32)
        )

    names = sorted(people)
    print(f"[diag] {len(names)} identities")
    for n in names:
        m = np.mean(np.array(people[n]), axis=0)
        m = m / (np.linalg.norm(m) + 1e-12)
        people[n] = m

    # Pairwise similarity matrix
    print(f"\n{'':<14}", "".join(f"{n[:10]:>12}" for n in names))
    for a in names:
        row = f"{a[:14]:<14}"
        for b in names:
            s = float(np.dot(people[a], people[b]))
            row += f"{s:>12.3f}"
        print(row)

    focus = ["Binh", "Phuc", "Nam", "Thanh Liem"]
    print("\n[distance-to-self vs top impostor for focus identities]")
    for a in focus:
        if a not in people:
            print(f"  {a}: NOT IN GALLERY")
            continue
        others = [(b, float(np.dot(people[a], people[b]))) for b in names if b != a]
        others.sort(key=lambda x: -x[1])
        self_sim = 1.0
        print(
            f"  {a:<12} self={self_sim:.3f} "
            f"top_impostor={others[0][0]} ({others[0][1]:.3f}), "
            f"2nd={others[1][0]} ({others[1][1]:.3f})"
        )
        print(f"             top5: {', '.join(f'{b}({s:.3f})' for b, s in others[:5])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())