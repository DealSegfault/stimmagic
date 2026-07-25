"""Tests for LoRA name normalization and matching in unified.py."""

import pytest
from agent.tools.stp_utils import (
    AmbiguousLoraError,
    _find_lora_match,
    _normalize_lora_name,
)
from collections import defaultdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_index(available: list[str]) -> dict[str, list[str]]:
    """Build the normalized_name -> [paths] index used by _find_lora_match."""
    idx: dict[str, list[str]] = defaultdict(list)
    for path in available:
        idx[_normalize_lora_name(path)].append(path)
    return idx


def _match(query: str, available: list[str]):
    """Shortcut: run _find_lora_match and return (path, tier) or None."""
    return _find_lora_match(query, available, _build_index(available))


# ---------------------------------------------------------------------------
# _normalize_lora_name
# ---------------------------------------------------------------------------

class TestNormalizeLoraName:
    def test_strips_directory_and_extension(self):
        assert _normalize_lora_name("styles/Anime_V2.safetensors") == "anime v2"

    def test_strips_ckpt_extension(self):
        assert _normalize_lora_name("Realistic_Vision-v2.1.ckpt") == "realistic vision v2 1"

    def test_strips_pt_extension(self):
        assert _normalize_lora_name("MY-MODEL.pt") == "my model"

    def test_collapses_mixed_separators(self):
        assert _normalize_lora_name("a___b--c  d") == "a b c d"

    def test_underscores_become_spaces(self):
        assert _normalize_lora_name("already_clean") == "already clean"


# ---------------------------------------------------------------------------
# _find_lora_match — tier 1 (exact endswith + extension fallback)
# ---------------------------------------------------------------------------

class TestTier1Exact:
    def test_exact_endswith(self):
        path, tier = _match("anime.safetensors", ["styles/anime.safetensors"])
        assert path == "styles/anime.safetensors"
        assert tier == 1

    def test_extension_fallback(self):
        path, tier = _match("anime", ["styles/anime.safetensors"])
        assert path == "styles/anime.safetensors"
        assert tier == 1


# ---------------------------------------------------------------------------
# _find_lora_match — tier 2 (normalized exact)
# ---------------------------------------------------------------------------

class TestTier2Normalized:
    def test_case_insensitive(self):
        path, tier = _match("Anime", ["styles/anime.safetensors"])
        assert path == "styles/anime.safetensors"
        assert tier == 2

    def test_punctuation_swap(self):
        path, tier = _match("anime_v2", ["styles/anime-v2.safetensors"])
        assert path == "styles/anime-v2.safetensors"
        assert tier == 2

    def test_case_and_punctuation(self):
        path, tier = _match("Anime V2", ["styles/anime_v2.safetensors"])
        assert path == "styles/anime_v2.safetensors"
        assert tier == 2


# ---------------------------------------------------------------------------
# _find_lora_match — tier 3 (normalized substring)
# ---------------------------------------------------------------------------

class TestTier3Substring:
    def test_query_subset_of_name(self):
        path, tier = _match("anime", ["styles/anime_v2.safetensors"])
        assert path == "styles/anime_v2.safetensors"
        assert tier == 3

    def test_short_query_in_long_name(self):
        path, tier = _match("realistic", ["models/realistic_vision_v5.safetensors"])
        assert path == "models/realistic_vision_v5.safetensors"
        assert tier == 3


# ---------------------------------------------------------------------------
# No fuzzy tier — a typo must fail, not silently resolve to a neighbour
# ---------------------------------------------------------------------------

class TestNoFuzzyFallback:
    def test_typo_does_not_resolve(self):
        """A near-miss with no substring relation matches nothing."""
        assert _match("anim_styl", ["styles/anime_style_v2.safetensors"]) is None

    def test_checkpoint_family_typo_does_not_swap_siblings(self):
        """
        The regression this guards: a mistyped training-step number must never
        resolve to a different checkpoint. Every sibling scores ~0.95 under any
        similarity metric, so a fuzzy match silently invalidates the sweep.
        """
        available = [
            f"lora_v1/lora_v1_{step:09d}.safetensors"
            for step in range(200, 2801, 200)
        ]
        # 10 digits instead of 9 — the exact shape of a zero-padding bug.
        assert _match("lora_v1_0000001400.safetensors", available) is None

    def test_valid_checkpoint_still_resolves_exactly(self):
        available = [
            f"lora_v1/lora_v1_{step:09d}.safetensors"
            for step in range(200, 2801, 200)
        ]
        path, tier = _match("lora_v1_000001400.safetensors", available)
        assert path == "lora_v1/lora_v1_000001400.safetensors"
        assert tier == 1


# ---------------------------------------------------------------------------
# Ambiguity is an error, not a coin flip
# ---------------------------------------------------------------------------

class TestAmbiguity:
    def test_multi_substring_match_raises(self):
        available = ["styles/anime_v1.safetensors", "styles/anime_v2.safetensors"]
        with pytest.raises(AmbiguousLoraError) as exc:
            _match("anime", available)
        assert set(exc.value.candidates) == set(available)

    def test_identical_names_different_dirs_raises(self):
        """Same basename in two directories is genuinely ambiguous."""
        available = ["a/style.safetensors", "b/style.safetensors"]
        with pytest.raises(AmbiguousLoraError):
            _match("style", available)

    def test_ambiguity_message_lists_candidates(self):
        available = ["a/style.safetensors", "b/style.safetensors"]
        with pytest.raises(AmbiguousLoraError, match="ambiguous"):
            _match("style", available)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_match(self):
        result = _match("nonexistent", ["styles/anime.safetensors"])
        assert result is None

    def test_verbatim_path_passthrough(self):
        """A full path that exists verbatim should match at tier 1."""
        available = ["styles/anime.safetensors", "models/other.safetensors"]
        path, tier = _match("styles/anime.safetensors", available)
        assert path == "styles/anime.safetensors"
        assert tier == 1

    def test_path_with_slash_not_in_available_falls_through(self):
        """A path with '/' that doesn't exist verbatim should still cascade."""
        available = ["loras/anime_v2.safetensors"]
        path, tier = _match("styles/anime_v2", available)
        assert path == "loras/anime_v2.safetensors"
