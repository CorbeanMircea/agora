"""
M3.3 — Presentation Format Registry Tests

Verifies structural completeness of all 7 format definitions and the
compatibility matrix.

Run with:
  pytest games/cronica/pipeline/creative_director/test_format_registry.py -v
"""

import pytest
from .format_registry import (
    FORMAT_REGISTRY,
    FormatDefinition,
    get_format,
    list_formats,
    get_compatible_formats,
    get_layout_for_panel_count,
    WESTERN_COMIC,
    FAKE_NEWS_BROADCAST,
    POLICE_REPORT,
    DOCUMENTARY_FILM,
    FOLK_TALE_ILLUSTRATION,
    INSTAGRAM_STORY_SEQUENCE,
    INTERPOL_DOSSIER,
)
from .genre_registry import GENRE_KEYS, list_genres
from .models import PresentationFormat, LayoutStrategy

ALL_FORMAT_ENUMS = list(PresentationFormat)


class TestRegistryCompleteness:
    def test_all_seven_formats_present(self):
        assert len(FORMAT_REGISTRY) == 7

    def test_all_presentation_format_enum_values_covered(self):
        for fmt in PresentationFormat:
            assert fmt in FORMAT_REGISTRY, f"Missing format: {fmt.value}"

    def test_get_format_returns_correct_type(self):
        for fmt in PresentationFormat:
            result = get_format(fmt)
            assert isinstance(result, FormatDefinition)

    def test_get_format_raises_for_invalid(self):
        with pytest.raises((KeyError, ValueError)):
            get_format("nonexistent_format")  # type: ignore[arg-type]

    def test_list_formats_returns_all_seven(self):
        formats = list_formats()
        assert len(formats) == 7
        assert all(isinstance(f, FormatDefinition) for f in formats)


class TestFormatStructure:
    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_identity_fields_non_empty(self, fmt_def: FormatDefinition):
        assert fmt_def.name_ro, f"{fmt_def.format.value}: name_ro must be non-empty"
        assert fmt_def.description_ro, f"{fmt_def.format.value}: description_ro must be non-empty"
        assert fmt_def.css_theme_key, f"{fmt_def.format.value}: css_theme_key must be non-empty"

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_supported_panel_counts_non_empty(self, fmt_def: FormatDefinition):
        assert len(fmt_def.supported_panel_counts) >= 1, (
            f"{fmt_def.format.value}: must support at least 1 panel count"
        )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_panel_counts_are_valid(self, fmt_def: FormatDefinition):
        for count in fmt_def.supported_panel_counts:
            assert count in (4, 5, 6, 8), (
                f"{fmt_def.format.value}: invalid panel count {count}"
            )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_layout_strategies_match_supported_counts(self, fmt_def: FormatDefinition):
        for count in fmt_def.supported_panel_counts:
            assert count in fmt_def.layout_strategies, (
                f"{fmt_def.format.value}: missing layout strategy for panel count {count}"
            )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_layout_strategies_are_valid(self, fmt_def: FormatDefinition):
        for count, layout in fmt_def.layout_strategies.items():
            assert isinstance(layout, LayoutStrategy), (
                f"{fmt_def.format.value}: layout for {count} panels must be a LayoutStrategy"
            )
            assert layout.panel_count == count, (
                f"{fmt_def.format.value}: layout.panel_count {layout.panel_count} "
                f"!= key {count}"
            )
            assert layout.grid_template, (
                f"{fmt_def.format.value}: grid_template must be non-empty for {count} panels"
            )
            assert layout.orientation in ("horizontal", "vertical"), (
                f"{fmt_def.format.value}: invalid orientation '{layout.orientation}'"
            )
            if layout.featured_panel_index is not None:
                assert 0 <= layout.featured_panel_index < count, (
                    f"{fmt_def.format.value}: featured_panel_index out of range for {count} panels"
                )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_style_tokens_non_empty(self, fmt_def: FormatDefinition):
        assert len(fmt_def.style_tokens_positive) >= 2, (
            f"{fmt_def.format.value}: need at least 2 positive style tokens"
        )
        assert len(fmt_def.style_tokens_negative) >= 2, (
            f"{fmt_def.format.value}: need at least 2 negative style tokens"
        )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_compatible_and_incompatible_keys_are_valid_genre_keys(
        self, fmt_def: FormatDefinition
    ):
        """All keys in compatible/incompatible lists must be real genre keys."""
        for key in fmt_def.compatible_genre_keys:
            assert key in GENRE_KEYS, (
                f"{fmt_def.format.value}: unknown genre key in compatible_genre_keys: '{key}'"
            )
        for key in fmt_def.incompatible_genre_keys:
            assert key in GENRE_KEYS, (
                f"{fmt_def.format.value}: unknown genre key in incompatible_genre_keys: '{key}'"
            )

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_no_overlap_between_compatible_and_incompatible(
        self, fmt_def: FormatDefinition
    ):
        overlap = set(fmt_def.compatible_genre_keys) & set(fmt_def.incompatible_genre_keys)
        assert not overlap, (
            f"{fmt_def.format.value}: genre keys appear in both compatible and "
            f"incompatible lists: {overlap}"
        )


class TestCompatibilityMatrix:
    def test_every_genre_has_at_least_one_compatible_format(self):
        for genre_key in GENRE_KEYS:
            compatible = get_compatible_formats(genre_key)
            assert len(compatible) >= 1, (
                f"Genre '{genre_key}' has no compatible formats"
            )

    def test_western_comic_is_compatible_with_all_genres(self):
        """Western Comic is the universal fallback — compatible with every genre."""
        for genre_key in GENRE_KEYS:
            compatible_keys = [f.format for f in get_compatible_formats(genre_key)]
            assert PresentationFormat.WESTERN_COMIC in compatible_keys, (
                f"Western Comic must be compatible with genre '{genre_key}'"
            )

    def test_folk_tale_only_compatible_with_basm_and_horror(self):
        """Folk Tale Illustration is restricted to Basm and Horror Mioritic."""
        expected_genres = {"basm_romanesc_absurd", "horror_mioritic"}
        for genre_key in GENRE_KEYS:
            compatible_keys = {f.format for f in get_compatible_formats(genre_key)}
            if genre_key in expected_genres:
                assert PresentationFormat.FOLK_TALE_ILLUSTRATION in compatible_keys, (
                    f"Folk Tale must be compatible with '{genre_key}'"
                )
            else:
                assert PresentationFormat.FOLK_TALE_ILLUSTRATION not in compatible_keys, (
                    f"Folk Tale must NOT be compatible with '{genre_key}'"
                )

    def test_incompatible_formats_excluded(self):
        """Incompatible formats must not appear in get_compatible_formats results."""
        basm_formats = {f.format for f in get_compatible_formats("basm_romanesc_absurd")}
        assert PresentationFormat.FAKE_NEWS_BROADCAST not in basm_formats
        assert PresentationFormat.POLICE_REPORT not in basm_formats
        assert PresentationFormat.INTERPOL_DOSSIER not in basm_formats

        actiune_formats = {f.format for f in get_compatible_formats("film_actiune_b")}
        assert PresentationFormat.DOCUMENTARY_FILM not in actiune_formats
        assert PresentationFormat.FOLK_TALE_ILLUSTRATION not in actiune_formats

    def test_get_compatible_formats_returns_format_definitions(self):
        for genre_key in GENRE_KEYS:
            results = get_compatible_formats(genre_key)
            for r in results:
                assert isinstance(r, FormatDefinition)


class TestLayoutLookup:
    def test_get_layout_for_panel_count_returns_correct_layout(self):
        layout = get_layout_for_panel_count(PresentationFormat.WESTERN_COMIC, 4)
        assert isinstance(layout, LayoutStrategy)
        assert layout.panel_count == 4
        assert layout.grid_template == "2x2"

    def test_get_layout_raises_for_unsupported_count(self):
        with pytest.raises(ValueError, match="does not support"):
            # Western Comic supports 4,5,6,8 but not 3
            get_layout_for_panel_count(PresentationFormat.WESTERN_COMIC, 3)

    @pytest.mark.parametrize("fmt_def", list_formats())
    def test_all_supported_counts_retrievable(self, fmt_def: FormatDefinition):
        for count in fmt_def.supported_panel_counts:
            layout = get_layout_for_panel_count(fmt_def.format, count)
            assert layout.panel_count == count


class TestSpecificFormats:
    def test_western_comic_is_universal(self):
        """Western Comic has no genre restrictions."""
        assert WESTERN_COMIC.compatible_genre_keys == []
        assert WESTERN_COMIC.incompatible_genre_keys == []

    def test_folk_tale_uses_frame_overlay(self):
        assert FOLK_TALE_ILLUSTRATION.uses_frame_overlay is True

    def test_news_broadcast_uses_frame_overlay(self):
        assert FAKE_NEWS_BROADCAST.uses_frame_overlay is True

    def test_documentary_film_does_not_use_frame_overlay(self):
        assert DOCUMENTARY_FILM.uses_frame_overlay is False

    def test_instagram_story_has_vertical_layouts(self):
        """Instagram Story should have at least one vertical layout."""
        has_vertical = any(
            layout.orientation == "vertical"
            for layout in INSTAGRAM_STORY_SEQUENCE.layout_strategies.values()
        )
        assert has_vertical, "Instagram Story must have at least one vertical layout"

    def test_police_report_has_vertical_layout_for_5_panels(self):
        layout = get_layout_for_panel_count(PresentationFormat.POLICE_REPORT, 5)
        assert layout.orientation == "vertical"

    def test_all_css_theme_keys_unique(self):
        keys = [f.css_theme_key for f in list_formats()]
        assert len(keys) == len(set(keys)), "All css_theme_key values must be unique"

    def test_interpol_dossier_incompatible_with_basm_and_telenovela(self):
        basm_formats = {f.format for f in get_compatible_formats("basm_romanesc_absurd")}
        tele_formats = {f.format for f in get_compatible_formats("telenovela_romaneasca")}
        assert PresentationFormat.INTERPOL_DOSSIER not in basm_formats
        assert PresentationFormat.INTERPOL_DOSSIER not in tele_formats