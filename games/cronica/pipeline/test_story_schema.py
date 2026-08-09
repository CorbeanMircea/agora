"""
M4.3 — Story Dataclass & Output Schema Tests

Tests the additional validation rules added in M4.3:
  - Player name presence in story text
  - English-only (ASCII) image prompt enforcement
  - story_schema.json structural completeness

Run with:
    pytest games/cronica/pipeline/test_story_schema.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .providers.story_llm_provider import Story, PanelDescription


# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel(index: int, image_prompt: str | None = None) -> PanelDescription:
    return PanelDescription(
        panel_index=index,
        description_ro=f"Descriere detaliată a panoului numărul {index} din poveste.",
        dialogue_ro=f"Dialog {index}.",
        image_prompt_en=image_prompt or f"Wide shot panel {index}, cinematic, dramatic lighting",
        narrator_line_ro=f"Naratorul descrie evenimentele din panoul {index}.",
    )


def _story(panel_count: int = 4, player_names_in_text: list[str] | None = None) -> Story:
    panels = [_panel(i) for i in range(panel_count)]

    # Embed player names into description_ro of the first panel if requested
    if player_names_in_text:
        name_text = " și ".join(player_names_in_text)
        panels[0].description_ro = (
            f"{name_text} se află în centrul acestei povești scandaloase."
        )

    return Story(
        title="Povestea de test pentru validare",
        panels=panels,
        narrator_script=[p.narrator_line_ro for p in panels],
        image_prompts=[p.image_prompt_en for p in panels],
    )


# ── Player name presence tests ────────────────────────────────────────────────

class TestPlayerNamePresence:
    def test_valid_story_with_all_player_names(self):
        story = _story(player_names_in_text=["Ana", "Bogdan"])
        errors = story.validate(4, expected_player_names=["Ana", "Bogdan"])
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_player_name_produces_error(self):
        story = _story(player_names_in_text=["Ana"])
        errors = story.validate(4, expected_player_names=["Ana", "Bogdan"])
        assert any("Bogdan" in e for e in errors), f"Expected missing-name error, got: {errors}"

    def test_all_player_names_missing_produces_multiple_errors(self):
        story = _story(panel_count=4)
        errors = story.validate(4, expected_player_names=["Ana", "Bogdan", "Cristi"])
        name_errors = [e for e in errors if "does not appear" in e]
        assert len(name_errors) == 3

    def test_player_name_in_dialogue_counts(self):
        story = _story(4)
        story.panels[2].dialogue_ro = "Ana: Nu am făcut nimic!"
        story.narrator_script[2] = story.panels[2].narrator_line_ro
        errors = story.validate(4, expected_player_names=["Ana"])
        name_errors = [e for e in errors if "Ana" in e and "does not appear" in e]
        assert name_errors == []

    def test_player_name_in_narrator_line_counts(self):
        story = _story(4)
        story.panels[1].narrator_line_ro = "Bogdan a intrat în cameră cu o privire suspectă."
        story.narrator_script[1] = story.panels[1].narrator_line_ro
        errors = story.validate(4, expected_player_names=["Bogdan"])
        name_errors = [e for e in errors if "Bogdan" in e and "does not appear" in e]
        assert name_errors == []

    def test_player_name_in_title_counts(self):
        story = _story(4)
        story.title = "Cristi și Marea Conspirație"
        errors = story.validate(4, expected_player_names=["Cristi"])
        assert errors == []

    def test_no_player_names_provided_skips_check(self):
        story = _story(4)
        errors = story.validate(4, expected_player_names=None)
        assert errors == []

    def test_empty_player_names_list_skips_check(self):
        story = _story(4)
        errors = story.validate(4, expected_player_names=[])
        assert errors == []

    def test_empty_name_string_in_list_is_skipped(self):
        story = _story(player_names_in_text=["Ana"])
        errors = story.validate(4, expected_player_names=["Ana", ""])
        assert errors == []


# ── English image prompt tests ────────────────────────────────────────────────

class TestEnglishImagePrompts:
    def test_ascii_prompt_passes(self):
        story = _story(4)
        errors = story.validate(4)
        assert errors == []

    def test_romanian_diacritics_in_image_prompt_fails(self):
        story = _story(4)
        # Accidentally write prompt in Romanian
        story.panels[1].image_prompt_en = "Panou larg cu personaje în conflict, lumină dramatică"
        story.image_prompts[1] = story.panels[1].image_prompt_en
        errors = story.validate(4)
        assert any("non-ASCII" in e for e in errors), f"Expected non-ASCII error, got: {errors}"

    def test_multiple_panels_with_romanian_prompts_produce_multiple_errors(self):
        story = _story(4)
        story.panels[0].image_prompt_en = "scenă cu personaje în conflict"
        story.image_prompts[0] = story.panels[0].image_prompt_en
        story.panels[2].image_prompt_en = "zoom pe față surprinsă"
        story.image_prompts[2] = story.panels[2].image_prompt_en
        errors = story.validate(4)
        non_ascii_errors = [e for e in errors if "non-ASCII" in e]
        assert len(non_ascii_errors) == 2

    def test_common_english_punctuation_passes(self):
        story = _story(4)
        story.panels[0].image_prompt_en = (
            "Wide shot, dramatic lighting, two characters facing off, "
            "cinematic framing, high contrast, warm tones"
        )
        story.image_prompts[0] = story.panels[0].image_prompt_en
        errors = story.validate(4)
        ascii_errors = [e for e in errors if "non-ASCII" in e]
        assert ascii_errors == []

    def test_mixed_ascii_and_romanian_fails(self):
        story = _story(4)
        story.panels[0].image_prompt_en = "Wide shot, dramatic, scenă cinematografică"
        story.image_prompts[0] = story.panels[0].image_prompt_en
        errors = story.validate(4)
        assert any("non-ASCII" in e for e in errors)

    def test_empty_prompt_fails_on_empty_check_not_ascii_check(self):
        story = _story(4)
        story.panels[0].image_prompt_en = "   "
        story.image_prompts[0] = story.panels[0].image_prompt_en
        errors = story.validate(4)
        # Should fail on the empty check, not the ASCII check
        empty_errors = [e for e in errors if "must not be empty" in e]
        assert empty_errors


# ── Combined validation tests ─────────────────────────────────────────────────

class TestCombinedValidation:
    def test_fully_valid_story_passes_all_checks(self):
        story = _story(5, player_names_in_text=["Ana", "Bogdan"])
        errors = story.validate(5, expected_player_names=["Ana", "Bogdan"])
        assert errors == []

    def test_multiple_distinct_errors_all_reported(self):
        story = _story(4)
        story.panels[0].image_prompt_en = "scenă românească"
        story.image_prompts[0] = story.panels[0].image_prompt_en
        errors = story.validate(4, expected_player_names=["Cristi"])
        assert any("non-ASCII" in e for e in errors)
        assert any("Cristi" in e for e in errors)


# ── JSON Schema file tests ────────────────────────────────────────────────────

class TestStorySchemaFile:
    @pytest.fixture
    def schema_path(self) -> Path:
        return (
            Path(__file__).parent / "providers" / "story_schema.json"
        )

    def test_schema_file_exists(self, schema_path: Path):
        assert schema_path.exists(), f"story_schema.json not found at {schema_path}"

    def test_schema_is_valid_json(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_schema_has_required_top_level_fields(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert data.get("type") == "object"
        required = data.get("required", [])
        for field in ["title", "panels", "narrator_script", "image_prompts"]:
            assert field in required, f"'{field}' not in schema required list"

    def test_schema_panel_definition_has_required_fields(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        panel_def = data["$defs"]["PanelDescription"]
        required = panel_def.get("required", [])
        for field in [
            "panel_index", "description_ro", "dialogue_ro",
            "image_prompt_en", "narrator_line_ro",
        ]:
            assert field in required, f"'{field}' not in PanelDescription required"

    def test_schema_image_prompt_enforces_ascii(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        # Check image_prompts array items have ASCII pattern
        items = data["properties"]["image_prompts"]["items"]
        assert "pattern" in items, "image_prompts items should have ASCII pattern"

    def test_schema_panel_image_prompt_enforces_ascii(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        panel_def = data["$defs"]["PanelDescription"]
        prompt_def = panel_def["properties"]["image_prompt_en"]
        assert "pattern" in prompt_def, "image_prompt_en should have ASCII pattern"

    def test_schema_panel_count_bounds(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        panels_prop = data["properties"]["panels"]
        assert panels_prop.get("minItems") == 4
        assert panels_prop.get("maxItems") == 8

    def test_schema_description_min_length(self, schema_path: Path):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        desc = data["$defs"]["PanelDescription"]["properties"]["description_ro"]
        assert desc.get("minLength", 0) >= 20, (
            "description_ro should enforce minimum 20 character length per GDD"
        )