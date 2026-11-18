"""Progressive-disclosure help for Stimma SDK code in run_code sandboxes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SDKMethodHelp:
    name: str
    signature: str
    summary: str
    details: str
    group: str
    is_async: bool


SDK_HELP: dict[str, SDKMethodHelp] = {
    "video_settings": SDKMethodHelp(
        name="video_settings",
        signature="await stimma.video_settings(duration=None, steps=None, resolution=None, fast=None) -> dict",
        summary="Read/update the existing visible video controls (pass only settings to change).",
        details="Duration is a clip request, 1–15 seconds in 0.5s increments. The result includes H3 fps, frame_count and effective_duration (24 fps, 17n+5 frames). Steps: integer 1–50; resolution: '480', '720', '1080', '2k'; fast: boolean. No arguments reads current settings. Changes preserve unrelated chat settings and update the UI immediately.",
        group="video",
        is_async=True,
    ),
    "video_plan": SDKMethodHelp(
        name="video_plan",
        signature="await stimma.video_plan(plan=None) -> dict | None",
        summary="Read/persist interactive video preparation; generation waits for recorded user reviews/start.",
        details="""Create the plan at the start of interactive preparation, then update it as assets/prompts become ready.
Input keys are exactly target_duration, assets, clips. Resolution/steps/fast are set separately with await stimma.video_settings(...).
Schema: {"target_duration": 30, "assets": [{"name": "Character", "media_id": 42}, {"name": "Opening keyframe", "media_id": null}], "clips": [{"id": "Shot 1", "tool_id": "REAL provider-qualified ID from the catalog", "duration": 5, "edit_duration": 5, "parameters": {"prompt": "...", "input_images": [42]}}]}.
Start preparation before clip references exist with this Python example:
plan = await stimma.video_plan({"target_duration": 30, "assets": [{"name": "Opening keyframe", "media_id": None}], "clips": []})
Fill exact clip tool_ids and reference media IDs as assets become available. Each clip uses only id, tool_id, duration, edit_duration, parameters; id can be a descriptive shot name.
target_duration is the final edit duration; each generation duration is 1–15s in 0.5s increments. edit_duration is on the 24fps edit grid, cannot exceed the generated clip's frame-aligned duration, and all edit durations must sum to the target before launch. Clips may initially be empty and prompts incomplete.
List ALL required assets/keyframes, using null for missing media. Bind exact immutable media IDs in every reference array. Use T2V for no references, I2V for one starting frame, R2V for multiple/semantic references. Keep Picture N tags in the input_images order. Prepare sound and transition prompts as part of each clip.
Generate planned missing stills one at a time, reuse established references and show each result, then continue to the next asset. Ask permission/approval per image only when the user explicitly requests those checkpoints. When the complete asset set is ready, present it for one collective review via ask_user(video_review={"media_ids": [42, 43, 44]}), listing the exact pending asset versions. Only the user's explicit approve button records approval. Replacing a media ID requires a fresh review, which may be included in the next collective review. Assets already approved in this plan keep their approvals.
When every asset and prompt is ready/reviewed, show the final plan and request ask_user(video_review={"start": true}); only the user's explicit launch button authorizes videos. Changes to the plan invalidate launch authorization. After approval: await stimma.generate_video_plan(). Do not use gather for this series.
The returned plan includes pending preparation/review issues, clip_timing, approved_media_ids and outputs; these are read-only server fields, not setter arguments. To update a returned plan, pass only its target_duration/assets/clips. No arguments reads it. Project shot contracts remain authoritative and apply to one shot at a time.""",
        group="video",
        is_async=True,
    ),
    "generate_video_plan": SDKMethodHelp(
        name="generate_video_plan",
        signature="await stimma.generate_video_plan() -> list[ToolResult]",
        summary="Run the user's approved clips sequentially, updating duration and displaying each output.",
        details="Prompts and references are prepared before the first GPU job. The helper reads the persisted plan, skips completed clips on resume, updates the existing duration control for each clip, awaits each job, checks output duration metadata against the H3 frame grid, then shows/flushes each result before starting the next. Errors/interruption stop the sequence; there is no automatic paid retry. A user interruption revokes start authorization. For multiple remaining clips, it explicitly keeps the executing Modal route warm and releases it on completion, error, or interruption. Single generations keep the default 2s idle shutdown; no global scaling settings are changed. The scoped hold expires after 60s without a job if the caller disappears. Keep the same route/configuration to reuse its loaded model. Multi-shot project production uses its own per-shot contract workflow.",
        group="video",
        is_async=True,
    ),
    "generated_tools": SDKMethodHelp(
        name="generated_tools",
        signature="from stimma.tools.<category> import <tool_name>",
        summary="Import STP generation tools from the generated .stimma/tools catalog.",
        details="""\
Generation tools are exposed as generated async Python functions.

Workflow:
  1. Inspect .stimma/tools/ to find available task categories.
  2. Inspect .stimma/tools/<category>/ to find real function names.
  3. Import the selected function from stimma.tools.<category>.
  4. Await it with flat keyword arguments.

Example:
  from stimma.tools.text_to_image import flux_schnell

  result = await flux_schnell(prompt="a cat in a garden", width=1024, height=1024)
  stimma.show(result, role="final")

Parallel execution:
  Use asyncio.gather() for independent batches such as prompt or seed sweeps.""",
        group="core",
        is_async=True,
    ),
    "project_path": SDKMethodHelp(
        name="project_path",
        signature="stimma.project_path(*parts: str) -> Path",
        summary="Resolve a durable path inside the shared project workspace.",
        details="""\
Use this only in project chats. It returns a Path inside the shared project
workspace, which persists across multiple chats in the same project.

Example:
  manifest_path = stimma.project_path("process", "manifest.json")
  manifest_path.parent.mkdir(parents=True, exist_ok=True)
  manifest_path.write_text("{}")""",
        group="core",
        is_async=False,
    ),
    "show": SDKMethodHelp(
        name="show",
        signature="stimma.show(items, *, role='intermediate'|'final', title=None)",
        summary="Display media to the user. Sync; do not await.",
        details="""\
Display one or more images/videos to the user. Items can be ToolResult objects,
media IDs, workspace paths, or lists of those values.

role="final" commits the items to the user's library as Assets — use it for results
you produced for them. role="intermediate" is plain display: work-in-progress, and
reference material found or downloaded from elsewhere.

Example:
  stimma.show(result, role="final", title="Final")
  stimma.show([a, b, c], role="intermediate", title="Work in progress")
  stimma.show(downloaded_paths, role="intermediate", title="Reference photos")""",
        group="display",
        is_async=False,
    ),
    "show_grid": SDKMethodHelp(
        name="show_grid",
        signature="stimma.show_grid(items, cols=3, *, role='intermediate'|'final', title=None)",
        summary="Display media in a grid layout. Sync; do not await.",
        details="""\
Use this for compact comparison sets.

Example:
  stimma.show_grid(results, cols=3, role="final", title="Prompt sweep")""",
        group="display",
        is_async=False,
    ),
    "library.prompt_examples": SDKMethodHelp(
        name="library.prompt_examples",
        signature='await stimma.library.prompt_examples(query="", *, example_id="", style="", topic="", similar_to="", limit=6)',
        summary="Explore H3 styles with real clips, original prompts and similar examples.",
        details="""\
Search the read-only H3 Atlas/ostris catalogue with English scene words. Search
returns compact items with id, style_label, excerpt, dimensions, duration and
chat_link. Read example_id for the original T2VA prompt, soundscape, music and
credits. Similarity uses style, subject tags and prompt words.

Present a small number of relevant examples as [your descriptive label](stimma-h3:000128).
The chat renders a thumbnail, hover preview and clickable details. A style
selection is inspiration, not an input_images reference: adapt the look/camera
and requested sound to the user's scene, actual duration and H3 mode; preserve
their identity, actions and dialogue. These clips do not become user Assets.

Example:
  examples = await stimma.library.prompt_examples("black white gangster cigar", limit=3)
  print(examples)
  example = await stimma.library.prompt_examples(example_id="000128")""",
        group="library",
        is_async=True,
    ),
    "library.search": SDKMethodHelp(
        name="library.search",
        signature="await stimma.library.search(query: str, *, limit=20)",
        summary="Semantic/text search of the media library.",
        details="""\
Find existing media before generating or editing.

Example:
  cats = await stimma.library.search("cats", limit=10)""",
        group="library",
        is_async=True,
    ),
    "library.browse": SDKMethodHelp(
        name="library.browse",
        signature="await stimma.library.browse(**filters)",
        summary="Browse library media with structured filters.",
        details="""\
Use browse when the user asks for recent items, media types, tags, or other
library filters rather than a semantic query.""",
        group="library",
        is_async=True,
    ),
    "library.get": SDKMethodHelp(
        name="library.get",
        signature="await stimma.library.get(media_id: int)",
        summary="Load metadata for one media item.",
        details="""\
Use get when you already know the media ID and need its metadata or workspace
file path. The result supports both dict and attribute access: info["path"]
or info.path.""",
        group="library",
        is_async=True,
    ),
    "library.save": SDKMethodHelp(
        name="library.save",
        signature="await stimma.library.save(item, tags=None, sources=None, inspired_by=None)",
        summary="Save workspace files or generated results to the media library.",
        details="""\
Library save is explicit. `show(..., role="final")` also commits a durable
Asset, while `role="intermediate"` only retains Media in the chat for viewing
(work-in-progress, downloaded reference material).
Use save when the user asks to keep something without presenting it.
`item` accepts a ToolResult, a PIL Image, or a workspace path. When saving an
image you composed or edited in code (an Image or path rather than a
ToolResult), pass sources=[media_id, ...] for the images it was made from so
the derivation shows up in lineage. ToolResults carry their own provenance.""",
        group="library",
        is_async=True,
    ),
    "library.lineage": SDKMethodHelp(
        name="library.lineage",
        signature="await stimma.library.lineage(media_id: int)",
        summary="Return provenance for a media item.",
        details="""\
Use lineage when the user asks where an asset came from, what tool made it, or
which source images were used.""",
        group="library",
        is_async=True,
    ),
    "library.generation_params": SDKMethodHelp(
        name="library.generation_params",
        signature="await stimma.library.generation_params(media_id: int)",
        summary="Get reusable generation parameters for an existing media item.",
        details="""\
Use this before regenerating, remixing, or making controlled variations from an
existing generated item.""",
        group="library",
        is_async=True,
    ),
    "library.regenerate": SDKMethodHelp(
        name="library.regenerate",
        signature="await stimma.library.regenerate(media_id: int, **overrides)",
        summary="Regenerate an item with optional parameter overrides.",
        details="""\
Use this when the user asks for another version of an existing generated image
and wants to preserve most of its original generation setup.""",
        group="library",
        is_async=True,
    ),
    "llm": SDKMethodHelp(
        name="llm",
        signature="await stimma.llm(prompt: str, *, images=None)",
        summary="Ask the configured language model for text or vision reasoning.",
        details="""\
Use stimma.llm() for local reasoning inside a code workflow, especially prompt
rewriting or structured summaries. Pass images only when needed.""",
        group="ai",
        is_async=True,
    ),
    "progress": SDKMethodHelp(
        name="progress",
        signature="stimma.progress(iterable, *, desc=None)",
        summary="Wrap loops so progress appears in the chat UI.",
        details="""\
Use progress for long loops that produce visible stages for the user.""",
        group="core",
        is_async=False,
    ),
    "detect_faces": SDKMethodHelp(
        name="detect_faces",
        signature="await stimma.detect_faces(media_id: int)",
        summary="Detect faces in a library image.",
        details="""\
Use this for face-aware workflows such as cropping, matching, or portrait
selection.""",
        group="image",
        is_async=True,
    ),
    "adjust": SDKMethodHelp(
        name="adjust",
        signature="stimma.adjust(image, **edits)",
        summary="Apply simple local image edits such as filters and levels.",
        details="""\
Use this for local image adjustments in PIL/numpy workflows rather than calling a
generation provider.""",
        group="image",
        is_async=False,
    ),
    "rasterize_svg": SDKMethodHelp(
        name="rasterize_svg",
        signature="await stimma.rasterize_svg(svg, *, width=None, height=None, out=None) -> Image | Path",
        summary="Render an SVG to pixels with the app's real browser engine.",
        details="""\
`svg` is a workspace path or SVG markup. Returns a PIL Image at exactly the
requested size (or the written path when `out` is given). Size defaults to the
document's own; pass one of width/height and the other follows the aspect ratio.
Warns on stdout if the document renders completely empty.

This is the same renderer behind thumbnails, view_image, PNG export and the
icon bundles. Do not shell out to rsvg-convert, inkscape or magick instead:
they are not installed on users' machines, and where they are they rasterize
differently from what the app ships — so you would be checking your work
against something other than the deliverable.

Example — check a mark at icon size:
  small = await stimma.rasterize_svg("mark.svg", width=16)
  print(small.size, small.getbbox())""",
        group="image",
        is_async=True,
    ),
    "ffmpeg": SDKMethodHelp(
        name="ffmpeg",
        signature="await stimma.ffmpeg(*args, timeout=600.0, check=True) -> AVToolResult",
        summary="Run ffmpeg in the chat workspace (concat, trim, remux, extract frames).",
        details="""\
Runs ffmpeg with the workspace as cwd. Paths must stay inside the chat
workspace (or shared project workspace); use workspace-relative paths.
Args can be flat strings, a single list, or one command string. Raises
RuntimeError with ffmpeg's stderr on nonzero exit unless check=False.

Example — concatenate two clips losslessly:
  open("list.txt", "w").write("file 'a.mp4'\\nfile 'b.mp4'\\n")
  await stimma.ffmpeg("-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                      "-c", "copy", "joined.mp4")
  saved = await stimma.library.save("joined.mp4")""",
        group="image",
        is_async=True,
    ),
    "ffprobe": SDKMethodHelp(
        name="ffprobe",
        signature="await stimma.ffprobe(*args, timeout=120.0, check=True) -> AVToolResult",
        summary="Inspect media files with ffprobe (duration, streams, fps).",
        details="""\
Same workspace rules as stimma.ffmpeg. The result's .stdout holds ffprobe's
output.

Example:
  r = await stimma.ffprobe("-v", "error", "-show_entries", "format=duration",
                           "-of", "json", "clip.mp4")
  print(r.stdout)""",
        group="image",
        is_async=True,
    ),
    "filters": SDKMethodHelp(
        name="filters",
        signature="stimma.filters -> list[str]",
        summary="List available filter preset names for stimma.adjust(filter=...).",
        details="""\
Example:
  print(stimma.filters)""",
        group="image",
        is_async=False,
    ),
}


_GROUP_ORDER = ["core", "display", "library", "image", "ai", "video"]
_GROUP_LABELS = {
    "video": "Video preparation",
    "core": "Core",
    "display": "Display",
    "library": "Library",
    "image": "Image",
    "ai": "AI",
}
_GROUP_DESCRIPTIONS = {
    "video": "visible settings, reviewed preparation, sequential generation",
    "core": "generated tools, parallel batches, progress, shared project paths",
    "display": "show, show_grid",
    "library": "search, browse, get, save, lineage, regeneration",
    "image": "adjust, filters, detect_faces",
    "ai": "llm text and vision reasoning",
}


def get_sdk_overview() -> str:
    """Compact group index for the sandbox's sdk_help function."""
    lines = ["stimma SDK - available method groups:", ""]
    for group in _GROUP_ORDER:
        label = _GROUP_LABELS[group]
        desc = _GROUP_DESCRIPTIONS.get(group, "")
        lines.append(f"  {label} - {desc}")
    lines.append("")
    lines.append('Call sdk_help("<group>") to see methods in a group, e.g. sdk_help("core").')
    lines.append('Call sdk_help("<method>") for method docs, e.g. sdk_help("generated_tools").')
    return "\n".join(lines)


def get_sdk_group_help(group: str, methods: list[SDKMethodHelp]) -> str:
    """Method names, signatures, and summaries for a group."""
    label = _GROUP_LABELS.get(group, group)
    lines = [f"{label} methods:", ""]
    for method in methods:
        async_note = " (async)" if method.is_async else " (sync)"
        lines.append(f"  {method.signature}{async_note}")
        lines.append(f"    {method.summary}")
    lines.append("")
    lines.append(f'Call sdk_help("<method>") for details, e.g. sdk_help("{methods[0].name}").')
    return "\n".join(lines)


def get_sdk_method_help(name: str | None = None) -> str:
    """Return help for a method, group, or namespace prefix."""
    if name is None:
        return get_sdk_overview()
    if name in SDK_HELP:
        method = SDK_HELP[name]
        return f"{method.signature}\n\n{method.details}"

    name_lower = name.lower()
    group_methods = [method for method in SDK_HELP.values() if method.group == name_lower]
    if group_methods:
        return get_sdk_group_help(name_lower, group_methods)

    prefix_methods = [method for method in SDK_HELP.values() if method.name.startswith(name + ".")]
    if prefix_methods:
        return get_sdk_group_help(prefix_methods[0].group, prefix_methods)

    groups = ", ".join(_GROUP_ORDER)
    methods = ", ".join(sorted(SDK_HELP))
    return f"Unknown SDK help topic: {name}. Groups: {groups}. Methods: {methods}"


def get_sdk_quick_ref() -> str:
    """Minimal SDK reference appended to run_code errors for self-correction."""
    return """\
stimma quick reference (inside run_code / run_file):
  Read SDK documentation with print(sdk_help("video_plan")) (or "video_settings", "library", etc.).
  Generation tools are imported by their REAL function name from the catalog.
  First read .stimma/tools/<category>/ (ls/cat) to get the exact name, then:
    from stimma.tools.<category> import <name_from_catalog>
    r = await <name_from_catalog>(prompt="a cat", width=1024)   # r.media_id, r.path, r.seed
  stimma.show(r, role="final") commits+displays produced results ("intermediate" = display only); asyncio.gather() for parallel batches.
  stimma.* also has: .library (search/get/save), .llm(), .show(), .detect_faces(),
    await stimma.ffmpeg(...) / stimma.ffprobe(...) for workspace-jailed video/audio processing.
NOT available in run_code (use as agent tools outside run_code): create_layout, bash, view_image, view_video, ask_user, browse_web, skill"""
