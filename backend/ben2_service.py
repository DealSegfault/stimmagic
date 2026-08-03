"""BEN2 Base foreground matting via ONNX Runtime.

The model is loaded on the first subject/background selection request and kept
alive for the process lifetime. Model bytes come only through ``model_cache``;
the upstream Hugging Face repository is attribution/provenance, not a runtime
download source.
"""

import asyncio
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from PIL import Image

import model_cache
from core.logging import get_logger

log = get_logger(__name__)

MODEL_KEY = "ben2/BEN2_Base.onnx"
MODEL_SIZE = 222_932_053
MODEL_SHA256 = "22cea62108ff53b7ccc20f7a008bf30494228d84b1687f29ecbe76936a998101"
INPUT_SIZE = 1024

# ONNX Runtime is synchronous. One worker plus the service semaphore keeps
# model execution serialized without blocking the API event loop.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ben2")


@dataclass
class BEN2Result:
    """One continuous subject alpha mask, or a useful load/inference error."""

    alpha: Optional[np.ndarray] = None
    original_width: int = 0
    original_height: int = 0
    error: Optional[str] = None


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Convert an RGB image to BEN2's float32 1x3x1024x1024 input."""

    rgb = image.convert("RGB")
    resized = rgb.resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float32) / 255.0
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None], dtype=np.float32)


def postprocess_alpha(output: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize BEN2 output to ``height x width`` and normalize to uint8 alpha.

    The official ONNX example bilinearly resizes the float output before
    min/max normalization. PIL takes ``(width, height)`` while array shapes are
    ``(height, width)``; keeping those conventions explicit prevents rotated or
    transposed masks for non-square editor composites.
    """

    squeezed = np.squeeze(np.asarray(output, dtype=np.float32))
    if squeezed.ndim != 2:
        raise ValueError(f"Unexpected BEN2 output shape: {np.asarray(output).shape}")

    resized = Image.fromarray(squeezed, mode="F").resize(
        (width, height), Image.Resampling.BILINEAR,
    )
    values = np.asarray(resized, dtype=np.float32)
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    span = maximum - minimum
    if not np.isfinite(span) or span <= np.finfo(np.float32).eps:
        log.warning("BEN2: Model returned a constant alpha output")
        return np.zeros((height, width), dtype=np.uint8)

    normalized = np.clip((values - minimum) / span, 0.0, 1.0)
    return np.ascontiguousarray(normalized * 255.0, dtype=np.uint8)


def _verify_official_artifact(path: Path) -> None:
    """Reject an incomplete or unexpected production mirror artifact."""

    actual_size = path.stat().st_size
    if actual_size != MODEL_SIZE:
        raise RuntimeError(
            f"BEN2 Base model has size {actual_size}, expected {MODEL_SIZE}; "
            "remove the cached file and try again"
        )

    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1 << 20), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != MODEL_SHA256:
        raise RuntimeError(
            "BEN2 Base model checksum does not match the official artifact; "
            "remove the cached file and try again"
        )


def _create_onnx_session(model_path: Path):
    """Create the production ONNX Runtime session using project conventions."""

    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    available = ort.get_available_providers()
    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if "CUDAExecutionProvider" in available
        else ["CPUExecutionProvider"]
    )
    log.info(f"BEN2: Using ONNX providers: {providers}")
    return ort.InferenceSession(
        str(model_path), sess_options=options, providers=providers,
    )


class BEN2Service:
    """Lazy singleton-compatible BEN2 service with one-result image caching."""

    def __init__(
        self,
        *,
        model_path: Optional[Path] = None,
        session_factory: Optional[Callable[[Path], Any]] = None,
    ):
        # Overrides are dependency-injection seams for tests and local model
        # inspection. Production always resolves MODEL_KEY through model_cache.
        self._model_path_override = Path(model_path) if model_path else None
        self._session_factory = session_factory
        self._session = None
        self._input_name: Optional[str] = None
        self._load_lock = asyncio.Lock()
        self._inference_semaphore = asyncio.Semaphore(1)
        self._cached_image_hash: Optional[str] = None
        self._cached_alpha: Optional[np.ndarray] = None
        self._load_stage = "idle"

    def _load_sync(self) -> None:
        if self._model_path_override is None:
            self._load_stage = (
                "loading" if model_cache.model_is_present(MODEL_KEY)
                else "downloading_model"
            )
        else:
            self._load_stage = "loading"
        model_path = self._model_path_override or model_cache.ensure_model(MODEL_KEY)
        self._load_stage = "loading"
        if self._model_path_override is None:
            _verify_official_artifact(model_path)

        factory = self._session_factory or _create_onnx_session
        log.info("BEN2: Loading Base ONNX model")
        session = factory(model_path)
        inputs = session.get_inputs()
        if not inputs:
            raise RuntimeError("BEN2 Base model has no inputs")
        self._session = session
        self._input_name = inputs[0].name
        self._load_stage = "ready"
        log.info("BEN2: Base ONNX model loaded")

    async def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        async with self._load_lock:
            if self._session is not None:
                return
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, self._load_sync)

    def _infer_sync(self, image: Image.Image) -> np.ndarray:
        if self._session is None or self._input_name is None:
            raise RuntimeError("BEN2 Base model is not loaded")
        width, height = image.size
        model_input = preprocess_image(image)
        outputs = self._session.run(None, {self._input_name: model_input})
        if not outputs:
            raise RuntimeError("BEN2 Base model returned no outputs")
        return postprocess_alpha(outputs[0], width, height)

    def selection_stage(self, image_hash: str) -> str:
        """Current user-visible phase for subject/background selection."""
        if self._load_stage in {"downloading_model", "loading"}:
            return self._load_stage
        if self._session is None:
            if self._model_path_override is not None:
                return "loading"
            return "loading" if model_cache.model_is_present(MODEL_KEY) else "downloading_model"
        return (
            "selecting"
            if image_hash == self._cached_image_hash and self._cached_alpha is not None
            else "processing_image"
        )

    async def subject_alpha(self, image_bytes: bytes) -> BEN2Result:
        """Return BEN2's continuous foreground alpha for encoded image bytes."""

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            width, height = image.size
            image_hash = hashlib.sha256(image_bytes).hexdigest()
        except Exception as exc:
            return BEN2Result(error=f"Could not read the image: {exc}")

        try:
            await self._ensure_loaded()
            async with self._inference_semaphore:
                if image_hash == self._cached_image_hash and self._cached_alpha is not None:
                    log.debug("BEN2: Reusing cached subject alpha")
                    alpha = self._cached_alpha
                else:
                    loop = asyncio.get_running_loop()
                    alpha = await loop.run_in_executor(_executor, self._infer_sync, image)
                    self._cached_image_hash = image_hash
                    self._cached_alpha = alpha
            return BEN2Result(
                alpha=alpha,
                original_width=width,
                original_height=height,
            )
        except Exception as exc:
            log.error(f"BEN2 selection failed: {exc}", exc_info=True)
            return BEN2Result(
                error=f"BEN2 Base selection failed: {exc}",
                original_width=width,
                original_height=height,
            )


_ben2_service: Optional[BEN2Service] = None


def get_ben2_service() -> BEN2Service:
    """Return the process-wide lazy BEN2 service."""

    global _ben2_service
    if _ben2_service is None:
        _ben2_service = BEN2Service()
    return _ben2_service
