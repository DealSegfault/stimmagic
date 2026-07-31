"""Tests for POST /api/tools/execute/{full_tool_id}.

The synchronous lightweight-tool route. It bypasses the generation queue
entirely: no GenerationJob, no tiles, no Asset — the caller gets an output path
back in the response. The op-stack editor uses it for backend-executed
parametric ops (darkroom tools and chain filters the client has no parity
implementation for), where a queued job would be the wrong shape.
"""

from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image


def _gradient(path: Path) -> Path:
    """A gradient across all channels — any colour op moves it."""
    x = np.linspace(0.0, 1.0, 64)
    arr = np.stack(
        [np.tile(x, (64, 1)), np.tile(x[::-1], (64, 1)), np.full((64, 64), 0.5)],
        axis=-1,
    )
    Image.fromarray((arr * 255).astype(np.uint8)).save(path)
    return path


class TestExecuteLightweightTool:
    async def test_executes_a_filter_and_returns_an_output_path(
        self, generation_client: httpx.AsyncClient, tmp_path: Path
    ):
        source = _gradient(tmp_path / "input.png")

        response = await generation_client.post(
            "/api/tools/execute/builtin:levels",
            json={
                "parameters": {
                    "input_images": [str(source)],
                    "brightness": 40,
                }
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True, body.get("error")

        outputs = body["outputs"]
        assert outputs, "the tool returned no outputs"
        out_path = Path(next(v for v in outputs.values() if isinstance(v, str)))
        assert out_path.exists()

        # Server-owned placement: never next to the input, always managed staging.
        assert out_path.parent != source.parent
        assert out_path.parent.parts[-2:] == ("staging", "generated")

        before = np.asarray(Image.open(source).convert("RGB"), dtype=np.float32)
        after = np.asarray(Image.open(out_path).convert("RGB"), dtype=np.float32)
        assert after.shape == before.shape
        assert np.abs(after - before).mean() > 1.0, "brightness change had no effect"

    async def test_unknown_tool_is_404(self, generation_client: httpx.AsyncClient):
        response = await generation_client.post(
            "/api/tools/execute/builtin:no-such-tool",
            json={"parameters": {}},
        )
        assert response.status_code == 404

    async def test_queued_provider_tools_are_rejected(
        self, generation_client: httpx.AsyncClient, tmp_path: Path
    ):
        """This route is only for tools that execute in-process."""
        response = await generation_client.post(
            "/api/tools/execute/test:text-to-image:test-model",
            json={"parameters": {"prompt": "x"}},
        )
        assert response.status_code == 400
        assert "lightweight" in response.json()["detail"].lower()

    async def test_legacy_inputs_field_does_not_break_the_call(
        self, generation_client: httpx.AsyncClient, tmp_path: Path
    ):
        """Older callers sent a second `inputs` dict the provider never accepted.

        The field is gone from the request model; a client still sending it must
        be ignored rather than 422'd or crashed.
        """
        source = _gradient(tmp_path / "legacy.png")
        response = await generation_client.post(
            "/api/tools/execute/builtin:levels",
            json={
                "parameters": {"input_images": [str(source)], "brightness": 40},
                "inputs": {"image": str(source)},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True
