import json
import os
import pytest
from pathlib import Path
from PIL import Image

from database import ChatItem
from agent.v2.conversation import (
    _item_to_message,
    _inject_last_user_context,
    _estimate_tokens,
    build_messages,
)


@pytest.mark.asyncio
async def test_user_message_multimodal_attachment(tmp_path, monkeypatch):
    # Create a dummy image
    img_path = tmp_path / "test_window.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_path)

    # Mock get_workspace_dir to return tmp_path
    monkeypatch.setattr("agent.v2.workspace.get_workspace_dir", lambda chat_id, project_id=None: tmp_path)

    item = ChatItem(
        chat_id=42,
        item_type="user_message",
        message_text="Generate a prompt with this window",
        item_metadata=json.dumps({
            "workspace_files": [
                {"filename": "test_window.png", "media_id": 99, "path": str(img_path)}
            ]
        })
    )

    msg = _item_to_message(item, include_images=True)
    assert msg is not None
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 2  # text + 1 image

    text_part = msg["content"][0]
    img_part = msg["content"][1]

    assert text_part["type"] == "text"
    assert "<Picture 1>" in text_part["text"]
    assert "test_window.png" in text_part["text"]

    assert img_part["type"] == "image_url"
    assert img_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_inject_last_user_context_multimodal():
    messages = [
        {"role": "system", "content": "system prompt"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "user original text"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,xyz"}}
            ]
        }
    ]

    _inject_last_user_context(messages, ["<system-reminder>test</system-reminder>"])

    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert "<system-reminder>test</system-reminder>" in user_content[0]["text"]
    assert "user original text" in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"
