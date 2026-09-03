import json

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
