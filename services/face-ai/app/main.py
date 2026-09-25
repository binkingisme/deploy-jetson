"""Main entry point for the face-ai service (Phase 0-5 pipeline).

Wires together:
  Camera -> DeepStream detection -> Tracking -> Embedding -> Gallery search
            -> Threshold decision -> Event persistence -> Annotated output.

Supports multiple cameras: one ``PipelineEngine`` per camera entry in the
``cameras`` list (each runs in its own daemon thread). The legacy single
``camera`` setting is still honoured when ``cameras`` is empty.

NOTE: The full DeepStream loop (engine.py) is the integration hub. This
module provides the CLI entry point and dependency wiring.
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
from dataclasses import replace
from pathlib import Path

from .config.settings import load_settings
from .utils.logging import setup_logging

logger = logging.getLogger("face-ai")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="face-ai",
        description="Open-set face recognition service (Phase 0-5)",
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        default=["configs/app.yaml", "configs/camera.yaml", "configs/recognition.yaml"],
        help="YAML config files to load",
    )
    parser.add_argument(
        "--import-flag",
        action="store_true",
        help="Import-only entry (no pipeline), for dependency verification",
    )
    return parser.parse_args(argv)


def verify_imports() -> None:
    """Import all modules to fail fast on structural errors."""
    from .config import settings  # noqa: F401
    from .pipeline import camera, engine  # noqa: F401
    from .detection import detector  # noqa: F401
    from .tracking import tracker  # noqa: F401
    from .recognition import embedder, quality  # noqa: F401
    from .openset import decision  # noqa: F401
    from .gallery import manager, pg_loader  # noqa: F401
    from .events import generator  # noqa: F401
    from .streaming import rtsp  # noqa: F401
    logger.info("All face-ai modules imported successfully")


def _run_engine(settings, name: str) -> None:
    """Run one pipeline engine in a dedicated thread."""
    from .pipeline.engine import PipelineEngine

    engine = PipelineEngine(settings)
    try:
        engine.run()
    except Exception:
        logger.exception("[%s] pipeline engine crashed", name)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging()
    settings = load_settings([Path(p) for p in args.configs])

    if args.import_flag:
        verify_imports()
        return 0

    cameras = list(settings.cameras)
    if not cameras:
        cameras = [settings.camera]

    n = len(cameras)
    if n == 1:
        _run_engine(settings, cameras[0].id)
        return 0

    logger.info("Launching %d camera pipeline(s) in parallel threads", n)
    threads = []
    for cam in cameras:
        per_cam = replace(settings, camera=cam)
        t = threading.Thread(
            target=_run_engine,
            args=(per_cam, cam.id),
            name=f"face-ai-{cam.id}",
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())