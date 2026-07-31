"""Storage for the op-stack image editor's working documents.

The document is a *directory* at the WorkingDocument's ``state_locator``:

    <state_locator>/
      document.json      the current stack — small, atomically rewritten
      journal.jsonl      recent undo history, append-mostly and bounded
      payloads/          masks, patches, stroke json, raster layers
      cache/             composite intermediates; reconstructible, deletable

Payload storage is deliberately pack-ratty, but undo history is not. Deleting
a step removes it from ``document.json`` only; its payloads stay, while the
journal retains a bounded window of recent actions and their inverses.
``cache/`` is reconstructible from document + payloads + base.

There is exactly one writer (the editor screen for that asset), no concurrent
access and no indexed queries, which is why this is JSON and an append-mostly
log rather than SQLite. The journal's ``(seq, ts, action, inverse)`` row shape
is chosen to match the NLE's op-log so that migration stays mechanical if
stacks ever outgrow this.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import app_dirs
from database import WorkingDocument


EDITOR_TYPE = "image-stack"
DOCUMENT_FORMAT = "stimma-image-stack"
DOCUMENT_VERSION = 1

# Payload and cache names are minted by the client (op ULIDs) but never trusted:
# no separators, no dots beyond the extension, so nothing can escape the
# document directory.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.(png|json|webp)$")
_HEAD_CACHE_NAME = re.compile(r"^head-[0-9a-f]{8}\.png$")

# The current document is authoritative. The journal exists only to restore a
# useful recent undo window after reopening, so reads are capped exactly at this
# size. Writes stay cheap and append-only until a little slack accumulates, then
# atomically compact back to the cap.
JOURNAL_MAX_ENTRIES = 500
JOURNAL_COMPACT_AT = 600


class ImageStackError(Exception):
    """Invalid request against a stack document."""


def document_dir(document: WorkingDocument, profile_id: str) -> Path:
    """The document's directory, derived from the profile when unset.

    Derivation rather than a hard requirement on ``state_locator`` keeps a
    document openable if the row was created before the directory existed.
    """
    if document.state_locator:
        return Path(document.state_locator)
    return app_dirs.get_profile_dir(profile_id) / "image_stacks" / str(document.id)


def ensure_layout(directory: Path) -> None:
    (directory / "payloads").mkdir(parents=True, exist_ok=True)
    (directory / "cache").mkdir(parents=True, exist_ok=True)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# document.json
# ---------------------------------------------------------------------------

def empty_document(
    *,
    asset_id: int,
    revision_id: int,
    media_id: int,
    file_hash: str,
    width: int,
    height: int,
) -> dict:
    """A stack with no edits — the base revision, and nothing on top of it."""
    return {
        "format": DOCUMENT_FORMAT,
        "version": DOCUMENT_VERSION,
        "base": {
            "asset_id": asset_id,
            "revision_id": revision_id,
            "media_id": media_id,
            # The durable pixel reference. Media ids are recyclable rowids on
            # existing installs; asset and revision ids are not.
            "file_hash": file_hash,
        },
        "canvas": {"width": width, "height": height},
        "edits": [],
    }


def validate_document(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ImageStackError("Document must be an object")
    if payload.get("format") != DOCUMENT_FORMAT:
        raise ImageStackError(f"Unknown document format: {payload.get('format')}")
    if payload.get("version") != DOCUMENT_VERSION:
        raise ImageStackError(f"Unsupported document version: {payload.get('version')}")
    if not isinstance(payload.get("base"), dict):
        raise ImageStackError("Document is missing its base revision")
    if not isinstance(payload.get("edits"), list):
        raise ImageStackError("Document edits must be a list")
    return payload


async def read_document(directory: Path) -> dict | None:
    path = directory / "document.json"
    if not path.exists():
        return None
    return await asyncio.to_thread(_read_json, path)


async def write_document(directory: Path, payload: dict) -> None:
    validate_document(payload)
    ensure_layout(directory)
    await asyncio.to_thread(_write_json_atomic, directory / "document.json", payload)


# ---------------------------------------------------------------------------
# journal.jsonl
# ---------------------------------------------------------------------------

def _append_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line)
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_jsonl_atomic(path: Path, entries: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temp.open("x", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, separators=(",", ":")))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


async def append_journal(directory: Path, entries: list[dict]) -> int:
    """Append entries and return the retained on-disk count.

    Entries are shaped ``{seq, ts, action, inverse}``. The client owns ``seq``
    because the undo cursor is a client-side position in this log; the server is
    deliberately dumb storage. Undos are themselves appended rather than
    truncating. Once enough slack accumulates, the journal is atomically
    compacted to the newest ``JOURNAL_MAX_ENTRIES`` entries.
    """
    for entry in entries:
        if not isinstance(entry, dict):
            raise ImageStackError("Journal entries must be objects")
        if "action" not in entry:
            raise ImageStackError("Journal entry is missing its action")
        entry.setdefault("ts", datetime.utcnow().isoformat())

    path = directory / "journal.jsonl"
    lines = [json.dumps(entry, separators=(",", ":")) for entry in entries]
    await asyncio.to_thread(_append_lines, path, lines)
    length = await journal_length(directory)
    if length >= JOURNAL_COMPACT_AT:
        return await asyncio.to_thread(_compact_journal, path)
    return length


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


async def journal_length(directory: Path) -> int:
    return await asyncio.to_thread(_count_lines, directory / "journal.jsonl")


def _read_journal_tail(path: Path) -> list[dict]:
    """Entries from the last checkpoint onward — the replayable suffix."""
    if not path.exists():
        return []
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # A torn final line from a crash mid-append. Everything before
                # it is still sound, so stop rather than discard the log.
                break
            if entry.get("action") == "checkpoint":
                entries = [entry]
            else:
                entries.append(entry)
    return entries


def _compact_journal(path: Path) -> int:
    entries = _read_journal_tail(path)[-JOURNAL_MAX_ENTRIES:]
    _write_jsonl_atomic(path, entries)
    return len(entries)


def _read_bounded_journal(path: Path) -> list[dict]:
    entries = _read_journal_tail(path)
    retained = entries[-JOURNAL_MAX_ENTRIES:]
    # Cull journals created before bounded retention on their first deferred
    # history read. This is intentionally outside the document-open path.
    if _count_lines(path) >= JOURNAL_COMPACT_AT:
        _write_jsonl_atomic(path, retained)
    return retained


async def read_journal(directory: Path) -> list[dict]:
    return await asyncio.to_thread(
        _read_bounded_journal, directory / "journal.jsonl"
    )


# ---------------------------------------------------------------------------
# payloads/ and cache/
# ---------------------------------------------------------------------------

def resolve_payload(directory: Path, name: str, *, subdir: str = "payloads") -> Path:
    if subdir not in {"payloads", "cache"}:
        raise ImageStackError(f"Unknown payload subdirectory: {subdir}")
    if not _SAFE_NAME.match(name or ""):
        raise ImageStackError("Invalid payload name")
    path = (directory / subdir / name).resolve()
    root = (directory / subdir).resolve()
    if root != path.parent:
        raise ImageStackError("Invalid payload name")
    return path


async def write_payload(
    directory: Path, name: str, data: bytes, *, subdir: str = "payloads"
) -> Path:
    path = resolve_payload(directory, name, subdir=subdir)
    ensure_layout(directory)

    def _write() -> None:
        temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            temp.write_bytes(data)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    await asyncio.to_thread(_write)
    return path


async def prune_head_caches(directory: Path, keep: str) -> None:
    """Keep only the newest hash-addressed materialized stack head.

    Other cache residents (selection derivatives and future intermediates) are
    unrelated and deliberately untouched.
    """
    if not _HEAD_CACHE_NAME.match(keep):
        return

    def _prune() -> None:
        cache = directory / "cache"
        if not cache.exists():
            return
        for path in cache.glob("head-*.png"):
            if path.name != keep and _HEAD_CACHE_NAME.match(path.name):
                path.unlink(missing_ok=True)

    await asyncio.to_thread(_prune)


async def clear_cache(directory: Path) -> None:
    """Drop the only subtree that is safe to drop."""
    cache = directory / "cache"
    if cache.exists():
        await asyncio.to_thread(shutil.rmtree, cache, True)
    ensure_layout(directory)


async def directory_size(directory: Path) -> int:
    def _size() -> int:
        total = 0
        for path in directory.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    if not directory.exists():
        return 0
    return await asyncio.to_thread(_size)
