"""
M5.4 — Style Token Injector Tests

Run with:
    pytest games/cronica/pipeline/providers/test_style_token_injector.py -v
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from .style_token_injector import StyleTokenInjector, _merge_tokens
from .image_generator_provider import ImagePrompt, VisualStyle
from .character_description import CharacterDescriptionGenerator
from ..creative_director import CreativeDirector, PlayerAnswer
from ..creative_director.models import PresentationFormat
from ..creative_director.genre_registry import GENRE_KEYS, get_genre, list_genres
from ..creative_director.format_registry import list_formats


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_player(player_id: str, nickname: str) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {"prompt_id": f"{player_id}_p0", "category": "CONCRET", "answer_text": "obiect"},
            {"prompt_id": f"{player_id}_p1", "category": "LOC",     "answer_text": "loc"},
        ],
    )


def _make_brief(seed: int = 0):
    cd = CreativeDirector()
    players = [
        _make_player("p1", "Ana"),
        _make_player("p2", "Bogdan"),
    ]
    return cd.generate(players, [], seed=seed)


@dataclass
class _FakePanel:
    panel_index: int
    image_prompt_en: str = "Wide shot, dramatic lighting"
    characters_in_panel: list[str] = field(default_factory=list)


@dataclass
class _FakeStory:
    panels: list[_FakePanel] = field(default_factory=list)


# ── _merge_tokens tests ───────────────────────────────────────────────────────

class TestMergeTokens:
    def test_merges_two_lists(self):
        result = _merge_tokens(["a", "b"], ["c", "d"])
        assert result == ["a", "b", "c", "d"]

    def test_removes_duplicates_case_insensitive(self):
        result = _merge_tokens(["Drama", "dark"], ["drama", "horror"])
        assert result.count("Drama") == 1 or result.count("drama") == 1
        assert "horror" in result

    def test_primary_comes_first(self):
        result = _merge_tokens(["first"], ["second"])
        assert result.index("first") < result.index("second")

    def test_empty_primary(self):
        result = _merge_tokens([], ["a", "b"])
        assert result == ["a", "b"]

    def test_empty_secondary(self):
        result = _merge_tokens(["a", "b"], [])
        assert result == ["a", "b"]

    def test_both_empty(self):
        assert _merge_tokens([], []) == []

    def test_strips_whitespace(self):
        result = _merge_tokens(["  token  "], [" other "])
        assert "token" in result
        assert "other" in result


# ── build_visual_style tests ──────────────────────────────────────────────────

class TestBuildVisualStyle:
    def test_returns_visual_style_instance(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert isinstance(style, VisualStyle)

    def test_genre_key_is_set(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert style.genre_key == brief.genre_key

    def test_visual_style_prose_is_set(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert style.visual_style == brief.visual_style

    def test_lighting_mood_is_set(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert style.lighting_mood == brief.lighting_mood

    def test_colour_palette_is_set(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert len(style.colour_palette) > 0

    def test_positive_tokens_non_empty(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert len(style.style_tokens_positive) >= 2

    def test_negative_tokens_non_empty(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        assert len(style.style_tokens_negative) >= 2

    def test_positive_tokens_include_genre_tokens(self):
        brief = _make_brief(seed=0)
        genre = get_genre(brief.genre_key)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        for token in genre.style_tokens_positive:
            assert token in style.style_tokens_positive

    def test_no_duplicate_tokens(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style = injector.build_visual_style(brief)
        lower_tokens = [t.lower() for t in style.style_tokens_positive]
        assert len(lower_tokens) == len(set(lower_tokens)), (
            f"Duplicate positive tokens: {style.style_tokens_positive}"
        )

    def test_output_is_deterministic(self):
        brief = _make_brief(seed=0)
        injector = StyleTokenInjector()
        style_a = injector.build_visual_style(brief)
        style_b = injector.build_visual_style(brief)
        assert style_a.style_tokens_positive == style_b.style_tokens_positive
        assert style_a.style_tokens_negative == style_b.style_tokens_negative

    def test_invalid_genre_key_returns_empty_tokens(self):
        @dataclass
        class BadBrief:
            genre_key: str = "nonexistent_genre"
            format: str = ""
            visual_style: str = ""
            lighting_mood: str = ""
            colour_palette: list = field(default_factory=list)

        injector = StyleTokenInjector()
        style = injector.build_visual_style(BadBrief())
        assert style.style_tokens_positive == []

    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_all_genres_produce_non_empty_tokens(self, genre_key: str):
        cd = CreativeDirector()
        players = [_make_player("p1", "Ana"), _make_player("p2", "Bogdan")]
        for seed in range(100):
            brief = cd.generate(players, [], seed=seed)
            if brief.genre_key == genre_key:
                injector = StyleTokenInjector()
                style = injector.build_visual_style(brief)
                assert len(style.style_tokens_positive) >= 2, (
                    f"Genre '{genre_key}' produced no positive tokens"
                )
                break


# ── build_image_prompts tests ─────────────────────────────────────────────────

class TestBuildImagePrompts:
    def test_returns_correct_panel_count(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(
            panels=[_FakePanel(i) for i in range(brief.panel_count)]
        )
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        assert len(prompts) == brief.panel_count

    def test_panel_indices_are_sequential(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(
            panels=[_FakePanel(i) for i in range(brief.panel_count)]
        )
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        for i, p in enumerate(prompts):
            assert p.panel_index == i

    def test_base_prompt_from_story_panel(self):
        brief = _make_brief(seed=0)
        panels = [_FakePanel(i, image_prompt_en=f"Custom prompt {i}") for i in range(brief.panel_count)]
        story = _FakeStory(panels=panels)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        for i, p in enumerate(prompts):
            assert p.base_prompt == f"Custom prompt {i}"

    def test_style_tokens_match_visual_style(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        visual_style = injector.build_visual_style(brief)
        prompts = injector.build_image_prompts(brief, story)
        for p in prompts:
            assert p.style_tokens_positive == visual_style.style_tokens_positive
            assert p.style_tokens_negative == visual_style.style_tokens_negative

    def test_camera_tokens_from_brief(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        # Each panel should have camera tokens from brief.camera_language
        for rule in brief.camera_language:
            idx = rule.panel_index
            if idx < len(prompts):
                assert prompts[idx].camera_tokens == rule.prompt_tokens

    def test_camera_tokens_non_empty_for_all_panels(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        for p in prompts:
            assert p.camera_tokens.strip() != "", (
                f"Panel {p.panel_index} has empty camera_tokens"
            )

    def test_character_descriptions_injected_when_roster_provided(self):
        brief = _make_brief(seed=0)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)

        # Build a story where panel 0 has characters
        archetype_key = brief.archetypes[0].key if brief.archetypes else "arch_0"
        panels = [
            _FakePanel(0, characters_in_panel=[archetype_key]),
            *[_FakePanel(i) for i in range(1, brief.panel_count)],
        ]
        story = _FakeStory(panels=panels)

        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story, character_roster=roster)

        # Panel 0 should have character descriptions
        assert len(prompts[0].character_descriptions) >= 1

    def test_no_character_descriptions_without_roster(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story, character_roster=None)
        for p in prompts:
            assert p.character_descriptions == []

    def test_build_positive_prompt_includes_base_and_camera(self):
        brief = _make_brief(seed=0)
        panels = [_FakePanel(i, image_prompt_en=f"Base prompt {i}") for i in range(brief.panel_count)]
        story = _FakeStory(panels=panels)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        for i, p in enumerate(prompts):
            assembled = p.build_positive_prompt()
            assert f"Base prompt {i}" in assembled
            if p.camera_tokens:
                assert p.camera_tokens in assembled

    def test_deterministic_output(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        prompts_a = injector.build_image_prompts(brief, story)
        prompts_b = injector.build_image_prompts(brief, story)
        for a, b in zip(prompts_a, prompts_b):
            assert a.camera_tokens == b.camera_tokens
            assert a.style_tokens_positive == b.style_tokens_positive
            assert a.base_prompt == b.base_prompt

    def test_returns_image_prompt_instances(self):
        brief = _make_brief(seed=0)
        story = _FakeStory(panels=[_FakePanel(i) for i in range(brief.panel_count)])
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        for p in prompts:
            assert isinstance(p, ImagePrompt)


# ── All 7 genres produce valid token sets ─────────────────────────────────────

class TestAllGenresTokenCoverage:
    def test_each_genre_has_positive_and_negative_tokens_in_registry(self):
        for genre in list_genres():
            assert len(genre.style_tokens_positive) >= 2, (
                f"Genre '{genre.key}' has fewer than 2 positive tokens"
            )
            assert len(genre.style_tokens_negative) >= 2, (
                f"Genre '{genre.key}' has fewer than 2 negative tokens"
            )

    def test_each_format_has_positive_and_negative_tokens_in_registry(self):
        for fmt in list_formats():
            assert len(fmt.style_tokens_positive) >= 2, (
                f"Format '{fmt.format.value}' has fewer than 2 positive tokens"
            )
            assert len(fmt.style_tokens_negative) >= 2, (
                f"Format '{fmt.format.value}' has fewer than 2 negative tokens"
            )

    def test_all_genres_produce_distinct_positive_token_sets(self):
        cd = CreativeDirector()
        players = [_make_player("p1", "Ana"), _make_player("p2", "Bogdan")]
        injector = StyleTokenInjector()
        token_sets: dict[str, frozenset[str]] = {}
        for genre_key in GENRE_KEYS:
            for seed in range(200):
                brief = cd.generate(players, [], seed=seed)
                if brief.genre_key == genre_key:
                    style = injector.build_visual_style(brief)
                    token_sets[genre_key] = frozenset(
                        t.lower() for t in style.style_tokens_positive
                    )
                    break
        # All 7 genres must produce different token sets
        unique_sets = set(frozenset(s) for s in token_sets.values())
        assert len(unique_sets) == 7, (
            "Some genres produced identical positive token sets"
        )