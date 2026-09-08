"""Supervise one authenticated local Modal bridge per configured account."""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default


def _token(path: Path) -> tuple[str, str]:
    payload = _read_json(path, {})
    return str(payload.get("Modal-Key") or ""), str(payload.get("Modal-Secret") or "")


def _port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class BridgeSupervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.processes: dict[str, subprocess.Popen] = {}
        self.occupied_keys: set[str] = set()
        self.specs: list[dict] = []
        self.stopping = False

    def load_specs(self) -> list[dict]:
        payload = _read_json(Path(self.args.accounts_file).expanduser(), {})
        raw_accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
        specs = []
        next_port = 8190
        for account in raw_accounts:
            if not isinstance(account, dict) or account.get("enabled") is False:
                continue
            endpoint = str(account.get("endpoint_url") or "").rstrip("/")
            token_path = Path(str(account.get("proxy_token_file") or "")).expanduser()
            key, secret = _token(token_path)
            if not endpoint or not key or not secret:
                continue
            port = int(account.get("local_port") or next_port)
            hd_endpoint = str(account.get("hd_endpoint_url") or "").rstrip("/")
            hd_port = int(account.get("local_hd_port") or port + 1) if hd_endpoint else None
            specs.append({
                "id": str(account["id"]),
                "endpoint": endpoint,
                "hd_endpoint": hd_endpoint,
                "key": key,
                "secret": secret,
                "port": port,
                "hd_port": hd_port,
            })
            next_port = max(next_port, (hd_port or port) + 1)
        if not specs and self.args.fallback_url:
            key, secret = _token(Path(self.args.fallback_token).expanduser())
            if key and secret:
                specs.append({
                    "id": "legacy",
                    "endpoint": self.args.fallback_url.rstrip("/"),
                    "hd_endpoint": (self.args.fallback_hd_url or "").rstrip("/"),
                    "key": key,
                    "secret": secret,
                    "port": 8190,
                    "hd_port": 8191 if self.args.fallback_hd_url else None,
                })
        return specs

    def write_manifest(self) -> None:
        path = Path(self.args.manifest).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [
            {
                "id": spec["id"],
                "port": spec["port"],
                **({"hd_port": spec["hd_port"]} if spec.get("hd_port") else {}),
            }
            for spec in self.specs if spec["id"] != "legacy"
        ]}
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def start_one(self, spec: dict, hd: bool = False) -> None:
        endpoint = spec["hd_endpoint"] if hd else spec["endpoint"]
        port = spec["hd_port"] if hd else spec["port"]
        if not endpoint or not port:
            return
        key = f"{spec['id']}{'-hd' if hd else ''}"
        if _port_is_listening(port):
            self.occupied_keys.add(key)
            return
        self.occupied_keys.discard(key)
        log_path = Path(self.args.log_dir) / f"modal-bridge-{key}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({
            "COMFY_MODAL_URL": endpoint,
            "MODAL_PROXY_TOKEN_ID": spec["key"],
            "MODAL_PROXY_TOKEN_SECRET": spec["secret"],
            "MODAL_BRIDGE_PORT": str(port),
        })
        with log_path.open("ab") as log_file:
            self.processes[key] = subprocess.Popen(
                [os.environ.get("MODAL_BRIDGE_PYTHON", sys.executable), self.args.bridge_script],
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    def start_all(self) -> None:
        self.specs = self.load_specs()
        self.write_manifest()
        for spec in self.specs:
            self.start_one(spec)
            if spec.get("hd_endpoint"):
                self.start_one(spec, hd=True)

    def stop_all(self) -> None:
        self.stopping = True
        for process in list(self.processes.values()):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    process.terminate()
        for process in list(self.processes.values()):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()
        self.occupied_keys.clear()

    def run(self) -> int:
        self.start_all()
        while not self.stopping:
            for spec in self.specs:
                for hd in (False, True):
                    if hd and not spec.get("hd_endpoint"):
                        continue
                    key = f"{spec['id']}{'-hd' if hd else ''}"
                    port = spec["hd_port"] if hd else spec["port"]
                    if key in self.occupied_keys:
                        if _port_is_listening(port):
                            continue
                        self.occupied_keys.discard(key)
                    process = self.processes.get(key)
                    if process is None or process.poll() is not None:
                        self.processes.pop(key, None)
                        self.start_one(spec, hd=hd)
            time.sleep(2)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts-file", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bridge-script", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--fallback-url", default="")
    parser.add_argument("--fallback-hd-url", default="")
    parser.add_argument("--fallback-token", default="")
    args = parser.parse_args()
    supervisor = BridgeSupervisor(args)
    for event in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(event, lambda *_: supervisor.stop_all())
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
