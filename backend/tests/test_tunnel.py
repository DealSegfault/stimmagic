import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from tunnel_service import TunnelService


@pytest.mark.asyncio
async def test_tunnel_status_endpoint(client: AsyncClient):
    response = await client.get("/api/tunnel/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "installed" in data


@pytest.mark.asyncio
async def test_tunnel_start_and_stop_mock(client: AsyncClient):
    service = TunnelService.get_instance()
    with patch.object(service, "start_tunnel", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = {
            "running": True,
            "starting": False,
            "url": "https://test-tunnel.trycloudflare.com",
            "error": None,
            "installed": True,
            "port": 9192,
        }
        res_start = await client.post("/api/tunnel/start", json={"port": 9192})
        assert res_start.status_code == 200
        assert res_start.json()["url"] == "https://test-tunnel.trycloudflare.com"

    with patch.object(service, "stop_tunnel", new_callable=AsyncMock) as mock_stop:
        mock_stop.return_value = {
            "running": False,
            "starting": False,
            "url": None,
            "error": None,
            "installed": True,
            "port": 9192,
        }
        res_stop = await client.post("/api/tunnel/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["running"] is False
