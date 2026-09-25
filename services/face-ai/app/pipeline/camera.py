"""Camera capture abstraction (FR-001).

Wraps CSI and RTSP sources. The actual frame acquisition is handled by the
DeepStream pipeline in engine.py; this module provides the source descriptor
and lightweight validation/test helpers.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import CameraConfig


@dataclass
class CameraSource:
    """Resolved camera source ready for the DeepStream pipeline."""

    source_type: str
    element_string: str
    width: int
    height: int
    fps: int


class Camera():
    """Factory + helper for camera sources."""

    def __init__(self, config: CameraConfig):
        self.config = config

    def _codec_pipeline(self) -> tuple[str, str, str]:
        """Return (depay, parse, caps-encoding-name) for the configured codec."""
        codec = self.config.codec.lower()
        if codec == "h265":
            return "rtph265depay", "h265parse", "H265"
        return "rtph264depay", "h264parse", "H264"

    def build_source(self) -> CameraSource:
        """Build the GStreamer source element string (CPU BGRx output)."""
        if self.config.source_type == "csi":
            element = (
                f"nvarguscamerasrc sensor-id={self.config.sensor_id} "
                f"! video/x-raw(memory:NVMM), width={self.config.width}, "
                f"height={self.config.height}, framerate={self.config.fps}/1 "
                f"! nvvidconv ! video/x-raw, format=(string)BGRx, width={self.config.width}, "
                f"height={self.config.height}, framerate={self.config.fps}/1 "
                f"! queue"
            )
            return CameraSource(
                source_type="csi",
                element_string=element,
                width=self.config.width,
                height=self.config.height,
                fps=self.config.fps,
            )

        # RTSP source
        depay, parse, enc = self._codec_pipeline()

        element = (
            f"rtspsrc location={self.config.uri} latency={self.config.latency_ms} "
            f"protocols={self.config.protocol} "
            f"! application/x-rtp, media=video, encoding-name=(string){enc} "
            f"! {depay} ! {parse} ! nvv4l2decoder ! "
            f"nvvidconv ! video/x-raw, format=(string)BGRx ! queue"
        )
        return CameraSource(
            source_type="rtsp",
            element_string=element,
            width=self.config.width,
            height=self.config.height,
            fps=self.config.fps,
        )

    def build_nvmm_element(self) -> str:
        """GStreamer chain ending in an NVMM buffer (for nvstreammux input).

        Keeps frames on GPU (nvv4l2decoder output) so DeepStream does not
        round-trip through CPU. For CSI the sensor already outputs NVMM.
        """
        if self.config.source_type == "csi":
            return (
                f"nvarguscamerasrc sensor-id={self.config.sensor_id} "
                f"! video/x-raw(memory:NVMM), width={self.config.width}, "
                f"height={self.config.height}, framerate={self.config.fps}/1"
            )

        depay, parse, enc = self._codec_pipeline()
        return (
            f"rtspsrc location={self.config.uri} latency={self.config.latency_ms} "
            f"protocols={self.config.protocol} "
            f"! application/x-rtp, media=video, encoding-name=(string){enc} "
            f"! {depay} ! {parse} ! nvv4l2decoder"
        )
