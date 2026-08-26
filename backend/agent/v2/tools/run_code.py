"""Execute sandboxed Python in the session workspace."""

import re

from ..code_runtime import ALLOWED_MODULES_PROMPT_DESCRIPTION, run_code_in_sandbox
from ..tools_registry import tool, ToolParameter


@tool(
    name="run_code",
    description=(
        "Execute Python code in a restricted workspace sandbox with a pre-injected `stimma` SDK. "
        "Code already runs inside `async def` — use `await` directly at the top level. Do NOT wrap in `async def main()` or use `asyncio.run()`. "
        "`stimma` is already available — no import needed (it has .show, .library, .llm, etc.). "
        "Generation/transformation tools are imported by their REAL name from the catalog: read .stimma/tools/<category>/ first "
        "(ls/cat) to get the exact function name, then `from stimma.tools.<category> import <name_from_catalog>` "
        "and `r = await <name_from_catalog>(...)` — the awaited result is a ToolResult (.media_id, .path, .seed). "
        "When generating multiple images, ALWAYS use asyncio.gather() to run them in parallel — this enables the progress display and is significantly faster. "
        "Batch: import the tool once, then `results = await asyncio.gather(*[<tool>(prompt=p) for p in prompts]); stimma.show(results, role='final')` "
        "If run_code already called stimma.show(), do NOT call the show tool again afterward — images are already visible. "
        + ALLOWED_MODULES_PROMPT_DESCRIPTION
        + " Invoked skills may provide additional importable modules — check the skills inventory."
    ),
    parameters=[
        ToolParameter(name="code", type="string", description="Python code to execute"),
        ToolParameter(
            name="label",
            type="string",
            description=(
                "A few words in present-progressive naming what this code does, shown to the "
                'user while it runs (e.g. "Generating image", "Upscaling", "Building grid").'
            ),
            required=False,
        ),
    ],
)
async def run_code(code: str, **kwargs) -> str:
    workspace_dir = kwargs.get("workspace_dir")
    session = kwargs.get("session")
    chat_id = kwargs.get("chat_id")

    if not workspace_dir:
        return "Error: no workspace directory available"
    if not session:
        return "Error: No database session available"
    if chat_id is None:
        return "Error: No chat available"

    # The import namespace is derived from the live provider catalog. When the
    # MiniMax H3 provider is disconnected, the old behavior leaked the internal
    # sandbox allow-list error ("Import ... is not allowed") and made it look as
    # if the requested adapter did not exist. Preflight the explicit H3 request
    # and report the actionable provider state before entering the sandbox.
    if "minimax_h3" in code.casefold():
        from providers.registry import ProviderRegistry
        from ..tool_fs import ensure_task_tools

        registry = ProviderRegistry.get_instance()
        await ensure_task_tools(registry, "reference-to-video")
        all_tools = registry.list_all_tools()
        h3_available = any(
            "minimax-h3" in str(full_id).casefold()
            or "minimax_h3" in str(full_id).casefold()
            or "minimax h3" in str(getattr(descriptor, "name", "")).casefold()
            for full_id, _provider, descriptor in all_tools
        )
        if not h3_available:
            return (
                "Error: MiniMax H3 provider is currently unavailable, so no video job was queued. "
                "Reconnect the configured H3/ComfyUI provider, then resend the same prompt; "
                "the attached clipboard assets are already materialized and will be reused."
            )
        requested_import = re.search(
            r"from\s+stimma\.tools\.([A-Za-z0-9_]+)\s+import\s+([A-Za-z_][A-Za-z0-9_]*)",
            code,
        )
        if requested_import:
            from ..tool_fs import build_manifest

            module_name, function_name = requested_import.groups()
            manifest = build_manifest(registry)
            available_functions = manifest.by_module.get(module_name, {})
            if function_name not in available_functions:
                available = ", ".join(sorted(available_functions)) or "none"
                return (
                    f"Error: the requested MiniMax H3 adapter "
                    f"stimma.tools.{module_name}.{function_name} is not in the live catalog. "
                    f"Available functions in that category: {available}. No video job was queued."
                )

    shot_contract = kwargs.get("_shot_contract")
    if isinstance(shot_contract, dict) and shot_contract.get("workflow") == "compose_opening_keyframe_then_i2v":
        # Image composition belongs to the real Antigravity CLI path. Catch
        # local image-adapter attempts before entering the sandbox, where they
        # would bypass the prompt+reference workflow and create a misleading
        # paid-tool approval.
        if "stimma.tools.image_to_image" in code or "nano_banana_pro" in code:
            return (
                "Error: shot workflow image composition must use the real `antigravity_image` "
                "tool with the exact ordered reference_media_ids and edit prompt. "
                "Do not import a local image_to_image adapter. After the returned keyframe, "
                "pass only its media_id to `minimax_h3_i2v`. No generation job was queued."
            )

    result, llm_usage = await run_code_in_sandbox(
        code=code,
        session=session,
        chat_id=chat_id,
        workspace_dir=workspace_dir,
        project_workspace_dir=kwargs.get("project_workspace_dir"),
        interrupt_checker=kwargs.get("interrupt_checker"),
        session_media_ids=kwargs.get("session_media_ids"),
        shown_media_ids=kwargs.get("_shown_media_ids"),
        enabled_stimpacks=kwargs.get("_enabled_stimpacks"),
        project_id=kwargs.get("project_id"),
        effective_model_slug=kwargs.get("_effective_model_slug"),
        shot_contract=kwargs.get("_shot_contract"),
    )
    # Stash usage on the mutable container so _execute_tool_call can read it
    usage_out = kwargs.get("_llm_usage_out")
    if usage_out is not None and llm_usage and llm_usage.get("calls", 0) > 0:
        usage_out["llm_usage"] = llm_usage
    return result
