"""
M5.2 — Character Description System

Generates consistent visual descriptions (CharacterSheets) for each
player-character at the start of image generation.

Key change from original: character sheets now generate richer, more
specific visual descriptions that the LLM can use directly in image prompts.
The visual identity (clothing color, hair, feature) is injected into the
LLM system prompt so image_prompt_en naturally includes these details.

GDD Section 7.3: maximum 3 characters per panel.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── Colour palette: unique per-character clothing colours ─────────────────────
# Visually distinct colours for comic book character identification.
_CHARACTER_COLOURS: list[tuple[str, str, str]] = [
    ("red",     "vibrant red",      "#E74C3C"),
    ("blue",    "deep blue",        "#2980B9"),
    ("green",   "forest green",     "#27AE60"),
    ("purple",  "rich purple",      "#8E44AD"),
    ("orange",  "burnt orange",     "#E67E22"),
    ("teal",    "teal",             "#16A085"),
    ("gold",    "golden yellow",    "#F1C40F"),
    ("pink",    "rose pink",        "#E91E63"),
]

# Hair descriptions — deterministic from player nickname hash
_HAIR_STYLES: list[str] = [
    "short dark brown hair",
    "long straight blonde hair",
    "curly black hair",
    "wavy auburn hair",
    "cropped grey hair",
    "short spiky black hair",
    "long red hair in a ponytail",
    "shoulder-length brown hair",
]

# Distinguishing features — deterministic from archetype key hash
_DISTINGUISHING_FEATURES: list[str] = [
    "wearing large round glasses",
    "with a long colourful scarf wrapped around neck",
    "with very thick expressive eyebrows",
    "wearing a distinctive wide-brimmed hat",
    "with large hoop earrings",
    "with a prominent jaw and confident posture",
    "wearing a vintage leather jacket",
    "with freckles across the nose and cheeks",
]

# Approximate ages — deterministic from player id hash
_AGES: list[str] = [
    "mid-30s",
    "late 20s",
    "early 40s",
    "mid-20s",
    "early 30s",
    "late 30s",
    "early 50s",
    "mid-40s",
]

MAX_CHARACTERS_PER_PANEL: int = 3


@dataclass
class CharacterSheet:
    """
    Visual specification for one player-character across all panels.
    """

    player_id: str
    nickname: str
    archetype_key: str
    archetype_name_ro: str

    # Dominant clothing colour (English, for image prompts)
    clothing_colour: str
    clothing_colour_verbose: str
    clothing_hex: str

    # Hair description (English)
    hair_description: str

    # One distinguishing visual feature (English)
    distinguishing_feature: str

    # Approximate age
    age: str

    def to_prompt_fragment(self) -> str:
        """
        Build a concise English character description for image prompts.

        Format used in image_prompt_en:
        "{nickname}, {age}, {hair}, wearing {clothing}, {feature}"

        This is injected into the image prompt so the model renders
        a consistent visual identity for this character.
        """
        return (
            f"{self.nickname}: {self.age}, {self.hair_description}, "
            f"wearing {self.clothing_colour_verbose} outfit, "
            f"{self.distinguishing_feature}"
        )

    def to_system_prompt_block(self) -> str:
        """
        Build a detailed character block for the LLM system prompt.

        This is more verbose than to_prompt_fragment() because the LLM
        needs to understand the character's visual identity to write
        accurate image_prompt_en descriptions.
        """
        return (
            f"CHARACTER VISUAL IDENTITY — {self.nickname}:\n"
            f"  Age: {self.age}\n"
            f"  Hair: {self.hair_description}\n"
            f"  Clothing: always wearing {self.clothing_colour_verbose} outfit "
            f"(colour code: {self.clothing_hex})\n"
            f"  Distinctive feature: {self.distinguishing_feature}\n"
            f"  RULE: In every image_prompt_en where {self.nickname} appears,\n"
            f"  describe them as: \"{self.to_prompt_fragment()}\"\n"
            f"  Do NOT call them '{self.archetype_name_ro}' in image descriptions.\n"
            f"  Use their name '{self.nickname}' and the appearance above."
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CharacterRoster:
    """
    The complete set of CharacterSheets for one round.
    """

    sheets: list[CharacterSheet] = field(default_factory=list)

    def get_by_player_id(self, player_id: str) -> CharacterSheet | None:
        for sheet in self.sheets:
            if sheet.player_id == player_id:
                return sheet
        return None

    def get_by_archetype_key(self, archetype_key: str) -> CharacterSheet | None:
        for sheet in self.sheets:
            if sheet.archetype_key == archetype_key:
                return sheet
        return None

    def get_by_nickname(self, nickname: str) -> CharacterSheet | None:
        for sheet in self.sheets:
            if sheet.nickname == nickname:
                return sheet
        return None

    def build_panel_character_descriptions(
        self,
        archetype_keys_in_panel: list[str],
    ) -> list[str]:
        """
        Build character description strings for a single panel.

        Returns plain English strings suitable for inclusion in image_prompt_en.
        Applies MAX_CHARACTERS_PER_PANEL hard constraint (GDD 7.3).
        """
        clamped_keys = archetype_keys_in_panel[:MAX_CHARACTERS_PER_PANEL]
        descriptions: list[str] = []
        for key in clamped_keys:
            sheet = self.get_by_archetype_key(key)
            if sheet is not None:
                descriptions.append(sheet.to_prompt_fragment())
        return descriptions

    def build_system_prompt_section(self) -> str:
        """
        Build the complete CHARACTER VISUAL IDENTITIES section for the
        LLM system prompt. This is injected early so the LLM writes
        image_prompt_en with correct visual descriptions.
        """
        if not self.sheets:
            return ""
        lines = ["CHARACTER VISUAL IDENTITIES (use these in every image_prompt_en):"]
        for sheet in self.sheets:
            lines.append("")
            lines.append(sheet.to_system_prompt_block())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"sheets": [s.to_dict() for s in self.sheets]}

    def save(self, output_dir: Path) -> None:
        path = output_dir / "character_sheets.json"
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, output_dir: Path) -> "CharacterRoster":
        path = output_dir / "character_sheets.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        sheets = [CharacterSheet(**s) for s in data["sheets"]]
        return cls(sheets=sheets)


class CharacterDescriptionGenerator:
    """
    Generates a CharacterRoster from a populated CreativeBrief.

    All character attributes are derived deterministically from player names
    and archetype keys for reproducibility.
    """

    def generate(self, brief: Any) -> CharacterRoster:
        """
        Generate a CharacterRoster from a CreativeBrief.

        Each player gets a unique clothing colour and consistent visual identity.
        """
        archetypes = list(getattr(brief, "archetypes", []))
        if not archetypes:
            return CharacterRoster(sheets=[])

        sheets: list[CharacterSheet] = []
        used_colours: set[str] = set()

        for i, arch in enumerate(archetypes):
            player_id: str = getattr(arch, "player_id", None) or f"player_{i}"
            nickname: str = getattr(arch, "player_nickname", None) or f"Player{i}"
            archetype_key: str = getattr(arch, "key", f"archetype_{i}")
            archetype_name_ro: str = getattr(arch, "name_ro", archetype_key)

            # Clothing colour: unique per character, assigned by position
            colour_index = i % len(_CHARACTER_COLOURS)
            colour_name, colour_verbose, colour_hex = _CHARACTER_COLOURS[colour_index]
            while colour_name in used_colours:
                colour_index = (colour_index + 1) % len(_CHARACTER_COLOURS)
                colour_name, colour_verbose, colour_hex = _CHARACTER_COLOURS[colour_index]
            used_colours.add(colour_name)

            # Deterministic from nickname hash
            hair = _HAIR_STYLES[_stable_hash(nickname) % len(_HAIR_STYLES)]

            # Deterministic from archetype key hash
            feature = _DISTINGUISHING_FEATURES[
                _stable_hash(archetype_key) % len(_DISTINGUISHING_FEATURES)
            ]

            # Deterministic from player_id hash
            age = _AGES[_stable_hash(player_id) % len(_AGES)]

            sheets.append(CharacterSheet(
                player_id=player_id,
                nickname=nickname,
                archetype_key=archetype_key,
                archetype_name_ro=archetype_name_ro,
                clothing_colour=colour_name,
                clothing_colour_verbose=colour_verbose,
                clothing_hex=colour_hex,
                hair_description=hair,
                distinguishing_feature=feature,
                age=age,
            ))

        return CharacterRoster(sheets=sheets)


def _stable_hash(text: str) -> int:
    """
    Return a stable, positive integer hash of a string.
    Uses SHA-256 truncated to 32 bits for cross-platform reproducibility.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")