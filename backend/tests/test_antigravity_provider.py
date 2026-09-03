import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from PIL import Image
import pytest

from providers.antigravity_provider import AntigravityImageProvider
from providers.base import ExecutionResult


@pytest.mark.asyncio
async def test_antigravity_provider_registers_tools():
    provider = AntigravityImageProvider()
    await provider.connect()
    tools = await provider.list_tools()
    assert len(tools) >= 2
    tool_ids = [t.id for t in tools]
    assert "nano-banana-pro:inpaint-image" in tool_ids
    assert "nano-banana-pro:image-to-image" in tool_ids

    inpaint_tool = next(t for t in tools if t.id == "nano-banana-pro:inpaint-image")
    assert "inpaint-image" in inpaint_tool.task_types
    assert "erase-image" in inpaint_tool.task_types
    assert inpaint_tool.model_vendor == "google"
    assert inpaint_tool.model == "Nano Banana Pro"
    assert inpaint_tool.metadata.get("cli") == "agy"


@pytest.mark.asyncio
async def test_antigravity_provider_inpaint_execution(tmp_path, monkeypatch):
    source_img = tmp_path / "source.png"
    mask_img = tmp_path / "mask.png"
    out_img = tmp_path / "out.png"

    # Create dummy images
    Image.new("RGB", (512, 512), color="blue").save(source_img)
    Image.new("RGB", (512, 512), color="white").save(mask_img)

    provider = AntigravityImageProvider()
    await provider.connect()

    async def mock_wait_for_agy_output(process, output_path, dims, timeout_seconds=300):
        # Create output image
        Image.new("RGB", (dims[0], dims[1]), color="green").save(output_path)
        return b"CLI finished", b"", True

    monkeypatch.setattr("providers.antigravity_provider._agy_executable", lambda: "agy")
    monkeypatch.setattr("agent.v2.tools.antigravity_image._wait_for_agy_output", mock_wait_for_agy_output)

    mock_process = AsyncMock()
    mock_process.returncode = 0
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_process))

    params = {
        "input_images": [str(source_img)],
        "mask": str(mask_img),
        "prompt": "replace with wooden chair",
    }

    results = []
    async for item in provider.execute("nano-banana-pro:inpaint-image", params, output_path=str(out_img)):
        results.append(item)

    assert len(results) == 1
    res = results[0]
    assert isinstance(res, ExecutionResult)
    assert res.success is True
    assert out_img.is_file()
    assert res.metadata.get("model") == "Nano Banana Pro"
    assert res.metadata.get("is_inpaint") is True
