"""Face embedding extraction using InsightFace IR-SE50 (w600k_r50).

Implements FR-004. Produces a 512-d L2-normalized embedding per face,
compatible with the PostgreSQL-stored gallery.

Supports two runtimes (configured via ``recognition.yaml runtime``):
  - ``tensorrt``: TensorRT FP16 engine via pycuda (preferred on Jetson).
  - ``onnx``:     ONNX Runtime with CUDAExecutionProvider (fallback).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..config.settings import RecognitionConfig

logger = logging.getLogger("face-ai.recognition.embedder")


class EmbeddingError(Exception):
    """Raised when embedding extraction fails."""


@dataclass
class EmbeddingResult:
    """Result of a single face embedding extraction."""

    embedding: np.ndarray  # (512,) L2-normalized float32
    shape: tuple[int, ...]
    norm: float


# ------------------------------------------------------------------
# TensorRT runtime (pycuda)
# ------------------------------------------------------------------

def _load_trt_engine(engine_path: Path) -> Any:
    """Deserialize a TensorRT engine from disk."""
    import tensorrt as trt

    logger.info("Loading TensorRT engine: %s", engine_path)
    runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
    with open(engine_path, "rb") as f:
        engine = runtime.deserialize_cuda_engine(f.read())
    if engine is None:
        raise EmbeddingError(f"Failed to deserialize TensorRT engine: {engine_path}")
    return engine


class _TRTSession:
    """Thin wrapper around a TensorRT engine + pycuda for inference.

    IMPORTANT: the pycuda CUDA context MUST be created before the TRT engine
    is deserialized. If the engine is deserialized first, subsequent kernel
    launches fail with ``Cask (Cask convolution execution)``. That is why the
    context is made in this constructor before deserializing.
    """

    def __init__(self, engine_path: Path) -> None:
        import tensorrt as trt
        import pycuda.driver as cuda

        # Explicit CUDA context (NOT pycuda.autoinit). cv2 / DeepStream may
        # initialize CUDA first; a manually-pushed context guarantees the
        # TensorRT kernels run on the right device/context.
        cuda.init()
        self._cuda_ctx = cuda.Device(0).make_context()

        self._engine = _load_trt_engine(engine_path)
        self._context = self._engine.create_execution_context_without_device_memory()
        self._stream = cuda.Stream()

        # Discover I/O tensor names + shapes from the engine. Names are
        # model-specific (e.g. "input.1" / "683" for w600k_r50 via trtexec).
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._output_size: int = 0
        for i in range(self._engine.num_io_tensors):
            name = self._engine.get_tensor_name(i)
            shape = self._engine.get_tensor_shape(name)
            if self._engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self._input_name = name
            else:
                self._output_name = name
                volume = 1
                for d in shape:
                    volume *= int(d)
                self._output_size = volume

        input_bytes = int(np.prod(list(self._engine.get_tensor_shape(self._input_name)))) * 4
        self._d_input = cuda.mem_alloc(input_bytes)
        self._d_output = cuda.mem_alloc(self._output_size * 4)

        # TRT 10 requires the execution context's scratch/workspace device
        # memory to be allocated by the caller and bound via set_device_memory.
        ctx_mem_size = int(self._engine.device_memory_size)
        self._d_ctx_mem = cuda.mem_alloc(ctx_mem_size)
        self._context.set_device_memory(int(self._d_ctx_mem), ctx_mem_size)

        self._context.set_tensor_address(self._input_name, int(self._d_input))
        self._context.set_tensor_address(self._output_name, int(self._d_output))

        # Balance the make_context() push: the context stays alive via
        # self._cuda_ctx and is pushed per-infer in infer(). Leaving it on
        # the stack here would make pycuda abort at module cleanup.
        self._cuda_ctx.pop()

    def infer(self, tensor: np.ndarray) -> np.ndarray:
        """Run inference: tensor (1,3,112,112) float32 → (512,) float32."""
        import pycuda.driver as cuda

        host_input = np.ascontiguousarray(tensor.ravel())
        self._cuda_ctx.push()
        try:
            cuda.memcpy_htod_async(self._d_input, host_input, self._stream)
            self._context.execute_async_v3(stream_handle=self._stream.handle)
            host_output = np.empty(self._output_size, dtype=np.float32)
            cuda.memcpy_dtoh_async(host_output, self._d_output, self._stream)
            self._stream.synchronize()
        finally:
            self._cuda_ctx.pop()
        return host_output


ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


class FaceEmbedder:
    """Runtime embedding extractor.

    The ONNX weights come from the InsightFace repo (w600k_r50), the same
    model the gallery embeddings were computed with. Input is 112x112 RGB,
    normalized as (x - 127.5) / 128.0.
    """

    def __init__(self, config: RecognitionConfig):
        self.config = config
        self._backend: str | None = None   # "tensorrt" | "onnx"
        self._trt_session: _TRTSession | None = None
        self._onnx_session: Any = None
        self._input_name: str | None = None

    # -- alignment ---------------------------------------------------

    def align_face(
        self, frame_bgr: np.ndarray, landmarks_5pt: np.ndarray
    ) -> np.ndarray | None:
        """Align face using 5 landmarks to standard ArcFace 112x112 space."""
        if landmarks_5pt is None or landmarks_5pt.shape != (5, 2):
            return None
        import cv2

        M, _ = cv2.estimateAffinePartial2D(
            landmarks_5pt.astype(np.float32), ARCFACE_DST
        )
        if M is None:
            return None
        return cv2.warpAffine(frame_bgr, M, (112, 112), borderValue=0.0)

    # -- lazy loaders ------------------------------------------------

    def _load_trt(self) -> bool:
        """Try to load the TensorRT engine. Returns True on success."""
        engine_path = Path(self.config.engine_path)
        if not engine_path.exists():
            logger.warning(
                "TensorRT engine not found (%s) — falling back to ONNX",
                engine_path,
            )
            return False
        try:
            self._trt_session = _TRTSession(engine_path)
            self._backend = "tensorrt"
            logger.info("Embedder backend: TensorRT (FP16)")
            return True
        except Exception:
            logger.exception("Failed to load TensorRT engine — falling back to ONNX")
            return False

    def _load_onnx(self) -> None:
        """Load the ONNX Runtime session (fallback)."""
        import onnxruntime as ort

        path = Path(self.config.model_path)
        if not path.exists():
            raise EmbeddingError(f"Model not found: {path}")

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self.config.device.startswith("cuda")
            else ["CPUExecutionProvider"]
        )
        self._onnx_session = ort.InferenceSession(str(path), providers=providers)
        self._input_name = self._onnx_session.get_inputs()[0].name
        self._backend = "onnx"
        logger.info("Embedder backend: ONNX Runtime (CUDA EP)")

    def _ensure_loaded(self) -> None:
        if self._backend is not None:
            return
        if self.config.runtime == "tensorrt":
            if self._load_trt():
                return
        # Either runtime is "onnx", or TRT load failed — load ONNX
        self._load_onnx()

    # -- public API --------------------------------------------------

    def preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        """InsightFace preprocessing: resize to 112x112 and normalize."""
        h, w = map(int, self.config.input_size)
        if face_bgr.ndim != 3 or face_bgr.shape[2] != 3:
            raise EmbeddingError(f"Expected BGR image (H,W,3), got {face_bgr.shape}")

        import cv2

        img = cv2.resize(face_bgr, (w, h), interpolation=cv2.INTER_AREA)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32)
        img = (img - np.float32(127.5)) / np.float32(128.0)
        img = np.transpose(img, (2, 0, 1))          # (3,112,112)
        img = np.expand_dims(img, axis=0)           # (1,3,112,112)
        return img

    def extract(self, face_bgr: np.ndarray) -> EmbeddingResult | None:
        """Extract a 512-d L2-normalized embedding from a face crop."""
        self._ensure_loaded()
        tensor = self.preprocess(face_bgr)

        if self._backend == "tensorrt":
            embedding = self._trt_session.infer(tensor)
        else:
            outputs = self._onnx_session.run(None, {self._input_name: tensor})
            embedding = np.asarray(outputs[0], dtype=np.float32).reshape(-1)

        norm = float(np.linalg.norm(embedding))
        if norm < 1e-12:
            return None
        embedding = embedding / norm  # L2 normalize for cosine search

        return EmbeddingResult(
            embedding=embedding,
            shape=embedding.shape,
            norm=norm,
        )
