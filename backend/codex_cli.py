"""Local Codex CLI transport for Stimma's LLM abstraction.

This transport deliberately shells out to ``codex exec`` instead of reading
Codex credentials or calling the OpenAI API.  The CLI owns ChatGPT OAuth,
refreshes it, and returns one structured next-step decision to Stimma.  Stimma
keeps ownership of tool execution and its permission model.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from core.logging import get_logger


log = get_logger(__name__)


class CodexCLIError(RuntimeError):
    """Raised when Codex CLI cannot produce a usable completion."""


@dataclass
class CodexCLIToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class CodexCLICompletion:
    content: str = ""
    tool_calls: List[CodexCLIToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0


CODEX_IMAGE_MAX_SIDE = 1024
CODEX_IMAGE_JPEG_QUALITY = 85


def _codex_executable() -> str:
    configured = os.environ.get("STIMMA_CODEX_CLI", "").strip()
    candidates = [
        configured,
        shutil.which("codex") or "",
        str(Path.home() / ".local" / "bin" / "codex"),
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise CodexCLIError(
        "Codex CLI was not found. Install it or set STIMMA_CODEX_CLI to its executable path."
    )


def _scrub_large_data(value: Any) -> Any:
    """Keep the planner prompt bounded when a message contains an inline asset."""
    if isinstance(value, list):
        return [_scrub_large_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _scrub_large_data(item) for key, item in value.items()}
    if isinstance(value, str) and len(value) > 4096 and (
        value.startswith("data:") or "base64," in value[:128]
    ):
        return "[inline binary asset omitted; use the available Stimma media tools]"
    return value


def _normalize_codex_image(source: bytes | Path, destination: Path) -> bool:
    """Write a bounded, orientation-correct JPEG for ``codex exec --image``.

    The CLI's image upload path is unreliable for large source PNGs. Chat
    messages already use the same bounded JPEG policy for provider vision, so
    apply it here too before handing files to the local CLI.
    """
    try:
        from PIL import Image, ImageOps

        stream = BytesIO(source) if isinstance(source, bytes) else source
        with Image.open(stream) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        if max(image.size) > CODEX_IMAGE_MAX_SIDE:
            scale = CODEX_IMAGE_MAX_SIDE / max(image.size)
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)),
                Image.LANCZOS,
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(
            destination,
            format="JPEG",
            quality=CODEX_IMAGE_JPEG_QUALITY,
            optimize=True,
        )
        image.close()
        return True
    except Exception as exc:
        log.warning("Failed to normalize image for codex exec", error=str(exc))
        return False


def _last_jsonl_agent_message(stdout: bytes) -> Optional[str]:
    """Return the last completed agent message emitted by ``codex --json``."""
    last_message: Optional[str] = None
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        if (
            isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            last_message = item["text"]
    return last_message


def _codex_image_args(
    messages: List[Dict[str, Any]],
    temp_dir: Path,
) -> List[str]:
    """Materialize multimodal message images as bounded CLI image files."""
    image_args: List[str] = []
    image_count = 0
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                continue
            url = (block.get("image_url") or {}).get("url", "")
            source: bytes | Path | None = None
            if isinstance(url, str) and url.startswith("data:") and "base64," in url:
                try:
                    source = base64.b64decode(url.split("base64,", 1)[1])
                except Exception as exc:
                    log.warning("Failed to decode image for codex exec", error=str(exc))
            elif isinstance(url, str) and url.startswith("file://"):
                source = Path(unquote(url[7:]))

            if source is None:
                continue
            image_count += 1
            image_file = temp_dir / f"input_image_{image_count}.jpg"
            if _normalize_codex_image(source, image_file):
                image_args.extend(["--image", str(image_file)])
    return image_args


def _output_schema(tool_names: List[str]) -> Dict[str, Any]:
    name_schema: Dict[str, Any] = {"type": "string"}
    if tool_names:
        name_schema["enum"] = sorted(set(tool_names))
    return {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": name_schema,
                        "arguments_json": {"type": "string"},
                    },
                    "required": ["id", "name", "arguments_json"],
                    "additionalProperties": False,
                },
            },
            "finish_reason": {
                "type": "string",
                "enum": ["stop", "tool_calls"],
            },
        },
        "required": ["content", "tool_calls", "finish_reason"],
        "additionalProperties": False,
    }


def _planner_prompt(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    workdir: Optional[Path] = None,
) -> str:
    safe_messages = _scrub_large_data(messages)
    safe_tools = tools or []
    workspace_hint = str(workdir) if workdir else "the current Stimma chat workspace"
    return (
        "You are the language-model planner inside Stimma. Work only from the "
        "conversation and tool schemas below. Do not run shell commands, browse, "
        "inspect files, edit files, or invoke Codex built-in tools. Stimma itself "
        "will execute any requested tool and return its result in the next call.\n\n"
        "Return exactly one structured next step matching the supplied output "
        "schema. If a Stimma tool is required, set finish_reason to tool_calls, "
        "use its exact name, and put a valid JSON object encoded as a string in "
        "arguments_json. Otherwise answer the user in content and set "
        "finish_reason to stop. Do not invent tool results. System messages in "
        "the conversation are authoritative.\n\n"
        "STIMMA IMAGE ROUTING RULES:\n"
        "- For still image generation (photo, illustration, scene visual), the chat uses its direct image generation pipeline (Codex / Antigravity), intentionally bypassing the local Stimma ComfyUI tool store.\n"
        "- When Antigravity is authoritative, call the exact Stimma tool antigravity_image with the complete prompt and ordered reference_media_ids; it materializes the files and invokes the real agy image generation pipeline. Do not call local image-to-image adapters.\n"
        "- Do not report still image generation as unavailable due to missing `.stimma/tools/` adapters. Never route still images to video adapters (MiniMax H3 / Wan22 / LTX).\n"
        "- Keep CLI prompts lean and focused on the scene description or delta. For iterative modifications in the same chat, use `--continue` or `resume --last`.\n"
        "- Include the model tag in the image filename (e.g. `<name>_antigravity.png` or `<name>_codex.png`) and display title in `show` (e.g. `<Title> · Antigravity` or `<Title> · Codex ImageGen`).\n"
        "- Respond by producing the generated image directly or utilizing agent tools (`run_code`, etc.) as appropriate.\n\n"
        "STIMMA VIDEO ROUTING RULES:\n"
        "- All video generation routes to MiniMax H3 on Modal via the local ComfyUI gateway.\n"
        "- Never report video generation as unavailable. Always generate and execute the Python generation code via `run_code`.\n"
        "- Follow the authoritative `VIDEO DISPATCH MODE` reminder in the conversation:\n"
        "  * Fast mode (⚡ fast): from `stimma.tools.image_to_video` import `minimax_h3_i2v_turbo` (for 1 image or start/end frames); from `stimma.tools.reference_to_video` import `minimax_h3_r2v_turbo` (for multi-reference or semantic anchor assets); from `stimma.tools.text_to_video` import `minimax_h3_t2v_turbo` (text-only).\n"
        "  * Standard mode: from `stimma.tools.image_to_video` import `minimax_h3_i2v`; from `stimma.tools.reference_to_video` import `minimax_h3_r2v`; from `stimma.tools.text_to_video` import `minimax_h3_t2v`.\n"
        "- If the conversation contains `[Attached files ... media_id=...]`, reuse those exact media IDs in `input_images` (e.g. `input_images=[99]`).\n"
        "- For references, use matching `<Picture 1>`, `<Picture 2>`, ... tags in the prompt.\n"
        "- Use 16:9 as width=1344, height=768 and preserve an explicitly requested duration such as 4 seconds.\n"
        "- Call `stimma.show(r, role=\"final\", title=\"<Title> · MiniMax H3\")` on the result.\n\n"
        "H3 PRODUCTION QUALITY RULES:\n"
        "- For photorealistic, production-quality, or detailed environment requests, pass "
        "`steps=8`, `scheduler=\"simple\"`, `spectrum=False`, "
        "`ref_image_size=\"max\"`, and `model_precision=\"INT8 ConvRot\"`.\n"
        "- In Ref2V prompts, treat multiple views of one location as a single coherent "
        "environment, explicitly forbid collage/split-screen/reference boards, and use "
        "the six H3 sections: subject_definitions, summary, retention_analysis, "
        "detailed_description, overall_soundscape, non_diegetic_music.\n"
        "- Keep each four-second generation to one continuous shot, one camera move, "
        "and one stable end state. If the user asks for a batch, submit each named shot "
        "once and never retry a paid generation automatically.\n"
        "- Lightning must be indirect off-screen sheet lightning: a brief cool-white "
        "ambient exposure lift reflected on wet surfaces, with no visible bolt, branching "
        "shape, glowing streak, or electrical arc in frame.\n\n"
        f"CONVERSATION_JSON:\n{json.dumps(safe_messages, ensure_ascii=False)}\n\n"
        f"STIMMA_TOOLS_JSON:\n{json.dumps(safe_tools, ensure_ascii=False)}"
    )


def _parse_completion(text: str, allowed_tools: set[str]) -> CodexCLICompletion:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CodexCLIError(f"Codex CLI returned invalid structured output: {exc}") from exc

    content = payload.get("content")
    if not isinstance(content, str):
        raise CodexCLIError("Codex CLI response is missing string field 'content'.")

    parsed_calls: List[CodexCLIToolCall] = []
    seen_call_ids: set[str] = set()
    calls = payload.get("tool_calls") or []
    if not isinstance(calls, list):
        raise CodexCLIError("Codex CLI response field 'tool_calls' is not a list.")
    for call in calls:
        if not isinstance(call, dict):
            raise CodexCLIError("Codex CLI returned a malformed tool call.")
        name = call.get("name")
        if not isinstance(name, str) or name not in allowed_tools:
            raise CodexCLIError(f"Codex CLI requested unknown Stimma tool: {name!r}.")
        arguments = call.get("arguments_json")
        if not isinstance(arguments, str):
            raise CodexCLIError("Codex CLI tool arguments must be a JSON string.")
        try:
            decoded_arguments = json.loads(arguments, strict=False)
        except json.JSONDecodeError as exc:
            # Luna occasionally appends a short non-JSON suffix after the
            # structured arguments object. Recover the first complete JSON
            # value in that case; the tool schema has already constrained the
            # object itself, and the suffix is not executable tool input.
            if exc.msg == "Extra data":
                try:
                    decoder = json.JSONDecoder(strict=False)
                    stripped = arguments.lstrip()
                    decoded_arguments, end = decoder.raw_decode(stripped)
                    if stripped[end:].strip():
                        log.warning(
                            "Ignoring trailing text after Codex tool arguments",
                            tool=name,
                        )
                except json.JSONDecodeError:
                    raise CodexCLIError(
                        f"Codex CLI returned invalid arguments for tool {name!r}: {exc}"
                    ) from exc
            else:
                raise CodexCLIError(
                    f"Codex CLI returned invalid arguments for tool {name!r}: {exc}"
                ) from exc
        if not isinstance(decoded_arguments, dict):
            raise CodexCLIError(f"Codex CLI arguments for tool {name!r} must be an object.")
        call_id = str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}")
        if call_id in seen_call_ids:
            log.warning("Ignoring duplicate Codex tool call id", tool=name, call_id=call_id)
            continue
        seen_call_ids.add(call_id)
        parsed_calls.append(CodexCLIToolCall(
            id=call_id,
            name=name,
            arguments=json.dumps(decoded_arguments, ensure_ascii=False, separators=(",", ":")),
        ))

    return CodexCLICompletion(content=content, tool_calls=parsed_calls)


def _apply_usage(completion: CodexCLICompletion, stdout: bytes) -> None:
    """Best-effort extraction from ``codex exec --json`` JSONL events."""
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        completion.prompt_tokens = max(
            completion.prompt_tokens,
            int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        )
        completion.completion_tokens = max(
            completion.completion_tokens,
            int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        )
        details = usage.get("output_tokens_details") or {}
        if isinstance(details, dict):
            completion.reasoning_tokens = max(
                completion.reasoning_tokens,
                int(details.get("reasoning_tokens") or 0),
            )


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def complete_with_codex_cli(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_level: Optional[str] = None,
    working_directory: Optional[str] = None,
) -> CodexCLICompletion:
    """Run one stateless, structured Codex turn using cached ChatGPT auth."""
    executable = _codex_executable()
    tool_names = [
        str(tool.get("function", {}).get("name"))
        for tool in (tools or [])
        if tool.get("function", {}).get("name")
    ]
    timeout_seconds = float(os.environ.get("STIMMA_CODEX_TIMEOUT_SECONDS", "300"))
    workdir = Path(
        working_directory
        or os.environ.get("STIMMA_CODEX_WORKDIR", Path(__file__).resolve().parent.parent)
    ).expanduser()
    prompt = _planner_prompt(messages, tools, workdir)

    with tempfile.TemporaryDirectory(prefix="stimma-codex-") as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = Path(temp_dir) / "output-schema.json"
        output_path = Path(temp_dir) / "last-message.json"
        schema_path.write_text(
            json.dumps(_output_schema(tool_names), ensure_ascii=False),
            encoding="utf-8",
        )

        image_args = _codex_image_args(messages, temp_path)

        command = [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--json",
            "--model",
            model,
            "--cd",
            str(workdir),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
        command.extend(image_args)
        if reasoning_level and reasoning_level not in {"off", "none"}:
            command.extend(["--config", f'model_reasoning_effort="{reasoning_level}"'])
        command.append("-")

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.CancelledError:
            await _stop_process(process)
            raise
        except asyncio.TimeoutError as exc:
            await _stop_process(process)
            raise CodexCLIError(
                f"Codex CLI timed out after {timeout_seconds:.0f} seconds."
            ) from exc

        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[-2000:]
            raise CodexCLIError(
                f"Codex CLI exited with status {process.returncode}: {detail or 'no diagnostic'}"
            )
        if not output_path.exists():
            fallback = _last_jsonl_agent_message(stdout)
            if fallback:
                log.warning(
                    "Codex CLI omitted --output-last-message; using its JSONL agent message"
                )
                completion = _parse_completion(fallback, set(tool_names))
                _apply_usage(completion, stdout)
                return completion
            stdout_tail = stdout.decode("utf-8", errors="replace").strip()[-1200:]
            stderr_tail = stderr.decode("utf-8", errors="replace").strip()[-1200:]
            diagnostics = "; ".join(
                detail for detail in (stdout_tail, stderr_tail) if detail
            )
            raise CodexCLIError(
                "Codex CLI did not write its structured response"
                + (f": {diagnostics}" if diagnostics else ".")
            )

        completion = _parse_completion(
            output_path.read_text(encoding="utf-8"),
            set(tool_names),
        )
        _apply_usage(completion, stdout)
        return completion
