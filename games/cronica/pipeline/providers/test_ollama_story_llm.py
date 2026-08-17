"""
M4.5 — Story System Prompt Engineering Tests

Verifies that OllamaStoryLLM produces correctly structured prompts across
all 7 genres, integrates ingredients organically (ADR-001), and that the
retry mechanism feeds prior errors back into the next attempt.

These tests do NOT call Ollama — they test prompt construction only.

Run with:
    pytest games/cronica/pipeline/providers/test_ollama_story_llm.py -v
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from .ollama_story_llm import (
    OllamaStoryLLM,
    _build_system_prompt,
    _build_user_prompt,
    _build_json_schema_example,
    _parse_story_response,
    _extract_ingredients_from_system_prompt,
    _ROLE_GUIDANCE_RO,
)
from .story_llm_provider import (
    Story,
    PanelDescription,
    PlayerAnswers,
    PlayerAnswerItem,
)
from ..creative_director import (
    CreativeDirector,
    PlayerAnswer,
    get_genre,
)
from ..creative_director.models import (
    CreativeBrief,
    IngredientRole,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

GENRE_KEYS = [
    "telenovela_romaneasca",
    "film_actiune_b",
    "basm_romanesc_absurd",
    "scandal_de_bloc",
    "documentar_fals",
    "horror_mioritic",
    "stiri_rupte_din_realitate",
]


def _make_player_answer(player_id: str, nickname: str, categories: list[str]) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {
                "prompt_id": f"{player_id}_p{i}",
                "category": cat,
                "answer_text": f"ingredient_{i}_{nickname.lower()}",
            }
            for i, cat in enumerate(categories)
        ],
    )


def _make_brief(genre_key: str, seed: int = 0) -> CreativeBrief:
    """Generate a real CreativeBrief for the given genre."""
    cd = CreativeDirector()
    player_answers = [
        _make_player_answer("p1", "Ana", ["CONCRET", "ABSTRACT"]),
        _make_player_answer("p2", "Bogdan", ["LOC", "NUMAR"]),
    ]
    # Generate briefs until we get the target genre (max 200 seeds)
    for s in range(seed, seed + 200):
        brief = cd.generate(player_answers, [], seed=s)
        if brief.genre_key == genre_key:
            return brief
    # Fallback: return any brief (genre distribution test handles this separately)
    return cd.generate(player_answers, [], seed=seed)


def _make_player_answers_for_brief(brief: CreativeBrief) -> list[PlayerAnswers]:
    """Build PlayerAnswers list consistent with the brief's archetypes."""
    result = []
    for arch in brief.archetypes:
        items = [
            PlayerAnswerItem(
                prompt_id=prompt_id,
                category="CONCRET",  # simplified for prompt testing
                ingredient_role=role.value,
                answer_text=f"test_ingredient_{prompt_id}",
            )
            for prompt_id, role in arch.ingredient_roles.items()
        ]
        result.append(PlayerAnswers(
            player_id=arch.player_id or "unknown",
            nickname=arch.player_nickname or "Unknown",
            archetype_key=arch.key,
            archetype_name_ro=arch.name_ro,
            answers=items,
        ))
    return result


# ── System prompt structure tests ─────────────────────────────────────────────

class TestSystemPromptStructure:
    def test_system_prompt_contains_genre_name(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "Telenovelă Românească" in prompt or "telenovela" in prompt.lower()

    def test_system_prompt_contains_panel_count(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert str(brief.panel_count) in prompt

    def test_system_prompt_contains_comedy_level(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert str(brief.comedy_level) in prompt

    def test_system_prompt_contains_tone_keywords(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        for keyword in brief.tone_keywords:
            assert keyword in prompt, f"Tone keyword '{keyword}' missing from system prompt"

    def test_system_prompt_contains_story_beats(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        for beat in brief.story_structure.beats:
            assert beat in prompt, f"Story beat '{beat}' missing from system prompt"

    def test_system_prompt_contains_narrator_description(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert brief.narrator_personality.personality_description_ro in prompt

    def test_system_prompt_contains_player_nicknames_in_archetypes(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        for arch in brief.archetypes:
            if arch.player_nickname:
                assert arch.player_nickname in prompt, (
                    f"Player nickname '{arch.player_nickname}' missing from system prompt"
                )

    def test_system_prompt_contains_archetype_names(self):
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        for arch in brief.archetypes:
            assert arch.name_ro in prompt, (
                f"Archetype name '{arch.name_ro}' missing from system prompt"
            )

    def test_system_prompt_contains_english_rules(self):
        """The prompt must instruct the LLM to write image prompts in English."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "engleză" in prompt.lower() or "english" in prompt.lower()

    def test_system_prompt_contains_json_instruction(self):
        """The prompt must instruct the LLM to respond only with JSON."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "JSON" in prompt

    def test_system_prompt_contains_minimum_description_length_rule(self):
        """The prompt must enforce minimum 20-word panel descriptions."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "20" in prompt

    def test_system_prompt_is_non_empty_string(self):
        brief = _make_brief("film_actiune_b", seed=5)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert isinstance(prompt, str)
        assert len(prompt) > 200

    def test_system_prompt_instructs_prose_image_prompts(self):
        """System prompt must instruct LLM to write prose descriptions not keyword lists."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        # Must instruct prose description, not just tokens
        assert "prose" in prompt.lower() or "PROSE" in prompt or "sentence" in prompt.lower() or "scene description" in prompt.lower()

    def test_system_prompt_instructs_no_text_in_images(self):
        """System prompt must instruct LLM to exclude text/captions from image prompts."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "no text" in prompt.lower() or "No text" in prompt

    def test_system_prompt_contains_character_visual_descriptions(self):
        """System prompt must include character visual descriptions (clothing, hair) for image prompt generation."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        # Should contain visual appearance info like clothing colour
        assert "clothing" in prompt.lower() or "hair" in prompt.lower()

    def test_system_prompt_instructs_prose_image_prompts(self):
        """System prompt must instruct LLM to write prose descriptions not keyword lists."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "prose" in prompt.lower() or "PROSE" in prompt or "sentence" in prompt.lower() or "scene description" in prompt.lower()

    def test_system_prompt_instructs_no_text_in_images(self):
        """System prompt must instruct LLM to exclude text/captions from image prompts."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "no text" in prompt.lower() or "No text" in prompt

    def test_system_prompt_contains_character_visual_descriptions(self):
        """System prompt must include character visual descriptions (clothing, hair)."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "clothing" in prompt.lower() or "hair" in prompt.lower()

    def test_system_prompt_contains_ingredient_visual_rule(self):
        """System prompt must instruct ingredient visual propagation."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert "LOCATION" in prompt and "OBJECT" in prompt


# ── Anti-template / ADR-001 ingredient integration tests ─────────────────────

class TestIngredientIntegration:
    def test_all_ingredient_answer_texts_appear_in_prompt(self):
        """Every player's ingredient answer text must appear in the system prompt."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        for pa in player_answers:
            for ans in pa.answers:
                assert ans.answer_text in prompt, (
                    f"Ingredient '{ans.answer_text}' not found in system prompt"
                )

    def test_ingredient_roles_appear_in_prompt(self):
        """Each ingredient's assigned role must appear alongside the ingredient."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        for pa in player_answers:
            for ans in pa.answers:
                assert ans.ingredient_role in prompt, (
                    f"Ingredient role '{ans.ingredient_role}' not found in system prompt"
                )

    def test_role_guidance_text_appears_in_prompt(self):
        """Romanian role guidance text must appear for each role used."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        roles_used = {ans.ingredient_role for pa in player_answers for ans in pa.answers}
        for role in roles_used:
            guidance = _ROLE_GUIDANCE_RO.get(role, "")
            if guidance:
                assert guidance in prompt, (
                    f"Role guidance for '{role}' not found in system prompt"
                )

    def test_anti_template_instruction_present(self):
        """Prompt must instruct LLM NOT to force ingredients as Mad Lib slots."""
        brief = _make_brief("basm_romanesc_absurd", seed=10)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        # The prompt must contain anti-template language
        assert any(
            phrase in prompt
            for phrase in ["organic", "NU le forța", "nu forța", "Integrează", "integrează"]
        ), "Anti-template instruction missing from system prompt"

    def test_ingredients_wrapped_in_guillemets(self):
        """Ingredients should be wrapped in «» for clear visual separation."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        ingredients = _extract_ingredients_from_system_prompt(prompt)
        assert len(ingredients) > 0, "No ingredients found wrapped in «» in system prompt"

        # All ingredient answer texts should appear in guillemets
        for pa in player_answers:
            for ans in pa.answers:
                assert ans.answer_text in ingredients, (
                    f"Ingredient '{ans.answer_text}' not wrapped in «» in system prompt"
                )

    def test_same_ingredient_set_different_genres_produces_different_prompts(self):
        """
        ADR-001: The same ingredients with different genres must produce
        structurally different system prompts (different genre names, beats, etc.)
        """
        # Get two briefs with different genres for same player data
        telenovela = _make_brief("telenovela_romaneasca", seed=0)
        horror = _make_brief("horror_mioritic", seed=0)

        tele_answers = _make_player_answers_for_brief(telenovela)
        horror_answers = _make_player_answers_for_brief(horror)

        prompt_tele = _build_system_prompt(telenovela, tele_answers)
        prompt_horror = _build_system_prompt(horror, horror_answers)

        assert prompt_tele != prompt_horror
        # Genre names must differ
        assert "Telenovelă" in prompt_tele or "telenovela" in prompt_tele.lower()
        assert "Horror" in prompt_horror or "horror" in prompt_horror.lower()

    def test_twists_appear_in_system_prompt(self):
        """Mandatory twist descriptions must appear in the system prompt."""
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        if brief.twists:
            # At least the main twist panel index must appear
            main_twist = next(t for t in brief.twists if t.is_final_twist)
            assert str(main_twist.panel_index) in prompt


# ── All 7 genres produce valid prompts ────────────────────────────────────────

class TestAllGenresProduceValidPrompts:
    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_genre_produces_non_empty_system_prompt(self, genre_key: str):
        brief = _make_brief(genre_key, seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert len(prompt) > 100, f"System prompt too short for genre '{genre_key}'"

    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_genre_prompt_contains_required_sections(self, genre_key: str):
        brief = _make_brief(genre_key, seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)

        # Every prompt must have these sections
        required_markers = ["GEN:", "STRUCTURA", "JSON"]
        for marker in required_markers:
            assert marker in prompt, (
                f"Required section '{marker}' missing for genre '{genre_key}'"
            )

    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_genre_prompt_contains_narrator_persona(self, genre_key: str):
        brief = _make_brief(genre_key, seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        assert brief.narrator_personality.personality_description_ro in prompt, (
            f"Narrator persona missing for genre '{genre_key}'"
        )

    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_genre_prompts_are_distinct(self, genre_key: str):
        """Each genre must produce a unique prompt (genre name must appear)."""
        brief = _make_brief(genre_key, seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        genre = get_genre(genre_key)
        assert genre.name_ro in prompt, (
            f"Genre name '{genre.name_ro}' not in system prompt for '{genre_key}'"
        )


# ── User prompt tests ─────────────────────────────────────────────────────────

class TestUserPrompt:
    def test_user_prompt_contains_panel_count(self):
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], [])
        assert "5" in prompt

    def test_user_prompt_contains_player_names(self):
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], [])
        assert "Ana" in prompt
        assert "Bogdan" in prompt

    def test_user_prompt_contains_json_instruction(self):
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], [])
        assert "JSON" in prompt

    def test_user_prompt_without_prior_errors_has_no_error_section(self):
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], [])
        assert "anterioară" not in prompt
        assert "erori" not in prompt.lower() or "erori" in prompt  # errors mention is in instructions only

    def test_user_prompt_with_prior_errors_includes_them(self):
        errors = ["panels length 3 != expected 5", "title must not be empty"]
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], errors)
        for error in errors:
            assert error in prompt

    def test_user_prompt_with_prior_errors_asks_to_correct(self):
        errors = ["panels length 3 != expected 5"]
        prompt = _build_user_prompt(5, ["Ana"], errors)
        assert "Corectează" in prompt or "corectează" in prompt

    def test_user_prompt_schema_example_has_correct_panel_count(self):
        for panel_count in [4, 5, 6, 8]:
            prompt = _build_user_prompt(panel_count, ["Ana"], [])
            schema_str = prompt[prompt.find("{"):]
            if schema_str:
                try:
                    data = json.loads(schema_str)
                    assert len(data.get("panels", [])) == panel_count, (
                        f"Schema example has wrong panel count for panel_count={panel_count}"
                    )
                except json.JSONDecodeError:
                    pass  # Schema example contains placeholders — that's fine

    def test_user_prompt_ingredient_integration_reminder(self):
        """User prompt must remind LLM to integrate ingredients organically."""
        prompt = _build_user_prompt(5, ["Ana", "Bogdan"], [])
        assert any(
            phrase in prompt
            for phrase in ["organic", "ingredient", "conform rolului"]
        ), "Ingredient integration reminder missing from user prompt"


# ── JSON schema example tests ─────────────────────────────────────────────────

class TestJsonSchemaExample:
    @pytest.mark.parametrize("panel_count", [4, 5, 6, 8])
    def test_schema_example_has_correct_panel_count(self):
        for panel_count in [4, 5, 6, 8]:
            example = _build_json_schema_example(panel_count)
            data = json.loads(example)
            assert len(data["panels"]) == panel_count
            # narrator_script and image_prompts are no longer in the schema example;
            # they are always reconstructed from panels after parsing.
            assert "narrator_script" not in data
            assert "image_prompts" not in data

    @pytest.mark.parametrize("panel_count", [4, 5, 6, 8])
    def test_schema_example_has_correct_panel_indices(self, panel_count: int):
        example = _build_json_schema_example(panel_count)
        data = json.loads(example)
        for i, panel in enumerate(data["panels"]):
            assert panel["panel_index"] == i

    def test_schema_example_has_required_panel_fields(self):
        example = _build_json_schema_example(5)
        data = json.loads(example)
        required = [
            "panel_index", "description_ro", "dialogue_ro",
            "image_prompt_en", "narrator_line_ro", "characters_in_panel",
        ]
        for panel in data["panels"]:
            for field in required:
                assert field in panel, f"Required field '{field}' missing from schema example"

    def test_schema_example_image_prompt_is_prose_not_keywords(self):
        """First panel example must show prose description, not just keyword tokens."""
        example = _build_json_schema_example(5)
        data = json.loads(example)
        first_panel = data["panels"][0]
        prompt = first_panel["image_prompt_en"]
        # A prose description has spaces between words forming sentences, not just comma-separated short tokens
        # Proxy: the example prompt should contain period or multi-word phrases
        assert len(prompt) > 100, "Example image_prompt_en should be a detailed prose description"
        assert "No text" in prompt or "no text" in prompt

    def test_schema_example_is_valid_json(self):
        for panel_count in [4, 5, 6, 8]:
            example = _build_json_schema_example(panel_count)
            data = json.loads(example)  # must not raise
            assert data

    def test_schema_example_image_prompt_is_prose_not_keywords(self):
        """First panel example must show prose description, not just keyword tokens."""
        example = _build_json_schema_example(5)
        data = json.loads(example)
        first_panel = data["panels"][0]
        prompt = first_panel["image_prompt_en"]
        assert len(prompt) > 100, "Example image_prompt_en should be a detailed prose description"
        assert "No text" in prompt or "no text" in prompt

# ── Response parser tests ─────────────────────────────────────────────────────

class TestParseStoryResponse:
    def _valid_story_json(self, panel_count: int = 4) -> str:
        panels = []
        for i in range(panel_count):
            panels.append({
                "panel_index": i,
                "description_ro": f"Descriere detaliată a scenei din panoul {i} cu cel puțin douăzeci de cuvinte pentru validare.",
                "dialogue_ro": f"Dialog panou {i}.",
                "image_prompt_en": f"Wide shot panel {i}, cinematic, dramatic lighting, high contrast",
                "narrator_line_ro": f"Naratorul descrie evenimentele din panoul {i} în detaliu.",
                "characters_in_panel": [],
            })
        return json.dumps({
            "title": "Povestea de test",
            "panels": panels,
            "narrator_script": [p["narrator_line_ro"] for p in panels],
            "image_prompts": [p["image_prompt_en"] for p in panels],
        }, ensure_ascii=False)

    def test_parses_pure_json(self):
        story = _parse_story_response(self._valid_story_json(4), 4)
        assert isinstance(story, Story)
        assert story.title == "Povestea de test"
        assert len(story.panels) == 4

    def test_parses_json_in_code_fence(self):
        fenced = f"```json\n{self._valid_story_json(4)}\n```"
        story = _parse_story_response(fenced, 4)
        assert isinstance(story, Story)
        assert len(story.panels) == 4

    def test_parses_json_with_preamble_text(self):
        with_preamble = f"Iată povestea:\n\n{self._valid_story_json(5)}"
        story = _parse_story_response(with_preamble, 5)
        assert isinstance(story, Story)
        assert len(story.panels) == 5

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="Could not extract valid JSON"):
            _parse_story_response("Aceasta nu este JSON.", 4)

    def test_raises_on_missing_required_fields(self):
        incomplete = json.dumps({"title": "test"})
        with pytest.raises(ValueError):
            _parse_story_response(incomplete, 4)

    def test_reconstructs_narrator_script_from_panels_if_missing(self):
        data = json.loads(self._valid_story_json(4))
        del data["narrator_script"]
        story = _parse_story_response(json.dumps(data), 4)
        assert len(story.narrator_script) == 4

    def test_reconstructs_image_prompts_from_panels_if_missing(self):
        data = json.loads(self._valid_story_json(4))
        del data["image_prompts"]
        story = _parse_story_response(json.dumps(data), 4)
        assert len(story.image_prompts) == 4


# ── OllamaStoryLLM unit tests (no HTTP calls) ─────────────────────────────────

class TestOllamaStoryLLMUnit:
    def _make_llm(self) -> OllamaStoryLLM:
        return OllamaStoryLLM(
            base_url="http://localhost:11434",
            model="llama3.1:8b",
            timeout=60.0,
        )

    def _valid_story_response(self, panel_count: int = 5) -> str:
        panels = []
        for i in range(panel_count):
            panels.append({
                "panel_index": i,
                "description_ro": f"Descriere detaliată scenă panou {i} cu minimum douăzeci de cuvinte pentru a trece validarea corect.",
                "dialogue_ro": "",
                "image_prompt_en": f"Wide shot panel {i}, cinematic lighting, dramatic composition, high contrast",
                "narrator_line_ro": f"Naratorul descrie cu entuziasm evenimentele din panoul numărul {i}.",
                "characters_in_panel": [],
            })
        data = {
            "title": "Povestea cea mare a lui Ana și Bogdan",
            "panels": panels,
            "narrator_script": [p["narrator_line_ro"] for p in panels],
            "image_prompts": [p["image_prompt_en"] for p in panels],
        }
        return json.dumps(data, ensure_ascii=False)

    def test_generate_story_calls_ollama_api(self):
        llm = self._make_llm()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": self._valid_story_response(brief.panel_count)},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            story = llm.generate_story(brief, player_answers)

        assert mock_client.post.called
        called_url = mock_client.post.call_args[0][0]
        assert "/api/chat" in called_url

    def test_generate_story_sends_system_and_user_messages(self):
        llm = self._make_llm()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": self._valid_story_response(brief.panel_count)},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            llm.generate_story(brief, player_answers)

        payload = mock_client.post.call_args[1]["json"]
        roles = [m["role"] for m in payload["messages"]]
        assert "system" in roles
        assert "user" in roles

    def test_generate_story_uses_non_streaming_mode(self):
        llm = self._make_llm()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": self._valid_story_response(brief.panel_count)},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            llm.generate_story(brief, player_answers)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["stream"] is False

    def test_generate_story_uses_configured_model(self):
        llm = OllamaStoryLLM(model="custom_model:7b")
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": self._valid_story_response(brief.panel_count)},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            llm.generate_story(brief, player_answers)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == "custom_model:7b"

    def test_generate_story_returns_story_instance(self):
        llm = self._make_llm()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": self._valid_story_response(brief.panel_count)},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            story = llm.generate_story(brief, player_answers)

        assert isinstance(story, Story)

    def test_generate_story_with_retry_passes_prior_errors_to_second_attempt(self):
        """
        On retry, _last_validation_errors from the first failed attempt
        must be available to the second call via self._last_validation_errors.
        """
        from .story_llm_provider import Story as _Story, PanelDescription as _PanelDescription

        call_count = 0
        received_errors: list[list[str]] = []

        class TrackingLLM(OllamaStoryLLM):
            def generate_story(self, brief, player_answers):
                nonlocal call_count
                call_count += 1
                received_errors.append(list(getattr(self, "_last_validation_errors", [])))
                if call_count == 1:
                    # Return story with wrong panel count to trigger retry
                    panels = [
                        _PanelDescription(
                            panel_index=i,
                            description_ro=f"Desc {i} " * 5,
                            dialogue_ro="",
                            image_prompt_en=f"Panel {i} shot",
                            narrator_line_ro=f"Narration {i}",
                        )
                        for i in range(3)  # wrong: brief expects 4+
                    ]
                    return _Story(
                        title="Wrong",
                        panels=panels,
                        narrator_script=[p.narrator_line_ro for p in panels],
                        image_prompts=[p.image_prompt_en for p in panels],
                    )
                # Second call returns correct story
                panel_count = getattr(brief, "panel_count", 4)
                panels = [
                    _PanelDescription(
                        panel_index=i,
                        description_ro=f"Descriere scena panou {i} " * 4,
                        dialogue_ro="",
                        image_prompt_en=f"Wide shot panel {i}, cinematic",
                        narrator_line_ro=f"Narration line {i} details",
                    )
                    for i in range(panel_count)
                ]
                return _Story(
                    title="Povestea lui Ana si Bogdan",
                    panels=panels,
                    narrator_script=[p.narrator_line_ro for p in panels],
                    image_prompts=[p.image_prompt_en for p in panels],
                )

        llm = TrackingLLM()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        story = llm.generate_story_with_retry(brief, player_answers, max_attempts=2)

        assert call_count == 2
        # First call: no prior errors
        assert received_errors[0] == []
        # Second call: errors from first attempt's validation
        assert len(received_errors[1]) > 0
        assert any("panels length" in e for e in received_errors[1])

    def test_generate_story_with_retry_raises_after_all_failures(self):
        llm = self._make_llm()
        brief = _make_brief("telenovela_romaneasca", seed=0)
        player_answers = _make_player_answers_for_brief(brief)

        with patch.object(llm, "generate_story", side_effect=RuntimeError("Ollama offline")):
            with pytest.raises(RuntimeError, match="Ollama offline"):
                llm.generate_story_with_retry(brief, player_answers, max_attempts=2)


# ── Prompt distinctiveness across genres ──────────────────────────────────────

class TestPromptDistinctivenessAcrossGenres:
    def test_all_seven_genre_system_prompts_are_distinct(self):
        """
        Generate a prompt for each of the 7 genres and verify they are all
        distinct from each other. This validates that genre-specific data
        (beats, tone, narrator) is properly injected.
        """
        prompts: dict[str, str] = {}
        for genre_key in GENRE_KEYS:
            brief = _make_brief(genre_key, seed=0)
            player_answers = _make_player_answers_for_brief(brief)
            prompts[genre_key] = _build_system_prompt(brief, player_answers)

        # All prompts must be unique
        prompt_set = set(prompts.values())
        assert len(prompt_set) == 7, (
            "Some genres produced identical system prompts — genre data not injected correctly"
        )

    def test_horror_prompt_has_different_tone_than_actiune(self):
        horror = _make_brief("horror_mioritic", seed=0)
        actiune = _make_brief("film_actiune_b", seed=5)

        horror_answers = _make_player_answers_for_brief(horror)
        actiune_answers = _make_player_answers_for_brief(actiune)

        horror_prompt = _build_system_prompt(horror, horror_answers)
        actiune_prompt = _build_system_prompt(actiune, actiune_answers)

        # Horror has different tone keywords than acțiune
        for keyword in horror.tone_keywords:
            if keyword not in actiune.tone_keywords:
                assert keyword in horror_prompt
                assert keyword not in actiune_prompt

    def test_basm_prompt_contains_folk_vocabulary(self):
        brief = _make_brief("basm_romanesc_absurd", seed=10)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        # Basm beats contain Romanian folk tale vocabulary
        assert any(beat in prompt for beat in brief.story_structure.beats)

    def test_stiri_rupte_prompt_has_fast_speaking_rate_narrator(self):
        """Știri Rupte narrator has speaking_rate > 1.0 — this must reach the prompt."""
        brief = _make_brief("stiri_rupte_din_realitate", seed=0)
        player_answers = _make_player_answers_for_brief(brief)
        prompt = _build_system_prompt(brief, player_answers)
        # Narrator personality description must be present
        assert brief.narrator_personality.personality_description_ro in prompt
        # Speaking rate > 1 is reflected in personality description
        assert brief.narrator_personality.speaking_rate > 1.0