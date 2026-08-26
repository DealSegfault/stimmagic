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
deployment before running it. A direct request to clone this repository and
finish the installation, made after the user supplied Modal credentials in the
current agent context, is sufficient confirmation; do not ask for the same
credentials again.

- Interactive: `infra/bin/setup-modal.sh --interactive`
- Non-interactive, only when the user has supplied the values in the current
  environment: `MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=... infra/bin/setup-modal.sh`
- `HF_TOKEN` is optional. Without it, install MiniMax H3 video and LatentSync,
  and skip the licensed Repaint and TRELLIS.2 extras.

Never echo, invent, commit, or paste secrets into tracked files. Modal stores
its own credentials. The generated local proxy token stays at
`~/.config/adp-comfy/modal-proxy-token.json` with mode `0600`; it must contain
the real Modal `wk-/ws-` Proxy Token created by the setup script, not the
`ak-/as-` account token.

## Finish the macOS handoff

The Modal setup scripts perform this handoff automatically after H3 deployment
and model download:

1. Create the executable `~/Desktop/Lancer Stimma.command` shortcut.
2. Start the local Modal bridge and the Stimma desktop development app.
3. Wait until the settings API reports `readiness.has_agent_llm: true`, the
   gateway is running, and at least one connected `minimax_h3_*` video tool is
   available.
4. Only after all checks pass, create
   `~/Desktop/STIMMA - Installation terminée.txt` with the message that the
   shortcut is on the Desktop and Stimma is ready for the first video.

If the user explicitly skipped H3 downloads or a readiness check fails, leave
the shortcut in place but do not create the success memo and do not claim the
installation is ready. Report the relevant log paths under
`~/Library/Logs/Stimma` instead. Never put a credential in the shortcut, memo,
logs, or Git.

For later launches, use the Desktop shortcut or run
`infra/bin/launch-stimma.sh`. For a browser-only development app, use
`STIMMA_MODAL_GATEWAY_URL=ws://127.0.0.1:8188/stp-v1 tools/stimma dev web`.
