import json

import httpx
import pytest
from fastapi import FastAPI

from routes import modal_usage as modal_usage_routes


@pytest.mark.asyncio
async def test_account_provisioning_api_starts_and_never_returns_secrets(monkeypatch):
    captured = {}

    class FakeService:
        def start_account_provisioning(self, **values):
            captured.update(values)
            return {"id": "job-1", "status": "running", "progress": 1, "logs": []}

        def provisioning_status(self):
            return {"id": "job-1", "status": "running", "progress": 42, "logs": ["Déploiement"]}

    monkeypatch.setattr(modal_usage_routes, "get_modal_usage_service", lambda: FakeService())
    app = FastAPI()
    app.include_router(modal_usage_routes.router)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/modal/accounts", json={
            "label": "Studio B",
            "profile": "studio-b",
            "modal_token_id": "ak-example",
            "modal_token_secret": "as-example",
            "hf_token": "hf_example",
            "monthly_budget": 50,
        })
        progress = await client.get("/api/modal/provisioning")

    assert response.status_code == 202
    assert captured["profile"] == "studio-b"
    assert captured["modal_token_id"] == "ak-example"
    assert captured["modal_token_secret"] == "as-example"
    assert captured["hf_token"] == "hf_example"
    assert progress.json()["progress"] == 42
    assert "ak-example" not in json.dumps(response.json())
    assert "as-example" not in json.dumps(response.json())
    assert "hf_example" not in json.dumps(response.json())
