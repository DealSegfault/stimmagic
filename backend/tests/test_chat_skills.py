"""Tests for enabling and disabling skills in a chat."""

import json

import pytest


async def _create_chat(client) -> int:
    response = await client.post("/api/chats", json={})
    assert response.status_code == 200
    return response.json()["id"]


@pytest.mark.anyio
async def test_disable_skill_removes_matching_injection(client):
    chat_id = await _create_chat(client)
    injection = await client.post(
        f"/api/chats/{chat_id}/items",
        json={
            "item_type": "stimpack_injection",
            "message_text": "## Skill: Alpha\n\nAlpha body",
            "item_metadata": json.dumps({
                "skill_name": "test-pack/alpha",
                "skill_display_name": "Alpha",
            }),
        },
    )
    assert injection.status_code == 200
    injection_id = injection.json()["id"]

    response = await client.post(
        f"/api/chats/{chat_id}/disable-skill",
        json={"name": "test-pack/alpha"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "disabled",
        "skill_name": "test-pack/alpha",
        "deleted_ids": [injection_id],
    }

    items = await client.get(f"/api/chats/{chat_id}/items")
    assert items.status_code == 200
    assert injection_id not in {item["id"] for item in items.json()["items"]}

    # Disabling an already-disabled skill is a successful no-op.
    response = await client.post(
        f"/api/chats/{chat_id}/disable-skill",
        json={"name": "test-pack/alpha"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "not_loaded"


@pytest.mark.anyio
async def test_disable_skill_accepts_legacy_metadata_key(client):
    chat_id = await _create_chat(client)
    injection = await client.post(
        f"/api/chats/{chat_id}/items",
        json={
            "item_type": "stimpack_injection",
            "message_text": "legacy",
            "item_metadata": json.dumps({"stimpack_name": "legacy-pack"}),
        },
    )
    assert injection.status_code == 200

    response = await client.post(
        f"/api/chats/{chat_id}/disable-skill",
        json={"name": "legacy-pack"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


@pytest.mark.anyio
async def test_disable_skill_accepts_qualified_name_for_legacy_slug(client, monkeypatch):
    chat_id = await _create_chat(client)
    injection = await client.post(
        f"/api/chats/{chat_id}/items",
        json={
            "item_type": "stimpack_injection",
            "message_text": "legacy",
            "item_metadata": json.dumps({"skill_name": "alpha"}),
        },
    )
    assert injection.status_code == 200

    class _Pack:
        name = "test-pack"

    class _Skill:
        qualified_name = "test-pack/alpha"
        slug = "alpha"

    monkeypatch.setattr("agent.v2.stimpacks.find_skill", lambda name: (_Pack(), _Skill()))
    response = await client.post(
        f"/api/chats/{chat_id}/disable-skill",
        json={"name": "test-pack/alpha"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


@pytest.mark.anyio
async def test_disable_skill_missing_chat_404s(client):
    response = await client.post(
        "/api/chats/999999/disable-skill",
        json={"name": "test-pack/alpha"},
    )
    assert response.status_code == 404
