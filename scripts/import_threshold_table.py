#!/usr/bin/env python3
"""
Import script for threshold_table.json into PostgreSQL identity_thresholds table.
Based on open_set_face_recognition_implementation_spec_v2.md Section 13.6.

Usage on Jetson:
    python3 scripts/import_threshold_table.py
    python3 scripts/import_threshold_table.py /home/jetson/open-set-face-recognition/thresholds/threshold_table.json
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

CANDIDATE_PATHS = [
    os.path.expanduser("~/open-set-face-recognition/thresholds/threshold_table.json"),
    "/home/jetson/open-set-face-recognition/thresholds/threshold_table.json",
    os.path.join(PROJECT_ROOT, "thresholds", "threshold_table.json"),
    os.path.join(PROJECT_ROOT, "threshold_table.json"),
    "/data/thresholds/threshold_table.json",
]


def find_json_file(user_arg=None):
    if user_arg:
        expanded = os.path.expanduser(user_arg)
        if os.path.isfile(expanded):
            return expanded
        print(f"[WARN] Specified file not found: {user_arg}")

    for p in CANDIDATE_PATHS:
        expanded = os.path.expanduser(p)
        if os.path.isfile(expanded):
            return expanded

    return None


def main():
    print("=" * 70)
    print("  IDENTITY-WISE EVT THRESHOLD TABLE IMPORTER (Spec Section 13.6)")
    print("=" * 70)

    arg_path = sys.argv[1] if len(sys.argv) > 1 else None
    json_path = find_json_file(arg_path)

    if not json_path:
        print("\n[ERROR] threshold_table.json could not be found!")
        print("Checked candidate paths:")
        for p in CANDIDATE_PATHS:
            print(f"  - {p}")
        print("\nPlease provide the exact path as an argument:")
        print("  python3 scripts/import_threshold_table.py /path/to/threshold_table.json\n")
        sys.exit(1)

    print(f"\n[1/3] Found threshold table at:\n  --> {json_path}")

    # Connect to DB via SQLAlchemy or psycopg2
    db_url = os.getenv("DATABASE_URL", "postgresql://open_set_fr:open_set_fr_pass@localhost:5432/open_set_fr")
    print(f"\n[2/3] Connecting to PostgreSQL database...")

    try:
        from app.db.database import engine, SessionLocal, Base
        from app.db.models import IdentityThreshold, Person
        from app.services.threshold_importer import import_thresholds_from_file

        # Ensure table schema exists
        Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        result = import_thresholds_from_file(file_path=json_path, db=db, clear_existing=True)

        print(f"\n[3/3] Import Successful!")
        print(f"  - Total entries imported: {result['imported_count']}")
        print(f"  - Identities matched:     {result['identities_matched']}")
        print(f"  - Table version:          {result['table_version']}")
        print(f"  - Model version:          {result['model_version']}")

        # Display audit summary
        thresholds = db.query(IdentityThreshold).all()
        print("\n" + "-" * 75)
        print(f"{'Identity / Type':<30} | {'Thresh':<8} | {'Status':<10} | {'Impostors':<10} | {'Fallback':<8}")
        print("-" * 75)
        for t in thresholds:
            id_disp = t.person.full_name if t.person else (t.threshold_type.upper())
            fb_disp = "YES" if t.fallback_used else "NO"
            imp_disp = str(t.n_impostor_scores) if t.n_impostor_scores is not None else "-"
            print(f"{id_disp:<30} | {t.threshold_value:<8.3f} | {t.fit_status:<10} | {imp_disp:<10} | {fb_disp:<8}")
        print("-" * 75)
        print("\nAll thresholds are now persisted in database and available at /thresholds in the web UI.\n")
        db.close()

    except Exception as e:
        print(f"\n[ERROR] Database import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
