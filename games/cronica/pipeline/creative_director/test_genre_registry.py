"""
M3.2 — Genre Registry Tests

Verifies structural completeness of all 7 genre definitions.
Run with: pytest games/cronica/pipeline/creative_director/test_genre_registry.py -v
"""

import pytest
from .genre_registry import (
    GENRE_REGISTRY,
    GENRE_KEYS,
    GenreDefinition,
    get_genre,
    list_genres,
    TELENOVELA,
    ACTIUNE_B,
    BASM_ABSURD,
    SCANDAL_BLOC,
    DOCUMENTAR_FALS,
    HORROR_MIORITIC,
    STIRI_RUPTE,
)
from .models import PresentationFormat, RevealPacing


EXPECTED_KEYS = [
    "telenovela_romaneasca",
    "film_actiune_b",
    "basm_romanesc_absurd",
    "scandal_de_bloc",
    "documentar_fals",
    "horror_mioritic",
    "stiri_rupte_din_realitate",
]


class TestRegistryCompleteness:
    def test_all_seven_genres_present(self):
        assert len(GENRE_REGISTRY) == 7

    def test_all_expected_keys_present(self):
        for key in EXPECTED_KEYS:
            assert key in GENRE_REGISTRY, f"Missing genre: {key}"

    def test_get_genre_returns_correct_type(self):
        for key in EXPECTED_KEYS:
            genre = get_genre(key)
            assert isinstance(genre, GenreDefinition)

    def test_get_genre_raises_for_unknown_key(self):
        with pytest.raises(KeyError, match="not found"):
            get_genre("nonexistent_genre")

    def test_list_genres_returns_all_seven(self):
        genres = list_genres()
        assert len(genres) == 7
        assert all(isinstance(g, GenreDefinition) for g in genres)


class TestGenreStructure:
    @pytest.mark.parametrize("genre", list_genres())
    def test_identity_fields_non_empty(self, genre: GenreDefinition):
        assert genre.key, f"{genre.key}: key must be non-empty"
        assert genre.name_ro, f"{genre.key}: name_ro must be non-empty"
        assert genre.tagline_ro, f"{genre.key}: tagline_ro must be non-empty"

    @pytest.mark.parametrize("genre", list_genres())
    def test_story_structure_valid(self, genre: GenreDefinition):
        ss = genre.story_structure
        assert len(ss.beats) >= 4, f"{genre.key}: need at least 4 beats"
        assert len(ss.act_descriptions) >= 2, f"{genre.key}: need at least 2 act descriptions"
        assert 0 <= ss.climax_beat_index < len(ss.beats), (
            f"{genre.key}: climax_beat_index {ss.climax_beat_index} out of range"
        )

    @pytest.mark.parametrize("genre", list_genres())
    def test_archetypes_minimum_count(self, genre: GenreDefinition):
        assert len(genre.archetype_templates) >= 2, (
            f"{genre.key}: needs at least 2 archetypes"
        )

    @pytest.mark.parametrize("genre", list_genres())
    def test_archetype_keys_unique(self, genre: GenreDefinition):
        keys = [a.key for a in genre.archetype_templates]
        assert len(keys) == len(set(keys)), f"{genre.key}: duplicate archetype keys: {keys}"

    @pytest.mark.parametrize("genre", list_genres())
    def test_archetype_templates_have_no_player_id(self, genre: GenreDefinition):
        """Templates must not have player assignments — that's M3.5's job."""
        for archetype in genre.archetype_templates:
            assert archetype.player_id is None, (
                f"{genre.key} / {archetype.key}: player_id must be None in template"
            )
            assert archetype.player_nickname is None

    @pytest.mark.parametrize("genre", list_genres())
    def test_comedy_level_range_valid(self, genre: GenreDefinition):
        lo, hi = genre.comedy_level_range
        assert 1 <= lo <= 10, f"{genre.key}: comedy_level_range min out of [1,10]"
        assert 1 <= hi <= 10, f"{genre.key}: comedy_level_range max out of [1,10]"
        assert lo <= hi, f"{genre.key}: comedy_level_range min > max"

    @pytest.mark.parametrize("genre", list_genres())
    def test_tone_keywords_non_empty(self, genre: GenreDefinition):
        assert len(genre.tone_keywords) >= 2, f"{genre.key}: need at least 2 tone_keywords"

    @pytest.mark.parametrize("genre", list_genres())
    def test_panel_counts_valid(self, genre: GenreDefinition):
        for count in genre.panel_counts:
            assert count in (4, 5, 6, 8), (
                f"{genre.key}: invalid panel count {count} (must be 4, 5, 6, or 8)"
            )

    @pytest.mark.parametrize("genre", list_genres())
    def test_preferred_formats_non_empty(self, genre: GenreDefinition):
        assert len(genre.preferred_formats) >= 1, (
            f"{genre.key}: must have at least one preferred format"
        )
        for fmt in genre.preferred_formats:
            assert isinstance(fmt, PresentationFormat), (
                f"{genre.key}: invalid format {fmt}"
            )

    @pytest.mark.parametrize("genre", list_genres())
    def test_colour_palette_has_hex_colours(self, genre: GenreDefinition):
        import re
        pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        assert len(genre.colour_palette) >= 3, f"{genre.key}: need at least 3 colours"
        for colour in genre.colour_palette:
            assert pattern.match(colour), (
                f"{genre.key}: invalid hex colour '{colour}'"
            )

    @pytest.mark.parametrize("genre", list_genres())
    def test_style_tokens_non_empty(self, genre: GenreDefinition):
        assert len(genre.style_tokens_positive) >= 2, (
            f"{genre.key}: need at least 2 positive style tokens"
        )
        assert len(genre.style_tokens_negative) >= 2, (
            f"{genre.key}: need at least 2 negative style tokens"
        )

    @pytest.mark.parametrize("genre", list_genres())
    def test_narrator_personality_valid(self, genre: GenreDefinition):
        n = genre.narrator_personality
        assert n.voice_key, f"{genre.key}: narrator voice_key must be non-empty"
        assert n.personality_description_ro, f"{genre.key}: narrator personality description required"
        assert 0.0 <= n.stability <= 1.0
        assert 0.0 <= n.similarity_boost <= 1.0
        assert 0.0 <= n.style_exaggeration <= 1.0
        assert n.speaking_rate > 0

    @pytest.mark.parametrize("genre", list_genres())
    def test_reveal_pacing_valid(self, genre: GenreDefinition):
        assert isinstance(genre.reveal_pacing, RevealPacing), (
            f"{genre.key}: invalid reveal_pacing"
        )

    @pytest.mark.parametrize("genre", list_genres())
    def test_player_count_bounds(self, genre: GenreDefinition):
        assert 2 <= genre.min_players <= genre.max_players <= 8, (
            f"{genre.key}: invalid player count bounds [{genre.min_players}, {genre.max_players}]"
        )


class TestGenreDistinctiveness:
    def test_all_genre_keys_unique(self):
        keys = [g.key for g in list_genres()]
        assert len(keys) == len(set(keys)), "Genre keys must be unique"

    def test_all_genre_names_unique(self):
        names = [g.name_ro for g in list_genres()]
        assert len(names) == len(set(names)), "Genre names must be unique"

    def test_narrator_voice_keys_unique(self):
        voices = [g.narrator_personality.voice_key for g in list_genres()]
        assert len(voices) == len(set(voices)), "Each genre must have a distinct narrator voice"

    def test_comedy_ranges_cover_spectrum(self):
        """Genres collectively cover comedy levels 3–10 (low to high)."""
        all_minimums = [g.comedy_level_range[0] for g in list_genres()]
        all_maximums = [g.comedy_level_range[1] for g in list_genres()]
        assert min(all_minimums) <= 4, "At least one genre should cover low comedy (≤4)"
        assert max(all_maximums) >= 9, "At least one genre should cover high comedy (≥9)"

    def test_reveal_pacing_variety(self):
        """Not all genres should have the same pacing."""
        pacings = {g.reveal_pacing for g in list_genres()}
        assert len(pacings) >= 2, "Genres should have varied reveal pacing"


class TestSpecificGenres:
    def test_telenovela_is_melodramatic(self):
        g = get_genre("telenovela_romaneasca")
        assert g.comedy_level_range[0] >= 5
        assert g.reveal_pacing == RevealPacing.DELIBERATE
        assert "melodramatic" in g.tone_keywords

    def test_actiune_is_rapid_fire(self):
        g = get_genre("film_actiune_b")
        assert g.reveal_pacing == RevealPacing.RAPID_FIRE
        assert g.comedy_level_range[1] == 10

    def test_basm_uses_folk_format(self):
        g = get_genre("basm_romanesc_absurd")
        assert PresentationFormat.FOLK_TALE_ILLUSTRATION in g.preferred_formats

    def test_horror_has_lowest_comedy(self):
        g = get_genre("horror_mioritic")
        all_minimums = [genre.comedy_level_range[0] for genre in list_genres()]
        assert g.comedy_level_range[0] == min(all_minimums)

    def test_stiri_rupte_is_fast(self):
        g = get_genre("stiri_rupte_din_realitate")
        assert g.reveal_pacing == RevealPacing.RAPID_FIRE
        assert g.narrator_personality.speaking_rate > 1.0