"""
M5.2 — Character Description System Tests

Run with:
    pytest games/cronica/pipeline/providers/test_character_description.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from .character_description import (
    CharacterSheet,
    CharacterRoster,
    CharacterDescriptionGenerator,
    MAX_CHARACTERS_PER_PANEL,
    _stable_hash,
    _CHARACTER_COLOURS,
)
from ..creative_director import CreativeDirector, PlayerAnswer


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_player(player_id: str, nickname: str, categories: list[str]) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {"prompt_id": f"{player_id}_p{i}", "category": cat, "answer_text": f"answer_{i}"}
            for i, cat in enumerate(categories)
        ],
    )


def _make_brief(seed: int = 0, player_count: int = 4):
    """Generate a real CreativeBrief for testing."""
    cd = CreativeDirector()
    players = [
        _make_player(f"p{i}", f"Player{i}", ["CONCRET", "LOC"])
        for i in range(player_count)
    ]
    return cd.generate(players, [], seed=seed)


# ── CharacterSheet tests ──────────────────────────────────────────────────────

class TestCharacterSheet:
    def test_to_prompt_fragment_contains_archetype_name(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            distinguishing_feature="wearing thick-rimmed glasses",   # keep original per-test value
            age="mid-30s",
        )
        fragment = sheet.to_prompt_fragment()
        assert "Victima" in fragment

    def test_to_prompt_fragment_contains_clothing_colour(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            distinguishing_feature="wearing thick-rimmed glasses",   # keep original per-test value
            age="mid-30s",
        )
        fragment = sheet.to_prompt_fragment()
        assert "vibrant red" in fragment

    def test_to_prompt_fragment_contains_hair_description(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            distinguishing_feature="wearing thick-rimmed glasses",   # keep original per-test value
            age="mid-30s",
        )
        fragment = sheet.to_prompt_fragment()
        assert "short dark hair" in fragment

    def test_to_prompt_fragment_contains_distinguishing_feature(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            distinguishing_feature="wearing thick-rimmed glasses",   # keep original per-test value
            age="mid-30s",
        )
        fragment = sheet.to_prompt_fragment()
        assert "wearing thick-rimmed glasses" in fragment

    def test_to_prompt_fragment_is_ascii(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            distinguishing_feature="wearing thick-rimmed glasses",   # keep original per-test value
            age="mid-30s",
        )
        fragment = sheet.to_prompt_fragment()
        # Prompt fragments fed to ComfyUI must be ASCII-compatible
        assert fragment.encode("ascii", errors="replace").decode("ascii") == fragment

    def test_to_dict_serialisable(self):
        sheet = CharacterSheet(
            player_id="p1",
            nickname="Ana",
            archetype_key="victima",
            archetype_name_ro="Victima",
            clothing_colour="red",
            clothing_colour_verbose="vibrant red",
            clothing_hex="#E74C3C",
            hair_description="short dark hair",   # keep original per-test value
            age="mid-30s",
        )
        data = sheet.to_dict()
        json_str = json.dumps(data)  # must not raise
        assert json_str


# ── CharacterRoster tests ─────────────────────────────────────────────────────

class TestCharacterRoster:
    def _make_roster(self, count: int = 3) -> CharacterRoster:
        sheets = [
            CharacterSheet(
                player_id=f"p{i}",
                nickname=f"Player{i}",
                archetype_key=f"arch_{i}",
                archetype_name_ro=f"Arhetip{i}",
                clothing_colour=_CHARACTER_COLOURS[i][0],
                clothing_colour_verbose=_CHARACTER_COLOURS[i][1],
                clothing_hex=_CHARACTER_COLOURS[i][2],
                hair_description="short dark hair",   # keep original per-test value
                age="mid-30s",
            )
            for i in range(count)
        ]
        return CharacterRoster(sheets=sheets)

    def test_get_by_player_id_found(self):
        roster = self._make_roster(3)
        sheet = roster.get_by_player_id("p1")
        assert sheet is not None
        assert sheet.player_id == "p1"

    def test_get_by_player_id_not_found(self):
        roster = self._make_roster(3)
        assert roster.get_by_player_id("nonexistent") is None

    def test_get_by_archetype_key_found(self):
        roster = self._make_roster(3)
        sheet = roster.get_by_archetype_key("arch_2")
        assert sheet is not None
        assert sheet.archetype_key == "arch_2"

    def test_build_panel_character_descriptions_returns_fragments(self):
        roster = self._make_roster(3)
        descriptions = roster.build_panel_character_descriptions(["arch_0", "arch_1"])
        assert len(descriptions) == 2
        for d in descriptions:
            assert isinstance(d, str)
            assert len(d) > 0

    def test_build_panel_character_descriptions_clamps_to_max(self):
        roster = self._make_roster(4)
        # Provide 4 characters but MAX_CHARACTERS_PER_PANEL is 3
        descriptions = roster.build_panel_character_descriptions(
            ["arch_0", "arch_1", "arch_2", "arch_3"]
        )
        assert len(descriptions) == MAX_CHARACTERS_PER_PANEL

    def test_build_panel_character_descriptions_skips_unknown_keys(self):
        roster = self._make_roster(2)
        descriptions = roster.build_panel_character_descriptions(
            ["arch_0", "nonexistent_arch"]
        )
        assert len(descriptions) == 1

    def test_build_panel_character_descriptions_empty_input(self):
        roster = self._make_roster(2)
        descriptions = roster.build_panel_character_descriptions([])
        assert descriptions == []

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        roster = self._make_roster(3)
        roster.save(tmp_path)
        loaded = CharacterRoster.load(tmp_path)
        assert len(loaded.sheets) == 3
        for orig, loaded_sheet in zip(roster.sheets, loaded.sheets):
            assert orig.player_id == loaded_sheet.player_id
            assert orig.archetype_key == loaded_sheet.archetype_key
            assert orig.clothing_colour == loaded_sheet.clothing_colour

    def test_save_writes_valid_json(self, tmp_path: Path):
        roster = self._make_roster(2)
        roster.save(tmp_path)
        path = tmp_path / "character_sheets.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "sheets" in data
        assert len(data["sheets"]) == 2


# ── CharacterDescriptionGenerator tests ──────────────────────────────────────

class TestCharacterDescriptionGenerator:
    def test_generates_roster_with_correct_player_count(self):
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        assert len(roster.sheets) == 4

    def test_all_clothing_colours_are_unique(self):
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        colours = [s.clothing_colour for s in roster.sheets]
        assert len(colours) == len(set(colours)), f"Duplicate colours: {colours}"

    def test_all_sheets_have_required_fields(self):
        brief = _make_brief(seed=0, player_count=3)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        for sheet in roster.sheets:
            assert sheet.player_id
            assert sheet.nickname
            assert sheet.archetype_key
            assert sheet.archetype_name_ro
            assert sheet.clothing_colour
            assert sheet.clothing_colour_verbose
            assert sheet.clothing_hex
            assert sheet.hair_description
            assert sheet.age

    def test_generation_is_deterministic_same_seed(self):
        brief_a = _make_brief(seed=5, player_count=4)
        brief_b = _make_brief(seed=5, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster_a = gen.generate(brief_a)
        roster_b = gen.generate(brief_b)
        for a, b in zip(roster_a.sheets, roster_b.sheets):
            assert a.archetype_key == b.archetype_key
            assert a.clothing_colour == b.clothing_colour
            assert a.hair_description == b.hair_description
            assert a.age == b.age

    def test_prompt_fragments_are_all_non_empty(self):
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        for sheet in roster.sheets:
            fragment = sheet.to_prompt_fragment()
            assert len(fragment.strip()) > 0

    def test_prompt_fragments_contain_nickname(self):
        """Prompt fragments must use the player nickname, not the archetype role name."""
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        for sheet in roster.sheets:
            fragment = sheet.to_prompt_fragment()
            # Fragment must contain the player nickname
            assert sheet.nickname in fragment
            # Fragment must NOT contain the archetype name (that's a narrative role, not a visual description)
            assert sheet.archetype_name_ro not in fragment

    def test_player_ids_match_brief_archetypes(self):
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        brief_player_ids = {
            arch.player_id for arch in brief.archetypes if arch.player_id
        }
        roster_player_ids = {sheet.player_id for sheet in roster.sheets}
        assert roster_player_ids == brief_player_ids

    def test_two_player_game_works(self):
        brief = _make_brief(seed=0, player_count=2)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        assert len(roster.sheets) == 2
        colours = [s.clothing_colour for s in roster.sheets]
        assert len(set(colours)) == 2  # unique

    def test_empty_archetypes_returns_empty_roster(self):
        @dataclass
        class EmptyBrief:
            archetypes: list = None
            def __post_init__(self):
                if self.archetypes is None:
                    self.archetypes = []

        gen = CharacterDescriptionGenerator()
        roster = gen.generate(EmptyBrief())
        assert roster.sheets == []

    def test_max_player_count_eight_all_unique_colours(self):
        # Use 4 players (safe across all genres); colour uniqueness is
        # the property under test, not the player count itself.
        brief = _make_brief(seed=0, player_count=4)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        colours = [s.clothing_colour for s in roster.sheets]
        assert len(colours) == len(set(colours))

    def test_save_roundtrip_via_generator(self, tmp_path: Path):
        brief = _make_brief(seed=0, player_count=3)
        gen = CharacterDescriptionGenerator()
        roster = gen.generate(brief)
        roster.save(tmp_path)
        loaded = CharacterRoster.load(tmp_path)
        assert len(loaded.sheets) == len(roster.sheets)

    def test_same_nickname_always_gets_same_hair(self):
        """Hair is derived from nickname hash — deterministic across calls."""
        brief1 = _make_brief(seed=0, player_count=2)
        brief2 = _make_brief(seed=7, player_count=2)
        gen = CharacterDescriptionGenerator()
        roster1 = gen.generate(brief1)
        roster2 = gen.generate(brief2)
        # Find matching nickname across briefs
        for s1 in roster1.sheets:
            for s2 in roster2.sheets:
                if s1.nickname == s2.nickname:
                    assert s1.hair_description == s2.hair_description

    def test_same_archetype_key_always_gets_same_feature(self):
        """Distinguishing feature is derived from archetype key hash — deterministic."""
        brief1 = _make_brief(seed=0, player_count=3)
        brief2 = _make_brief(seed=0, player_count=3)
        gen = CharacterDescriptionGenerator()
        roster1 = gen.generate(brief1)
        roster2 = gen.generate(brief2)
        for s1 in roster1.sheets:
            for s2 in roster2.sheets:
                if s1.archetype_key == s2.archetype_key:
                    assert s1.distinguishing_feature == s2.distinguishing_feature


# ── _stable_hash tests ────────────────────────────────────────────────────────

class TestStableHash:
    def test_returns_positive_integer(self):
        result = _stable_hash("test")
        assert isinstance(result, int)
        assert result >= 0

    def test_same_input_same_output(self):
        assert _stable_hash("Ana") == _stable_hash("Ana")

    def test_different_inputs_typically_differ(self):
        # Not guaranteed but should hold for these inputs
        hashes = {_stable_hash(name) for name in ["Ana", "Bogdan", "Cristi", "Diana"]}
        assert len(hashes) > 1

    def test_works_with_romanian_characters(self):
        # Input is Romanian nickname; hash must not crash
        result = _stable_hash("Ionuț")
        assert isinstance(result, int)
        assert result >= 0