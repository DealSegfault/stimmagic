#!/usr/bin/env python3
"""Run one dev command in an isolated, parent-aware process group.

The Stimma dev CLI launches npm/npx, which in turn launches more processes.
This helper keeps the whole component in one process group and force-cleans
that group if the CLI parent disappears (including a terminal close or a
SIGKILL, where the parent cannot run its own cleanup handler).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


POLL_SECONDS = 0.2
TERM_GRACE_SECONDS = 3.0


def main() -> int:
    command = sys.argv[1:]
    if not command:
        print("process-supervisor.py: missing command", file=sys.stderr)
        return 2

    if os.name == "nt":
        child = subprocess.Popen(command)
    else:
        # The helper is not a process-group leader yet, so setsid() gives the
        # component a private session and PGID equal to this PID.  All npm,
        # nodemon, Vite, Python, and Tauri descendants inherit it.
        os.setsid()
        child = subprocess.Popen(command)

    parent_pid = os.getppid()
    stopping = False
    stop_started_at = 0.0

    def forward(signum: int, _frame: object) -> None:
        nonlocal stopping, stop_started_at
        if stopping:
            return
        stopping = True
        stop_started_at = time.monotonic()
        if os.name == "nt":
            child.send_signal(signum)
            return

        # Ignore this signal in the supervisor while forwarding it to the
        # private group; otherwise the supervisor would interrupt itself and
        # never get a chance to wait for the child to exit gracefully.
        signal.signal(signum, signal.SIG_IGN)
        try:
            os.killpg(os.getpgid(os.getpid()), signum)
        except OSError:
            try:
                child.send_signal(signum)
            except OSError:
                pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, forward)
    if os.name != "nt" and hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, forward)

    while True:
        return_code = child.poll()
        if return_code is not None:
            return return_code

        # If the CLI parent was killed with SIGKILL, no signal handler can run
        # there.  Detect reparenting and kill the complete private group.
        if os.name != "nt" and os.getppid() != parent_pid:
            try:
                os.killpg(os.getpgid(os.getpid()), signal.SIGKILL)
            except OSError:
                pass
            return 137

        if stopping and time.monotonic() - stop_started_at >= TERM_GRACE_SECONDS:
            if os.name != "nt":
                try:
                    os.killpg(os.getpgid(os.getpid()), signal.SIGKILL)
                except OSError:
                    pass
            else:
                child.kill()
            return child.wait()

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
