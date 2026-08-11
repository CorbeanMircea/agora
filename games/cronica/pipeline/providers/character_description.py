"""
M5.2 — Character Description System

Generates consistent visual descriptions (CharacterSheets) for each
player-character at the start of image generation.

Design constraints (from TASKS.md M5.2 + GDD Section 7.3):
  - Each player-character gets a CharacterSheet: name, hair colour/style,
    clothing dominant colour (unique per character), one distinguishing feature.
  - Colour assignments are unique within a round (no two characters share
    a dominant clothing colour).
  - Character sheets are derived from player names and archetype (not randomly
    per-call — same inputs → same output for reproducibility).
  - Same character sheet is injected into every panel prompt featuring that
    character.
  - Character sheets are written alongside brief.json in the output directory.
  - Maximum 3 characters per panel (GDD Section 7.3 hard constraint).

Character consistency strategy (GDD Section 7.3):
  Face identity locking across panels is an unsolved problem with FLUX.1.
  Consistency is achieved through:
    - Unique clothing colour per character (instinctive visual parsing)
    - Consistent hair + distinguishing feature description in every panel
    - Character count limit (max 3 per panel) enforced at prompt build time
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── Colour palette: unique per-character clothing colours ─────────────────────
# 8 colours — enough for up to 8 players (GDD max player count).
# Chosen for visual distinctiveness in generated images.
_CHARACTER_COLOURS: list[tuple[str, str]] = [
    ("red",     "vibrant red"),
    ("blue",    "deep blue"),
    ("green",   "forest green"),
    ("purple",  "rich purple"),
    ("orange",  "burnt orange"),
    ("teal",    "teal"),
    ("gold",    "golden yellow"),
    ("pink",    "rose pink"),
]

# Hair description pool — derived deterministically from player name hash
_HAIR_STYLES: list[str] = [
    "short dark hair",
    "long blonde hair",
    "curly brown hair",
    "straight black hair",
    "wavy auburn hair",
    "cropped grey hair",
    "long red hair",
    "shoulder-length brown hair",
]

# Distinguishing feature pool — derived from archetype key hash
_DISTINGUISHING_FEATURES: list[str] = [
    "wearing thick-rimmed glasses",
    "with a prominent moustache",
    "with a long flowing scarf",
    "with large expressive eyebrows",
    "with a distinctive hat",
    "with a visible scar on the chin",
    "with earrings and an intense gaze",
    "with a short beard and suspicious eyes",
]

# Maximum characters per panel (GDD Section 7.3 hard constraint)
MAX_CHARACTERS_PER_PANEL: int = 3


# ── CharacterSheet dataclass ──────────────────────────────────────────────────

@dataclass
class CharacterSheet:
    """
    Visual specification for one player-character across all panels.

    Used by the Panel Composition Orchestrator (M5.5) to build consistent
    character_descriptions for every panel prompt that includes this character.
    """

    # Player identifier (from SQLite / archetype assignment)
    player_id: str

    # Display name shown in the story (Romanian nickname)
    nickname: str

    # Archetype key (e.g. "victima", "tradatorul") from the genre registry
    archetype_key: str

    # Short archetype label in Romanian (e.g. "Victima", "Trădătorul")
    archetype_name_ro: str

    # Dominant clothing colour name (used in image prompts, English)
    clothing_colour: str

    # Verbose clothing colour description (e.g. "vibrant red")
    clothing_colour_verbose: str

    # Hair description (English, for image prompts)
    hair_description: str

    # One distinguishing visual feature (English, for image prompts)
    distinguishing_feature: str

    def to_prompt_fragment(self) -> str:
        """
        Build the English image-prompt fragment for this character.

        This string is injected into every panel prompt where this character
        appears. It describes the character visually without revealing the
        player's actual identity to the image model.

        Format: "{nickname}, {hair}, {clothing}, {feature}"
        Example: "Victima, short dark hair, vibrant red dress, wearing thick-rimmed glasses"
        """
        return (
            f"{self.archetype_name_ro}, "
            f"{self.hair_description}, "
            f"{self.clothing_colour_verbose} clothing, "
            f"{self.distinguishing_feature}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for brief.json embedding."""
        return asdict(self)


# ── CharacterRoster ───────────────────────────────────────────────────────────

@dataclass
class CharacterRoster:
    """
    The complete set of CharacterSheets for one round.

    Written to character_sheets.json in the round output directory.
    Consumed by the Panel Composition Orchestrator to build per-panel prompts.
    """

    sheets: list[CharacterSheet] = field(default_factory=list)

    def get_by_player_id(self, player_id: str) -> CharacterSheet | None:
        """Look up a sheet by player_id."""
        for sheet in self.sheets:
            if sheet.player_id == player_id:
                return sheet
        return None

    def get_by_archetype_key(self, archetype_key: str) -> CharacterSheet | None:
        """Look up a sheet by archetype key."""
        for sheet in self.sheets:
            if sheet.archetype_key == archetype_key:
                return sheet
        return None

    def build_panel_character_descriptions(
        self,
        archetype_keys_in_panel: list[str],
    ) -> list[str]:
        """
        Build the list of character description strings for a single panel.

        Applies the MAX_CHARACTERS_PER_PANEL hard constraint (GDD 7.3):
        if more than 3 archetype keys are provided, only the first 3 are used.

        Parameters
        ----------
        archetype_keys_in_panel:
            Archetype keys of characters appearing in this panel,
            from PanelDescription.characters_in_panel.

        Returns
        -------
        list[str]
            One prompt fragment per character (max 3).
        """
        clamped_keys = archetype_keys_in_panel[:MAX_CHARACTERS_PER_PANEL]
        descriptions: list[str] = []
        for key in clamped_keys:
            sheet = self.get_by_archetype_key(key)
            if sheet is not None:
                descriptions.append(sheet.to_prompt_fragment())
        return descriptions

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {"sheets": [s.to_dict() for s in self.sheets]}

    def save(self, output_dir: Path) -> None:
        """Write character_sheets.json to the output directory."""
        path = output_dir / "character_sheets.json"
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, output_dir: Path) -> "CharacterRoster":
        """Load character_sheets.json from the output directory."""
        path = output_dir / "character_sheets.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        sheets = [
            CharacterSheet(**s)
            for s in data["sheets"]
        ]
        return cls(sheets=sheets)


# ── CharacterDescriptionGenerator ────────────────────────────────────────────

class CharacterDescriptionGenerator:
    """
    Generates a CharacterRoster from a populated CreativeBrief.

    Derives all character attributes deterministically from player names
    and archetype keys so the same inputs always produce the same sheets.
    This is critical for reproducibility in debug/test scenarios.

    Usage
    -----
    ::
        generator = CharacterDescriptionGenerator()
        roster = generator.generate(brief)
        roster.save(output_dir)
    """

    def generate(self, brief: Any) -> CharacterRoster:
        """
        Generate a CharacterRoster from a CreativeBrief.

        Parameters
        ----------
        brief:
            A populated CreativeBrief instance (from creative_director.models).
            Must have archetypes with player_id and player_nickname assigned.

        Returns
        -------
        CharacterRoster
            One CharacterSheet per player. Clothing colours are unique.
        """
        archetypes = list(getattr(brief, "archetypes", []))
        if not archetypes:
            return CharacterRoster(sheets=[])

        # Assign unique clothing colours in archetype order
        sheets: list[CharacterSheet] = []
        used_colours: set[str] = set()

        for i, arch in enumerate(archetypes):
            player_id: str = getattr(arch, "player_id", None) or f"player_{i}"
            nickname: str = getattr(arch, "player_nickname", None) or f"Player{i}"
            archetype_key: str = getattr(arch, "key", f"archetype_{i}")
            archetype_name_ro: str = getattr(arch, "name_ro", archetype_key)

            # Clothing colour: assigned by position to guarantee uniqueness
            colour_index = i % len(_CHARACTER_COLOURS)
            colour_name, colour_verbose = _CHARACTER_COLOURS[colour_index]
            # If somehow colliding (shouldn't happen within 8 players), shift
            while colour_name in used_colours:
                colour_index = (colour_index + 1) % len(_CHARACTER_COLOURS)
                colour_name, colour_verbose = _CHARACTER_COLOURS[colour_index]
            used_colours.add(colour_name)

            # Hair: derived from nickname hash (deterministic)
            hair = _HAIR_STYLES[_stable_hash(nickname) % len(_HAIR_STYLES)]

            # Distinguishing feature: derived from archetype key hash (deterministic)
            feature = _DISTINGUISHING_FEATURES[
                _stable_hash(archetype_key) % len(_DISTINGUISHING_FEATURES)
            ]

            sheets.append(CharacterSheet(
                player_id=player_id,
                nickname=nickname,
                archetype_key=archetype_key,
                archetype_name_ro=archetype_name_ro,
                clothing_colour=colour_name,
                clothing_colour_verbose=colour_verbose,
                hair_description=hair,
                distinguishing_feature=feature,
            ))

        return CharacterRoster(sheets=sheets)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stable_hash(text: str) -> int:
    """
    Return a stable, positive integer hash of a string.
    Uses SHA-256 truncated to 32 bits for cross-platform reproducibility.
    Python's built-in hash() is not stable across processes.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")