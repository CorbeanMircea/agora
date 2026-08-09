"""
M4.2 — StoryLLMProvider Interface Tests

Verifies the Story/PanelDescription dataclasses, Story.validate(),
Story serialisation round-trip, and the abstract provider contract.

Run with:
    pytest games/cronica/pipeline/test_story_llm_provider.py -v
"""

from __future__ import annotations

import json
import pytest
from dataclasses import dataclass
from typing import Any

from .providers.story_llm_provider import (
    StoryLLMProvider,
    Story,
    PanelDescription,
    PlayerAnswers,
    PlayerAnswerItem,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel(index: int, suffix: str = "") -> PanelDescription:
    return PanelDescription(
        panel_index=index,
        description_ro=f"Descriere panou {index}{suffix}.",
        dialogue_ro=f"Dialog {index}.",
        image_prompt_en=f"Panel {index} wide shot, cinematic{suffix}",
        narrator_line_ro=f"Naratorul spune ceva la panoul {index}{suffix}.",
        characters_in_panel=["victima", "tradatorul"] if index == 0 else [],
    )


def _story(panel_count: int, suffix: str = "") -> Story:
    panels = [_panel(i, suffix) for i in range(panel_count)]
    return Story(
        title=f"Povestea de test{suffix}",
        panels=panels,
        narrator_script=[p.narrator_line_ro for p in panels],
        image_prompts=[p.image_prompt_en for p in panels],
    )


# ── PanelDescription tests ─────────────────────────────────────────────────────

class TestPanelDescription:
    def test_basic_instantiation(self):
        panel = _panel(0)
        assert panel.panel_index == 0
        assert panel.description_ro
        assert panel.image_prompt_en
        assert panel.narrator_line_ro

    def test_dialogue_ro_defaults_to_empty(self):
        panel = PanelDescription(
            panel_index=0,
            description_ro="Test.",
            dialogue_ro="",
            image_prompt_en="test prompt",
            narrator_line_ro="test narration",
        )
        assert panel.dialogue_ro == ""

    def test_characters_in_panel_defaults_to_empty_list(self):
        panel = PanelDescription(
            panel_index=1,
            description_ro="Test.",
            dialogue_ro="",
            image_prompt_en="test",
            narrator_line_ro="test",
        )
        assert panel.characters_in_panel == []


# ── Story dataclass tests ──────────────────────────────────────────────────────

class TestStory:
    def test_basic_instantiation(self):
        story = _story(5)
        assert story.title == "Povestea de test"
        assert len(story.panels) == 5
        assert len(story.narrator_script) == 5
        assert len(story.image_prompts) == 5

    def test_validate_valid_story(self):
        story = _story(5)
        errors = story.validate(5)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_validate_wrong_panel_count(self):
        story = _story(5)
        errors = story.validate(6)
        assert any("panels length" in e for e in errors)

    def test_validate_empty_title(self):
        story = _story(4)
        story.title = "   "
        errors = story.validate(4)
        assert any("title" in e for e in errors)

    def test_validate_empty_description(self):
        story = _story(4)
        story.panels[2].description_ro = ""
        errors = story.validate(4)
        assert any("description_ro" in e for e in errors)

    def test_validate_empty_image_prompt(self):
        story = _story(4)
        story.panels[0].image_prompt_en = "  "
        story.image_prompts[0] = "  "
        errors = story.validate(4)
        assert any("image_prompt_en" in e for e in errors)

    def test_validate_empty_narrator_line(self):
        story = _story(4)
        story.panels[1].narrator_line_ro = ""
        story.narrator_script[1] = ""
        errors = story.validate(4)
        assert any("narrator_line_ro" in e for e in errors)

    def test_validate_panel_index_mismatch(self):
        story = _story(4)
        story.panels[2].panel_index = 99
        errors = story.validate(4)
        assert any("panel_index" in e for e in errors)

    def test_validate_narrator_script_mismatch(self):
        story = _story(4)
        story.narrator_script[1] = "Un text diferit"
        errors = story.validate(4)
        assert any("narrator_script" in e for e in errors)

    def test_validate_image_prompts_mismatch(self):
        story = _story(4)
        story.image_prompts[0] = "different prompt"
        errors = story.validate(4)
        assert any("image_prompts" in e for e in errors)


# ── Serialisation tests ────────────────────────────────────────────────────────

class TestStorySerialisation:
    def test_to_dict_is_json_serialisable(self):
        story = _story(5)
        data = story.to_dict()
        json_str = json.dumps(data)
        assert json_str

    def test_to_dict_has_expected_keys(self):
        story = _story(4)
        data = story.to_dict()
        assert set(data.keys()) == {"title", "panels", "narrator_script", "image_prompts"}

    def test_panel_dicts_have_expected_keys(self):
        story = _story(4)
        for panel_dict in story.to_dict()["panels"]:
            assert "panel_index" in panel_dict
            assert "description_ro" in panel_dict
            assert "dialogue_ro" in panel_dict
            assert "image_prompt_en" in panel_dict
            assert "narrator_line_ro" in panel_dict
            assert "characters_in_panel" in panel_dict

    def test_from_dict_round_trip(self):
        original = _story(5)
        data = original.to_dict()
        restored = Story.from_dict(data)

        assert restored.title == original.title
        assert len(restored.panels) == len(original.panels)
        assert restored.narrator_script == original.narrator_script
        assert restored.image_prompts == original.image_prompts

        for orig_p, rest_p in zip(original.panels, restored.panels):
            assert orig_p.panel_index == rest_p.panel_index
            assert orig_p.description_ro == rest_p.description_ro
            assert orig_p.image_prompt_en == rest_p.image_prompt_en
            assert orig_p.narrator_line_ro == rest_p.narrator_line_ro

    def test_from_dict_missing_fields_raises(self):
        with pytest.raises(ValueError, match="missing required fields"):
            Story.from_dict({"title": "test"})

    def test_from_dict_optional_dialogue_defaults_empty(self):
        data = _story(2).to_dict()
        for p in data["panels"]:
            p.pop("dialogue_ro", None)
        restored = Story.from_dict(data)
        for panel in restored.panels:
            assert panel.dialogue_ro == ""

    def test_from_dict_optional_characters_defaults_empty(self):
        data = _story(2).to_dict()
        for p in data["panels"]:
            p.pop("characters_in_panel", None)
        restored = Story.from_dict(data)
        for panel in restored.panels:
            assert panel.characters_in_panel == []

    def test_json_round_trip_via_string(self):
        original = _story(4)
        json_str = json.dumps(original.to_dict(), ensure_ascii=False)
        restored = Story.from_dict(json.loads(json_str))
        assert restored.title == original.title
        assert len(restored.panels) == 4


# ── PlayerAnswers / PlayerAnswerItem tests ────────────────────────────────────

class TestPlayerAnswers:
    def test_player_answer_item_fields(self):
        item = PlayerAnswerItem(
            prompt_id="c_001",
            category="CONCRET",
            ingredient_role="OBJECT",
            answer_text="crocodil",
        )
        assert item.prompt_id == "c_001"
        assert item.ingredient_role == "OBJECT"
        assert item.answer_text == "crocodil"

    def test_player_answers_defaults_to_empty_list(self):
        pa = PlayerAnswers(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
        )
        assert pa.answers == []

    def test_player_answers_with_items(self):
        pa = PlayerAnswers(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            answers=[
                PlayerAnswerItem("c_001", "CONCRET", "OBJECT", "crocodil"),
                PlayerAnswerItem("a_001", "ABSTRACT", "ATMOSPHERE", "teamă"),
            ],
        )
        assert len(pa.answers) == 2
        assert pa.answers[0].answer_text == "crocodil"


# ── Abstract provider contract tests ─────────────────────────────────────────

class TestStoryLLMProviderContract:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            StoryLLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_generate_story(self):
        class IncompleteProvider(StoryLLMProvider):
            pass  # Missing generate_story

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_concrete_subclass_is_instantiable(self):
        class MinimalProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                return _story(4)

        provider = MinimalProvider()
        assert isinstance(provider, StoryLLMProvider)

    def test_generate_story_is_callable(self):
        class EchoProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                panel_count = getattr(brief, "panel_count", 4)
                return _story(panel_count)

        provider = EchoProvider()

        @dataclass
        class MiniBrief:
            panel_count: int = 5

        result = provider.generate_story(MiniBrief(), [])
        assert isinstance(result, Story)
        assert len(result.panels) == 5


# ── generate_story_with_retry tests ──────────────────────────────────────────

class TestGenerateStoryWithRetry:
    def test_succeeds_on_first_attempt(self):
        class GoodProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                return _story(4)

        provider = GoodProvider()

        @dataclass
        class Brief:
            panel_count: int = 4

        story = provider.generate_story_with_retry(Brief(), [])
        assert isinstance(story, Story)
        assert len(story.panels) == 4

    def test_retries_on_invalid_story_and_succeeds(self):
        call_count = 0

        class RetryProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call returns wrong panel count
                    bad = _story(3)
                    return bad
                return _story(4)

        provider = RetryProvider()

        @dataclass
        class Brief:
            panel_count: int = 4

        story = provider.generate_story_with_retry(Brief(), [], max_attempts=2)
        assert len(story.panels) == 4
        assert call_count == 2

    def test_raises_after_all_attempts_fail(self):
        class AlwaysFailProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                raise RuntimeError("LLM unavailable")

        provider = AlwaysFailProvider()

        @dataclass
        class Brief:
            panel_count: int = 4

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            provider.generate_story_with_retry(Brief(), [], max_attempts=2)

    def test_exposes_last_validation_errors_on_retry(self):
        received_errors: list[list[str]] = []

        class TrackingProvider(StoryLLMProvider):
            def generate_story(self, brief: Any, player_answers: list) -> Story:
                received_errors.append(list(getattr(self, "_last_validation_errors", [])))
                return _story(4)

        provider = TrackingProvider()

        @dataclass
        class Brief:
            panel_count: int = 4

        provider.generate_story_with_retry(Brief(), [], max_attempts=1)
        # First call: _last_validation_errors is [] (no prior errors)
        assert received_errors[0] == []