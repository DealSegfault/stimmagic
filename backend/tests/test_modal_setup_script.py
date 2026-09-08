import os
import subprocess
from pathlib import Path


def test_setup_reuses_active_modal_apps_unless_forced(tmp_path):
    calls = tmp_path / "modal-calls.log"
    modal = tmp_path / "modal"
    modal.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$MODAL_TEST_CALLS"
case "$1 $2" in
  "--version ") echo "modal test" ;;
  "secret list") echo '[]' ;;
  "workspace proxy-tokens") echo '{"Modal-Key":"wk-test","Modal-Secret":"ws-test"}' ;;
  "app list") echo '[{"description":"comfyui-minimax-h3","state":"deployed"},{"description":"maya-latentsync","state":"initializing..."}]' ;;
esac
""",
        encoding="utf-8",
    )
    modal.chmod(0o755)
    script = Path(__file__).parents[2] / "infra" / "bin" / "setup-modal.sh"
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "MODAL_TEST_CALLS": str(calls)}
    env.pop("HF_TOKEN", None)
    base = [
        str(script),
        "--modal-token-id", "ak-test",
        "--modal-token-secret", "as-test",
        "--modal-profile", "test-profile",
        "--proxy-token-file", str(tmp_path / "proxy.json"),
        "--skip-downloads",
        "--skip-desktop",
        "--skip-trellis2",
    ]

    subprocess.run(base, env=env, check=True, capture_output=True, text=True)
    assert not any(line.startswith("deploy ") for line in calls.read_text().splitlines())

    calls.write_text("", encoding="utf-8")
    subprocess.run(
        [*base, "--force-redeploy", "--skip-lipsync"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    forced_calls = calls.read_text().splitlines()
    assert "deploy --strategy recreate modal_h3.py" in forced_calls
    assert not any(line.startswith("workspace proxy-tokens") for line in forced_calls)
