"""The test provider's process-image tool: a real transform, not a dummy.

The base chain in the image editor depends on the process-image contract —
image in, image out at the SAME dimensions, no prompt — and on candidates
being visibly different pixels. The test tool exists so that contract is
demoable and testable without a cloud provider; these tests pin it.
"""

import io
from pathlib import Path

import numpy as np
from PIL import Image

from providers.test_provider import get_test_provider


def _photo(path: Path, size=(64, 48)) -> Path:
    x = np.linspace(0.0, 1.0, size[0])
    arr = np.stack(
        [
            np.tile(x, (size[1], 1)),
            np.tile(x[::-1], (size[1], 1)),
            np.full((size[1], size[0]), 0.5),
        ],
        axis=-1,
    )
    Image.fromarray((arr * 255).astype(np.uint8)).save(path)
    return path


async def _provider():
    provider = get_test_provider()
    await provider.connect()
    return provider


async def _run(parameters):
    provider = await _provider()
    results = [
        event
        async for event in provider.execute("process-image:test-process", parameters)
    ]
    return results[-1]


class TestProcessImageTool:
    async def test_declares_the_process_image_task_type(self):
        provider = await _provider()
        tool = await provider.get_tool("process-image:test-process")
        assert tool is not None
        assert tool.task_type == "process-image"
        assert "prompt" not in tool.parameter_schema["properties"]

    async def test_transforms_input_pixels_at_the_same_dimensions(self, tmp_path):
        source = _photo(tmp_path / "in.png")

        result = await _run(
            {"input_images": [str(source)], "operation": "colorize", "strength": 0.8, "seed": 3}
        )

        assert result.success, result.error
        output = Image.open(io.BytesIO(result.output_data))
        assert output.size == Image.open(source).size
        assert (
            np.asarray(output.convert("RGB")).tolist()
            != np.asarray(Image.open(source).convert("RGB")).tolist()
        )

    async def test_seeds_produce_distinct_candidates(self, tmp_path):
        source = _photo(tmp_path / "in.png")
        base = {"input_images": [str(source)], "operation": "enhance", "strength": 0.7}

        first = await _run({**base, "seed": 1})
        second = await _run({**base, "seed": 2})

        assert first.success and second.success
        assert first.output_data != second.output_data
