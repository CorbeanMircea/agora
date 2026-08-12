"""
M5.4 — Style Token Injection

Translates a CreativeBrief's genre visual style, presentation format,
and per-panel camera rules into ComfyUI prompt tokens.

Produces:
  - A populated VisualStyle (genre + format tokens merged)
  - A list of per-panel ImagePrompt objects with camera and style tokens

Design constraints (TASKS.md M5.4):
  - Tokens constructed deterministically from the CreativeBrief.
  - No hard-coded prompt strings outside this module.
  - Camera language per panel translated to composition tokens
    (from CreativeBrief.camera_language[i].prompt_tokens).
  - Genre positive/negative tokens come from GenreDefinition.
  - Format positive/negative tokens come from FormatDefinition.
  - The two token sets are merged (genre first, format second).

Usage (Panel Composition Orchestrator, M5.5):
::
    injector = StyleTokenInjector()
    visual_style = injector.build_visual_style(brief)
    image_prompts = injector.build_image_prompts(brief, story, character_roster)
"""

from __future__ import annotations

from typing import Any

from .image_generator_provider import ImagePrompt, VisualStyle
from ..creative_director.genre_registry import get_genre
from ..creative_director.format_registry import get_format
from ..creative_director.models import PresentationFormat


class StyleTokenInjector:
    """
    Builds VisualStyle and ImagePrompt objects from a CreativeBrief.

    All token construction is deterministic: the same brief always produces
    the same tokens. No randomness is introduced here.
    """

    def build_visual_style(self, brief: Any) -> VisualStyle:
        """
        Build a fully populated VisualStyle from a CreativeBrief.

        Merges genre-level and format-level style tokens into the
        positive/negative token lists consumed by FluxImageGenerator.

        Parameters
        ----------
        brief:
            A populated CreativeBrief instance.

        Returns
        -------
        VisualStyle
            With genre + format style tokens merged into
            style_tokens_positive and style_tokens_negative.
        """
        genre_key: str = getattr(brief, "genre_key", "")
        fmt_value: str = getattr(brief, "format", "")

        # Retrieve genre and format style tokens
        genre_positive: list[str] = []
        genre_negative: list[str] = []
        if genre_key:
            try:
                genre_def = get_genre(genre_key)
                genre_positive = list(genre_def.style_tokens_positive)
                genre_negative = list(genre_def.style_tokens_negative)
            except KeyError:
                pass

        format_positive: list[str] = []
        format_negative: list[str] = []
        if fmt_value:
            try:
                fmt_enum = PresentationFormat(fmt_value)
                fmt_def = get_format(fmt_enum)
                format_positive = list(fmt_def.style_tokens_positive)
                format_negative = list(fmt_def.style_tokens_negative)
            except (ValueError, KeyError):
                pass

        # Merge: genre tokens first, format tokens second (deduplicating)
        merged_positive = _merge_tokens(genre_positive, format_positive)
        merged_negative = _merge_tokens(genre_negative, format_negative)

        return VisualStyle(
            genre_key=genre_key,
            visual_style=getattr(brief, "visual_style", ""),
            lighting_mood=getattr(brief, "lighting_mood", ""),
            colour_palette=list(getattr(brief, "colour_palette", [])),
            style_tokens_positive=merged_positive,
            style_tokens_negative=merged_negative,
        )

    def build_image_prompts(
        self,
        brief: Any,
        story: Any,
        character_roster: Any | None = None,
    ) -> list[ImagePrompt]:
        """
        Build one ImagePrompt per panel from the brief, story, and roster.

        Parameters
        ----------
        brief:
            A populated CreativeBrief instance.
        story:
            A Story instance (from story_llm_provider).
            story.panels[i].image_prompt_en is the LLM-generated base prompt.
            story.panels[i].characters_in_panel lists archetype keys.
        character_roster:
            A CharacterRoster instance (from character_description).
            May be None — character descriptions are skipped if absent.

        Returns
        -------
        list[ImagePrompt]
            One ImagePrompt per panel, in panel order.
        """
        visual_style = self.build_visual_style(brief)
        panel_count: int = getattr(brief, "panel_count", 0)

        # Build camera token map: panel_index → prompt_tokens
        camera_rules = list(getattr(brief, "camera_language", []))
        camera_token_map: dict[int, str] = {}
        for rule in camera_rules:
            idx = getattr(rule, "panel_index", None)
            tokens = getattr(rule, "prompt_tokens", "")
            if idx is not None:
                camera_token_map[idx] = tokens

        panels = list(getattr(story, "panels", []))

        prompts: list[ImagePrompt] = []
        for i in range(panel_count):
            panel = panels[i] if i < len(panels) else None

            base_prompt: str = ""
            archetype_keys: list[str] = []
            if panel is not None:
                base_prompt = getattr(panel, "image_prompt_en", "")
                archetype_keys = list(getattr(panel, "characters_in_panel", []))

            camera_tokens: str = camera_token_map.get(i, "")

            # Character descriptions from the roster
            char_descriptions: list[str] = []
            if character_roster is not None and archetype_keys:
                char_descriptions = character_roster.build_panel_character_descriptions(
                    archetype_keys
                )

            prompts.append(ImagePrompt(
                panel_index=i,
                base_prompt=base_prompt,
                style_tokens_positive=list(visual_style.style_tokens_positive),
                style_tokens_negative=list(visual_style.style_tokens_negative),
                camera_tokens=camera_tokens,
                character_descriptions=char_descriptions,
            ))

        return prompts


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge_tokens(primary: list[str], secondary: list[str]) -> list[str]:
    """
    Merge two token lists, preserving order and removing duplicates.
    Primary tokens come first; secondary tokens are appended if not already present.
    Comparison is case-insensitive.
    """
    seen: set[str] = set()
    result: list[str] = []
    for token in primary + secondary:
        key = token.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(token.strip())
    return result