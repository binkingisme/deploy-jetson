"""Configuration loading and settings.

Loads YAML config files + environment variables into typed dataclasses.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml


@dataclass
class AppConfig:
    """Root application configuration."""

    name: str = "open-set-face-recognition"
    version: str = "1.0.0"
    environment: str = "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@dataclass
class CameraConfig:
    """Camera configuration (FR-001)."""

    id: str = "camera_01"
    code: str = "CAM-FRONT-01"
    name: str = "Front Door Camera"
    source_type: str = "csi"  # csi | rtsp
    sensor_id: int = 0
    width: int = 1920
    height: int = 1080
    fps: int = 30
    uri: str = ""
    protocol: str = "tcp"            # tcp | udp
    latency_ms: int = 300
    codec: str = "h265"              # h264 | h265 video track codec
    deepstream: dict = field(default_factory=dict)
    csi_tuning: dict = field(default_factory=dict)  # nvarguscamerasrc ISP props (CSI only)


@dataclass
class RecognitionConfig:
    """Recognition model config (FR-004, FR-011)."""

    backbone: str = "IR-SE50"
    model_name: str = "w600k_r50"
    model_version: str = "1.0.0"
    input_size: list[int] = field(default_factory=lambda: [112, 112])
    embedding_dimension: int = 512
    normalization: str = "l2"
    model_path: str = "models/recognition/w600k_r50.onnx"
    engine_path: str = "models/recognition/face_recog.engine"
    runtime: str = "onnx"
    device: str = "cuda:0"
    recognition_interval_frames: int = 3


@dataclass
class QualityConfig:
    """Face quality gate config."""

    enabled: bool = True
    min_face_size: int = 40
    min_confidence: float = 0.5
    max_blur: float = 100.0
    min_brightness: float = 30.0
    max_brightness: float = 220.0


@dataclass
class GalleryConfig:
    """Embedding gallery config."""

    model_version: str = "w600k_r50@1.0.0"
    embedding_dim: int = 512
    load_on_startup: bool = True


@dataclass
class DetectorModelConfig:
    """Face detector model config (SCRFD det_10g)."""

    onnx_path: str = "models/detector/det_10g.onnx"
    engine_path: str = "models/detector/det_10g_fp16_4d.engine"
    input_size: list[int] = field(default_factory=lambda: [640, 640])
    num_classes: int = 1
    score_threshold: float = 0.5
    nms_threshold: float = 0.4
    stride: int = 8


@dataclass
class DeepStreamConfig:
    """DeepStream integration config (primary/secondary GIE)."""

    config_dir: str = "configs/deepstream"
    primary_gie_config: str = "configs/deepstream/config_infer_primary.txt"
    secondary_gie_config: str = "configs/deepstream/config_infer_secondary.txt"


@dataclass
class PostgresConfig:
    """PostgreSQL connection config."""

    host: str = "localhost"
    port: int = 5432
    dbname: str = "open_set_fr"
    user: str = "open_set_fr"
    password: str = ""
    sslmode: str = "prefer"

    @property
    def dsn(self) -> str:
        user = quote(self.user, safe="")
        password = quote(self.password, safe="")
        return (
            f"postgresql://{user}:{password}@"
            f"{self.host}:{self.port}/{self.dbname}?sslmode={self.sslmode}"
        )


@dataclass
class Settings:
    """Aggregated settings used across the whole service."""

    app: AppConfig = field(default_factory=AppConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    cameras: list[CameraConfig] = field(default_factory=list)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    gallery: GalleryConfig = field(default_factory=GalleryConfig)
    postgresql: PostgresConfig = field(default_factory=PostgresConfig)
    detector: DetectorModelConfig = field(default_factory=DetectorModelConfig)
    deepstream: DeepStreamConfig = field(default_factory=DeepStreamConfig)

    # Paths
    config_dir: Path = Path("configs")
    models_dir: Path = Path("models")
    thresholds_path: Path = Path("thresholds/threshold_table.json")


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay dict into base dict."""
    result = dict(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_interpolate(data: Any) -> Any:
    """Expand ${VAR:default} placeholders in string values."""
    if isinstance(data, dict):
        return {k: _env_interpolate(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_env_interpolate(v) for v in data]
    if isinstance(data, str) and "${" in data:
        import re

        def repl(match: re.Match) -> str:
            name, default = match.group(1), match.group(2)
            return os.environ.get(name, default or "")

        return re.sub(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}", repl, data)
    return data


def _load_env_file(env_path: Path | None = None) -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    if env_path is None:
        env_path = Path(".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def load_settings(config_paths: list[Path] | None = None) -> Settings:
    """Load and merge YAML configs + environment into a Settings object."""
    config_paths = config_paths or [
        Path("configs/app.yaml"),
        Path("configs/camera.yaml"),
        Path("configs/recognition.yaml"),
    ]

    # Environment (POSTGRES_PASSWORD etc.) from .env, without overriding env
    _load_env_file()

    merged: dict = {}
    for path in config_paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, data)
        else:
            print(f"[settings] WARNING: config not found: {path}")

    merged = _env_interpolate(merged)

    app_cfg = AppConfig(**(merged.get("app") or {}))
    camera_cfg = CameraConfig(**(merged.get("camera") or {}))
    cameras_cfg = [
        CameraConfig(**(c or {}))
        for c in (merged.get("cameras") or [])
        if isinstance(c, dict)
    ]
    recognition_cfg = RecognitionConfig(**(merged.get("recognition") or {}))
    quality_cfg = QualityConfig(**(merged.get("quality") or {}))
    gallery_cfg = GalleryConfig(**(merged.get("gallery") or {}))
    pg_cfg = PostgresConfig(**(merged.get("postgresql") or {}))
    detector_cfg = DetectorModelConfig(
        **((merged.get("models") or {}).get("detector") or {})
    )
    deepstream_cfg = DeepStreamConfig(**(merged.get("deepstream") or {}))

    return Settings(
        app=app_cfg,
        camera=camera_cfg,
        cameras=cameras_cfg,
        recognition=recognition_cfg,
        quality=quality_cfg,
        gallery=gallery_cfg,
        postgresql=pg_cfg,
        detector=detector_cfg,
        deepstream=deepstream_cfg,
    )
