import hashlib
import io
from unittest.mock import MagicMock

import numpy as np
from PIL import Image

import skywater_service


def _encoded_test_image(width: int = 80, height: int = 40) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[: height // 2] = (80, 150, 230)
    pixels[height // 2 :] = (40, 80, 35)
    buf = io.BytesIO()
    Image.fromarray(pixels, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_preprocess_uses_native_fixed_shape_and_imagenet_normalization():
    image = Image.new("RGB", (80, 40), (255, 0, 0))
    tensor = skywater_service.preprocess_image(image)

    assert tensor.shape == (1, 3, 384, 384)
    assert tensor.dtype == np.float32
    assert tensor[0, 0, 0, 0] == np.float32((1.0 - 0.485) / 0.229)


def test_sky_probability_is_softmax_not_hard_argmax():
    logits = np.zeros((1, 4, 2, 3), dtype=np.float32)
    logits[:, 1] = 1.0
    probability = skywater_service.sky_probability(logits)

    assert probability.shape == (2, 3)
    assert np.all((probability > 0.47) & (probability < 0.48))


def test_component_cleanup_rejects_confident_lower_image_island():
    probability = np.full((384, 384), 0.02, dtype=np.float32)
    probability[:150, 20:360] = 0.95
    probability[340:380, 120:260] = 0.99

    support, score = skywater_service.select_sky_support(probability)

    assert score == np.float32(0.95)
    assert support[50, 100]
    assert not support[350, 150]


def test_component_cleanup_returns_empty_when_sky_confidence_is_low():
    probability = np.full((384, 384), 0.20, dtype=np.float32)
    support, score = skywater_service.select_sky_support(probability)

    assert score == np.float32(0.20)
    assert not support.any()


def test_refinement_returns_full_resolution_soft_alpha():
    image = Image.new("RGB", (96, 48), (120, 160, 210))
    x = np.linspace(0, 1, 384, dtype=np.float32)
    probability = np.repeat(x[None, :], 384, axis=0)
    support = probability > 0.15

    alpha = skywater_service.refine_sky_alpha(image, probability, support)

    assert alpha.shape == (48, 96)
    assert alpha.dtype == np.uint8
    assert alpha[:, 0].max() == 0
    assert alpha[:, -1].min() == 255
    assert np.any((alpha > 0) & (alpha < 255))


async def test_service_runs_model_refines_and_reuses_cached_result(tmp_path):
    logits = np.full((1, 4, 384, 384), -4.0, dtype=np.float32)
    logits[:, 0] = 2.0
    logits[:, 1, :200] = 8.0
    session = MagicMock()
    input_meta = MagicMock()
    input_meta.name = "input"
    session.get_inputs.return_value = [input_meta]
    session.run.return_value = [logits]
    service = skywater_service.SkyWaterService(
        model_path=tmp_path / "model.onnx",
        session_factory=lambda _: session,
    )
    encoded = _encoded_test_image()

    first = await service.sky_alpha(encoded)
    second = await service.sky_alpha(encoded)

    assert first.error is None
    assert first.alpha is not None
    assert first.alpha.shape == (40, 80)
    assert first.alpha[:10].mean() > first.alpha[-10:].mean()
    assert second is first
    session.run.assert_called_once()
    assert service.selection_stage(hashlib.sha256(encoded).hexdigest()) == "selecting"


def test_artifact_integrity_rejects_wrong_bytes(tmp_path):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"not the model")
    try:
        skywater_service._verify_artifact(path)
    except RuntimeError as exc:
        assert "expected" in str(exc)
    else:
        raise AssertionError("bad artifact was accepted")
