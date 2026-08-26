---
name: stimma-local-setup
description: Set up this Stimma checkout on a new machine with the installed Codex CLI, the local ComfyUI-to-Modal gateway, and optional Modal GPU deployments. Use when bootstrapping, repairing, or verifying this repository for a collaborator without requiring a Stimma account or an LLM API key.
---

# Stimma Local Setup

Keep Stimma Cloud optional. Never initiate Stimma sign-in unless the user asks
for cloud credits or hosted Stimma models.

## Local bootstrap

1. Work from the repository root.
2. Run `codex --version` and `codex login status`. Codex owns ChatGPT
   authentication; never read, copy, or persist its credentials.
3. If Codex is not logged in, ask the user to run `codex` and choose **Sign in
   with ChatGPT**, then resume after `codex login status` succeeds.
4. Run `infra/bin/bootstrap-local.sh`. This creates the ignored
   `infra/.runtime/ComfyUI` runtime and links the tracked Stimma custom node.
5. Do not add an OpenAI API key. The backend auto-detects Codex CLI and exposes
   it as the keyless `Codex CLI · ChatGPT` provider.

## Modal setup

Modal deployment can incur external cost. Confirm that the user wants the
deployment before running it.

- Interactive: `infra/bin/setup-modal.sh --interactive`
- Non-interactive, only when the user has supplied the values in the current
  environment: `HF_TOKEN=... MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=... infra/bin/setup-modal.sh`

Never echo, invent, commit, or paste secrets into tracked files. Modal stores
its own credentials. The generated local proxy token stays at
`~/.config/adp-comfy/modal-proxy-token.json` with mode `0600`; it must contain
the real Modal `wk-/ws-` Proxy Token created by the setup script, not the
`ak-/as-` account token.

## Start and verify

1. Start the bridge with `infra/bin/start-gateway.sh`.
2. Start Stimma with `infra/bin/start-stimma.sh`. For a browser-only app, use
   `STIMMA_MODAL_GATEWAY_URL=ws://127.0.0.1:8188/stp-v1 tools/stimma dev web`.
3. Verify Codex remains connected with `codex login status`.
4. Verify the settings API reports `readiness.has_agent_llm: true` and that the
   UI lists `Codex CLI · ChatGPT` without asking for a Stimma account or API
   key.
5. Verify the configured generation provider separately. Agent chat can be
   ready through Codex even when no Modal generation service has been deployed.
