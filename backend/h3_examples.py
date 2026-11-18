"""Read-only H3 prompt/render catalogue shared by the chat and agent library."""

import base64
import gzip
import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data" / "h3_examples"
ATLAS_URL = "https://cohub.live/baize/video-altas/w/h3-atlas"
DATASET_URL = "https://huggingface.co/datasets/ostris/minimax_h3_1k"


def _tokens(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {word for word in re.findall(r"[a-z0-9]+", plain) if len(word) > 2}


@lru_cache(maxsize=1)
def _catalogue() -> dict:
    with gzip.open(DATA_DIR / "prompts.json.gz", "rt", encoding="utf-8") as source:
        data = json.load(source)
    data["by_id"] = {record["id"]: record for record in data["records"]}
    data["tokens"] = {
        record["id"]: _tokens(" ".join((
            record["description"], record["soundscape"], record["music"],
            data["styles"][record["style"]], " ".join(record["topics"]),
        ))) for record in data["records"]
    }
    counts = Counter(word for words in data["tokens"].values() for word in words)
    data["weights"] = {word: math.log(1 + len(data["records"]) / count) for word, count in counts.items()}
    return data


def _record(example_id: str) -> dict:
    if not re.fullmatch(r"\d{6}", str(example_id)):
        raise KeyError(example_id)
    return _catalogue()["by_id"][example_id]


def _summary(record: dict) -> dict:
    data = _catalogue()
    return {
        key: record[key] for key in ("id", "style", "topics", "aspect", "w", "h", "seconds", "shots", "langs")
    } | {
        "style_label": data["styles"][record["style"]],
        "excerpt": record["description"].removeprefix("[Shot 1] ")[:240],
        "thumbnail_url": f"/api/prompt/h3/examples/{record['id']}/thumbnail",
        "video_url": data["video"]["huggingface"].format(id=record["id"]),
        "chat_link": f"[{{label}}](stimma-h3:{record['id']})",
    }


def get_example(example_id: str) -> dict:
    record = _record(example_id)
    opening = record["description"].removeprefix("[Shot 1] ")
    treatment = re.split(r", (?:in|inside|at|a|an|the)\b", opening, maxsplit=1)[0]
    camera = re.findall(r"[^.!?]*(?:[Cc]amera)[^.!?]*[.!?]", record["description"])
    return _summary(record) | {
        "visual_treatment": treatment[:320],
        "camera": " ".join(sentence.strip() for sentence in camera)[-700:],
        "description": record["description"],
        "soundscape": record["soundscape"],
        "music": record["music"],
        "prompt": (
            f"integrated_multimodal_description: {record['description']}\n\n"
            f"overall_soundscape: {record['soundscape']}\n\n"
            f"non_diegetic_music: {record['music']}"
        ),
        "task": "T2VA",
        "credit": _catalogue()["credit"],
        "atlas_url": ATLAS_URL,
        "source_url": f"{DATASET_URL}/blob/main/{record['id']}.mp4",
    }


def search_examples(
    query: str = "", *, style: str = "", topic: str = "", similar_to: str = "",
    limit: int = 24, offset: int = 0,
) -> dict:
    data = _catalogue()
    related = _record(similar_to) if similar_to else None
    words = _tokens(query)
    # The source prompts are English; these common scene terms also work in the French chat.
    aliases = {
        "noir": "black white noir", "blanc": "white", "mafieux": "don mafia gangster",
        "mafia": "don mafia gangster", "cigare": "cigar", "fumee": "smoke",
        "publicite": "advertising product", "cuisine": "cooking kitchen",
        "pluie": "rain", "voiture": "car", "foret": "forest", "nuit": "night",
    }
    for word in tuple(words):
        if word in aliases:
            words.remove(word)
            words.update(_tokens(aliases[word]))
    related_words = data["tokens"][similar_to] if related else set()
    ranked = []
    for record in data["records"]:
        if (style and record["style"] != style) or (topic and topic not in record["topics"]):
            continue
        if related and record["id"] == related["id"]:
            continue
        tokens = data["tokens"][record["id"]]
        score = sum(data["weights"].get(word, 0) for word in words & tokens)
        if query.strip() == record["id"]:
            score += 100
        if words and not score:
            continue
        if related:
            overlap = sum(data["weights"][word] for word in related_words & tokens)
            union = sum(data["weights"][word] for word in related_words | tokens)
            score += overlap / max(1, union)
            score += 0.3 * (record["style"] == related["style"])
            score += 0.1 * len(set(record["topics"]) & set(related["topics"]))
        ranked.append((score, record))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    offset = max(0, int(offset))
    limit = min(60, max(1, int(limit)))
    return {
        "items": [_summary(record) for _, record in ranked[offset:offset + limit]],
        "total": len(ranked), "offset": offset,
        "styles": data["styles"], "topics": data["topics"],
    }


@lru_cache(maxsize=1)
def _thumbnails() -> dict:
    with gzip.open(DATA_DIR / "thumbs.json.gz", "rt", encoding="utf-8") as source:
        return json.load(source)["thumbs"]


def get_thumbnail(example_id: str) -> bytes:
    _record(example_id)
    return base64.b64decode(_thumbnails()[example_id])
