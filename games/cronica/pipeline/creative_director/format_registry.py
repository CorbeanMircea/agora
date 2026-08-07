"""
M3.3 — Presentation Format Registry

All 7 CRONICĂ presentation formats as structured data.

A presentation format is independent of genre: it controls *how* the story
is visually presented, not *what* story is told. The same telenovelă plot
can be rendered as a Western Comic or a Fake News Broadcast.

Sources:
  GDD v0.2.1 Section 6.4 (Presentation Formats)
  GDD v0.2.1 Section 6.3 (Genre Registry — compatible_formats per genre)

Design principles:
  - Formats are pure data (no executable logic).
  - Each format encodes the layout strategy the Tauri presenter needs.
  - The compatibility matrix is encoded here (not in the genre registry)
    so it can be consulted independently of genre selection.
  - All ComfyUI tokens are in English; all display copy is in Romanian.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import PresentationFormat, LayoutStrategy


# ── FormatDefinition ──────────────────────────────────────────────────────────

@dataclass
class FormatDefinition:
    """
    Complete specification for one CRONICĂ presentation format.

    A FormatDefinition is consumed by:
      - The Creative Director (M3.6) to populate layout fields in the
        CreativeBrief.
      - The Style Token Injector (M5.4) to add format-specific ComfyUI tokens.
      - The Tauri presenter (M7) to select the correct CSS layout template.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    # The canonical enum value for this format.
    format: PresentationFormat

    # Display name in Romanian, shown in debug/host UI.
    name_ro: str

    # Short atmospheric description (Romanian).
    description_ro: str

    # ── Layout ────────────────────────────────────────────────────────────

    # Supported panel counts for this format, in order of preference.
    # Creative Director picks the panel count from the intersection of
    # genre.panel_counts and format.supported_panel_counts.
    supported_panel_counts: list[int]

    # Layout strategy for each supported panel count.
    # Key: panel_count, Value: LayoutStrategy.
    layout_strategies: dict[int, LayoutStrategy]

    # ── Visual ────────────────────────────────────────────────────────────

    # ComfyUI positive style tokens applied to every panel when this format
    # is active (English). Appended to genre-level tokens.
    style_tokens_positive: list[str]

    # ComfyUI negative style tokens (English). Appended to genre-level negatives.
    style_tokens_negative: list[str]

    # CSS theme key used by the Tauri presenter to select a stylesheet variant.
    # e.g. "western_comic", "news_broadcast"
    css_theme_key: str

    # Whether this format uses a framing device (e.g. a TV screen border,
    # a police report form, a newspaper layout). The presenter applies the
    # appropriate frame overlay if True.
    uses_frame_overlay: bool = False

    # ── Compatibility ─────────────────────────────────────────────────────

    # Genre keys that are compatible with this format.
    # An empty list means compatible with ALL genres.
    # Used by the Creative Director to validate/constrain format selection.
    compatible_genre_keys: list[str] = field(default_factory=list)

    # Genre keys that are NEVER compatible with this format (hard exclusions).
    # Takes precedence over compatible_genre_keys.
    incompatible_genre_keys: list[str] = field(default_factory=list)


# ── Helper ────────────────────────────────────────────────────────────────────

def _layout(
    panel_count: int,
    grid_template: str,
    featured_panel_index: int | None = None,
    orientation: str = "horizontal",
) -> LayoutStrategy:
    return LayoutStrategy(
        panel_count=panel_count,
        grid_template=grid_template,
        featured_panel_index=featured_panel_index,
        orientation=orientation,
    )


# ── Format 1: Western Comic ───────────────────────────────────────────────────

WESTERN_COMIC = FormatDefinition(
    format=PresentationFormat.WESTERN_COMIC,
    name_ro="Bandă Desenată",
    description_ro="Panouri clasice de benzi desenate cu chenare îngroșate și onomatopee.",
    supported_panel_counts=[4, 5, 6, 8],
    layout_strategies={
        4: _layout(4,  "2x2"),
        5: _layout(5,  "2x2+1", featured_panel_index=4),
        6: _layout(6,  "3x2"),
        8: _layout(8,  "4x2"),
    },
    style_tokens_positive=[
        "comic book style", "bold outlines", "halftone dots", "speech bubbles",
        "sequential art", "panel borders", "dynamic composition",
    ],
    style_tokens_negative=[
        "photorealistic", "photograph", "3d render", "watercolor",
        "impressionist", "abstract",
    ],
    css_theme_key="western_comic",
    uses_frame_overlay=False,
    compatible_genre_keys=[],  # Compatible with all genres
    incompatible_genre_keys=[],
)


# ── Format 2: Fake News Broadcast ─────────────────────────────────────────────

FAKE_NEWS_BROADCAST = FormatDefinition(
    format=PresentationFormat.FAKE_NEWS_BROADCAST,
    name_ro="Jurnal de Știri",
    description_ro="Cadre de televiziune cu grafice breaking news, lower thirds și studio TV.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "2x2"),
        5: _layout(5, "2x2+1", featured_panel_index=0),
        6: _layout(6, "3x2"),
    },
    style_tokens_positive=[
        "news broadcast", "television screen", "lower thirds graphics",
        "chyron text overlay", "studio lighting", "talking head framing",
        "breaking news aesthetic", "16:9 composition",
    ],
    style_tokens_negative=[
        "fantasy", "folk art", "comic book", "animation", "illustration",
        "nature landscape", "no text overlay",
    ],
    css_theme_key="news_broadcast",
    uses_frame_overlay=True,
    compatible_genre_keys=[
        "telenovela_romaneasca",
        "scandal_de_bloc",
        "documentar_fals",
        "stiri_rupte_din_realitate",
    ],
    incompatible_genre_keys=[
        "basm_romanesc_absurd",
        "horror_mioritic",
    ],
)


# ── Format 3: Police Report ───────────────────────────────────────────────────

POLICE_REPORT = FormatDefinition(
    format=PresentationFormat.POLICE_REPORT,
    name_ro="Dosar de Poliție",
    description_ro="Pagini de raport oficial cu ștampile, fotografii tip dosar și redactări.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "2x2"),
        5: _layout(5, "1x5", orientation="vertical"),
        6: _layout(6, "2x3"),
    },
    style_tokens_positive=[
        "police report aesthetic", "official document", "mugshot style",
        "evidence photograph", "black and white with red stamps",
        "typewriter font overlay", "bureaucratic framing",
    ],
    style_tokens_negative=[
        "colorful", "fantasy", "folk art", "animation", "bright cheerful",
        "natural outdoor", "warm tones",
    ],
    css_theme_key="police_report",
    uses_frame_overlay=True,
    compatible_genre_keys=[
        "film_actiune_b",
        "scandal_de_bloc",
        "documentar_fals",
        "stiri_rupte_din_realitate",
    ],
    incompatible_genre_keys=[
        "basm_romanesc_absurd",
        "horror_mioritic",
    ],
)


# ── Format 4: Documentary Film ────────────────────────────────────────────────

DOCUMENTARY_FILM = FormatDefinition(
    format=PresentationFormat.DOCUMENTARY_FILM,
    name_ro="Film Documentar",
    description_ro="Cadre de documentar cu interviuri față în față, imagini de arhivă și muzică ambientală.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "2x2"),
        5: _layout(5, "2x2+1", featured_panel_index=2),
        6: _layout(6, "3x2"),
    },
    style_tokens_positive=[
        "documentary film aesthetic", "handheld camera", "natural lighting",
        "talking head interview", "slightly desaturated", "16mm film grain",
        "archival footage look", "observational framing",
    ],
    style_tokens_negative=[
        "comic book", "animation", "bright saturated", "fantasy", "folk art",
        "action movie", "dramatic studio lighting",
    ],
    css_theme_key="documentary_film",
    uses_frame_overlay=False,
    compatible_genre_keys=[
        "documentar_fals",
        "horror_mioritic",
        "scandal_de_bloc",
    ],
    incompatible_genre_keys=[
        "film_actiune_b",
        "basm_romanesc_absurd",
    ],
)


# ── Format 5: Folk Tale Illustration ──────────────────────────────────────────

FOLK_TALE_ILLUSTRATION = FormatDefinition(
    format=PresentationFormat.FOLK_TALE_ILLUSTRATION,
    name_ro="Ilustrație de Poveste",
    description_ro="Panouri în stilul ilustrațiilor tradiționale românești cu ornamente, culori calde și naivism.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "2x2"),
        5: _layout(5, "2x2+1", featured_panel_index=0),
        6: _layout(6, "3x2"),
    },
    style_tokens_positive=[
        "folk art illustration", "Romanian naive art", "ornamental borders",
        "flat colors", "hand-drawn quality", "peasant aesthetic",
        "earthy warm tones", "storybook illustration", "decorative patterns",
    ],
    style_tokens_negative=[
        "photorealistic", "dark horror", "urban setting", "modern technology",
        "cold colors", "sci-fi", "news broadcast", "documentary",
    ],
    css_theme_key="folk_tale",
    uses_frame_overlay=True,
    compatible_genre_keys=[
        "basm_romanesc_absurd",
        "horror_mioritic",
    ],
    incompatible_genre_keys=[
        "film_actiune_b",
        "stiri_rupte_din_realitate",
        "scandal_de_bloc",
    ],
)


# ── Format 6: Instagram Story Sequence ───────────────────────────────────────

INSTAGRAM_STORY_SEQUENCE = FormatDefinition(
    format=PresentationFormat.INSTAGRAM_STORY_SEQUENCE,
    name_ro="Story Social Media",
    description_ro="Cadre verticale în stilul stories Instagram cu stickere, poll-uri false și font modern.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "1x4", orientation="vertical"),
        5: _layout(5, "1x5", orientation="vertical"),
        6: _layout(6, "2x3"),
    },
    style_tokens_positive=[
        "instagram story format", "vertical composition", "social media aesthetic",
        "millennial pink palette", "bold sans-serif text overlay",
        "emoji stickers", "candid photography style", "modern filter",
    ],
    style_tokens_negative=[
        "folk art", "historical", "dark horror", "black and white",
        "official document", "news broadcast", "low resolution",
    ],
    css_theme_key="instagram_story",
    uses_frame_overlay=True,
    compatible_genre_keys=[
        "telenovela_romaneasca",
        "scandal_de_bloc",
        "stiri_rupte_din_realitate",
    ],
    incompatible_genre_keys=[
        "basm_romanesc_absurd",
        "horror_mioritic",
        "documentar_fals",
    ],
)


# ── Format 7: Interpol Dossier ────────────────────────────────────────────────

INTERPOL_DOSSIER = FormatDefinition(
    format=PresentationFormat.INTERPOL_DOSSIER,
    name_ro="Dosar Interpol",
    description_ro="Fișe de urmărire internațională cu fotografii de supraveghere, hărți și coduri de caz.",
    supported_panel_counts=[4, 5, 6],
    layout_strategies={
        4: _layout(4, "2x2"),
        5: _layout(5, "2x2+1", featured_panel_index=4),
        6: _layout(6, "3x2"),
    },
    style_tokens_positive=[
        "Interpol dossier aesthetic", "surveillance photograph", "classified document",
        "red WANTED stamp", "security camera angle", "muted official colors",
        "intelligence report framing", "evidence board aesthetic",
    ],
    style_tokens_negative=[
        "cheerful", "colorful", "fantasy", "folk art", "animation",
        "warm tones", "social media", "comic book",
    ],
    css_theme_key="interpol_dossier",
    uses_frame_overlay=True,
    compatible_genre_keys=[
        "film_actiune_b",
        "stiri_rupte_din_realitate",
        "documentar_fals",
    ],
    incompatible_genre_keys=[
        "basm_romanesc_absurd",
        "telenovela_romaneasca",
        "scandal_de_bloc",
        "horror_mioritic",
    ],
)


# ── Registry ──────────────────────────────────────────────────────────────────

FORMAT_REGISTRY: dict[PresentationFormat, FormatDefinition] = {
    PresentationFormat.WESTERN_COMIC:           WESTERN_COMIC,
    PresentationFormat.FAKE_NEWS_BROADCAST:     FAKE_NEWS_BROADCAST,
    PresentationFormat.POLICE_REPORT:           POLICE_REPORT,
    PresentationFormat.DOCUMENTARY_FILM:        DOCUMENTARY_FILM,
    PresentationFormat.FOLK_TALE_ILLUSTRATION:  FOLK_TALE_ILLUSTRATION,
    PresentationFormat.INSTAGRAM_STORY_SEQUENCE: INSTAGRAM_STORY_SEQUENCE,
    PresentationFormat.INTERPOL_DOSSIER:        INTERPOL_DOSSIER,
}

FORMAT_KEYS: list[PresentationFormat] = list(FORMAT_REGISTRY.keys())


def get_format(fmt: PresentationFormat) -> FormatDefinition:
    """
    Retrieve a format definition by its enum value.
    Raises KeyError with a helpful message if not found.
    """
    if fmt not in FORMAT_REGISTRY:
        available = ", ".join(f.value for f in FORMAT_KEYS)
        raise KeyError(f"Format '{fmt}' not found. Available: {available}")
    return FORMAT_REGISTRY[fmt]


def list_formats() -> list[FormatDefinition]:
    """Return all format definitions in registration order."""
    return list(FORMAT_REGISTRY.values())


def get_compatible_formats(genre_key: str) -> list[FormatDefinition]:
    """
    Return all formats compatible with the given genre key.

    A format is compatible if:
      1. The genre key is not in its incompatible_genre_keys list, AND
      2. Either compatible_genre_keys is empty (all genres) OR the genre key
         is explicitly listed in compatible_genre_keys.
    """
    result = []
    for fmt_def in FORMAT_REGISTRY.values():
        if genre_key in fmt_def.incompatible_genre_keys:
            continue
        if fmt_def.compatible_genre_keys and genre_key not in fmt_def.compatible_genre_keys:
            continue
        result.append(fmt_def)
    return result


def get_layout_for_panel_count(
    fmt: PresentationFormat,
    panel_count: int,
) -> LayoutStrategy:
    """
    Return the LayoutStrategy for the given format and panel count.
    Raises ValueError if the panel count is not supported by this format.
    """
    fmt_def = get_format(fmt)
    if panel_count not in fmt_def.layout_strategies:
        supported = list(fmt_def.layout_strategies.keys())
        raise ValueError(
            f"Format '{fmt.value}' does not support {panel_count} panels. "
            f"Supported counts: {supported}"
        )
    return fmt_def.layout_strategies[panel_count]