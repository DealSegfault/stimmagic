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
