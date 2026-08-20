"""Stable bilingual prompt envelope used by the H3 chat workflow.

The envelope is deliberately plain text so it survives model history and can
be copied by a small agent.  The HTML comment markers are invisible in the
normal Markdown renderer, while the dispatch layer can still select the
Chinese production prompt without guessing from prose.
"""

from __future__ import annotations

from typing import Any, Mapping


H3_EN_START = "<!-- STIMMA_H3_PROMPT_EN -->"
H3_ZH_START = "<!-- STIMMA_H3_PROMPT_ZH -->"
H3_END = "<!-- STIMMA_H3_PROMPT_END -->"


def format_h3_prompt_pair(english: str, chinese: str) -> str:
    """Serialize two complete H3 prompts into the chat-safe envelope."""
    english = str(english or "").strip()
    chinese = str(chinese or "").strip()
    if not english or not chinese:
        raise ValueError("Both English and Chinese H3 prompts are required")
    return "\n\n".join((H3_EN_START, english, H3_ZH_START, chinese, H3_END))


def parse_h3_prompt_pair(value: Any) -> dict[str, str] | None:
    """Return the pair from an envelope or a persisted metadata object."""
    if isinstance(value, Mapping):
        english = str(value.get("english") or value.get("en") or "").strip()
        chinese = str(value.get("chinese") or value.get("zh") or "").strip()
        if english and chinese:
            return {"english": english, "chinese": chinese}
        return None

    text = str(value or "")
    en_start = text.find(H3_EN_START)
    zh_start = text.find(H3_ZH_START)
    end = text.find(H3_END)
    if en_start < 0 or zh_start < 0 or end < 0 or not en_start < zh_start < end:
        return None

    english = text[en_start + len(H3_EN_START):zh_start].strip()
    chinese = text[zh_start + len(H3_ZH_START):end].strip()
    if not english or not chinese:
        return None
    return {"english": english, "chinese": chinese}


def prompt_pair_metadata(pair: Mapping[str, Any], *, h3_task: str | None = None) -> dict[str, Any]:
    """Build the compact JSON-safe metadata stored on an assistant item."""
    parsed = parse_h3_prompt_pair(pair)
    if not parsed:
        raise ValueError("Invalid H3 prompt pair")
    metadata: dict[str, Any] = {
        "english": parsed["english"],
        "chinese": parsed["chinese"],
        "generation_language": "zh-Hans",
    }
    if h3_task:
        metadata["h3_task"] = h3_task
    return metadata


def select_chinese_h3_prompt(value: Any) -> tuple[str, dict[str, str] | None]:
    """Select Chinese from an envelope, otherwise return the original value."""
    pair = parse_h3_prompt_pair(value)
    if not pair:
        return str(value or ""), None
    return pair["chinese"], pair
