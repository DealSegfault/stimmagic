import io

import numpy as np
from PIL import Image

import ben2_service


def _image_bytes(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), (12, 34, 56))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class _FakeInput:
    name = "discovered_ben2_input"


class _FakeSession:
    def __init__(self, output: np.ndarray):
        self.output = output
        self.feeds = []

    def get_inputs(self):
        return [_FakeInput()]

    def run(self, output_names, feed):
        self.feeds.append(feed)
        return [self.output]


def test_preprocess_is_float32_nchw():
    image = Image.new("RGBA", (7, 3), (10, 20, 30, 128))

    result = ben2_service.preprocess_image(image)

    assert result.shape == (1, 3, 1024, 1024)
    assert result.dtype == np.float32
    assert 0.0 <= float(result.min()) <= float(result.max()) <= 1.0
    np.testing.assert_allclose(result[0, :, 0, 0], [10 / 255, 20 / 255, 30 / 255])


async def test_fake_session_uses_discovered_input_without_downloading(
    tmp_path, monkeypatch
):
    model_path = tmp_path / "fake-ben2.onnx"
    model_path.write_bytes(b"fake model supplied by the test")
    output = np.array([[[[0.0, 0.5, 1.0], [0.0, 0.5, 1.0]]]], dtype=np.float32)
    session = _FakeSession(output)
    factory_paths = []

    def forbid_model_download(*args, **kwargs):
        raise AssertionError("fake-session tests must not resolve or download weights")

    monkeypatch.setattr(ben2_service.model_cache, "ensure_model", forbid_model_download)
    service = ben2_service.BEN2Service(
        model_path=model_path,
        session_factory=lambda path: factory_paths.append(path) or session,
    )

    result = await service.subject_alpha(_image_bytes(6, 3))

    assert result.error is None
    assert factory_paths == [model_path]
    assert set(session.feeds[0]) == {"discovered_ben2_input"}
    model_input = session.feeds[0]["discovered_ben2_input"]
    assert model_input.shape == (1, 3, 1024, 1024)
    assert model_input.dtype == np.float32
    assert service._idle.unload_now()
    assert service._session is None
    assert service._input_name is None


async def test_non_square_output_has_correct_dimensions_and_orientation(tmp_path):
    model_path = tmp_path / "fake-ben2.onnx"
    model_path.write_bytes(b"fake")
    # Horizontal ramp repeated vertically: a width/height swap would turn this
    # into the wrong output shape or a vertical ramp.
    output = np.array([[[[0.0, 0.5, 1.0], [0.0, 0.5, 1.0]]]], dtype=np.float32)
    service = ben2_service.BEN2Service(
        model_path=model_path,
        session_factory=lambda path: _FakeSession(output),
    )

    result = await service.subject_alpha(_image_bytes(9, 4))

    assert result.error is None
    assert result.alpha is not None
    assert result.alpha.shape == (4, 9)
    assert np.all(result.alpha[:, 0] == 0)
    assert np.all(result.alpha[:, -1] == 255)
    assert np.all(np.diff(result.alpha[2].astype(np.int16)) >= 0)


def test_constant_output_is_guarded_without_nan_or_thresholding():
    alpha = ben2_service.postprocess_alpha(
        np.full((1, 1, 2, 3), 4.25, dtype=np.float32), width=7, height=5,
    )

    assert alpha.shape == (5, 7)
    assert alpha.dtype == np.uint8
    assert np.count_nonzero(alpha) == 0


def test_progress_distinguishes_download_load_process_and_cached_select(monkeypatch):
    service = ben2_service.BEN2Service()
    monkeypatch.setattr(ben2_service.model_cache, "model_is_present", lambda key: False)
    assert service.selection_stage("image-a") == "downloading_model"

    monkeypatch.setattr(ben2_service.model_cache, "model_is_present", lambda key: True)
    assert service.selection_stage("image-a") == "loading"

    service._load_stage = "ready"
    service._session = object()
    assert service.selection_stage("image-a") == "processing_image"
    service._cached_image_hash = "image-a"
    service._cached_alpha = np.ones((1, 1), dtype=np.uint8)
    assert service.selection_stage("image-a") == "selecting"
