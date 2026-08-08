"""
M3.7 — Creative Director Unit Tests

Tests for the CreativeDirector.generate() method covering:
  - Genre distribution over many calls
  - Archetype assignment correctness
  - Brief structural completeness
  - Genre avoidance across simulated round history
  - Serialisation round-trip (to_json / from_dict)

Run with:
  pytest games/cronica/pipeline/creative_director/test_creative_director.py -v
"""

from __future__ import annotations

import json
import pytest
from collections import Counter
from pathlib import Path

from .creative_director import CreativeDirector, PlayerAnswer, CreativeBriefValidationError
from .models import CreativeBrief, PresentationFormat
from .genre_registry import GENRE_KEYS


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_player(player_id: str, nickname: str, categories: list[str]) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {
                "prompt_id": f"{player_id}_p{i}",
                "category": cat,
                "answer_text": f"răspuns {i} de la {nickname}",
            }
            for i, cat in enumerate(categories)
        ],
    )


def _two_players() -> list[PlayerAnswer]:
    return [
        _make_player("player_1", "Ana",    ["CONCRET", "ABSTRACT"]),
        _make_player("player_2", "Bogdan", ["LOC",     "NUMAR"]),
    ]


def _four_players() -> list[PlayerAnswer]:
    return [
        _make_player("player_1", "Ana",    ["CONCRET", "ABSTRACT"]),
        _make_player("player_2", "Bogdan", ["LOC",     "NUMAR"]),
        _make_player("player_3", "Cristi", ["PROPRIU", "ATRIBUT"]),
        _make_player("player_4", "Diana",  ["ACTIUNE", "CONCRET"]),
    ]


# ── Basic generation tests ─────────────────────────────────────────────────────

class TestCreativeDirectorBasic:
    def test_returns_creative_brief(self):
        cd = CreativeDirector()
        brief = cd.generate(_two_players(), [], seed=0)
        assert isinstance(brief, CreativeBrief)

    def test_seeded_call_is_reproducible(self):
        cd = CreativeDirector()
        b1 = cd.generate(_two_players(), [], seed=42)
        b2 = cd.generate(_two_players(), [], seed=42)
        assert b1.genre_key == b2.genre_key
        assert b1.panel_count == b2.panel_count
        assert b1.comedy_level == b2.comedy_level

    def test_different_seeds_may_differ(self):
        cd = CreativeDirector()
        genres = {cd.generate(_two_players(), [], seed=s).genre_key for s in range(30)}
        assert len(genres) > 1

    def test_raises_with_fewer_than_two_players(self):
        cd = CreativeDirector()
        single = [_make_player("p1", "Ana", ["CONCRET", "LOC"])]
        with pytest.raises(ValueError, match="at least 2"):
            cd.generate(single, [], seed=0)

    def test_four_players_generates_successfully(self):
        cd = CreativeDirector()
        brief = cd.generate(_four_players(), [], seed=1)
        assert isinstance(brief, CreativeBrief)
        assert len(brief.archetypes) == 4


# ── Structural completeness tests ─────────────────────────────────────────────

class TestBriefCompleteness:
    @pytest.fixture
    def brief(self) -> CreativeBrief:
        return CreativeDirector().generate(_four_players(), [], seed=7)

    def test_genre_fields_non_empty(self, brief: CreativeBrief):
        assert brief.genre
        assert brief.genre_key in GENRE_KEYS
        assert brief.subgenre

    def test_panel_count_is_valid(self, brief: CreativeBrief):
        assert brief.panel_count in (4, 5, 6, 8)

    def test_story_structure_beats_match_panel_count(self, brief: CreativeBrief):
        assert len(brief.story_structure.beats) == brief.panel_count

    def test_camera_language_matches_panel_count(self, brief: CreativeBrief):
        assert len(brief.camera_language) == brief.panel_count
        for i, cam in enumerate(brief.camera_language):
            assert cam.panel_index == i

    def test_archetypes_count_matches_players(self, brief: CreativeBrief):
        assert len(brief.archetypes) == 4

    def test_no_duplicate_archetype_keys(self, brief: CreativeBrief):
        keys = [a.key for a in brief.archetypes]
        assert len(keys) == len(set(keys))

    def test_all_archetypes_have_player_assigned(self, brief: CreativeBrief):
        for archetype in brief.archetypes:
            assert archetype.player_id is not None
            assert archetype.player_nickname is not None

    def test_all_archetypes_have_ingredient_roles(self, brief: CreativeBrief):
        for archetype in brief.archetypes:
            assert len(archetype.ingredient_roles) >= 1

    def test_twists_have_valid_panel_indices(self, brief: CreativeBrief):
        for twist in brief.twists:
            assert 0 <= twist.panel_index < brief.panel_count

    def test_punchline_panel_is_valid(self, brief: CreativeBrief):
        assert 0 <= brief.punchline_panel < brief.panel_count

    def test_comedy_level_in_range(self, brief: CreativeBrief):
        assert 1 <= brief.comedy_level <= 10

    def test_colour_palette_has_hex_colours(self, brief: CreativeBrief):
        import re
        pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        assert len(brief.colour_palette) >= 3
        for colour in brief.colour_palette:
            assert pattern.match(colour), f"Invalid hex colour: {colour}"

    def test_narrator_voice_key_non_empty(self, brief: CreativeBrief):
        assert brief.narrator_voice_key
        assert brief.narrator_personality.voice_key == brief.narrator_voice_key

    def test_tone_keywords_non_empty(self, brief: CreativeBrief):
        assert len(brief.tone_keywords) >= 1

    def test_generated_at_is_set(self, brief: CreativeBrief):
        assert brief.generated_at is not None

    def test_visual_style_non_empty(self, brief: CreativeBrief):
        assert brief.visual_style

    def test_lighting_mood_non_empty(self, brief: CreativeBrief):
        assert brief.lighting_mood

    def test_music_direction_non_empty(self, brief: CreativeBrief):
        assert brief.music_direction

    def test_sound_effects_panel_indices_valid(self, brief: CreativeBrief):
        for sfx in brief.sound_effects:
            assert 0 <= sfx.panel_index < brief.panel_count

    def test_format_is_valid_presentation_format(self, brief: CreativeBrief):
        assert brief.format in PresentationFormat.__members__.values() or brief.format in [f.value for f in PresentationFormat]


# ── Genre distribution tests ──────────────────────────────────────────────────

class TestGenreDistribution:
    def test_all_seven_genres_appear_over_100_calls(self):
        """All 7 genres must appear across 100 seeded calls."""
        cd = CreativeDirector()
        seen = {
            cd.generate(_two_players(), [], seed=s).genre_key
            for s in range(100)
        }
        assert seen == set(GENRE_KEYS), (
            f"Missing genres after 100 calls: {set(GENRE_KEYS) - seen}"
        )

    def test_no_genre_dominates_more_than_30_percent(self):
        """No single genre should appear in more than 30% of 100 calls."""
        cd = CreativeDirector()
        counts = Counter(
            cd.generate(_two_players(), [], seed=s).genre_key
            for s in range(100)
        )
        for key, count in counts.items():
            assert count / 100 <= 0.30, (
                f"Genre '{key}' dominates at {count/100:.0%} (max 30%)"
            )

    def test_recent_genre_avoided(self):
        """A genre in history should appear less often than unpenalised genres."""
        cd = CreativeDirector()
        penalised = GENRE_KEYS[0]
        history = [penalised]

        counts = Counter(
            cd.generate(_two_players(), history, seed=s).genre_key
            for s in range(200)
        )
        # The penalised genre's share should be well below 1/7 ≈ 14.3%
        share = counts[penalised] / 200
        assert share < 0.10, (
            f"Penalised genre '{penalised}' appeared {share:.1%} (expected < 10%)"
        )

    def test_genre_avoidance_with_two_recent_genres(self):
        cd = CreativeDirector()
        penalised = GENRE_KEYS[:2]

        counts = Counter(
            cd.generate(_two_players(), penalised, seed=s).genre_key
            for s in range(200)
        )
        for key in penalised:
            share = counts[key] / 200
            assert share < 0.10, (
                f"Penalised genre '{key}' appeared {share:.1%} (expected < 10%)"
            )

    def test_all_genres_appear_in_simulated_session(self):
        """Simulate 7-round sessions; all 7 genres must appear within 50 sessions."""
        cd = CreativeDirector()
        seen: set[str] = set()
        for session_seed in range(50):
            history: list[str] = []
            for round_offset in range(7):
                brief = cd.generate(
                    _two_players(),
                    history,
                    seed=session_seed * 100 + round_offset,
                )
                seen.add(brief.genre_key)
                history.insert(0, brief.genre_key)
        assert seen == set(GENRE_KEYS), (
            f"Not all genres appeared across 50 sessions. Missing: {set(GENRE_KEYS) - seen}"
        )


# ── Archetype assignment tests ────────────────────────────────────────────────

class TestArchetypeAssignment:
    def test_no_duplicate_player_ids_in_archetypes(self):
        cd = CreativeDirector()
        brief = cd.generate(_four_players(), [], seed=3)
        player_ids = [a.player_id for a in brief.archetypes]
        assert len(player_ids) == len(set(player_ids))

    def test_correct_player_nicknames_in_archetypes(self):
        players = _four_players()
        cd = CreativeDirector()
        brief = cd.generate(players, [], seed=3)
        expected_nicknames = {p.nickname for p in players}
        assigned_nicknames = {a.player_nickname for a in brief.archetypes}
        assert assigned_nicknames == expected_nicknames

    def test_ingredient_roles_match_submitted_prompts(self):
        players = _two_players()
        cd = CreativeDirector()
        brief = cd.generate(players, [], seed=5)
        for player_answer in players:
            archetype = next(
                a for a in brief.archetypes if a.player_id == player_answer.player_id
            )
            expected_ids = {a["prompt_id"] for a in player_answer.answers}
            assigned_ids = set(archetype.ingredient_roles.keys())
            assert assigned_ids == expected_ids

    def test_player_with_no_answers_gets_empty_roles(self):
        """A player who didn't submit still gets an archetype with empty roles."""
        players = [
            PlayerAnswer("p1", "Ana", []),  # no answers submitted
            _make_player("p2", "Bogdan", ["CONCRET", "LOC"]),
        ]
        cd = CreativeDirector()
        brief = cd.generate(players, [], seed=0)
        p1_archetype = next(a for a in brief.archetypes if a.player_id == "p1")
        assert p1_archetype.ingredient_roles == {}


# ── Serialisation tests ───────────────────────────────────────────────────────

class TestSerialisation:
    def test_to_dict_is_json_serialisable(self):
        cd = CreativeDirector()
        brief = cd.generate(_two_players(), [], seed=0)
        data = brief.to_dict()
        json_str = json.dumps(data)  # must not raise
        assert json_str

    def test_to_json_then_from_dict_round_trip(self):
        cd = CreativeDirector()
        original = cd.generate(_two_players(), [], seed=0)
        json_str = original.to_json()
        restored = CreativeBrief.from_json(json_str)

        assert restored.genre == original.genre
        assert restored.genre_key == original.genre_key
        assert restored.panel_count == original.panel_count
        assert restored.comedy_level == original.comedy_level
        assert restored.narrator_voice_key == original.narrator_voice_key
        assert len(restored.archetypes) == len(original.archetypes)
        assert len(restored.camera_language) == len(original.camera_language)
        assert len(restored.twists) == len(original.twists)

    def test_serialised_enum_values_are_strings(self):
        cd = CreativeDirector()
        brief = cd.generate(_two_players(), [], seed=0)
        data = brief.to_dict()
        assert isinstance(data["format"], str)
        assert isinstance(data["reveal_pacing"], str)

    def test_write_brief_json_to_disk(self, tmp_path: Path):
        cd = CreativeDirector()
        brief = cd.generate(_two_players(), [], seed=0)
        cd._write_brief_json(brief, str(tmp_path))
        brief_file = tmp_path / "brief.json"
        assert brief_file.exists()
        data = json.loads(brief_file.read_text(encoding="utf-8"))
        assert data["genre_key"] in GENRE_KEYS

    def test_generate_with_output_dir_writes_file(self, tmp_path: Path):
        cd = CreativeDirector()
        brief = cd.generate(
            _two_players(),
            [],
            seed=0,
            round_id=42,
            output_dir=str(tmp_path),
        )
        brief_file = tmp_path / "brief.json"
        assert brief_file.exists()
        data = json.loads(brief_file.read_text(encoding="utf-8"))
        assert data["round_id"] == 42

    def test_round_id_is_preserved(self):
        cd = CreativeDirector()
        brief = cd.generate(_two_players(), [], seed=0, round_id=7)
        assert brief.round_id == 7


# ── All genres test ───────────────────────────────────────────────────────────

class TestAllGenres:
    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_each_genre_generates_valid_brief_with_two_players(self, genre_key: str):
        """
        Force-select each genre by using a seed that produces it,
        or directly test by mocking. Since we can't force the genre directly
        without mocking, we generate many briefs until each genre is covered.
        """
        # Generate briefs until we find the target genre or exhaust attempts
        cd = CreativeDirector()
        found = False
        for s in range(200):
            brief = cd.generate(_two_players(), [], seed=s)
            if brief.genre_key == genre_key:
                found = True
                # Validate structural completeness for this genre
                assert brief.panel_count in (4, 5, 6, 8)
                assert len(brief.story_structure.beats) == brief.panel_count
                assert len(brief.camera_language) == brief.panel_count
                assert len(brief.archetypes) == 2
                assert brief.narrator_voice_key
                break
        assert found, (
            f"Genre '{genre_key}' was not selected in 200 seeded calls. "
            "This suggests a bug in the selection algorithm."
        )