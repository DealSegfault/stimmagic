import pytest
from pathlib import Path
from inpaint_service import compile_inpaint_prompt
from agent.v2.tools.antigravity_image import build_antigravity_prompt


def test_compile_inpaint_prompt_formats_edit_map():
    zones = [
        {
            "color_name": "YELLOW",
            "target": "apartment door @image1",
            "operation": "replace",
            "instruction": "use the exact design from reference @image2",
        },
        {
            "color_name": "RED",
            "target": "lamp on table",
            "operation": "remove",
            "instruction": "reconstruct clean wood",
        },
    ]
    compiled = compile_inpaint_prompt(zones)
    assert "EDIT MAP" in compiled
    assert "ZONE 1 — YELLOW" in compiled
    assert "Target: apartment door @image1" in compiled
    assert "Operation: replace" in compiled
    assert "Instruction: use the exact design from reference @image2" in compiled
    assert "ZONE 2 — RED" in compiled
    assert "GLOBAL LOCK:" in compiled
    assert "Everything not selected by a zone remains unchanged." in compiled


def test_build_antigravity_prompt_injects_inpaint_system_prompt(tmp_path):
    prompt_text = compile_inpaint_prompt([{"color_name": "YELLOW", "target": "door", "operation": "replace", "instruction": "new"}])
    rendered = build_antigravity_prompt(
        prompt_text,
        [(1, tmp_path / "src.png"), (2, tmp_path / "mask.png")],
        tmp_path / "output.png",
        expected_dimensions=[1344, 768],
    )
    assert "SOURCE-LOCKED MULTI-ZONE IMAGE INPAINTING EDITOR" in rendered
    assert "OPERATING SYSTEM DIRECTIVE (INPAINTING)" in rendered
    assert "<Picture 1> (media_id=1)" in rendered
    assert "<Picture 2> (media_id=2)" in rendered


def test_build_antigravity_prompt_injects_reference_system_prompt(tmp_path):
    rendered = build_antigravity_prompt(
        "Generate realistic room with character",
        [(1, tmp_path / "char.png")],
        tmp_path / "output.png",
        expected_dimensions=[1024, 1024],
    )
    assert "OPERATING SYSTEM DIRECTIVE (REFERENCE FIDELITY)" in rendered
    assert "SOURCE FIDELITY > CREATIVE REINTERPRETATION" in rendered
