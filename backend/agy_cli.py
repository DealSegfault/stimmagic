"""Local Antigravity CLI transport for Stimma's LLM abstraction.

This transport shells out to ``agy -p ...`` with structured output (--json-schema)
instead of reading credentials or calling Gemini API directly. The CLI owns Google
OAuth, refreshes it, and returns one structured next-step decision to Stimma. Stimma
keeps ownership of tool execution and its permission model.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logging import get_logger


log = get_logger(__name__)


class AgyCLIError(RuntimeError):
    """Raised when Antigravity CLI cannot produce a usable completion."""


@dataclass
class AgyCLIToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class AgyCLICompletion:
    content: str = ""
    tool_calls: List[AgyCLIToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0


def _agy_executable() -> str:
    configured = os.environ.get("STIMMA_AGY_CLI", "").strip()
    candidates = [
        configured,
        shutil.which("agy") or "",
        shutil.which("antigravity") or "",
        str(Path.home() / ".local" / "bin" / "agy"),
        str(Path.home() / ".gemini" / "antigravity-cli" / "bin" / "agy"),
        "/opt/homebrew/bin/agy",
        "/usr/local/bin/agy",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise AgyCLIError(
        "Antigravity CLI (agy) was not found. Install it or set STIMMA_AGY_CLI to its executable path."
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
        "inspect files, edit files, or invoke external agent tools directly. Stimma itself "
        "will execute any requested tool and return its result in the next call.\n\n"
        "Return exactly one structured next step matching the supplied output "
        "schema. If a Stimma tool is required, set finish_reason to tool_calls, "
        "use its exact name, and put a valid JSON object encoded as a string in "
        "arguments_json. Otherwise answer the user in content and set "
        "finish_reason to stop. Do not invent tool results. System messages in "
        "the conversation are authoritative.\n\n"
        "STIMMA IMAGE ROUTING RULES:\n"
        "- For still image generation (photo, illustration, scene visual), the chat uses its direct image generation pipeline (Codex / Antigravity), intentionally bypassing the local Stimma ComfyUI tool store.\n"
        "- Do not report still image generation as unavailable due to missing `.stimma/tools/` adapters. Never route still images to video adapters (MiniMax H3 / Wan22 / LTX).\n"
        "- Keep CLI prompts lean and focused on the scene description or delta. For iterative modifications in the same chat, use `--continue` or `resume --last`.\n"
        "- Include the model tag in the image filename (e.g. `<name>_antigravity.png` or `<name>_codex.png`) and display title in `show` (e.g. `<Title> · Antigravity` or `<Title> · Codex ImageGen`).\n"
        "- Respond by producing the generated image directly or utilizing agent tools (`run_code`, etc.) as appropriate.\n\n"
        "STIMMA VIDEO ROUTING RULES:\n"
        "- All video generation routes to MiniMax H3 on Modal via the local ComfyUI gateway.\n"
        "- Never report video generation as unavailable. Always generate and execute the Python generation code via `run_code`.\n"
        "- Follow the authoritative `VIDEO DISPATCH MODE` reminder in the conversation:\n"
        "  * Fast mode (⚡ fast): from `stimma.tools.image_to_video` import `minimax_h3_i2v_turbo` (for 1 image or start/end frames) or `minimax_h3_r2v_turbo` (for multi-reference assets); from `stimma.tools.text_to_video` import `minimax_h3_t2v_turbo` (text-only).\n"
        "  * Standard mode: from `stimma.tools.image_to_video` import `minimax_h3_i2v` or `minimax_h3_r2v`; from `stimma.tools.text_to_video` import `minimax_h3_t2v`.\n"
        "- If the conversation contains `[Attached files ... media_id=...]`, reuse those exact media IDs in `input_images` (e.g. `input_images=[99]`).\n"
        "- For references, use matching `<Picture 1>`, `<Picture 2>`, ... tags in the prompt.\n"
        "- Use 16:9 as width=1344, height=768 and preserve an explicitly requested duration such as 4 seconds.\n"
        "- Call `stimma.show(r, role=\"final\", artifact=True, title=\"<Title> · MiniMax H3\")` on the result.\n\n"
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


def _parse_completion(text: str, allowed_tools: set[str]) -> AgyCLICompletion:
    try:
        raw_payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgyCLIError(f"Antigravity CLI returned invalid JSON: {exc}") from exc

    if not isinstance(raw_payload, dict):
        raise AgyCLIError("Antigravity CLI output is not a JSON object.")

    # Agy CLI print mode returns {status, structured_output, response, usage, ...}
    payload: Dict[str, Any]
    if "structured_output" in raw_payload and isinstance(raw_payload["structured_output"], dict):
        payload = raw_payload["structured_output"]
    elif "content" in raw_payload:
        payload = raw_payload
    elif "response" in raw_payload and isinstance(raw_payload["response"], str):
        try:
            payload = json.loads(raw_payload["response"])
        except json.JSONDecodeError:
            payload = {"content": raw_payload["response"], "tool_calls": [], "finish_reason": "stop"}
    else:
        payload = raw_payload

    content = payload.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)

    parsed_calls: List[AgyCLIToolCall] = []
    calls = payload.get("tool_calls") or []
    if not isinstance(calls, list):
        raise AgyCLIError("Antigravity CLI response field 'tool_calls' is not a list.")
    for call in calls:
        if not isinstance(call, dict):
            raise AgyCLIError("Antigravity CLI returned a malformed tool call.")
        name = call.get("name")
        if not isinstance(name, str) or (allowed_tools and name not in allowed_tools):
            raise AgyCLIError(f"Antigravity CLI requested unknown Stimma tool: {name!r}.")
        arguments = call.get("arguments_json")
        if arguments is None:
            decoded_arguments = {}
        elif isinstance(arguments, dict):
            decoded_arguments = arguments
        elif isinstance(arguments, str):
            try:
                decoded_arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                if exc.msg == "Extra data":
                    try:
                        decoder = json.JSONDecoder()
                        stripped = arguments.lstrip()
                        decoded_arguments, end = decoder.raw_decode(stripped)
                        if stripped[end:].strip():
                            log.warning(
                                "Ignoring trailing text after Antigravity tool arguments",
                                tool=name,
                            )
                    except json.JSONDecodeError:
                        raise AgyCLIError(
                            f"Antigravity CLI returned invalid arguments for tool {name!r}: {exc}"
                        ) from exc
                else:
                    raise AgyCLIError(
                        f"Antigravity CLI returned invalid arguments for tool {name!r}: {exc}"
                    ) from exc
        else:
            raise AgyCLIError(f"Antigravity CLI arguments for tool {name!r} must be a JSON string or object.")

        if not isinstance(decoded_arguments, dict):
            raise AgyCLIError(f"Antigravity CLI arguments for tool {name!r} must be an object.")

        parsed_calls.append(
            AgyCLIToolCall(
                id=str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                name=name,
                arguments=json.dumps(decoded_arguments, ensure_ascii=False, separators=(",", ":")),
            )
        )

    completion = AgyCLICompletion(content=content, tool_calls=parsed_calls)

    usage = raw_payload.get("usage")
    if isinstance(usage, dict):
        completion.prompt_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        completion.completion_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        completion.reasoning_tokens = int(usage.get("thinking_tokens") or usage.get("reasoning_tokens") or 0)

    return completion


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def complete_with_agy_cli(
    *,
    model: Optional[str] = None,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_level: Optional[str] = None,
    working_directory: Optional[str] = None,
) -> AgyCLICompletion:
    """Run one stateless, structured Antigravity turn using authenticated AGY CLI."""
    executable = _agy_executable()
    tool_names = [
        str(tool.get("function", {}).get("name"))
        for tool in (tools or [])
        if tool.get("function", {}).get("name")
    ]
    timeout_seconds = float(os.environ.get("STIMMA_AGY_TIMEOUT_SECONDS", "300"))
    workdir = Path(
        working_directory
        or os.environ.get("STIMMA_AGY_WORKDIR", Path(__file__).resolve().parent.parent)
    ).expanduser()
    prompt = _planner_prompt(messages, tools, workdir)
    schema = _output_schema(tool_names)

    command = [
        executable,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--disable-slash-commands",
    ]
    if model:
        command.extend(["--model", model])
    if (
        reasoning_level
        and reasoning_level in {"low", "medium", "high"}
        and (not model or "(" not in model)
    ):
        command.extend(["--effort", reasoning_level])

    import tempfile

    with tempfile.TemporaryDirectory(prefix="stimma-agy-") as temp_dir:
        stdout_file = Path(temp_dir) / "stdout.log"
        stderr_file = Path(temp_dir) / "stderr.log"
        with open(stdout_file, "wb") as out_f, open(stderr_file, "wb") as err_f:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=out_f,
                stderr=err_f,
            )
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=timeout_seconds,
                )
            except asyncio.CancelledError:
                await _stop_process(process)
                raise
            except asyncio.TimeoutError as exc:
                await _stop_process(process)
                raise AgyCLIError(
                    f"Antigravity CLI timed out after {timeout_seconds:.0f} seconds."
                ) from exc

        stderr_text = stderr_file.read_text(encoding="utf-8", errors="replace").strip()
        stdout_text = stdout_file.read_text(encoding="utf-8", errors="replace").strip()

        if process.returncode != 0:
            diagnostic = ""
            if stdout_text:
                try:
                    payload = json.loads(stdout_text)
                    if isinstance(payload, dict):
                        diagnostic = str(payload.get("error") or payload.get("response") or "")
                except json.JSONDecodeError:
                    diagnostic = stdout_text[-2000:]
            if not diagnostic:
                diagnostic = stderr_text[-2000:]
            raise AgyCLIError(
                f"Antigravity CLI exited with status {process.returncode}: {diagnostic or 'no diagnostic'}"
            )

        if not stdout_text:
            raise AgyCLIError("Antigravity CLI returned empty response.")

        return _parse_completion(
            stdout_text,
            set(tool_names),
        )
