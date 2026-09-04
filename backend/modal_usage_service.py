"""Local multi-account Modal usage tracking and lightweight account scheduler.

The browser only sees redacted account metadata. Modal credentials and proxy
tokens are intentionally not loaded by this module and must stay in the
gateway/deployment environment.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
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
    "B300": "Nvidia B300",
    "NVIDIA B300": "Nvidia B300",
    "B200": "Nvidia B200",
    "NVIDIA B200": "Nvidia B200",
    "H100": "Nvidia H100 SXM5",
    "NVIDIA H100": "Nvidia H100 SXM5",
    "NVIDIA H100 SXM5": "Nvidia H100 SXM5",
    "H200": "Nvidia H200 SXM",
    "NVIDIA H200": "Nvidia H200 SXM",
    "NVIDIA H200 SXM": "Nvidia H200 SXM",
    "L40S": "Nvidia L40S",
    "NVIDIA L40S": "Nvidia L40S",
    "A100": "Nvidia A100, 80 GB",
}
CPU_PRICE_PER_CORE_SECOND = 0.0000131
MEMORY_PRICE_PER_GIB_SECOND = 0.00000222
VOLUME_PRICE_PER_GIB_MONTH = 0.09
ROUTING_MODES = {"auto", "fixed"}

# A crashed desktop process can leave a generation row in ``processing``
# forever.  Such a row must not reserve a Modal account indefinitely.  Modal
# jobs in this project have a maximum timeout of two hours, so six hours is a
# conservative recovery window that still protects genuinely long jobs.
ACTIVE_RESERVATION_TTL_SECONDS = 6 * 60 * 60


def _routing_state_path() -> Path:
    configured = os.environ.get("MODAL_ROUTER_STATE_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "adp-comfy" / "modal-router.state.json"


def _bridge_manifest_path() -> Path:
    configured = os.environ.get("MODAL_ROUTER_BRIDGES_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "adp-comfy" / "modal-router.bridges.json"


@dataclass(frozen=True)
class ModalAccount:
    id: str
    label: str
    workspace: str | None = None
    monthly_budget: float = 30.0
    gpu_type: str = "Nvidia RTX PRO 6000"
    gpu_hour_price: float | None = None
    hd_gpu_type: str | None = None
    hd_gpu_hour_price: float | None = None
    cpu_cores: float = 0.125
    memory_gib: float = 32.0
    hd_memory_gib: float | None = None
    max_concurrency: int = 1
    enabled: bool = True
    endpoint_url: str | None = None
    hd_endpoint_url: str | None = None
    proxy_token_file: str | None = None
    local_port: int | None = None
    local_hd_port: int | None = None


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


def _utc_timestamp(value: Any) -> float | None:
    """Parse a stored timestamp, treating legacy naive values as UTC."""
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class ModalUsageService:
    """Persist generation telemetry and select an eligible Modal account."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config_mtime: float | None = None
        self._accounts: list[ModalAccount] = []
        self._billing_cache: dict[str, dict[str, Any]] = {}
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
            # These columns were added after the first version of the tracker.
            # Keep existing installations upgradeable without requiring a
            # destructive database reset.
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(modal_generation_usage)")
            }
            for name, declaration in (
                ("gpu_type", "TEXT"),
                ("cpu_cores", "REAL"),
                ("memory_gib", "REAL"),
                ("billing_source", "TEXT"),
                ("parameters", "TEXT"),
            ):
                if name not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE modal_generation_usage ADD COLUMN {name} {declaration}"
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
                        hd_gpu_type=(str(item["hd_gpu_type"]) if item.get("hd_gpu_type") else None),
                        hd_gpu_hour_price=(
                            max(0.0, float(item["hd_gpu_hour_price"]))
                            if item.get("hd_gpu_hour_price") is not None
                            else None
                        ),
                        cpu_cores=max(0.0, float(item.get("cpu_cores", 0.125))),
                        memory_gib=max(0.0, float(item.get("memory_gib", 32.0))),
                        hd_memory_gib=(
                            max(0.0, float(item["hd_memory_gib"]))
                            if item.get("hd_memory_gib") is not None
                            else None
                        ),
                        max_concurrency=max(1, int(item.get("max_concurrency", 1))),
                        enabled=bool(item.get("enabled", True)),
                        endpoint_url=str(item["endpoint_url"]).rstrip("/") if item.get("endpoint_url") else None,
                        hd_endpoint_url=str(item["hd_endpoint_url"]).rstrip("/") if item.get("hd_endpoint_url") else None,
                        proxy_token_file=str(item["proxy_token_file"]) if item.get("proxy_token_file") else None,
                        local_port=(max(1, int(item["local_port"])) if item.get("local_port") is not None else None),
                        local_hd_port=(max(1, int(item["local_hd_port"])) if item.get("local_hd_port") is not None else None),
                    )
                )
            self._accounts = accounts
            self._config_mtime = mtime
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._accounts = []
            self._config_mtime = mtime

    def _bridge_accounts(self) -> dict[str, dict[str, Any]]:
        """Read the non-secret bridge manifest written by the gateway."""
        try:
            payload = json.loads(_bridge_manifest_path().read_text(encoding="utf-8"))
            rows = payload.get("accounts", []) if isinstance(payload, dict) else []
            return {
                str(row["id"]): row
                for row in rows
                if isinstance(row, dict) and row.get("id")
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _has_route_metadata(self) -> bool:
        self._load_accounts()
        return bool(self._bridge_accounts()) or any(
            account.endpoint_url or account.proxy_token_file for account in self._accounts
        )

    def _account_route_configured(self, account: ModalAccount) -> bool:
        manifest = self._bridge_accounts().get(account.id)
        if manifest:
            return bool(manifest.get("port"))
        if not account.endpoint_url or not account.proxy_token_file:
            return False
        token_path = Path(account.proxy_token_file).expanduser()
        return token_path.is_file() and os.access(token_path, os.R_OK)

    def _read_routing_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(_routing_state_path().read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        mode = payload.get("mode", "auto") if isinstance(payload, dict) else "auto"
        if mode not in ROUTING_MODES:
            mode = "auto"
        account_id = payload.get("account_id") if isinstance(payload, dict) else None
        return {
            "mode": mode,
            "account_id": str(account_id) if account_id else None,
            "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        }

    def get_routing(self) -> dict[str, Any]:
        """Return the live routing preference and its effective account."""
        self._load_accounts()
        state = self._read_routing_state()
        fixed = next(
            (account for account in self._accounts if account.id == state["account_id"]),
            None,
        )
        fixed_valid = bool(
            state["mode"] == "fixed"
            and fixed
            and fixed.enabled
            and (not self._has_route_metadata() or self._account_route_configured(fixed))
        )
        return {
            **state,
            "effective_account_id": state["account_id"] if fixed_valid else None,
            "fixed_account_valid": fixed_valid if state["mode"] == "fixed" else None,
            "route_accounts_configured": [
                account.id for account in self._accounts if self._account_route_configured(account)
            ],
        }

    def update_routing(self, mode: str, account_id: str | None = None) -> dict[str, Any]:
        """Persist a routing mode without ever persisting credentials."""
        self._load_accounts()
        mode = str(mode or "").strip().lower()
        if mode not in ROUTING_MODES:
            raise ValueError("mode must be 'auto' or 'fixed'")
        account_id = str(account_id).strip() if account_id else None
        if mode == "auto":
            account_id = None
        else:
            account = next((item for item in self._accounts if item.id == account_id), None)
            if not account:
                raise ValueError("Unknown Modal account")
            if not account.enabled:
                raise ValueError("This Modal account is disabled")
            if self._has_route_metadata() and not self._account_route_configured(account):
                raise ValueError("This Modal account has no configured gateway route")

        path = _routing_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": mode,
            "account_id": account_id,
            "updated_at": _utc_now().isoformat(),
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return self.get_routing()

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
    def _cost_for_duration(
        cls,
        account: ModalAccount,
        duration_seconds: float,
        *,
        gpu_type: str | None = None,
        gpu_hour_price: float | None = None,
        memory_gib: float | None = None,
    ) -> float:
        """Estimate Modal resource cost for one execution.

        ``duration_seconds`` is deliberately an estimate: Modal bills the
        resources used by the container, while the local queue only knows the
        job lifecycle.  The resource overrides let us distinguish the H3 HD
        B300/128-GiB endpoint from the normal RTX PRO 6000 endpoint.
        """
        if gpu_hour_price is not None:
            gpu_rate = max(0.0, float(gpu_hour_price)) / 3600
        elif gpu_type:
            gpu_rate = GPU_PRICES_PER_SECOND.get(
                cls._canonical_gpu_type(gpu_type),
                0.0,
            )
        else:
            gpu_rate = cls._gpu_price_per_second(account)
        resource_rate = (
            gpu_rate
            + CPU_PRICE_PER_CORE_SECOND * account.cpu_cores
            + MEMORY_PRICE_PER_GIB_SECOND * (
                account.memory_gib if memory_gib is None else max(0.0, float(memory_gib))
            )
        )
        return max(0.0, duration_seconds * resource_rate)

    @staticmethod
    def _job_parameters(job: dict[str, Any]) -> dict[str, Any]:
        raw = job.get("parameters") if isinstance(job, dict) else None
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _serialize_parameters(value: Any) -> str | None:
        """Keep only routing dimensions; never persist prompts or media IDs."""
        if value is None:
            return None
        try:
            source = json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(source, dict):
            return None
        dimensions = {
            key: source[key]
            for key in ("width", "height", "steps")
            if source.get(key) is not None
        }
        return json.dumps(dimensions, separators=(",", ":")) if dimensions else None

    @staticmethod
    def _is_h3_hd_job(job: dict[str, Any]) -> bool:
        """Match the routing predicate used by ComfyUI-Stimma's client."""
        if str(job.get("backend_name") or "").lower() != "comfyui-modal-h3":
            return False
        params = ModalUsageService._job_parameters(job)
        try:
            width = float(params.get("width"))
            height = float(params.get("height"))
            steps = float(params.get("steps"))
        except (TypeError, ValueError):
            return False
        return width * height / 1_000_000 >= 2.0 and steps >= 20

    @classmethod
    def _resource_for_job(cls, account: ModalAccount, job: dict[str, Any]) -> dict[str, Any]:
        """Return the resource configuration used by a Modal-backed job."""
        backend = str(job.get("backend_name") or "").lower()
        if cls._is_h3_hd_job(job):
            # The deployed HD endpoint is explicitly a full-BF16 B300 with
            # 128 GiB.  Account fields can override this for negotiated rates
            # or a future deployment change.
            gpu_type = account.hd_gpu_type or (
                "Nvidia B300" if account.hd_endpoint_url else account.gpu_type
            )
            gpu_hour_price = account.hd_gpu_hour_price
            memory_gib = account.hd_memory_gib or (
                128.0 if account.hd_endpoint_url else account.memory_gib
            )
        elif backend == "modal-trellis2":
            gpu_type = (
                account.gpu_type
                if account.gpu_type != "Nvidia RTX PRO 6000"
                else "Nvidia H100 SXM5"
            )
            gpu_hour_price = (
                account.gpu_hour_price
                if account.gpu_hour_price is not None
                and account.gpu_type != "Nvidia RTX PRO 6000"
                else None
            )
            memory_gib = account.memory_gib if account.memory_gib != 32.0 else 64.0
        elif backend in {"modal-repaint", "stimma-flux-fill"}:
            gpu_type = "Nvidia L40S"
            gpu_hour_price = None
            memory_gib = 48.0
        else:
            gpu_type = account.gpu_type
            gpu_hour_price = account.gpu_hour_price
            memory_gib = account.memory_gib
        return {
            "gpu_type": gpu_type,
            "gpu_hour_price": gpu_hour_price,
            "memory_gib": memory_gib,
        }

    def _month_start(self) -> str:
        now = _utc_now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    def _account_spend(self, conn: sqlite3.Connection, account_id: str) -> float:
        # Timestamps written by older queue versions are naive UTC strings,
        # while newer ones may include an offset.  Comparing those strings in
        # SQLite is not chronological (and silently drops some rows), so parse
        # them before applying the month boundary.
        month_start = _utc_timestamp(self._month_start()) or 0.0
        rows = conn.execute(
            """
            SELECT COALESCE(actual_cost, estimated_cost, 0) AS cost,
                   COALESCE(started_at, created_at) AS occurred_at
            FROM modal_generation_usage
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchall()
        return sum(
            float(row["cost"] or 0.0)
            for row in rows
            if (_utc_timestamp(row["occurred_at"]) or 0.0) >= month_start
        )

    def _modal_billing_totals(self) -> dict[str, float]:
        """Read the authoritative current-workspace Modal billing report.

        The Modal CLI uses the user's already configured local profile; no API
        token is read or sent to the browser.  If the CLI is unavailable or a
        workspace is offline, callers transparently fall back to the local
        lifecycle estimate.
        """
        if not any(account.workspace for account in self._accounts):
            return {}
        modal_bin = shutil.which("modal")
        if not modal_bin:
            return {}
        cache_key = "__current__"
        cached = self._billing_cache.get(cache_key)
        if cached and time.monotonic() - cached["fetched_at"] < 60:
            return dict(cached["totals"])
        try:
            profile = subprocess.run(
                [modal_bin, "profile", "current"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            workspace = ""
            if profile.returncode == 0:
                lines = [line.strip() for line in profile.stdout.splitlines() if line.strip()]
                if lines:
                    workspace = lines[-1]
            report = subprocess.run(
                [modal_bin, "billing", "report", "--for", "this month", "--json"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if report.returncode != 0:
                return {}
            payload = json.loads(report.stdout)
            if not isinstance(payload, list):
                return {}
            rows = payload
            total = sum(float(row.get("cost") or 0.0) for row in rows if isinstance(row, dict))
            totals = {workspace: total} if workspace else {}
            self._billing_cache[cache_key] = {
                "fetched_at": time.monotonic(),
                "totals": totals,
            }
            return totals
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
            # Billing is an enhancement to the local estimate; it must never
            # make the usage endpoint fail or block a generation.
            return {}

    def _active_count(self, conn: sqlite3.Connection, account_id: str) -> int:
        rows = conn.execute(
            """
            SELECT status, COALESCE(started_at, created_at) AS occurred_at
            FROM modal_generation_usage
            WHERE account_id = ? AND status IN (?, ?, ?)
            """,
            (account_id, *sorted(ACTIVE_STATUSES)),
        ).fetchall()
        now = _utc_now().timestamp()
        return sum(
            1
            for row in rows
            if (timestamp := _utc_timestamp(row["occurred_at"])) is not None
            and now - timestamp <= ACTIVE_RESERVATION_TTL_SECONDS
        )

    def select_account(self) -> str:
        """Select the least-loaded account that remains within its budget."""
        self._load_accounts()
        if not self._accounts:
            return "unassigned"

        routing = self.get_routing()
        if routing["effective_account_id"]:
            return routing["effective_account_id"]

        billing_totals = self._modal_billing_totals()
        with self._lock, self._connect() as conn:
            candidates = []
            eligible = []
            for account in self._accounts:
                if not account.enabled:
                    continue
                if self._has_route_metadata() and not self._account_route_configured(account):
                    continue
                active = self._active_count(conn, account.id)
                local_spend = self._account_spend(conn, account.id)
                spend = (
                    billing_totals.get(account.workspace, local_spend)
                    if account.workspace
                    else local_spend
                )
                if spend >= account.monthly_budget:
                    continue
                eligible.append((active, spend, account))
                if active >= account.max_concurrency:
                    continue
                candidates.append((active / account.max_concurrency, spend / account.monthly_budget, account.id))
            if candidates:
                candidates.sort()
                return candidates[0][2]
            if eligible:
                # A queued job still runs on a real bridge; it must not become
                # ``unassigned`` merely because that bridge is temporarily at
                # its local concurrency limit.  Passing the account through to
                # the STP client makes it wait in that account's queue and keeps
                # the spend attributable.
                eligible.sort(key=lambda item: (item[0] / item[2].max_concurrency,
                                                item[1] / item[2].monthly_budget,
                                                item[2].id))
                return eligible[0][2].id
            return "unassigned"

    def account_for_job(self, profile_id: str, job_id: Any) -> str | None:
        """Return the account already reserved for a queued generation."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT account_id FROM modal_generation_usage WHERE profile_id = ? AND job_id = ?",
                (str(profile_id or "default"), str(job_id)),
            ).fetchone()
        account_id = row["account_id"] if row else None
        return account_id if account_id and account_id != "unassigned" else None

    def record_event(self, event: str, data: dict[str, Any]) -> None:
        """Record a generation lifecycle event emitted by the existing queue."""
        if not event.startswith("generation_job_"):
            return
        # Completion/failure events can arrive without the earlier queue or
        # start event (for example after a websocket reconnect).  Load the
        # account configuration before resolving route metadata so those
        # events remain attributable as well.
        self._load_accounts()
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
            event_account_id = data.get("modal_account_id") or job.get("modal_account_id")
            account_id = (
                str(event_account_id)
                if event_account_id
                else existing["account_id"]
                if existing and existing["account_id"] != "unassigned"
                else self.select_account()
            )
            created_at = job.get("created_at") or (existing["created_at"] if existing else _utc_now().isoformat())
            started_at = job.get("started_at") or (existing["started_at"] if existing else None)
            completed_at = job.get("completed_at")
            start_timestamp = _utc_timestamp(started_at)
            end_timestamp = _utc_timestamp(completed_at)
            duration = (
                max(0.0, end_timestamp - start_timestamp)
                if start_timestamp is not None and end_timestamp is not None
                else None
            )
            account = next((item for item in self._accounts if item.id == account_id), None)
            resource = self._resource_for_job(account, job) if account else {}
            # The STP executor reports elapsed time while it owns a concrete
            # Modal bridge.  Prefer it over GenerationJob wall time, which may
            # include time waiting behind another account-local queue.
            reported_runtime = job.get("modal_runtime_seconds")
            try:
                if reported_runtime is not None and float(reported_runtime) >= 0:
                    duration = float(reported_runtime)
            except (TypeError, ValueError):
                pass
            if job.get("modal_gpu_type"):
                resource["gpu_type"] = job["modal_gpu_type"]
                resource["gpu_hour_price"] = None
            if job.get("modal_memory_gib") is not None:
                resource["memory_gib"] = job["modal_memory_gib"]
            estimated_cost = None
            if duration is not None and account:
                estimated_cost = self._cost_for_duration(account, duration, **resource)

            conn.execute(
                """
                INSERT INTO modal_generation_usage
                    (profile_id, job_id, account_id, status, task_type, model_name, backend_name,
                     created_at, started_at, completed_at, duration_seconds, estimated_cost, error,
                     gpu_type, cpu_cores, memory_gib, billing_source, parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    error = excluded.error,
                    gpu_type = COALESCE(excluded.gpu_type, modal_generation_usage.gpu_type),
                    cpu_cores = COALESCE(excluded.cpu_cores, modal_generation_usage.cpu_cores),
                    memory_gib = COALESCE(excluded.memory_gib, modal_generation_usage.memory_gib),
                    billing_source = COALESCE(excluded.billing_source, modal_generation_usage.billing_source),
                    parameters = COALESCE(excluded.parameters, modal_generation_usage.parameters)
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
                    resource.get("gpu_type"),
                    account.cpu_cores if account else None,
                    resource.get("memory_gib"),
                    "local_estimate" if estimated_cost is not None else None,
                    self._serialize_parameters(job.get("parameters")),
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
                        source_columns = {
                            row[1] for row in source_conn.execute("PRAGMA table_info(generation_jobs)")
                        }
                        parameters_column = ", parameters" if "parameters" in source_columns else ""
                        rows = source_conn.execute(
                            f"""
                            SELECT id, status, task_type, model_name, backend_name,
                                   created_at, started_at, completed_at, error{parameters_column}
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
                             backend_name, created_at, started_at, completed_at, duration_seconds, error,
                             parameters)
                        VALUES (?, ?, 'unassigned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(profile_id, job_id) DO UPDATE SET
                            parameters = CASE
                                WHEN excluded.parameters IS NOT NULL THEN excluded.parameters
                                ELSE modal_generation_usage.parameters
                            END
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
                                    _utc_timestamp(row["completed_at"])
                                    - _utc_timestamp(row["started_at"]),
                                )
                                if _utc_timestamp(row["completed_at"]) is not None
                                and _utc_timestamp(row["started_at"]) is not None
                                else None
                            ),
                            row["error"],
                            self._serialize_parameters(row["parameters"] if "parameters" in row.keys() else None),
                        ),
                    )

    def _route_attribution_cutoff(self) -> float | None:
        """Return when the currently configured bridge metadata became valid."""
        paths = []
        configured = os.environ.get("MODAL_ROUTER_ACCOUNTS_FILE", "").strip()
        paths.append(
            Path(configured).expanduser()
            if configured
            else Path.home() / ".config" / "adp-comfy" / "modal-router.accounts.json"
        )
        paths.append(_bridge_manifest_path())
        mtimes = []
        for path in paths:
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                pass
        return min(mtimes) if mtimes else None

    def _reconcile_unassigned_modal_jobs(self, conn: sqlite3.Connection) -> None:
        """Recover route attribution and resource metadata for H3 jobs.

        This is intentionally conservative: only a single currently routed
        account can be inferred safely for unassigned rows, and only H3 jobs
        created after the account/bridge configuration existed are moved.
        Already-attributed rows are refreshed only when their resource facts
        are missing or were produced by this reconciliation.  Ambiguous
        historical rows remain ``unassigned`` instead of being presented as
        fact.
        """
        routed = [
            account for account in self._accounts
            if account.enabled and self._account_route_configured(account)
        ]
        if len(routed) != 1:
            return
        account = routed[0]
        cutoff = self._route_attribution_cutoff()
        rows = conn.execute(
            """
            SELECT id, account_id, billing_source, task_type, model_name,
                   backend_name, parameters, started_at, completed_at,
                   duration_seconds
            FROM modal_generation_usage
            WHERE backend_name = 'comfyui-modal-h3'
              AND (
                  account_id = 'unassigned'
                  OR (
                      account_id = ?
                      AND (billing_source = 'route_reconciliation' OR gpu_type IS NULL)
                  )
              )
            """,
            (account.id,),
        ).fetchall()
        for row in rows:
            started_timestamp = _utc_timestamp(row["started_at"])
            if row["account_id"] == "unassigned" and cutoff is not None and (
                started_timestamp is None or started_timestamp < cutoff
            ):
                continue
            duration = row["duration_seconds"]
            if duration is None:
                start = _utc_timestamp(row["started_at"])
                end = _utc_timestamp(row["completed_at"])
                duration = max(0.0, end - start) if start is not None and end is not None else None
            job = {
                "task_type": row["task_type"],
                "model_name": row["model_name"],
                "backend_name": row["backend_name"],
                "parameters": row["parameters"],
            }
            resource = self._resource_for_job(account, job)
            estimated_cost = (
                self._cost_for_duration(account, float(duration), **resource)
                if duration is not None
                else None
            )
            conn.execute(
                    """
                UPDATE modal_generation_usage
                SET account_id = ?, estimated_cost = ?, gpu_type = ?,
                    cpu_cores = ?, memory_gib = ?, billing_source = ?
                WHERE id = ?
                  AND (
                      account_id = 'unassigned'
                      OR (
                          account_id = ?
                          AND (billing_source = 'route_reconciliation' OR gpu_type IS NULL)
                      )
                  )
                """,
                (
                    account.id,
                    estimated_cost,
                    resource.get("gpu_type"),
                    account.cpu_cores,
                    resource.get("memory_gib"),
                    (
                        "route_reconciliation"
                        if row["account_id"] == "unassigned"
                        else "resource_reconciliation"
                    ) if estimated_cost is not None else None,
                    row["id"],
                    account.id,
                ),
            )

    def _public_account(
        self,
        account: ModalAccount,
        conn: sqlite3.Connection,
        billing_totals: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        estimated_spend = self._account_spend(conn, account.id)
        actual_spend = (
            billing_totals.get(account.workspace)
            if billing_totals and account.workspace
            else None
        )
        spend = actual_spend if actual_spend is not None else estimated_spend
        active = self._active_count(conn, account.id)
        return {
            "id": account.id,
            "label": account.label,
            "workspace": account.workspace,
            "enabled": account.enabled,
            "status": "available" if account.enabled and spend < account.monthly_budget else "budget_reached",
            "monthly_budget": account.monthly_budget,
            "spent": round(spend, 6),
            "estimated_spent": round(estimated_spend, 6),
            "actual_spent": round(actual_spend, 6) if actual_spend is not None else None,
            "spend_source": "modal_billing" if actual_spend is not None else "local_estimate",
            "remaining": round(max(0.0, account.monthly_budget - spend), 6),
            "active_jobs": active,
            "max_concurrency": account.max_concurrency,
            "gpu_type": account.gpu_type,
            "gpu_hour_price": round(self._gpu_price_per_second(account) * 3600, 6),
            "hd_gpu_type": account.hd_gpu_type or (
                "Nvidia B300" if account.hd_endpoint_url else None
            ),
            "hd_gpu_hour_price": round(
                (
                    account.hd_gpu_hour_price
                    if account.hd_gpu_hour_price is not None
                    else GPU_PRICES_PER_SECOND.get(
                        self._canonical_gpu_type(
                            account.hd_gpu_type
                            or ("Nvidia B300" if account.hd_endpoint_url else "")
                        ),
                        0.0,
                    )
                    * 3600
                ),
                6,
            ) if account.hd_endpoint_url or account.hd_gpu_type or account.hd_gpu_hour_price is not None else None,
            "cpu_cores": account.cpu_cores,
            "memory_gib": account.memory_gib,
            "hd_memory_gib": account.hd_memory_gib or (128.0 if account.hd_endpoint_url else None),
            "route_configured": self._account_route_configured(account),
            "route_status": "configured" if self._account_route_configured(account) else "not_configured",
        }

    def snapshot(self, limit: int = 50) -> dict[str, Any]:
        self._load_accounts()
        self._backfill_existing_jobs()
        billing_totals = self._modal_billing_totals()
        with self._lock, self._connect() as conn:
            self._reconcile_unassigned_modal_jobs(conn)
            accounts = [
                self._public_account(account, conn, billing_totals)
                for account in self._accounts
            ]
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
                    "spend_source": (
                        "modal_billing"
                        if any(account["spend_source"] == "modal_billing" for account in accounts)
                        else "local_estimate"
                    ),
                },
                "accounts": accounts,
                "generations": generations,
                "routing": self.get_routing(),
            }

    def _generation_count(self, conn: sqlite3.Connection) -> int:
        month_start = _utc_timestamp(self._month_start()) or 0.0
        rows = conn.execute(
            "SELECT COALESCE(started_at, created_at) AS occurred_at FROM modal_generation_usage"
        ).fetchall()
        return sum(
            1
            for row in rows
            if (_utc_timestamp(row["occurred_at"]) or 0.0) >= month_start
        )


_service: ModalUsageService | None = None


def get_modal_usage_service() -> ModalUsageService:
    global _service
    if _service is None:
        _service = ModalUsageService()
    return _service
