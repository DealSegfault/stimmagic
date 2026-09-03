from unittest.mock import AsyncMock, MagicMock

import pytest

import gateway_service as gateway_module


class FakeProcess:
    pid = 12345

    def __init__(self, returncode=None):
        self.returncode = returncode


def _fake_script(tmp_path):
    script = tmp_path / "start-gateway.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.mark.asyncio
async def test_start_waits_for_gateway_and_returns_success(monkeypatch, tmp_path):
    service = gateway_module.GatewayService()
    process = FakeProcess()
    statuses = iter([
        {"running": False, "partial": False},
        {"running": True, "partial": False},
    ])

    monkeypatch.setattr(gateway_module, "GATEWAY_SCRIPT", _fake_script(tmp_path))
    monkeypatch.setattr(gateway_module, "START_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(gateway_module, "POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(gateway_module, "_h3_provider_configured", lambda: False)
    monkeypatch.setattr(
        gateway_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(service, "get_status", lambda: next(statuses, {"running": True, "partial": False}))
    monkeypatch.setattr(service, "_broadcast_status", AsyncMock())

    result = await service.start_gateway()

    assert result["running"] is True
    assert service._error is None
    assert service._is_starting is False


@pytest.mark.asyncio
async def test_start_reports_supervisor_exit(monkeypatch, tmp_path):
    service = gateway_module.GatewayService()
    process = FakeProcess(returncode=23)

    monkeypatch.setattr(gateway_module, "GATEWAY_SCRIPT", _fake_script(tmp_path))
    monkeypatch.setattr(gateway_module, "POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(gateway_module, "_h3_provider_configured", lambda: False)
    monkeypatch.setattr(
        gateway_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: {"running": False, "partial": False, "error": service._error},
    )
    monkeypatch.setattr(service, "_broadcast_status", AsyncMock())

    result = await service.start_gateway()

    assert result["running"] is False
    assert "arrêté prématurément" in result["error"]
    assert "gateway-service.log" in result["error"]


@pytest.mark.asyncio
async def test_start_reports_timeout_instead_of_silent_success(monkeypatch, tmp_path):
    service = gateway_module.GatewayService()

    monkeypatch.setattr(gateway_module, "GATEWAY_SCRIPT", _fake_script(tmp_path))
    monkeypatch.setattr(gateway_module, "START_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(gateway_module, "POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(gateway_module, "_h3_provider_configured", lambda: False)
    monkeypatch.setattr(
        gateway_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcess()),
    )
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: {"running": False, "partial": False, "error": service._error},
    )
    monkeypatch.setattr(service, "_broadcast_status", AsyncMock())

    result = await service.start_gateway()

    assert result["running"] is False
    assert "n’est pas prête" in result["error"]


def test_gateway_process_filter_never_targets_backend():
    assert gateway_module._is_gateway_process("python modal_bridge.py")
    assert gateway_module._is_gateway_process("python main.py --cpu --port 8188")
    assert not gateway_module._is_gateway_process("uv run python main.py --port 9191")


@pytest.mark.asyncio
async def test_stop_uses_safe_cleanup_for_all_gateway_ports(monkeypatch):
    service = gateway_module.GatewayService()
    cleanup = MagicMock()
    monkeypatch.setattr(gateway_module, "_kill_orphan_gateway_processes", cleanup)
    monkeypatch.setattr(gateway_module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service, "_broadcast_status", AsyncMock())
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: {"running": False, "partial": False, "error": service._error},
    )

    await service.stop_gateway()

    cleanup.assert_called_once_with()
    assert service._error is None
