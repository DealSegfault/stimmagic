"""Reviewed video preparation, stored in the existing chat settings JSON."""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path

from database import Chat, MediaItem
from sqlalchemy.ext.asyncio import async_sessionmaker

from .video_settings import h3_timing


def read_settings(chat) -> dict:
    value = chat.generation_settings
    return json.loads(value or "{}") if isinstance(value, str) else dict(value or {})


def preserve_video_plan(current: dict, incoming: dict) -> dict:
    """UI controls cannot erase or fabricate server-owned preparation state."""
    if not isinstance(incoming, dict):
        raise ValueError("generation_settings must encode an object")
    result = dict(incoming)
    if "_video_plan" in current:
        result["_video_plan"] = current["_video_plan"]
    else:
        result.pop("_video_plan", None)
    return result


def plan_key(plan: dict) -> str:
    content = {key: plan[key] for key in ("target_duration", "assets", "clips")}
    content["settings"] = plan.get("settings", {})
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _number(value, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
    return float(value)


def normalize_plan(value: dict, previous: dict | None = None, *, controls: dict | None = None) -> dict:
    if not isinstance(value, dict) or set(value) - {"target_duration", "assets", "clips"}:
        unsupported = sorted(map(str, set(value) - {"target_duration", "assets", "clips"})) if isinstance(value, dict) else []
        raise ValueError(
            f"video_plan requires an object with target_duration, assets and clips only; unsupported fields: {unsupported}. "
            "Use target_duration for final edit length; set steps/resolution with await stimma.video_settings(...). "
            "Review approvals belong to the user. Read the schema with print(sdk_help('video_plan'))."
        )
    target = _number(value.get("target_duration"), "target_duration", 1, 3600)
    assets = value.get("assets")
    clips = value.get("clips")
    if not isinstance(assets, list) or not isinstance(clips, list) or len(assets) > 100 or len(clips) > 100:
        raise ValueError("assets and clips must be lists (at most 100 each)")
    normalized_assets = []
    names = set()
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) - {"name", "media_id"}:
            raise ValueError("Each asset contains name and media_id (null until prepared)")
        name, media_id = asset.get("name"), asset.get("media_id")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Asset names must be nonempty and unique")
        if media_id is not None and (type(media_id) is not int or media_id <= 0):
            raise ValueError("Assets must bind immutable positive media IDs")
        names.add(name)
        normalized_assets.append({"name": name, "media_id": media_id})
    normalized_clips = []
    ids = set()
    for clip in clips:
        if not isinstance(clip, dict) or set(clip) - {"id", "tool_id", "duration", "edit_duration", "parameters"}:
            raise ValueError(
                "Each clip contains id, tool_id, duration, edit_duration and parameters; use id for its descriptive name. "
                "tool_id comes from the live catalog, duration is the generation request, edit_duration is its length in the final film, "
                "and parameters contains the actual prompt and media references. Read the schema with print(sdk_help('video_plan'))."
            )
        clip_id, tool_id = clip.get("id"), clip.get("tool_id")
        if not isinstance(clip_id, str) or not clip_id.strip() or clip_id in ids:
            raise ValueError("Clip IDs must be nonempty and unique")
        if not isinstance(tool_id, str) or "minimax_h3" not in tool_id.lower().replace("-", "_"):
            raise ValueError("Use a real MiniMax H3 tool_id from the catalog")
        duration = _number(clip.get("duration"), "duration", 1, 15)
        if duration * 2 != round(duration * 2):
            raise ValueError("Generation duration uses the chat's 0.5 second increments")
        edit_duration = _number(clip.get("edit_duration"), "edit_duration", 1 / 24, h3_timing(duration)["effective_duration"])
        if abs(edit_duration * 24 - round(edit_duration * 24)) > 1e-6:
            raise ValueError("edit_duration must align to the 24 fps edit timeline")
        params = clip.get("parameters", {})
        if not isinstance(params, dict) or any(not isinstance(key, str) or key.startswith("_") for key in params):
            raise ValueError("parameters must contain public tool arguments only")
        if "duration" in params and params["duration"] != duration:
            raise ValueError("parameters.duration must match the clip duration")
        params = {**params, "duration": duration}
        json.dumps(params, allow_nan=False)
        for field in ("input_images", "input_videos", "input_audios"):
            refs = params.get(field, [])
            if not isinstance(refs, list) or any(type(ref) is not int or ref <= 0 for ref in refs):
                raise ValueError(f"{field} must use immutable media IDs")
        if "i2v" in tool_id.lower() and len(params.get("input_images", [])) != 1:
            raise ValueError("I2V requires exactly one starting frame; use R2V for multiple references")
        if "t2v" in tool_id.lower() and any(params.get(field) for field in ("input_images", "input_videos", "input_audios")):
            raise ValueError("T2V is text-only; use R2V for semantic references")
        ids.add(clip_id)
        normalized_clips.append({"id": clip_id, "tool_id": tool_id, "duration": duration, "edit_duration": edit_duration, "parameters": params})
    plan = {"target_duration": target, "assets": normalized_assets, "clips": normalized_clips, "settings": controls or {}}
    media_ids = {asset["media_id"] for asset in normalized_assets if asset["media_id"]}
    previous = previous or {}
    plan["approved_media_ids"] = sorted(media_ids.intersection(previous.get("approved_media_ids", [])))
    unchanged = bool(previous) and plan_key(previous) == plan_key(plan)
    plan["authorized_key"] = previous.get("authorized_key") if unchanged else None
    plan["outputs"] = previous.get("outputs", {}) if unchanged else {}
    return plan


def preparation_errors(plan: dict, *, require_reviews: bool = True) -> list[str]:
    errors = []
    media_ids = {asset["media_id"] for asset in plan["assets"] if asset["media_id"]}
    for asset in plan["assets"]:
        if not asset["media_id"]:
            errors.append(f"Prepare {asset['name']}")
        elif require_reviews and asset["media_id"] not in plan["approved_media_ids"]:
            errors.append(f"Review {asset['name']} (media {asset['media_id']})")
    if not plan["clips"]:
        errors.append("Prepare the clips and prompts")
    for clip in plan["clips"]:
        if not str(clip["parameters"].get("prompt") or "").strip():
            errors.append(f"Prepare the prompt for {clip['id']}")
        for field in ("input_images", "input_videos", "input_audios"):
            if set(clip["parameters"].get(field, [])) - media_ids:
                errors.append(f"Register all {field} assets for {clip['id']}")
    if abs(sum(clip["edit_duration"] for clip in plan["clips"]) - plan["target_duration"]) > 1e-6:
        errors.append("Clip edit durations must sum to target_duration")
    return errors


def asset_preparation_needs_continuation(previous: dict | None, current: dict | None, *, continuing: bool = False) -> bool:
    """An asset was prepared this run, but the preparation is still incomplete."""
    if not current:
        return False
    missing = {asset["name"] for asset in (previous or {}).get("assets", []) if asset["media_id"] is None}
    progressed = any(asset["name"] in missing and asset["media_id"] is not None for asset in current["assets"])
    return bool((continuing or progressed) and preparation_errors(current))


async def validate_assets(session, plan: dict) -> None:
    for media_id in {asset["media_id"] for asset in plan["assets"] if asset["media_id"]}:
        media = await session.get(MediaItem, media_id, populate_existing=True)
        if not media or media.deleted_at or media.deletion_pending_at or media.file_unavailable:
            raise ValueError(f"Asset media {media_id} is unavailable; replace it and request a new review")
        if not Path(media.file_path).is_file():
            raise ValueError(f"Asset media {media_id} has no available file; restore it before generation")


def prepare_review(settings: dict, review: dict) -> tuple[dict, list[dict]]:
    plan = settings.get("_video_plan")
    if not plan:
        raise ValueError("Create a video plan before requesting its review")
    if not isinstance(review, dict) or set(review) - {"media_ids", "start"}:
        raise ValueError("video_review contains media_ids or start=true")
    media_ids = review.get("media_ids", [])
    if not isinstance(media_ids, list) or any(type(mid) is not int for mid in media_ids):
        raise ValueError("Review media_ids must be integers")
    start = review.get("start") is True
    if bool(media_ids) == start:
        raise ValueError("Review assets or request the video series start separately")
    if set(media_ids) - {asset["media_id"] for asset in plan["assets"]}:
        raise ValueError("Review only the current plan's exact asset versions")
    if start and preparation_errors(plan):
        raise ValueError("Video preparation incomplete: " + "; ".join(preparation_errors(plan)))
    label = "Lancer les vidéos" if start else "Valider les assets"
    controls = plan.get("settings", {})
    resolution = "2K" if controls.get("resolution") == "2k" else f"{controls.get('resolution', '720')}p"
    steps = 8 if controls.get("fast") else controls.get("steps", 20)
    detail = (
        f"Générer les {len(plan['clips'])} clips préparés, un par un, pour le montage de {plan['target_duration']:g} s, en {resolution} avec {steps} steps."
        if start else "Valider : " + ", ".join(f"{asset['name']} (media {asset['media_id']})" for asset in plan["assets"] if asset["media_id"] in media_ids)
    )
    return {"key": plan_key(plan), "media_ids": media_ids, "start": start, "label": label}, [
        {"label": label, "description": detail},
        {"label": "Modifier", "description": "Poursuivre la préparation sans lancer de vidéo."},
    ]


def record_review(settings: dict, pending: dict, answer: str) -> None:
    review = pending.get("video_review")
    plan = settings.get("_video_plan")
    if not review or not plan or answer.strip() != review["label"] or review["key"] != plan_key(plan):
        return
    if review["start"]:
        if not preparation_errors(plan):
            plan["authorized_key"] = review["key"]
    else:
        plan["approved_media_ids"] = sorted(set(plan["approved_media_ids"]) | set(review["media_ids"]))


def validate_dispatch(settings: dict, *, clip_id: str | None, key: str | None, tool_id: str, parameters: dict, effective_duration: float, controls: dict | None = None, effective_parameters: dict | None = None) -> None:
    plan = settings.get("_video_plan")
    if not plan:
        return
    errors = preparation_errors(plan)
    if errors:
        raise ValueError("Video preparation incomplete: " + "; ".join(errors))
    if plan.get("authorized_key") != plan_key(plan):
        raise ValueError("The user must explicitly start the reviewed video series via ask_user(video_review={start: true})")
    if controls is not None and controls != plan.get("settings", {}):
        raise ValueError("Video controls changed after review; update the plan and request a new start")
    next_clip = next((clip for clip in plan["clips"] if clip["id"] not in plan["outputs"]), None)
    if not next_clip or clip_id != next_clip["id"] or key != plan_key(plan):
        raise ValueError("Generate the prepared clips sequentially with await stimma.generate_video_plan()")
    if tool_id != next_clip["tool_id"] or parameters != next_clip["parameters"] or effective_duration != next_clip["duration"]:
        raise ValueError("The video request differs from the reviewed plan; update the plan and request a new start")
    for name in ("steps", "width", "height"):
        if effective_parameters is not None and name in parameters and parameters[name] != effective_parameters.get(name):
            raise ValueError(f"Effective {name} differs from the prepared clip; update the plan before launch")


async def update_chat_settings(session, chat_id: int, mutate) -> dict:
    """Read fresh settings before merging, preserving HITL and UI state."""
    from utils.websocket import ws_manager

    async with async_sessionmaker(session.bind, expire_on_commit=False)() as fresh:
        chat = await fresh.get(Chat, chat_id)
        if not chat or chat.deleted_at:
            raise ValueError("Chat is unavailable")
        settings = read_settings(chat)
        result = await mutate(settings, fresh)
        encoded = json.dumps(settings)
        if encoded != chat.generation_settings:
            chat.generation_settings = encoded
            await fresh.commit()
            await ws_manager.broadcast("chat_updated", {"chat_id": chat_id, "chat": chat.to_dict(), "settings_changed": True})
        return result
