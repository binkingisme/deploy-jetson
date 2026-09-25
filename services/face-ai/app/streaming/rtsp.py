"""RTSP streaming output (later phase, placeholder).

Publishes the annotated pipeline to RTSP (typically via MediaMTX in a later
phase). Current scope (Phase 0-5) produces annotated video locally.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RTSPSink:
    """RTSP output sink configuration placeholder."""

    enabled: bool = False
    uri: str = "rtsp://localhost:8554/out"


class RTSPServer:
    """Placeholder for RTSP publishing.

    Real implementation (MediaMTX + WebRTC) is planned for a later phase
    (Phase 9+). Present as a stub for structural completeness.
    """

    def __init__(self, sink: RTSPSink):
        self.sink = sink

    def start(self) -> None:
        if not self.sink.enabled:
            return
        raise NotImplementedError("RTSP publishing lands in a later phase")
