"""
M5.4 — Style Token Injection

Translates a CreativeBrief's genre visual style and camera rules into
ComfyUI prompt tokens.

Target visual style: bold Romanian comic-book illustration matching the
reference image — strong ink outlines, expressive characters, vibrant
saturated colors, dramatic lighting.

Text overlays (narration, dialogue) are added by a separate PIL renderer.
The image generator produces clean comic artwork. To prevent garbled
AI-generated text in images, text-rendering tokens are in the NEGATIVE list.
Comic book STYLE tokens are in the POSITIVE list (they define the art style,
not text rendering).
"""

from __future__ import annotations

from typing import Any

from .image_generator_provider import ImagePrompt, VisualStyle
from ..creative_director.genre_registry import get_genre
from ..creative_director.format_registry import get_format
from ..creative_director.models import PresentationFormat

# ── Global comic-book style anchor ────────────────────────────────────────────
#
# These tokens establish the visual medium for EVERY panel.
# Matches the reference image: bold Romanian comic-book illustration.
#
_GLOBAL_STYLE_POSITIVE: list[str] = [
    "Bradhamel art style",
    "comic book illustration",
    "bold ink outlines",
    "exaggerated expressive characters",
    "vibrant saturated colors",
    "flat color shading",
    "dynamic action composition",
    "dramatic lighting",
    "detailed illustrated background",
    "professional comic book art",
    "sharp clean lines",
    "graphic novel style",
]

# Negative tokens:
# - Prevent photorealism
# - Prevent AI text rendering (garbled speech bubbles, captions)
#   NOTE: "comic book" stays in POSITIVE (art style). We prevent TEXT, not the art style.
_GLOBAL_STYLE_NEGATIVE: list[str] = [
    "photorealistic",
    "photograph",
    "realistic",
    "hyperrealistic",
    "3d render",
    "CGI",
    "anime",
    "manga",
    "low quality",
    "blurry",
    "bad anatomy",
    "deformed",
    "ugly",
    "worst quality",
    "extra limbs",
    "watermark",
    "signature",
    "text",
    "caption",
    "speech bubble",
    "word balloon",
    "subtitle",
    "written text",
    "typography",
]


class StyleTokenInjector:
    """
    Builds VisualStyle and ImagePrompt objects from a CreativeBrief.
    All token construction is deterministic.
    """

    def build_visual_style(self, brief: Any) -> VisualStyle:
        """
        Build a fully populated VisualStyle from a CreativeBrief.
        Merges global comic style + genre-level + format-level tokens.
        """
        genre_key: str = getattr(brief, "genre_key", "")
        fmt_value: str = getattr(brief, "format", "")

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

        # Global comic style first, then genre/format (deduplicating)
        merged_positive = _merge_tokens(
            _GLOBAL_STYLE_POSITIVE,
            _merge_tokens(genre_positive, format_positive),
        )
        merged_negative = _merge_tokens(
            _GLOBAL_STYLE_NEGATIVE,
            _merge_tokens(genre_negative, format_negative),
        )

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
        """
        visual_style = self.build_visual_style(brief)
        panel_count: int = getattr(brief, "panel_count", 0)

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
    Merge two token lists, preserving order and removing case-insensitive duplicates.
    """
    seen: set[str] = set()
    result: list[str] = []
    for token in primary + secondary:
        key = token.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(token.strip())
    return result