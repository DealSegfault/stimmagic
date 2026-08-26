"""Local multi-account Modal usage tracking and lightweight account scheduler.

The browser only sees redacted account metadata. Modal credentials and proxy
tokens are intentionally not loaded by this module and must stay in the
gateway/deployment environment.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app_dirs


ACTIVE_STATUSES = {"queued", "assigned", "processing"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
MODAL_PRICING_URL = "https://modal.com/pricing"

# Modal's public standard resource rates, refreshed from the official pricing
# page on 2026-08-21. Values are USD per second. Account config can override
# the GPU rate when a workspace has a negotiated or non-standard rate.
GPU_PRICES_PER_SECOND = {
    "Nvidia B300": 0.001972,
    "Nvidia B200": 0.001736,
    "Nvidia H200 SXM": 0.001261,
    "Nvidia H100 SXM5": 0.001097,
    "Nvidia RTX PRO 6000": 0.000842,
    "Nvidia A100, 80 GB": 0.000694,
    "Nvidia A100, 40 GB": 0.000583,
    "Nvidia L40S": 0.000542,
    "Nvidia A10": 0.000306,
    "Nvidia L4": 0.000222,
    "Nvidia T4": 0.000164,
}
GPU_ALIASES = {
    "RTX-PRO-6000": "Nvidia RTX PRO 6000",
    "RTX PRO 6000": "Nvidia RTX PRO 6000",
    "RTX_PRO_6000": "Nvidia RTX PRO 6000",
    "L40S": "Nvidia L40S",
    "A100": "Nvidia A100, 80 GB",
}
CPU_PRICE_PER_CORE_SECOND = 0.0000131
MEMORY_PRICE_PER_GIB_SECOND = 0.00000222
VOLUME_PRICE_PER_GIB_MONTH = 0.09


@dataclass(frozen=True)
class ModalAccount:
    id: str
    label: str
    workspace: str | None = None
    monthly_budget: float = 30.0
    gpu_type: str = "Nvidia RTX PRO 6000"
    gpu_hour_price: float | None = None
    cpu_cores: float = 0.125
    memory_gib: float = 32.0
    max_concurrency: int = 1
    enabled: bool = True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


class ModalUsageService:
    """Persist generation telemetry and select an eligible Modal account."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config_mtime: float | None = None
        self._accounts: list[ModalAccount] = []
        self._db_path = app_dirs.get_data_dir() / "modal_usage.sqlite3"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def configured(self) -> bool:
        self._load_accounts()
        return bool(self._accounts)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS modal_generation_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_type TEXT,
                    model_name TEXT,
                    backend_name TEXT,
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL,
                    estimated_cost REAL,
                    actual_cost REAL,
                    error TEXT,
                    UNIQUE(profile_id, job_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_modal_usage_created ON modal_generation_usage(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_modal_usage_account ON modal_generation_usage(account_id)"
            )

    def _load_accounts(self) -> None:
        config_path_value = os.environ.get("MODAL_ROUTER_ACCOUNTS_FILE", "")
        config_path = (
            Path(config_path_value).expanduser()
            if config_path_value
            else Path.home() / ".config" / "adp-comfy" / "modal-router.accounts.json"
        )
        try:
            mtime = config_path.stat().st_mtime
        except OSError:
            self._accounts = []
            self._config_mtime = None
            return
        if self._config_mtime == mtime:
            return

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            raw_accounts = payload.get("accounts", payload) if isinstance(payload, dict) else payload
            accounts: list[ModalAccount] = []
            for item in raw_accounts or []:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                accounts.append(
                    ModalAccount(
                        id=str(item["id"]),
                        label=str(item.get("label") or item["id"]),
                        workspace=str(item["workspace"]) if item.get("workspace") else None,
                        monthly_budget=max(0.0, float(item.get("monthly_budget", 30.0))),
                        gpu_type=str(item.get("gpu_type") or "Nvidia RTX PRO 6000"),
                        gpu_hour_price=(
                            max(0.0, float(item["gpu_hour_price"]))
                            if item.get("gpu_hour_price") is not None
                            else None
                        ),
                        cpu_cores=max(0.0, float(item.get("cpu_cores", 0.125))),
                        memory_gib=max(0.0, float(item.get("memory_gib", 32.0))),
                        max_concurrency=max(1, int(item.get("max_concurrency", 1))),
                        enabled=bool(item.get("enabled", True)),
                    )
                )
            self._accounts = accounts
            self._config_mtime = mtime
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._accounts = []
            self._config_mtime = mtime

    @staticmethod
    def _canonical_gpu_type(value: str) -> str:
        normalized = str(value or "").strip()
        return GPU_ALIASES.get(normalized.upper(), normalized or "Nvidia RTX PRO 6000")

    @staticmethod
    def _gpu_price_per_second(account: ModalAccount) -> float:
        if account.gpu_hour_price is not None:
            return account.gpu_hour_price / 3600
        return GPU_PRICES_PER_SECOND.get(
            ModalUsageService._canonical_gpu_type(account.gpu_type),
            0.0,
        )

    @classmethod
    def _cost_for_duration(cls, account: ModalAccount, duration_seconds: float) -> float:
        resource_rate = (
            cls._gpu_price_per_second(account)
            + CPU_PRICE_PER_CORE_SECOND * account.cpu_cores
            + MEMORY_PRICE_PER_GIB_SECOND * account.memory_gib
        )
        return max(0.0, duration_seconds * resource_rate)

    def _month_start(self) -> str:
        now = _utc_now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    def _account_spend(self, conn: sqlite3.Connection, account_id: str) -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(COALESCE(actual_cost, estimated_cost, 0)), 0) AS spend
            FROM modal_generation_usage
            WHERE account_id = ? AND COALESCE(started_at, created_at) >= ?
            """,
            (account_id, self._month_start()),
        ).fetchone()
        return float(row["spend"] or 0.0)

    def _active_count(self, conn: sqlite3.Connection, account_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM modal_generation_usage WHERE account_id = ? AND status IN (?, ?, ?)",
            (account_id, *sorted(ACTIVE_STATUSES)),
        ).fetchone()
        return int(row["count"] or 0)

    def select_account(self) -> str:
        """Select the least-loaded account that remains within its budget."""
        self._load_accounts()
        if not self._accounts:
            return "unassigned"

        with self._lock, self._connect() as conn:
            candidates = []
            for account in self._accounts:
                if not account.enabled:
                    continue
                active = self._active_count(conn, account.id)
                spend = self._account_spend(conn, account.id)
                if spend >= account.monthly_budget:
                    continue
                if active >= account.max_concurrency:
                    continue
                candidates.append((active / account.max_concurrency, spend / account.monthly_budget, account.id))
            if not candidates:
                return "unassigned"
            candidates.sort()
            return candidates[0][2]

    def record_event(self, event: str, data: dict[str, Any]) -> None:
        """Record a generation lifecycle event emitted by the existing queue."""
        if not event.startswith("generation_job_"):
            return
        job = data.get("job") or {}
        job_id = job.get("id")
        if job_id is None:
            return
        profile_id = str(data.get("profile_id") or "default")
        status_by_event = {
            "generation_job_queued": "queued",
            "generation_job_started": "processing",
            "generation_job_completed": "completed",
            "generation_job_failed": "failed",
            "generation_job_cancelled": "cancelled",
        }
        status = status_by_event.get(event)
        if not status:
            return

        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT account_id, created_at, started_at FROM modal_generation_usage WHERE profile_id = ? AND job_id = ?",
                (profile_id, str(job_id)),
            ).fetchone()
            account_id = (
                existing["account_id"]
                if existing and existing["account_id"] != "unassigned"
                else self.select_account()
            )
            created_at = job.get("created_at") or (existing["created_at"] if existing else _utc_now().isoformat())
            started_at = job.get("started_at") or (existing["started_at"] if existing else None)
            completed_at = job.get("completed_at")
            start = _parse_datetime(started_at)
            end = _parse_datetime(completed_at)
            duration = max(0.0, (end - start).total_seconds()) if start and end else None
            account = next((item for item in self._accounts if item.id == account_id), None)
            estimated_cost = None
            if duration is not None and account:
                estimated_cost = self._cost_for_duration(account, duration)

            conn.execute(
                """
                INSERT INTO modal_generation_usage
                    (profile_id, job_id, account_id, status, task_type, model_name, backend_name,
                     created_at, started_at, completed_at, duration_seconds, estimated_cost, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, job_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    status = excluded.status,
                    task_type = excluded.task_type,
                    model_name = excluded.model_name,
                    backend_name = excluded.backend_name,
                    created_at = COALESCE(modal_generation_usage.created_at, excluded.created_at),
                    started_at = COALESCE(excluded.started_at, modal_generation_usage.started_at),
                    completed_at = excluded.completed_at,
                    duration_seconds = COALESCE(excluded.duration_seconds, modal_generation_usage.duration_seconds),
                    estimated_cost = COALESCE(excluded.estimated_cost, modal_generation_usage.estimated_cost),
                    error = excluded.error
                """,
                (
                    profile_id,
                    str(job_id),
                    account_id,
                    status,
                    job.get("task_type"),
                    job.get("model_name"),
                    job.get("backend_name"),
                    created_at,
                    started_at,
                    completed_at,
                    duration,
                    estimated_cost,
                    job.get("error"),
                ),
            )

    def _backfill_existing_jobs(self) -> None:
        """Import jobs created before the Modal tracker was installed.

        Historical jobs cannot be attributed to a workspace reliably, so they
        remain explicitly marked as ``unassigned`` and do not affect budgets.
        """
        data_root = app_dirs.get_data_dir()
        if not data_root.is_dir():
            return
        with self._lock, self._connect() as usage_conn:
            for profile_dir in data_root.iterdir():
                database_path = profile_dir / "stimma_v1.db"
                if not profile_dir.is_dir() or not database_path.is_file():
                    continue
                try:
                    with sqlite3.connect(database_path, timeout=1) as source_conn:
                        source_conn.row_factory = sqlite3.Row
                        rows = source_conn.execute(
                            """
                            SELECT id, status, task_type, model_name, backend_name,
                                   created_at, started_at, completed_at, error
                            FROM generation_jobs
                            """
                        ).fetchall()
                except (sqlite3.Error, OSError):
                    continue
                for row in rows:
                    usage_conn.execute(
                        """
                        INSERT OR IGNORE INTO modal_generation_usage
                            (profile_id, job_id, account_id, status, task_type, model_name,
                             backend_name, created_at, started_at, completed_at, duration_seconds, error)
                        VALUES (?, ?, 'unassigned', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            profile_dir.name,
                            str(row["id"]),
                            row["status"],
                            row["task_type"],
                            row["model_name"],
                            row["backend_name"],
                            row["created_at"],
                            row["started_at"],
                            row["completed_at"],
                            (
                                max(
                                    0.0,
                                    (
                                        _parse_datetime(row["completed_at"])
                                        - _parse_datetime(row["started_at"])
                                    ).total_seconds(),
                                )
                                if _parse_datetime(row["completed_at"]) and _parse_datetime(row["started_at"])
                                else None
                            ),
                            row["error"],
                        ),
                    )

    def _public_account(self, account: ModalAccount, conn: sqlite3.Connection) -> dict[str, Any]:
        spend = self._account_spend(conn, account.id)
        active = self._active_count(conn, account.id)
        return {
            "id": account.id,
            "label": account.label,
            "workspace": account.workspace,
            "enabled": account.enabled,
            "status": "available" if account.enabled and spend < account.monthly_budget else "budget_reached",
            "monthly_budget": account.monthly_budget,
            "spent": round(spend, 6),
            "remaining": round(max(0.0, account.monthly_budget - spend), 6),
            "active_jobs": active,
            "max_concurrency": account.max_concurrency,
            "gpu_type": account.gpu_type,
            "gpu_hour_price": round(self._gpu_price_per_second(account) * 3600, 6),
            "cpu_cores": account.cpu_cores,
            "memory_gib": account.memory_gib,
        }

    def snapshot(self, limit: int = 50) -> dict[str, Any]:
        self._load_accounts()
        self._backfill_existing_jobs()
        with self._lock, self._connect() as conn:
            accounts = [self._public_account(account, conn) for account in self._accounts]
            rows = conn.execute(
                "SELECT * FROM modal_generation_usage ORDER BY COALESCE(created_at, '') DESC, id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
            generations = [dict(row) for row in rows]
            for item in generations:
                item["estimated_cost"] = round(float(item["estimated_cost"] or 0.0), 6)
                item["actual_cost"] = round(float(item["actual_cost"]), 6) if item["actual_cost"] is not None else None
                item["duration_seconds"] = round(float(item["duration_seconds"]), 2) if item["duration_seconds"] is not None else None

            total_spent = round(sum(account["spent"] for account in accounts), 6)
            total_budget = round(sum(account["monthly_budget"] for account in accounts), 6)
            return {
                "configured": bool(accounts),
                "updated_at": _utc_now().isoformat(),
                "pricing": {
                    "source": MODAL_PRICING_URL,
                    "gpu_prices_per_second": GPU_PRICES_PER_SECOND,
                    "cpu_price_per_core_second": CPU_PRICE_PER_CORE_SECOND,
                    "memory_price_per_gib_second": MEMORY_PRICE_PER_GIB_SECOND,
                    "volume_price_per_gib_month": VOLUME_PRICE_PER_GIB_MONTH,
                },
                "summary": {
                    "spent": total_spent,
                    "budget": total_budget,
                    "remaining": round(max(0.0, total_budget - total_spent), 6),
                    "active_jobs": sum(account["active_jobs"] for account in accounts),
                    "generation_count": self._generation_count(conn),
                },
                "accounts": accounts,
                "generations": generations,
            }

    def _generation_count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM modal_generation_usage WHERE COALESCE(started_at, created_at) >= ?",
            (self._month_start(),),
        ).fetchone()
        return int(row["count"] or 0)


_service: ModalUsageService | None = None


def get_modal_usage_service() -> ModalUsageService:
    global _service
    if _service is None:
        _service = ModalUsageService()
    return _service
