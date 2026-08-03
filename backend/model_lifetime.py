"""Idle lifetime management for large in-process inference models."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from core.logging import get_logger

log = get_logger(__name__)


def idle_seconds(environment_key: str, default: float) -> float:
    """Read a positive idle timeout, falling back safely on bad input."""

    raw = os.getenv(environment_key)
    if raw is None:
        return default
    try:
        value = float(raw)
        return value if value > 0 else default
    except ValueError:
        log.warning(f"Ignoring invalid {environment_key} idle timeout")
        return default


class IdleModelHandle:
    """Unload a model after its last active inference has been idle.

    A lease covers loading as well as inference. The timer callback and lease
    acquisition share one lock, so an unload can never land between a caller's
    load check and its model use.
    """

    def __init__(self, name: str, timeout_seconds: float, unload: Callable[[], None]):
        self._name = name
        self._timeout_seconds = timeout_seconds
        self._unload = unload
        self._lock = threading.RLock()
        self._active = 0
        self._timer: threading.Timer | None = None

    @contextmanager
    def use(self) -> Iterator[None]:
        with self._lock:
            self._cancel_timer_locked()
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                if self._active == 0:
                    self._schedule_locked()

    def unload_now(self) -> bool:
        """Unload immediately when idle; primarily useful for shutdown/tests."""

        with self._lock:
            self._cancel_timer_locked()
            if self._active:
                return False
            self._run_unload_locked()
            return True

    def _schedule_locked(self) -> None:
        self._cancel_timer_locked()
        timer = threading.Timer(self._timeout_seconds, self._on_timer)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._active == 0:
                self._run_unload_locked()

    def _run_unload_locked(self) -> None:
        try:
            self._unload()
            log.info(f"{self._name}: unloaded after idle timeout")
        except Exception:
            log.exception(f"{self._name}: idle unload failed")
