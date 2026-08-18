"""Server-side generate-time prompt pipeline.

The exact counterpart of the frontend's interactive pipeline
(frontend/src/utils/promptProcessor.ts + useSubmissionQueue.ts), for
generations that run with no client attached (post-processing chain steps).
The behavior must stay in lockstep with the client implementation — users
expect a chain-step prompt to be treated identically to one submitted from
the editor:

  1. Resolve wildcards — expand {{name}} (segments first, then wildcards)
     and inline {a|b|c}, preserving # comments and [verbatim] markers for
     the LLM steps.
  2. Enhance (autoImprove) — family-aware LLM rewrite with [verbatim]
     protection and a 3-attempt retry when placeholders get dropped
     (falls back to the original prompt, like improveViaApi).
     Skipped in Ideogram JSON mode — that runs post-resolve (step 5).
  3. Translate — same verbatim protection; unknown language codes are a
     no-op (mirrors translateViaApi).
  4. Final cleanup — strip # comments, unwrap [verbatim], and resolve any
     wildcard syntax the LLM may have introduced.
  5. Ideogram JSON — when Enhance is on and the tool is Ideogram 4,
     convert the fully-resolved prompt to structured JSON (final step).

All steps are non-destructive: the stored step prompt is untouched; only
the prompt actually sent to the tool is transformed.
"""

from __future__ import annotations

import random
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from core.logging import get_logger

log = get_logger(__name__)

# Matches improveViaApi/translateViaApi in useSubmissionQueue.ts.
_MAX_LLM_RETRIES = 3


# --- promptProcessor.ts ports -------------------------------------------------

def extract_verbatim(
    prompt: str, *, preserve_h3_structure: bool = False
) -> Tuple[str, List[Dict[str, str]]]:
    """Extract [verbatim] segments and replace with placeholders (before LLM)."""
    segments: List[Dict[str, str]] = []

    def _repl(match: re.Match) -> str:
        if preserve_h3_structure and (
            re.fullmatch(r"Shot\s+\d+", match.group(1), re.IGNORECASE)
            or prompt[max(0, match.start() - 3):match.start()] == "<d>"
        ):
            return match.group(0)
        placeholder = f"__VERBATIM_{chr(65 + len(segments))}__"  # A, B, C, ...
        segments.append({"placeholder": placeholder, "original": match.group(1)})
        return placeholder

    processed = re.sub(r"\[([^\[\]]+)\]", _repl, prompt)
    return processed, segments


def restore_verbatim(
    prompt: str, segments: List[Dict[str, str]], *, include_brackets: bool = True
) -> str:
    """Restore [verbatim] segments from placeholders (after LLM)."""
    result = prompt
    for segment in segments:
        restored = f"[{segment['original']}]" if include_brackets else segment["original"]
        result = result.replace(segment["placeholder"], restored, 1)
    return result


def verify_verbatim_preserved(output: str, segments: List[Dict[str, str]]) -> bool:
    """True when every placeholder survived the LLM rewrite."""
    return all(segment["placeholder"] in output for segment in segments)


def strip_comments(prompt: str) -> str:
    """Drop # comment lines (they guide Enhance but never reach the tool)."""
    kept = [line for line in prompt.split("\n") if not line.lstrip().startswith("#")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def unwrap_verbatim(prompt: str) -> str:
    """Drop the [ ] markers — the final prompt uses the text directly."""
    return re.sub(r"\[([^\[\]]+)\]", r"\1", prompt)


def expand_named_wildcards(
    prompt: str,
    wildcards: List[Dict[str, Any]],
    segments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Replace each {{name}} with a segment's fixed content (checked first) or
    a random value from the matching wildcard list. Unknown names stay as-is."""
    if not wildcards and not segments:
        return prompt

    wildcard_lookup = {str(w["name"]).lower(): w.get("values") or [] for w in wildcards}
    segment_lookup = {str(s["name"]).lower(): s.get("content", "") for s in (segments or [])}

    def _repl(match: re.Match) -> str:
        key = match.group(1).strip().lower()
        if key in segment_lookup:
            return segment_lookup[key]
        values = wildcard_lookup.get(key)
        if not values:
            return match.group(0)
        return random.choice(values)

    return re.sub(r"\{\{([^{}]+)\}\}", _repl, prompt)


def expand_wildcards(prompt: str) -> str:
    """Replace each inline {a|b|c} with a random option ({foo} → "foo").
    Unresolved {{name}} tokens are protected so this pass can't eat their
    inner braces."""
    protected: List[str] = []

    def _protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    result = re.sub(r"\{\{[^{}]+\}\}", _protect, prompt)

    def _pick(match: re.Match) -> str:
        choices = [s.strip() for s in match.group(1).split("|")]
        return random.choice(choices)

    result = re.sub(r"\{([^{}]+)\}", _pick, result)
    return re.sub("\x00(\\d+)\x00", lambda m: protected[int(m.group(1))], result)


def process_final_prompt(
    prompt: str,
    wildcards: Optional[List[Dict[str, Any]]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    preserve_brackets: bool = False,
) -> str:
    """Final resolve: {{name}} first (segment content gets further processing),
    then strip comments, unwrap verbatim, expand inline wildcards."""
    result = prompt
    if wildcards or segments:
        result = expand_named_wildcards(result, wildcards or [], segments)
    result = strip_comments(result)
    if not preserve_brackets:
        result = unwrap_verbatim(result)
    result = expand_wildcards(result)
    return result


def resolve_wildcards_for_llm(
    prompt: str,
    wildcards: Optional[List[Dict[str, Any]]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resolve random prompt syntax before any LLM step, while preserving
    comments and [verbatim] markers."""
    result = prompt
    if wildcards or segments:
        result = expand_named_wildcards(result, wildcards or [], segments)
    return expand_wildcards(result)


# --- Ideogram 4 detection (mirrors isIdeogram4 in ToolView.vue) ----------------

def is_ideogram4(model_vendor: Optional[str], model: Optional[str]) -> bool:
    vendor = (model_vendor or "").lower()
    if vendor != "ideogram":
        return False
    m = (model or "").lower()
    return bool(re.search(r"ideogram[\s:_-]*v?4(\b|@|\.0|$)", m)) or "ideogram:4" in m


# --- LLM steps (mirror improveViaApi / translateViaApi) -------------------------

async def _improve_with_verbatim_protection(
    db,
    prompt: str,
    instructions: Optional[str],
    model: Optional[str],
    is_video: bool,
    is_audio: bool,
    input_image_count: int,
    audio_conditioned: bool,
    media_id: Optional[int],
    h3_task: Optional[str],
    h3_duration: Optional[float],
    h3_media_ids: Optional[List[Optional[int]]],
    h3_reference_manifest: Optional[List[Dict[str, Any]]],
    h3_generate_audio: bool,
    project_id: Optional[int],
) -> str:
    from routes.prompt_enhancement import ImprovePromptRequest, improve_prompt

    prompt_with_placeholders, segments = extract_verbatim(
        prompt,
        preserve_h3_structure=(
            h3_task is not None and "integrated_multimodal_description:" in prompt
        ),
    )

    last_candidate: Optional[str] = None
    for attempt in range(_MAX_LLM_RETRIES):
        request = ImprovePromptRequest(
            prompt=prompt_with_placeholders,
            instructions=instructions or None,
            model=model or None,
            is_video=is_video,
            is_audio=is_audio,
            input_image_count=input_image_count,
            audio_conditioned=audio_conditioned,
            media_id=media_id,
            h3_task=h3_task,
            h3_duration=h3_duration,
            h3_media_ids=h3_media_ids or [],
            h3_reference_manifest=h3_reference_manifest or [],
            h3_generate_audio=h3_generate_audio,
            project_id=project_id,
        )
        async with db.async_session_maker() as session:
            candidate = (await improve_prompt(request, session)).improved_prompt
        last_candidate = candidate
        if h3_task is not None and not _valid_h3_context_ir(
            candidate,
            h3_task,
            h3_duration,
            h3_reference_manifest,
            source_prompt=prompt_with_placeholders,
        ):
            log.warning(
                f"[prompt-pipeline] Improve attempt {attempt + 1}: invalid H3 Context-IR, retrying..."
            )
            continue
        if not segments:
            return candidate
        if verify_verbatim_preserved(candidate, segments):
            return restore_verbatim(
                candidate, segments, include_brackets=(h3_task is None)
            )
        log.warning(f"[prompt-pipeline] Improve attempt {attempt + 1}: verbatim placeholders dropped, retrying...")

    if h3_task is not None and last_candidate is not None and not segments:
        log.warning("[prompt-pipeline] H3 enhancement never passed validation; using original prompt")
        return prompt
    log.warning("[prompt-pipeline] All improve retries failed validation, using original prompt")
    return prompt


def _valid_h3_context_ir(
    prompt: str,
    task: str,
    duration: Optional[float],
    reference_manifest: Optional[List[Dict[str, Any]]] = None,
    *,
    source_prompt: Optional[str] = None,
) -> bool:
    """Cheap structural guardrail for the official H3 Base prompt schema."""
    fields = (
        "integrated_multimodal_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    )
    positions = [prompt.find(field) for field in fields]
    if positions[0] < 0 or positions != sorted(positions):
        return False
    if source_prompt is not None and not _h3_dialogue_is_grounded(prompt, source_prompt):
        return False
    stripped = prompt.strip()
    if task == "t2va":
        return stripped.startswith(fields[0])
    if task == "ref2va":
        if not stripped.startswith(fields[0]):
            return False
        return all(
            f"<{item.get('label')}>" in stripped
            for item in (reference_manifest or [])
            if item.get("label")
        )
    if task == "i2va":
        return stripped.startswith(
            "For the target video, at 0.00 seconds into the target video, <Picture 1> "
            "(from [Shot 1]) is fully referenced."
        )
    end_time = f"{max(0.0, float(duration or 0.0)):.2f}-second mark"
    if task == "fl2va":
        return (
            stripped.startswith("How the reference pictures align with the target video —")
            and "Picture 1 (from Shot 1)" in stripped
            and "Picture 2 (from Shot " in stripped
            and end_time in stripped
            and "Shot N" not in stripped
        )
    if task == "l2va":
        return (
            stripped.startswith("How the reference pictures align with the target video —")
            and "<Picture 1> (from [Shot " in stripped
            and end_time in stripped
            and "Shot N" not in stripped
        )
    return False


_H3_DIALOGUE_CONTENT_RE = re.compile(r"<d>(.*?)</d>", re.IGNORECASE | re.DOTALL)
_H3_DIALOGUE_CONTROL_RE = re.compile(
    r"(?:^\s*\[[^\[\]\n]+\]\s*|</?(?:scenetrans|cutoff)>|</?d>)",
    re.IGNORECASE,
)
_H3_REFERENCE_TAG_RE = re.compile(r"<(?:Picture|Video|Audio)\s+\d+>")
_H3_REFERENCE_TEXT_RE = re.compile(
    r"\b(?:Picture|Video|Audio|Shot)\s+\d+\b", re.IGNORECASE
)
_H3_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")
_H3_SCHEMA_FIELDS = {
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
    # Keep these too when a user supplies a Seedance-style prompt before the
    # H3 enhancer is run. Translation must not silently reshape that input.
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
}


def _translation_numeric_signature(value: str) -> List[str]:
    """Numbers are semantic prompt data, not prose for an LLM to rewrite."""
    return _H3_NUMBER_RE.findall(value)


def _h3_translation_signature(value: str) -> Dict[str, Any]:
    """Extract the H3/Context-IR tokens a translation is never allowed to change."""
    fields = re.findall(
        r"(?m)^\s*([a-z][a-z0-9_]*)\s*:", value
    )
    fields = [field for field in fields if field in _H3_SCHEMA_FIELDS]

    numeric_source = _H3_REFERENCE_TEXT_RE.sub(" ", value)
    numbers = _H3_NUMBER_RE.findall(numeric_source)
    return {
        "references": _H3_REFERENCE_TAG_RE.findall(value),
        "fields": fields,
        "numbers": numbers,
        "dialogue": _H3_DIALOGUE_CONTENT_RE.findall(value),
        "first_line": value.strip().splitlines()[0] if value.strip() else "",
    }


def _h3_translation_is_structurally_preserved(
    candidate: str,
    source: str,
    task: str,
    reference_manifest: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Ensure Chinese translation cannot turn H3 references/timing into prose."""
    source_sig = _h3_translation_signature(source)
    candidate_sig = _h3_translation_signature(candidate)

    if source_sig["references"] != candidate_sig["references"]:
        return False
    if source_sig["fields"] != candidate_sig["fields"]:
        return False
    if source_sig["numbers"] != candidate_sig["numbers"]:
        return False
    if source_sig["dialogue"] != candidate_sig["dialogue"]:
        return False

    # H3 alignment lines and the R2V leading field are protocol text. Keep
    # them byte-for-byte so the local validator and the ComfyUI node agree.
    source_first_line = source_sig["first_line"]
    if (
        source_first_line.startswith("How the reference pictures align with")
        or source_first_line.startswith("For the target video, at 0.00 seconds")
    ) and candidate_sig["first_line"] != source_first_line:
        return False
    if task == "ref2va" and source_first_line.startswith(
        "integrated_multimodal_description:"
    ) and not candidate_sig["first_line"].startswith(
        "integrated_multimodal_description:"
    ):
        return False

    for item in reference_manifest or []:
        label = str(item.get("label") or "").strip()
        if label and f"<{label}>" not in candidate:
            return False
    return True


def _normalized_h3_dialogue(value: str) -> str:
    value = _H3_DIALOGUE_CONTROL_RE.sub(" ", value)
    return " ".join(re.findall(r"\w+", value.lower(), flags=re.UNICODE))


def _h3_dialogue_is_grounded(candidate: str, source_prompt: str) -> bool:
    """Reject H3 dialogue that is absent from or adds words to the user input."""
    from routes.prompt_enhancement import _h3_input_has_dialogue

    blocks = _H3_DIALOGUE_CONTENT_RE.findall(candidate)
    if not _h3_input_has_dialogue(source_prompt):
        return not blocks
    if not blocks:
        return False

    normalized_source = _normalized_h3_dialogue(source_prompt)
    return all(
        bool(normalized := _normalized_h3_dialogue(block))
        and normalized in normalized_source
        for block in blocks
    )


async def _translate_with_verbatim_protection(
    prompt: str,
    language_code: str,
    project_id: Optional[int] = None,
    *,
    h3_task: Optional[str] = None,
    h3_duration: Optional[float] = None,
    h3_reference_manifest: Optional[List[Dict[str, Any]]] = None,
) -> str:
    from routes.prompt_enhancement import (
        PROMPT_LANGUAGE_ENGLISH_BY_CODE,
        TranslatePromptRequest,
        translate_prompt,
    )

    target = PROMPT_LANGUAGE_ENGLISH_BY_CODE.get(language_code)
    if not target:
        return prompt  # unknown code — nothing to do

    prompt_with_placeholders, segments = extract_verbatim(
        prompt, preserve_h3_structure=h3_task is not None
    )
    source_numbers = _translation_numeric_signature(prompt_with_placeholders)

    for attempt in range(_MAX_LLM_RETRIES):
        request = TranslatePromptRequest(
            prompt=prompt_with_placeholders,
            target_language=target,
            project_id=project_id,
            h3_task=h3_task,
            h3_duration=h3_duration,
            h3_reference_manifest=h3_reference_manifest or [],
        )
        candidate = (await translate_prompt(request)).translated_prompt
        if segments and not verify_verbatim_preserved(candidate, segments):
            log.warning(
                f"[prompt-pipeline] Translate attempt {attempt + 1}: "
                "verbatim placeholders dropped, retrying..."
            )
            continue
        if not h3_task and _translation_numeric_signature(candidate) != source_numbers:
            log.warning(
                f"[prompt-pipeline] Translate attempt {attempt + 1}: "
                "numeric values changed, retrying..."
            )
            continue
        if h3_task and not _h3_translation_is_structurally_preserved(
            candidate, prompt_with_placeholders, h3_task, h3_reference_manifest
        ):
            log.warning(
                f"[prompt-pipeline] Translate attempt {attempt + 1}: "
                "H3 structure/timing/references changed, retrying..."
            )
            continue
        if segments:
            return restore_verbatim(candidate, segments)
        return candidate

    log.warning(
        "[prompt-pipeline] All translate retries failed validation, "
        "using untranslated prompt"
    )
    return prompt


async def _to_ideogram_json(
    prompt: str,
    width: Optional[int],
    height: Optional[int],
    project_id: Optional[int] = None,
) -> str:
    from routes.prompt_enhancement import IdeogramJsonRequest, prompt_to_ideogram_json

    request = IdeogramJsonRequest(
        prompt=prompt, width=width or None, height=height or None, project_id=project_id
    )
    return (await prompt_to_ideogram_json(request)).json_prompt


# --- Orchestration (mirrors submitJobAsync steps 1-3 + applyJsonMode) -----------

def _profile_wildcards_and_segments(profile_id: Optional[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not profile_id:
        return [], []
    try:
        from config import get_settings
        settings = get_settings()
        wildcards = [
            {"name": w.name, "values": list(w.values or [])}
            for w in settings.get_wildcards_for_profile(profile_id)
        ]
        segments = [
            {"name": s.name, "content": s.content or ""}
            for s in settings.get_prompt_segments_for_profile(profile_id)
        ]
        return wildcards, segments
    except Exception as e:
        log.warning(f"[prompt-pipeline] Could not load wildcards for profile {profile_id}: {e}")
        return [], []


def prompt_sources_signature(
    wildcards: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> str:
    """Stable signature shared with usePromptPreloader.ts for preload validation."""
    normalized_wildcards = sorted(
        (
            {
                "name": str(w.get("name", "")).lower(),
                "values": list(w.get("values") or []),
            }
            for w in wildcards
        ),
        key=lambda item: item["name"],
    )
    normalized_segments = sorted(
        (
            {
                "name": str(s.get("name", "")).lower(),
                "content": s.get("content") or "",
            }
            for s in segments
        ),
        key=lambda item: item["name"],
    )
    return json.dumps(
        {"wildcards": normalized_wildcards, "segments": normalized_segments},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _normalized_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _validated_prompt_preload(
    prompt_preload: Optional[Dict[str, Any]],
    *,
    prompt: str,
    instructions: Optional[str],
    model: Optional[str],
    is_video: bool,
    is_audio: bool,
    input_image_count: int,
    audio_conditioned: bool,
    source_signature: str,
) -> Optional[str]:
    if not isinstance(prompt_preload, dict):
        return None

    try:
        if prompt_preload.get("originalPrompt") != prompt:
            return None
        if prompt_preload.get("promptSourcesSignature") != source_signature:
            return None
        if _normalized_optional_string(prompt_preload.get("instructions")) != _normalized_optional_string(instructions):
            return None
        if _normalized_optional_string(prompt_preload.get("model")) != _normalized_optional_string(model):
            return None
        if bool(prompt_preload.get("isVideo")) != bool(is_video):
            return None
        if bool(prompt_preload.get("isAudio")) != bool(is_audio):
            return None
        if int(prompt_preload.get("inputImageCount") or 0) != int(input_image_count or 0):
            return None
        if bool(prompt_preload.get("audioConditioned")) != bool(audio_conditioned):
            return None
    except (TypeError, ValueError):
        return None

    processed_prompt = prompt_preload.get("processedPrompt")
    improved_prompt = prompt_preload.get("improvedPrompt")
    if not isinstance(processed_prompt, str) or not processed_prompt.strip():
        return None
    if not isinstance(improved_prompt, str) or not improved_prompt.strip():
        return None
    return improved_prompt


def _is_llm_unconfigured_error(exc: Exception) -> bool:
    """True only for the strict "no LLM source configured at all" failure.

    A user with zero LLM sources has opted out of LLM features, so a stale
    enhance/translate flag (an old preset, a queued job, a chain step) must not
    fail their generation — the step is skipped instead. Every other LLM
    failure (no balance, provider down, cloud unreachable) means a configured
    source is broken, and the job keeps failing loudly as before.
    """
    from fastapi import HTTPException

    from llm_resolver import LLMNotConfiguredError

    if isinstance(exc, HTTPException):
        detail = exc.detail
        return isinstance(detail, dict) and detail.get("code") == "llm_not_configured"
    return isinstance(exc, LLMNotConfiguredError) and exc.code == "llm_not_configured"


async def run_prompt_pipeline(
    db,
    prompt: str,
    prompt_options: Optional[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    model_vendor: Optional[str] = None,
    is_video: bool = False,
    is_audio: bool = False,
    input_image_count: int = 0,
    audio_conditioned: bool = False,
    media_id: Optional[int] = None,
    h3_task: Optional[str] = None,
    h3_duration: Optional[float] = None,
    h3_media_ids: Optional[List[Optional[int]]] = None,
    h3_reference_manifest: Optional[List[Dict[str, Any]]] = None,
    h3_generate_audio: bool = True,
    width: Optional[int] = None,
    height: Optional[int] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[int] = None,
    prompt_preload: Optional[Dict[str, Any]] = None,
) -> str:
    """Run the full generate-time pipeline on a prompt, server-side.

    `prompt_options` is the raw PromptOptions shape the editor persists
    ({autoImprove: {enabled, instructions}, translate: {enabled, language}});
    absent/disabled options skip the LLM steps, but final processing
    (comments/verbatim and any LLM-introduced wildcards) ALWAYS runs — same
    as an interactive submit.
    LLM failures propagate (the caller fails the step, like the interactive
    submit surfaces the error); verbatim-drop retries fall back non-fatally.
    The one exception is the strict "no LLM configured at all" state — the
    user has opted out of LLM features, so the LLM steps are skipped and the
    prompt passes through (see _is_llm_unconfigured_error).
    """
    if not prompt:
        return prompt

    options = prompt_options or {}
    auto_improve = options.get("autoImprove") or {}
    translate = options.get("translate") or {}

    enhance_on = bool(auto_improve.get("enabled"))
    ideogram_json_mode = enhance_on and (
        auto_improve.get("mode") == "ideogram-json"
        or is_ideogram4(model_vendor, model)
    )

    wildcards, segments = _profile_wildcards_and_segments(profile_id)
    source_signature = prompt_sources_signature(wildcards, segments)
    instructions = (auto_improve.get("instructions") or "").strip() or None

    preloaded_improved: Optional[str] = None
    if enhance_on and not ideogram_json_mode and h3_task is None:
        preloaded_improved = _validated_prompt_preload(
            prompt_preload,
            prompt=prompt,
            instructions=instructions,
            model=model,
            is_video=is_video,
            is_audio=is_audio,
            input_image_count=input_image_count,
            audio_conditioned=audio_conditioned,
            source_signature=source_signature,
        )

    if preloaded_improved is not None:
        log.debug("[prompt-pipeline] Using preloaded prompt enhancement")
        processed = preloaded_improved
    else:
        processed = resolve_wildcards_for_llm(prompt, wildcards, segments)

    # 2) Enhance (text styles only; Ideogram JSON runs post-resolve).
    if enhance_on and not ideogram_json_mode and preloaded_improved is None:
        try:
            processed = await _improve_with_verbatim_protection(
                db,
                processed,
                instructions=instructions,
                model=model,
                is_video=is_video,
                is_audio=is_audio,
                input_image_count=input_image_count,
                audio_conditioned=audio_conditioned,
                media_id=media_id,
                h3_task=h3_task,
                h3_duration=h3_duration,
                h3_media_ids=h3_media_ids,
                h3_reference_manifest=h3_reference_manifest,
                h3_generate_audio=h3_generate_audio,
                project_id=project_id,
            )
        except Exception as e:
            if not _is_llm_unconfigured_error(e):
                raise
            log.info("[prompt-pipeline] No LLM configured; skipping enhancement")

    # 3) Translate. H3 gets a dedicated translation pass: natural-language
    # prose is translated, while Context-IR fields, references, dialogue,
    # numeric values, and task-specific alignment syntax are protected.
    if translate.get("enabled") and translate.get("language"):
        try:
            processed = await _translate_with_verbatim_protection(
                processed,
                translate["language"],
                project_id,
                h3_task=h3_task,
                h3_duration=h3_duration,
                h3_reference_manifest=h3_reference_manifest,
            )
        except Exception as e:
            if not _is_llm_unconfigured_error(e):
                raise
            log.info("[prompt-pipeline] No LLM configured; skipping translation")

    # 4) Final cleanup: comments, verbatim, and any wildcard syntax introduced
    # by the LLM.
    processed = process_final_prompt(
        processed, wildcards, segments, preserve_brackets=(h3_task is not None)
    )

    # 5) Ideogram JSON — on the fully resolved prompt (last step).
    if ideogram_json_mode:
        try:
            processed = await _to_ideogram_json(processed, width, height, project_id)
        except Exception as e:
            if not _is_llm_unconfigured_error(e):
                raise
            log.info("[prompt-pipeline] No LLM configured; skipping Ideogram JSON conversion")

    return processed
