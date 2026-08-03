"""
SAM3 Tracker (promptable visual segmentation) via ONNX Runtime.

The tracker is SAM3's SAM2-style interactive head: point/box prompts against a
vision-encoder embedding, returning three candidate masks at different
granularities (subpart / object / region) with IoU estimates. It serves the
editor's click-to-mask gesture; concept (text) segmentation stays in
sam3_service.py.

Models are mirrored to R2 (models.stimma.ai/sam3-tracker/) from the upstream
HuggingFace repo "onnx-community/sam3-tracker-ONNX" (fp32 export of
facebook/sam3's tracker head).
"""

import asyncio
import gc
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from PIL import Image

import model_cache
from core.logging import get_logger
from model_lifetime import IdleModelHandle, idle_seconds
from sam3_service import SAM3Detection, SAM3Result, _compute_bbox_from_mask, _mask_to_png

log = get_logger(__name__)

# ONNX inference is synchronous; one worker serializes it.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sam3-tracker")

# Two encoder precisions: uint8-quantized for CPU (2.3× faster than fp32 at
# ≥0.99 object-mask IoU, and a quarter of the download), fp32 where CUDA is
# available (quantized ConvInteger/DynamicQuantize ops don't run on the CUDA
# EP). Only the chosen variant is downloaded.
ENCODER_FILES_CPU = ["vision_encoder_quantized.onnx", "vision_encoder_quantized.onnx_data"]
ENCODER_FILES_CUDA = ["vision_encoder.onnx", "vision_encoder.onnx_data"]
DECODER_FILES = ["prompt_encoder_mask_decoder.onnx", "prompt_encoder_mask_decoder.onnx_data"]

# Sam3ImageProcessor: resize to 1008, scale to [0,1], normalize mean/std 0.5.
INPUT_SIZE = 1008


def _ensure_models_downloaded(encoder_files: list[str]):
    for filename in [*encoder_files, *DECODER_FILES]:
        model_cache.ensure_model(f"sam3-tracker/{filename}")
    return model_cache.models_root() / "sam3-tracker"


def _runtime_encoder_files() -> list[str]:
    import onnxruntime as ort
    return (
        ENCODER_FILES_CUDA
        if 'CUDAExecutionProvider' in ort.get_available_providers()
        else ENCODER_FILES_CPU
    )


def _models_present(encoder_files: list[str]) -> bool:
    return all(
        model_cache.model_is_present(f"sam3-tracker/{filename}")
        for filename in [*encoder_files, *DECODER_FILES]
    )


class SAM3TrackerService:
    """Lazy-loaded tracker with a small embedding cache for interactive clicks."""

    # Embeddings are ~21MB per image (3 FPN levels), so a handful is cheap and
    # makes every click after the first on an image decoder-only (~20ms).
    EMBED_CACHE_SIZE = 4

    def __init__(self):
        self._sess_encoder = None
        self._sess_decoder = None
        self._load_lock = asyncio.Lock()
        self._inference_semaphore = asyncio.Semaphore(1)
        self._embed_cache: dict[str, list[np.ndarray]] = {}
        self._load_stage = "idle"
        self._encoder_files: list[str] | None = None
        self._idle = IdleModelHandle(
            "SAM3 tracker",
            idle_seconds("STIMMA_SAM3_TRACKER_IDLE_SECONDS", 300),
            self._unload_sync,
        )

    def _unload_sync(self):
        self._sess_encoder = None
        self._sess_decoder = None
        self._embed_cache.clear()
        self._load_stage = "idle"
        gc.collect()

    def _load_sync(self):
        import onnxruntime as ort

        log.info("SAM3 tracker: Loading ONNX models...")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        providers = ort.get_available_providers()
        encoder_files = _runtime_encoder_files()
        self._encoder_files = encoder_files
        if encoder_files == ENCODER_FILES_CUDA:
            exec_providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        else:
            exec_providers = ['CPUExecutionProvider']
            sess_options.enable_cpu_mem_arena = False
        log.info(f"SAM3 tracker: Using providers: {exec_providers}")

        self._load_stage = "loading" if _models_present(encoder_files) else "downloading_model"
        models_dir = _ensure_models_downloaded(encoder_files)
        self._load_stage = "loading"

        def load(model_name: str) -> "ort.InferenceSession":
            return ort.InferenceSession(
                str(models_dir / model_name),
                sess_options=sess_options,
                providers=exec_providers,
            )

        self._sess_encoder = load(encoder_files[0])
        self._sess_decoder = load(DECODER_FILES[0])
        self._load_stage = "ready"
        log.info("SAM3 tracker: ONNX models loaded")

    async def _ensure_loaded(self):
        if self._sess_encoder is not None:
            return
        async with self._load_lock:
            if self._sess_encoder is not None:
                return
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, self._load_sync)

    def _embed_sync(self, image: Image.Image, cache_key: str) -> list[np.ndarray]:
        cached = self._embed_cache.get(cache_key)
        if cached is not None:
            log.debug("SAM3 tracker: Reusing cached embedding")
            return cached

        pixels = np.asarray(image.resize((INPUT_SIZE, INPUT_SIZE)), dtype=np.float32) / 255.0
        pixels = ((pixels - 0.5) / 0.5).transpose(2, 0, 1)[None]
        embeddings = self._sess_encoder.run(None, {"pixel_values": pixels})

        if len(self._embed_cache) >= self.EMBED_CACHE_SIZE:
            self._embed_cache.pop(next(iter(self._embed_cache)))
        self._embed_cache[cache_key] = embeddings
        return embeddings

    def selection_stage(self, cache_key: str) -> str:
        """Current user-visible phase for a point selection on ``cache_key``."""
        if self._load_stage in {"downloading_model", "loading"}:
            return self._load_stage
        if self._sess_encoder is None or self._sess_decoder is None:
            encoder_files = self._encoder_files or _runtime_encoder_files()
            return "loading" if _models_present(encoder_files) else "downloading_model"
        return "selecting" if cache_key in self._embed_cache else "processing_image"

    def _point_masks_sync(
        self,
        image: Image.Image,
        cache_key: str,
        points: list[tuple[float, float, int]],
    ) -> SAM3Result:
        try:
            original_width, original_height = image.size
            embeddings = self._embed_sync(image, cache_key)

            coords = np.array(
                [[[(px * INPUT_SIZE, py * INPUT_SIZE) for px, py, _ in points]]],
                dtype=np.float32,
            )
            labels = np.array([[[label for _, _, label in points]]], dtype=np.int64)
            iou_scores, pred_masks, _object_logits = self._sess_decoder.run(None, {
                "image_embeddings.0": embeddings[0],
                "image_embeddings.1": embeddings[1],
                "image_embeddings.2": embeddings[2],
                "input_points": coords,
                "input_labels": labels,
                "input_boxes": np.zeros((1, 0, 4), dtype=np.float32),
            })

            detections = []
            for i in range(pred_masks.shape[2]):
                # Upsample the float logits, not the thresholded bitmap — the
                # zero-crossing lands on a smooth boundary instead of 288-px stairs.
                logits = Image.fromarray(pred_masks[0, 0, i], mode="F")
                logits = logits.resize((original_width, original_height), Image.BILINEAR)
                mask = np.asarray(logits) > 0
                bbox_result = _compute_bbox_from_mask(mask, original_width, original_height)
                if bbox_result is None:
                    continue
                bbox, area_percent = bbox_result
                detections.append(SAM3Detection(
                    bbox=bbox,
                    score=float(iou_scores[0, 0, i]),
                    mask_data=_mask_to_png(mask),
                    area_percent=area_percent,
                ))

            # Object-level first: the editor defaults to the largest granularity
            # and cycles finer on repeated clicks.
            detections.sort(key=lambda d: d.area_percent, reverse=True)

            return SAM3Result(
                detections=detections,
                original_width=original_width,
                original_height=original_height,
            )
        except Exception as e:
            log.error(f"SAM3 tracker segmentation failed: {e}", exc_info=True)
            return SAM3Result(error=str(e), original_width=0, original_height=0)

    async def warm(self, image_bytes: bytes) -> None:
        """
        Load the models and run the encoder into the cache, so the user's
        first click on this image pays only the ~20ms decoder. Fired when the
        editor arms the Object tool; the bytes must match what the click will
        send, since the cache key is their hash.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            cache_key = hashlib.sha1(image_bytes).hexdigest()
        except Exception as e:
            log.warning(f"SAM3 tracker warm: bad image: {e}")
            return
        with self._idle.use():
            await self._ensure_loaded()
            async with self._inference_semaphore:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(_executor, self._embed_sync, image, cache_key)

    async def point_masks(
        self,
        image_bytes: bytes,
        points: list[tuple[float, float, int]],
    ) -> SAM3Result:
        """
        Segment at click points ((x, y, label), normalized 0-1; label 1 =
        foreground, 0 = background). Returns every non-empty granularity,
        largest area first.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            cache_key = hashlib.sha1(image_bytes).hexdigest()
        except Exception as e:
            return SAM3Result(error=str(e), original_width=0, original_height=0)

        with self._idle.use():
            await self._ensure_loaded()
            async with self._inference_semaphore:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    _executor, self._point_masks_sync, image, cache_key, points,
                )


_tracker_service: Optional[SAM3TrackerService] = None


def get_sam3_tracker_service() -> SAM3TrackerService:
    global _tracker_service
    if _tracker_service is None:
        _tracker_service = SAM3TrackerService()
    return _tracker_service
