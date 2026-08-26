# MiniMax H3 & Video Generation Guidelines

## Model Mode Selection Rules (MANDATORY)

When generating or proposing MiniMax H3 video generation modes:

1. **0 Reference Image (Text only)**:
   - Mode: `T2V` (`minimax_h3_t2v` / `minimax_h3_t2v_turbo`)

2. **Exactly 1 Reference Image (Starting Frame)**:
   - Mode: `I2V` / `FL2VA` (`minimax_h3_i2v` / `minimax_h3_i2v_turbo`)
   - Uses `input_images=[media_id]` as first frame (00:00).

3. **$\ge 2$ Reference Images (Character + Environment/Location, Multi-character)**:
   - Mode: `R2V` / `Ref2VA` (`minimax_h3_r2v` / `minimax_h3_r2v_turbo`)
   - **STRICT PROHIBITION**: NEVER use `I2V` when multiple references are active. `I2V` will fail to inject separate character and environment references.
   - Map each visual reference explicitly via `<Picture 1>`, `<Picture 2>` semantic alignment tags in Context-IR.

4. **1 Reference Image used as semantic anchor (Identity/Style without locking frame 0)**:
   - Mode: `R2V` (`minimax_h3_r2v_turbo`)

## OpenCode CLI Direct Interaction

When instructed to use OpenCode, chat via OpenCode, or perform actions with OpenCode CLI:

1. **Default Model & Direct Execution**:
   - Default model: `opencode-go/deepseek-v4-flash` (auto-configured in `~/.config/opencode/opencode.jsonc`).
   - Run prompt / action automatically (using PTY wrapper for clean output):
     ```bash
     script -q /dev/null opencode run "<message or instruction>" --dir <target_dir> --auto
     ```

2. **Image Support**:
   - Pass images via `-f <image_path>`:
     ```bash
     script -q /dev/null opencode run "<prompt>" -f <image_path> -m opencode-go/mimo-v2.5 --auto
     ```

3. **Session Continuity**:
   - Continue last session: `script -q /dev/null opencode run "<follow-up>" -c --auto`
   - Resume specific session: `script -q /dev/null opencode run "<message>" -s <sessionID> --auto`
   - List sessions: `opencode session list`

4. **Autonomous Edits & Multi-Agent**:
   - Scope files: `script -q /dev/null opencode run "<prompt>" -f <file_path> --auto`
   - Use agents (`plan`, `summary`): `script -q /dev/null opencode run "<prompt>" --agent plan --auto`


## Modal Infrastructure & Setup for Agents

When configuring or deploying Modal containers for an agent:
1. **Local bootstrap**: Run `infra/bin/bootstrap-local.sh` from the repository root.
2. **Interactive Wizard**: Run `python3 infra/bin/setup-interactive.py` or `infra/bin/setup-modal.sh -i`.
3. **Non-interactive / Automated**:
   ```bash
   HF_TOKEN="hf_..." MODAL_TOKEN_ID="ak-..." MODAL_TOKEN_SECRET="as-..." infra/bin/setup-modal.sh
   ```
4. Full manual and troubleshooting: see [MAN_MODAL.md](MAN_MODAL.md).

