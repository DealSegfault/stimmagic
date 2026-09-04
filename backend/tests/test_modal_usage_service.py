import json
import sqlite3
from datetime import datetime, timedelta, timezone

from modal_usage_service import ModalUsageService


def test_modal_usage_tracks_generation_lifecycle(tmp_path, monkeypatch):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": "workspace-a",
                        "label": "Workspace A",
                        "monthly_budget": 30,
                        "gpu_hour_price": 3.6,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODAL_ROUTER_ACCOUNTS_FILE", str(accounts_path))
    monkeypatch.setenv("MODAL_ROUTER_BRIDGES_FILE", str(tmp_path / "no-bridges.json"))
    monkeypatch.setenv("STIMMA_DATA_DIR", str(tmp_path / "data"))

    service = ModalUsageService()
    job = {
        "id": 42,
        "model_name": "minimax-h3",
        "task_type": "text-to-video",
        "created_at": "2026-08-21T10:00:00+00:00",
    }
    service.record_event("generation_job_queued", {"profile_id": "default", "job": job})
    service.record_event(
        "generation_job_started",
        {
            "profile_id": "default",
            "job": {**job, "started_at": "2026-08-21T10:00:01+00:00"},
        },
    )
    service.record_event(
        "generation_job_completed",
        {
            "profile_id": "default",
            "job": {
                **job,
                "started_at": "2026-08-21T10:00:01+00:00",
                "completed_at": "2026-08-21T10:02:01+00:00",
            },
        },
    )

    snapshot = service.snapshot()
    assert snapshot["accounts"][0]["id"] == "workspace-a"
    assert snapshot["generations"][0]["status"] == "completed"
    assert snapshot["generations"][0]["duration_seconds"] == 120.0
    assert snapshot["generations"][0]["estimated_cost"] == 0.128721


def test_modal_routing_persists_auto_and_fixed_modes(tmp_path, monkeypatch):
    accounts_path = tmp_path / "accounts.json"
    token_path = tmp_path / "modal-token.json"
    token_path.write_text('{"Modal-Key":"key","Modal-Secret":"secret"}', encoding="utf-8")
    accounts_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": "workspace-a",
                        "label": "Workspace A",
                        "endpoint_url": "https://workspace-a.modal.run",
                        "proxy_token_file": str(token_path),
                    },
                    {"id": "workspace-b", "label": "Workspace B"},
                ]
            }
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "routing.json"
    monkeypatch.setenv("MODAL_ROUTER_ACCOUNTS_FILE", str(accounts_path))
    monkeypatch.setenv("MODAL_ROUTER_STATE_FILE", str(state_path))
    monkeypatch.setenv("MODAL_ROUTER_BRIDGES_FILE", str(tmp_path / "bridges.json"))
    monkeypatch.setenv("STIMMA_DATA_DIR", str(tmp_path / "data"))

    service = ModalUsageService()
    assert service.get_routing()["mode"] == "auto"
    assert service.get_routing()["route_accounts_configured"] == ["workspace-a"]

    routing = service.update_routing("fixed", "workspace-a")
    assert routing["mode"] == "fixed"
    assert routing["effective_account_id"] == "workspace-a"
    assert service.select_account() == "workspace-a"
    assert service.account_for_job("default", 999) is None

    routing = service.update_routing("auto")
    assert routing["mode"] == "auto"
    assert routing["account_id"] is None

    try:
        service.update_routing("fixed", "workspace-b")
    except ValueError as exc:
        assert "gateway route" in str(exc)
    else:
        raise AssertionError("unconfigured account should not be selectable")


def test_modal_account_selection_recovers_stale_reservation_and_keeps_queue_attributed(tmp_path, monkeypatch):
    accounts_path = tmp_path / "accounts.json"
    token_path = tmp_path / "modal-token.json"
    token_path.write_text('{"Modal-Key":"key","Modal-Secret":"secret"}', encoding="utf-8")
    accounts_path.write_text(
        json.dumps({
            "accounts": [{
                "id": "workspace-a",
                "workspace": "workspace-a",
                "endpoint_url": "https://workspace-a.modal.run",
                "proxy_token_file": str(token_path),
                "hd_endpoint_url": "https://workspace-a-hd.modal.run",
                "max_concurrency": 1,
            }]
        }),
        encoding="utf-8",
    )
    bridge_path = tmp_path / "bridges.json"
    bridge_path.write_text(json.dumps({"accounts": [{"id": "workspace-a", "port": 8190, "hd_port": 8191}]}))
    monkeypatch.setenv("MODAL_ROUTER_ACCOUNTS_FILE", str(accounts_path))
    monkeypatch.setenv("MODAL_ROUTER_BRIDGES_FILE", str(bridge_path))
    monkeypatch.setenv("STIMMA_DATA_DIR", str(tmp_path / "data"))

    service = ModalUsageService()
    monkeypatch.setattr(service, "_modal_billing_totals", lambda: {})
    stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with sqlite3.connect(service._db_path) as conn:
        conn.execute(
            """
            INSERT INTO modal_generation_usage
                (profile_id, job_id, account_id, status, backend_name, started_at)
            VALUES ('default', 'stale', 'workspace-a', 'processing', 'comfyui-modal-h3', ?)
            """,
            (stale,),
        )

    # The stale row no longer blocks the only route.  A second queued job is
    # still assigned to that route rather than becoming unassigned.
    assert service.select_account() == "workspace-a"
    service.record_event(
        "generation_job_queued",
        {
            "profile_id": "default",
            "job": {
                "id": 7,
                "backend_name": "comfyui-modal-h3",
                "parameters": json.dumps({"width": 1216, "height": 704, "steps": 8}),
            },
        },
    )
    assert service.account_for_job("default", 7) == "workspace-a"


def test_modal_hd_resource_uses_b300_rate_and_memory(tmp_path, monkeypatch):
    accounts_path = tmp_path / "accounts.json"
    accounts_path.write_text(json.dumps({"accounts": [{
        "id": "workspace-a",
        "gpu_type": "Nvidia RTX PRO 6000",
        "hd_endpoint_url": "https://workspace-a-hd.modal.run",
    }]}), encoding="utf-8")
    monkeypatch.setenv("MODAL_ROUTER_ACCOUNTS_FILE", str(accounts_path))
    monkeypatch.setenv("STIMMA_DATA_DIR", str(tmp_path / "data"))

    service = ModalUsageService()
    service._load_accounts()
    account = service._accounts[0]
    resource = service._resource_for_job(account, {
        "backend_name": "comfyui-modal-h3",
        "parameters": json.dumps({"width": 2048, "height": 1024, "steps": 20}),
    })
    assert resource["gpu_type"] == "Nvidia B300"
    assert resource["memory_gib"] == 128.0
    assert service._cost_for_duration(account, 1, **resource) > service._cost_for_duration(account, 1)
