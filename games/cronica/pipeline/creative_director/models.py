"""
M3.1 — CreativeBrief Data Model

All Python dataclasses and enums that represent the structured creative
specification produced by the Creative Director. Every downstream AI
component (LLM, ComfyUI, ElevenLabs/Piper) receives these objects and
uses them to shape their output.

Sources:
  GDD v0.2.1 Section 6.2 (CreativeBrief structure)
  GDD v0.2.1 Section 6.3 (Genre Registry — informs Archetype / StoryArc)
  ADR-001 (Ingredient System — informs how answers flow into archetypes)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import json


# ── Enums ────────────────────────────────────────────────────────────────────

class PresentationFormat(str, Enum):
    """
    The visual presentation format for the generated comic.
    Genre determines the *story*; format determines *how it is visually presented*.
    These are independent axes (GDD Section 6.4).
    """
    WESTERN_COMIC = "western_comic"
    FAKE_NEWS_BROADCAST = "fake_news_broadcast"
    POLICE_REPORT = "police_report"
    DOCUMENTARY_FILM = "documentary_film"
    FOLK_TALE_ILLUSTRATION = "folk_tale_illustration"
    INSTAGRAM_STORY_SEQUENCE = "instagram_story_sequence"
    INTERPOL_DOSSIER = "interpol_dossier"


class RevealPacing(str, Enum):
    """
    Controls the rhythm of the cinematic panel reveal in the Tauri presenter.
    GDD Section 6.2: revealPacing field.
    """
    SLOW_BURN = "slow-burn"
    RAPID_FIRE = "rapid-fire"
    DELIBERATE = "deliberate"
    CHAOTIC = "chaotic"


class IngredientRole(str, Enum):
    """
    The structural narrative role assigned to a player's ingredient answer
    by the Creative Director. An ingredient adapts to the story, not the
    reverse (ADR-001, GDD Section 3.5 completion criteria).
    """
    CHARACTER = "CHARACTER"
    LOCATION = "LOCATION"
    OBJECT = "OBJECT"
    CONCEPT = "CONCEPT"
    NAME = "NAME"
    QUANTITY = "QUANTITY"
    ACTION = "ACTION"
    ATMOSPHERE = "ATMOSPHERE"


# ── Supporting Dataclasses ────────────────────────────────────────────────────

@dataclass
class StoryArc:
    """
    The act structure and beat map for the generated story.
    Each genre defines a canonical StoryArc; the CD populates it from
    the genre's template (GDD Section 6.3).
    """
    beats: list[str]
    act_descriptions: list[str] = field(default_factory=list)
    climax_beat_index: int = 0
    causality_beats: list[dict] = field(default_factory=list)  # ← add this line


@dataclass
class Archetype:
    """
    A character role that one player's answers will fill in the story.
    Each genre defines its own archetype set (GDD Section 6.3).

    In the context of ADR-001: the Archetype is the *narrative role*,
    while the player's ingredient answers are assigned IngredientRole values
    by the Creative Director to map concrete answers → story structure.
    """
    # Machine-readable identifier, e.g. "vinovatul"
    key: str

    # Display name in Romanian, e.g. "Vinovatul"
    name_ro: str

    # One-sentence description of this archetype's role in the story.
    description_ro: str

    # The playerId that has been assigned this archetype.
    # Set by M3.5 (Archetype Assignment); None until then.
    player_id: str | None = None

    # The player's nickname at assignment time (for prompt building).
    player_nickname: str | None = None

    # Maps promptId → IngredientRole for this player's answers.
    # e.g. {"c_001": IngredientRole.OBJECT, "a_003": IngredientRole.ATMOSPHERE}
    ingredient_roles: dict[str, IngredientRole] = field(default_factory=dict)


@dataclass
class Twist:
    """
    A mandatory story twist injected at a specific panel.
    The CD generates 1–2 twists per round (GDD Section 6.2: twists field).
    """
    # The panel index (0-based) at which this twist is revealed.
    panel_index: int

    # Short description of the twist content (used in LLM prompt).
    description_ro: str

    # Whether this twist is the final/main reveal or a mid-story complication.
    is_final_twist: bool = False


@dataclass
class CameraRule:
    """
    A per-panel camera/composition instruction.
    Translates into ComfyUI prompt tokens by the Style Token Injector (M5.4).
    GDD Section 6.2: cameraLanguage field.
    """
    # 0-based panel index this rule applies to.
    panel_index: int

    # Human-readable description of the shot, e.g. "wide establishing shot, low angle"
    description: str

    # ComfyUI-ready English token string derived from description.
    # e.g. "wide shot, low angle, establishing, cinematic"
    prompt_tokens: str


@dataclass
class NarratorPersona:
    """
    The narrator's voice and personality specification.
    Maps to ElevenLabs voice parameters or Piper model (GDD Section 6.2,
    GDD Section 6.3 per-genre narrator definitions, M6.4).
    """
    # Maps to an ElevenLabs voice ID string or a Piper model filename.
    voice_key: str

    # Short prose description of the narrator's personality (for LLM prompt).
    # e.g. "Breathless, rhetorical questions, speaks directly to viewer"
    personality_description_ro: str

    # ElevenLabs stability parameter (0.0–1.0).
    stability: float = 0.5

    # ElevenLabs similarity_boost parameter (0.0–1.0).
    similarity_boost: float = 0.75

    # ElevenLabs style exaggeration parameter (0.0–1.0).
    style_exaggeration: float = 0.5

    # Speaking rate multiplier (1.0 = normal, >1.0 = faster).
    speaking_rate: float = 1.0


@dataclass
class SFXNote:
    """
    A per-panel sound effect instruction for the Tauri presenter.
    GDD Section 6.2: soundEffects field.
    """
    # 0-based panel index this sound effect accompanies.
    panel_index: int

    # Description of the sound effect, e.g. "dramatic violin sting"
    description: str

    # Timing relative to panel reveal: "on_reveal" | "during" | "on_exit"
    timing: str = "on_reveal"


@dataclass
class LayoutStrategy:
    """
    How panels are arranged in the presentation format.
    Used by the Tauri presenter to choose the correct CSS grid layout.
    GDD Section 6.2: panelLayout field.
    """
    # Total number of panels in this round (GDD: 4 | 5 | 6 | 8).
    panel_count: int

    # CSS grid template string for the presenter, e.g. "2x2", "3x2", "2x4"
    grid_template: str

    # Which panel index (0-based) is displayed at full width / featured size.
    # None if no panel is featured.
    featured_panel_index: int | None = None

    # Whether the layout is vertical (phone-native) or horizontal (TV).
    orientation: str = "horizontal"


# ── Root Brief ────────────────────────────────────────────────────────────────

@dataclass
class CreativeBrief:
    """
    The complete creative specification produced by the Creative Director
    before any story, image, or audio is generated.

    Every downstream AI component receives this object and uses it to
    shape its output. This is the single source of truth for one round's
    creative direction (GDD Section 6.1, 6.2).

    Serialises to/from JSON via to_dict() / from_dict() for:
      - brief.json written to output/round_XXX/ by the pipeline
      - round record in SQLite (genre + format persisted per GDD Section 8.3)
    """

    # ── Narrative ─────────────────────────────────────────────────────────

    # Genre name (Romanian), e.g. "Telenovelă Românească"
    genre: str

    # Genre machine key for registry lookups, e.g. "telenovela_romaneasca"
    genre_key: str

    # Subgenre label, e.g. "Răzbunarea neașteptată"
    subgenre: str

    # Ordered act/beat structure for the round.
    story_structure: StoryArc

    # One archetype per player, populated by M3.5.
    archetypes: list[Archetype]

    # 1–2 mandatory twists injected at specific panels.
    twists: list[Twist]

    # Comedy level 1–10; 1 = dry/dark, 10 = pure slapstick.
    comedy_level: int

    # Short tone-defining keywords fed directly into the LLM system prompt.
    # e.g. ["melodramatic", "breathless", "ironic"]
    tone_keywords: list[str]

    # ── Presentation ──────────────────────────────────────────────────────

    # Visual presentation format (independent of genre).
    format: PresentationFormat

    # Number of panels: 4, 5, 6, or 8.
    panel_count: int

    # Panel arrangement strategy for the presenter.
    panel_layout: LayoutStrategy

    # ── Visual ────────────────────────────────────────────────────────────

    # Prose description of the visual style fed to ComfyUI.
    # e.g. "Warm oversaturated colours, extreme close-ups on faces"
    visual_style: str

    # Dominant hex colours for panel generation.
    # e.g. ["#D4AF37", "#8B1A1A", "#CD8500"]
    colour_palette: list[str]

    # Per-panel camera and composition rules.
    camera_language: list[CameraRule]

    # Lighting mood description fed to ComfyUI.
    # e.g. "warm, harsh top light, dramatic shadows"
    lighting_mood: str

    # ── Audio ─────────────────────────────────────────────────────────────

    # Narrator personality and TTS voice mapping.
    narrator_personality: NarratorPersona

    # Direct key into ElevenLabs voice ID map or Piper model filename.
    # Redundant with narrator_personality.voice_key but kept for explicit
    # top-level access by TTS pipeline (GDD Section 6.2).
    narrator_voice_key: str

    # Music direction description for the presenter.
    # e.g. "Dramatic violin, sudden silence before twist"
    music_direction: str

    # Per-panel sound effect notes.
    sound_effects: list[SFXNote]

    # ── Pacing ────────────────────────────────────────────────────────────

    # Controls cinematic reveal rhythm in the Tauri presenter.
    reveal_pacing: RevealPacing

    # 0-based index of the panel that delivers the main punchline.
    punchline_panel: int

    # ── Metadata ──────────────────────────────────────────────────────────

    # Round ID from SQLite (set when persisting brief.json to disk).
    round_id: int | None = None

    # ISO 8601 timestamp of brief generation.
    generated_at: str | None = None

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a JSON-serialisable dict.
        Enum values are serialised as their .value strings.
        """
        raw = asdict(self)
        # Walk the dict and convert Enum instances to their .value
        return _normalise_enums(raw)

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a formatted JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CreativeBrief":
        """
        Reconstruct a CreativeBrief from a plain dict (e.g. from brief.json).
        Raises ValueError with a descriptive message if required fields are missing.
        """
        _require_fields(data, [
            "genre", "genre_key", "subgenre", "story_structure", "archetypes",
            "twists", "comedy_level", "tone_keywords", "format", "panel_count",
            "panel_layout", "visual_style", "colour_palette", "camera_language",
            "lighting_mood", "narrator_personality", "narrator_voice_key",
            "music_direction", "sound_effects", "reveal_pacing", "punchline_panel",
        ])

        story_structure = _parse_story_arc(data["story_structure"])
        archetypes = [_parse_archetype(a) for a in data["archetypes"]]
        twists = [_parse_twist(t) for t in data["twists"]]
        panel_layout = _parse_layout_strategy(data["panel_layout"])
        camera_language = [_parse_camera_rule(c) for c in data["camera_language"]]
        narrator_personality = _parse_narrator_persona(data["narrator_personality"])
        sound_effects = [_parse_sfx_note(s) for s in data["sound_effects"]]

        return cls(
            genre=data["genre"],
            genre_key=data["genre_key"],
            subgenre=data["subgenre"],
            story_structure=story_structure,
            archetypes=archetypes,
            twists=twists,
            comedy_level=int(data["comedy_level"]),
            tone_keywords=list(data["tone_keywords"]),
            format=PresentationFormat(data["format"]),
            panel_count=int(data["panel_count"]),
            panel_layout=panel_layout,
            visual_style=data["visual_style"],
            colour_palette=list(data["colour_palette"]),
            camera_language=camera_language,
            lighting_mood=data["lighting_mood"],
            narrator_personality=narrator_personality,
            narrator_voice_key=data["narrator_voice_key"],
            music_direction=data["music_direction"],
            sound_effects=sound_effects,
            reveal_pacing=RevealPacing(data["reveal_pacing"]),
            punchline_panel=int(data["punchline_panel"]),
            round_id=data.get("round_id"),
            generated_at=data.get("generated_at"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "CreativeBrief":
        """Reconstruct from a JSON string (e.g. contents of brief.json)."""
        return cls.from_dict(json.loads(json_str))


# ── Parse helpers ─────────────────────────────────────────────────────────────

def _require_fields(data: dict[str, Any], fields: list[str]) -> None:
    missing = [f for f in fields if f not in data]
    if missing:
        raise ValueError(
            f"CreativeBrief.from_dict: missing required fields: {missing}"
        )


def _parse_story_arc(d: dict[str, Any]) -> StoryArc:
    return StoryArc(
        beats=list(d["beats"]),
        act_descriptions=list(d["act_descriptions"]),
        climax_beat_index=int(d["climax_beat_index"]),
    )


def _parse_archetype(d: dict[str, Any]) -> Archetype:
    roles_raw: dict[str, str] = d.get("ingredient_roles") or {}
    ingredient_roles = {
        prompt_id: IngredientRole(role_val)
        for prompt_id, role_val in roles_raw.items()
    }
    return Archetype(
        key=d["key"],
        name_ro=d["name_ro"],
        description_ro=d["description_ro"],
        player_id=d.get("player_id"),
        player_nickname=d.get("player_nickname"),
        ingredient_roles=ingredient_roles,
    )


def _parse_twist(d: dict[str, Any]) -> Twist:
    return Twist(
        panel_index=int(d["panel_index"]),
        description_ro=d["description_ro"],
        is_final_twist=bool(d.get("is_final_twist", False)),
    )


def _parse_camera_rule(d: dict[str, Any]) -> CameraRule:
    return CameraRule(
        panel_index=int(d["panel_index"]),
        description=d["description"],
        prompt_tokens=d["prompt_tokens"],
    )


def _parse_narrator_persona(d: dict[str, Any]) -> NarratorPersona:
    return NarratorPersona(
        voice_key=d["voice_key"],
        personality_description_ro=d["personality_description_ro"],
        stability=float(d.get("stability", 0.5)),
        similarity_boost=float(d.get("similarity_boost", 0.75)),
        style_exaggeration=float(d.get("style_exaggeration", 0.5)),
        speaking_rate=float(d.get("speaking_rate", 1.0)),
    )


def _parse_sfx_note(d: dict[str, Any]) -> SFXNote:
    return SFXNote(
        panel_index=int(d["panel_index"]),
        description=d["description"],
        timing=d.get("timing", "on_reveal"),
    )


def _parse_layout_strategy(d: dict[str, Any]) -> LayoutStrategy:
    return LayoutStrategy(
        panel_count=int(d["panel_count"]),
        grid_template=d["grid_template"],
        featured_panel_index=d.get("featured_panel_index"),
        orientation=d.get("orientation", "horizontal"),
    )


def _normalise_enums(obj: Any) -> Any:
    """Recursively convert Enum instances to their .value in a nested structure."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _normalise_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalise_enums(i) for i in obj]
    return obj