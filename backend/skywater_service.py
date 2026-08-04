"""Sky selection via SkyWater-Seg with full-resolution edge refinement.

The semantic pass runs at the model's native 384x384 input. Its coarse sky
probability is then refined against the original pixels with a guided filter;
only a plausible upper-image sky component and confident upper islands are
kept. Model bytes come exclusively through ``model_cache``.
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, find_objects, label, uniform_filter

import model_cache
from core.logging import get_logger
from model_lifetime import IdleModelHandle, idle_seconds

log = get_logger(__name__)

MODEL_KEY = "skywater/skywater_segformer_b2_fp32.onnx"
MODEL_SIZE = 99_310_780
MODEL_SHA256 = "e4e9a6927c2d910c3243f86e392b18da715b41c03e6e6f41672f8f6b8eaa71b5"
INPUT_SIZE = 384
SKY_CLASS = 1

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="skywater")


@dataclass
class SkyWaterResult:
    alpha: Optional[np.ndarray] = None
    score: float = 0.0
    original_width: int = 0
    original_height: int = 0
    error: Optional[str] = None


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Create the model's fixed-size, ImageNet-normalized float input."""
    resized = image.convert("RGB").resize(
        (INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR,
    )
    pixels = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return np.ascontiguousarray(((pixels - MEAN) / STD)[None], dtype=np.float32)


def sky_probability(logits: np.ndarray) -> np.ndarray:
    """Stable softmax of the four-class logits, returning the sky plane."""
    values = np.asarray(logits, dtype=np.float32)
    if values.ndim == 4 and values.shape[0] == 1:
        values = values[0]
    if values.ndim != 3 or values.shape[0] != 4:
        raise ValueError(f"Unexpected SkyWater output shape: {np.asarray(logits).shape}")
    values = values - values.max(axis=0, keepdims=True)
    exponent = np.exp(values)
    return exponent[SKY_CLASS] / exponent.sum(axis=0)


def select_sky_support(probability: np.ndarray) -> tuple[np.ndarray, float]:
    """Keep the likely sky component plus strong gaps through upper foliage."""
    height, width = probability.shape
    search_height = max(1, round(height * 0.65))
    click_y, click_x = np.unravel_index(
        np.argmax(probability[:search_height]), (search_height, width),
    )
    score = float(probability[click_y, click_x])
    if score < 0.45:
        return np.zeros_like(probability, dtype=bool), score

    threshold = float(np.clip(score * 0.52, 0.30, 0.52))
    labels, count = label(probability >= threshold, structure=np.ones((3, 3), dtype=np.uint8))
    clicked_label = int(labels[click_y, click_x])
    selected = labels == clicked_label if clicked_label else np.zeros_like(labels, dtype=bool)

    slices = find_objects(labels, max_label=count)
    for component_label, bounds in enumerate(slices, start=1):
        if bounds is None or component_label == clicked_label:
            continue
        local_labels = labels[bounds]
        local_component = local_labels == component_label
        area = int(local_component.sum())
        if area < 2:
            continue
        values = probability[bounds][local_component]
        y0, y1 = bounds[0].start, bounds[0].stop
        centroid_y = (y0 + y1 - 1) / 2
        touches_top = y0 <= 1
        very_confident = float(values.max()) >= 0.90 and float(values.mean()) >= 0.62
        if touches_top or (centroid_y < height * 0.58 and very_confident):
            selected[bounds] |= local_component
    return selected, score


def _resize_float(values: np.ndarray, width: int, height: int, resample: int) -> np.ndarray:
    image = Image.fromarray(values.astype(np.float32), mode="F")
    return np.asarray(image.resize((width, height), resample), dtype=np.float32)


def guided_filter(
    guidance: np.ndarray, source: np.ndarray, *, radius: int = 10, eps: float = 1e-3,
) -> np.ndarray:
    """Fast grayscale guided filter using SciPy's native uniform filter."""
    size = radius * 2 + 1
    mean_i = uniform_filter(guidance, size=size, mode="reflect")
    mean_p = uniform_filter(source, size=size, mode="reflect")
    covariance = uniform_filter(guidance * source, size=size, mode="reflect") - mean_i * mean_p
    variance = uniform_filter(guidance * guidance, size=size, mode="reflect") - mean_i * mean_i
    a = covariance / (variance + eps)
    b = mean_p - a * mean_i
    return (
        uniform_filter(a, size=size, mode="reflect") * guidance
        + uniform_filter(b, size=size, mode="reflect")
    )


def refine_sky_alpha(
    image: Image.Image, probability: np.ndarray, support: np.ndarray,
) -> np.ndarray:
    """Refine the coarse semantic result against full-resolution pixels."""
    width, height = image.size
    full_probability = _resize_float(
        probability, width, height, Image.Resampling.BILINEAR,
    )
    full_support = _resize_float(
        support.astype(np.float32), width, height, Image.Resampling.NEAREST,
    ) >= 0.5
    full_support = binary_dilation(full_support, structure=np.ones((3, 3)), iterations=4)

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    guidance = (
        0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    ).astype(np.float32)
    refined = guided_filter(guidance, full_probability)
    alpha = np.clip((refined - 0.16) / 0.50, 0.0, 1.0)
    alpha *= full_support
    confident = (full_probability >= 0.72) & full_support
    alpha[confident] = 1.0
    return np.ascontiguousarray(np.round(alpha * 255), dtype=np.uint8)


def _verify_artifact(path: Path) -> None:
    actual_size = path.stat().st_size
    if actual_size != MODEL_SIZE:
        raise RuntimeError(
            f"SkyWater model has size {actual_size}, expected {MODEL_SIZE}; "
            "remove the cached file and try again"
        )
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError(
            "SkyWater model checksum does not match the mirrored artifact; "
            "remove the cached file and try again"
        )


def _create_session(model_path: Path):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # The upstream graph currently fails while Core ML builds a plan. CPU is
    # deterministic and measures about 60 ms warm on Apple Silicon.
    return ort.InferenceSession(
        str(model_path), sess_options=options, providers=["CPUExecutionProvider"],
    )


class SkyWaterService:
    """Lazy, serialized sky inference with one-result image caching."""

    def __init__(
        self,
        *,
        model_path: Optional[Path] = None,
        session_factory: Optional[Callable[[Path], Any]] = None,
    ):
        self._model_path_override = Path(model_path) if model_path else None
        self._session_factory = session_factory
        self._session = None
        self._input_name: Optional[str] = None
        self._load_lock = asyncio.Lock()
        self._inference_semaphore = asyncio.Semaphore(1)
        self._cached_image_hash: Optional[str] = None
        self._cached_result: Optional[SkyWaterResult] = None
        self._load_stage = "idle"
        self._idle = IdleModelHandle(
            "SkyWater", idle_seconds("STIMMA_SKYWATER_IDLE_SECONDS", 300), self._unload_sync,
        )

    def _unload_sync(self) -> None:
        self._session = None
        self._input_name = None
        self._cached_image_hash = None
        self._cached_result = None
        self._load_stage = "idle"
        gc.collect()

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
            _verify_artifact(model_path)
        session = (self._session_factory or _create_session)(model_path)
        inputs = session.get_inputs()
        if not inputs:
            raise RuntimeError("SkyWater model has no inputs")
        self._session = session
        self._input_name = inputs[0].name
        self._load_stage = "ready"

    async def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        async with self._load_lock:
            if self._session is None:
                await asyncio.get_running_loop().run_in_executor(_executor, self._load_sync)

    def _infer_sync(self, image: Image.Image) -> tuple[np.ndarray, float]:
        if self._session is None or self._input_name is None:
            raise RuntimeError("SkyWater model is not loaded")
        outputs = self._session.run(None, {self._input_name: preprocess_image(image)})
        if not outputs:
            raise RuntimeError("SkyWater model returned no outputs")
        probability = sky_probability(outputs[0])
        support, score = select_sky_support(probability)
        if not support.any():
            return np.zeros((image.height, image.width), dtype=np.uint8), score
        return refine_sky_alpha(image, probability, support), score

    def selection_stage(self, image_hash: str) -> str:
        if self._load_stage in {"downloading_model", "loading"}:
            return self._load_stage
        if self._session is None:
            if self._model_path_override is not None:
                return "loading"
            return "loading" if model_cache.model_is_present(MODEL_KEY) else "downloading_model"
        return (
            "selecting"
            if image_hash == self._cached_image_hash and self._cached_result is not None
            else "processing_image"
        )

    async def sky_alpha(self, image_bytes: bytes) -> SkyWaterResult:
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            width, height = image.size
            image_hash = hashlib.sha256(image_bytes).hexdigest()
        except Exception as exc:
            return SkyWaterResult(error=f"Could not read the image: {exc}")

        try:
            with self._idle.use():
                await self._ensure_loaded()
                async with self._inference_semaphore:
                    if image_hash == self._cached_image_hash and self._cached_result is not None:
                        return self._cached_result
                    alpha, score = await asyncio.get_running_loop().run_in_executor(
                        _executor, self._infer_sync, image,
                    )
                    result = SkyWaterResult(
                        alpha=alpha,
                        score=score,
                        original_width=width,
                        original_height=height,
                    )
                    self._cached_image_hash = image_hash
                    self._cached_result = result
                    return result
        except Exception as exc:
            log.error(f"Sky selection failed: {exc}", exc_info=True)
            return SkyWaterResult(
                error=f"Sky selection failed: {exc}",
                original_width=width,
                original_height=height,
            )


_skywater_service: Optional[SkyWaterService] = None


def get_skywater_service() -> SkyWaterService:
    global _skywater_service
    if _skywater_service is None:
        _skywater_service = SkyWaterService()
    return _skywater_service
