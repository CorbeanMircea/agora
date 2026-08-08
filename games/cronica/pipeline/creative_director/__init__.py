"""
CRONICĂ Creative Director package.
"""
from .models import (
    CreativeBrief,
    StoryArc,
    Archetype,
    Twist,
    CameraRule,
    NarratorPersona,
    SFXNote,
    LayoutStrategy,
    PresentationFormat,
    RevealPacing,
    IngredientRole,
)
from .genre_registry import GENRE_REGISTRY, GenreDefinition, get_genre, list_genres
from .format_registry import (
    FORMAT_REGISTRY,
    FormatDefinition,
    get_format,
    list_formats,
    get_compatible_formats,
    get_layout_for_panel_count,
)
from .genre_selection import (
    select_genre,
    compute_genre_weights,
)
from .archetype_assignment import (
    assign as assign_archetypes,
    validate_assignments,
    PlayerIngredient,
    AssignedArchetype,
)

__all__ = [
    # models
    "CreativeBrief",
    "StoryArc",
    "Archetype",
    "Twist",
    "CameraRule",
    "NarratorPersona",
    "SFXNote",
    "LayoutStrategy",
    "PresentationFormat",
    "RevealPacing",
    "IngredientRole",
    # genre registry
    "GENRE_REGISTRY",
    "GenreDefinition",
    "get_genre",
    "list_genres",
    # format registry
    "FORMAT_REGISTRY",
    "FormatDefinition",
    "get_format",
    "list_formats",
    "get_compatible_formats",
    "get_layout_for_panel_count",
    # genre selection
    "select_genre",
    "compute_genre_weights",
    # archetype assignment
    "assign_archetypes",
    "validate_assignments",
    "PlayerIngredient",
    "AssignedArchetype",
]