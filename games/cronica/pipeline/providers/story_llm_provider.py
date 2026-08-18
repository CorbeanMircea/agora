"""
M4.2 — StoryLLMProvider Interface

Abstract base class that all LLM story generation implementations must satisfy.
No Ollama-specific code lives here — only the contract.

Sources:
    GDD v0.2.1 Section 6.5 (Story Generation)
    ADR-001 (Ingredient System — ingredients arrive with assigned roles)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class PanelDescription:
    """
    The complete description of one comic panel as produced by the LLM.

    Every field is populated by the LLM; none are optional in a valid Story.
    The presenter and image pipeline consume these fields directly.
    """

    # 0-based index matching the brief's panel sequence.
    panel_index: int

    # Scene description in Romanian (shown to host in debug mode).
    description_ro: str

    # Dialogue or caption text in Romanian, rendered as speech bubbles / captions.
    # Empty string if this panel has no dialogue.
    dialogue_ro: str

    # Image generation prompt in English — fed directly to ComfyUI.
    # Must be entirely in English; character names replaced with visual descriptions.
    image_prompt_en: str

    # The narrator's voice-over line for this panel, in Romanian.
    # Synthesised to narration_N.wav by the TTS pipeline.
    narrator_line_ro: str

    # Archetype keys of characters appearing in this panel (references
    # Archetype.key values from the CreativeBrief). May be empty.
    characters_in_panel: list[str] = field(default_factory=list)


@dataclass
class Story:
    """
    The complete structured story produced by the LLM for one round.

    Written to story.json in the round output directory.
    Consumed by the image pipeline (image_prompt_en per panel) and
    the TTS pipeline (narrator_line_ro per panel).

    All narrative text is in Romanian; all image prompts are in English.
    """

    # Story title in Romanian, shown on the presenter title card.
    title: str

    # Ordered list of panel descriptions — length must equal brief.panel_count.
    panels: list[PanelDescription]

    # One narrator line per panel in order (mirrors panels[i].narrator_line_ro
    # for convenient sequential access by the TTS pipeline).
    narrator_script: list[str]

    # One image prompt per panel in order (mirrors panels[i].image_prompt_en
    # for convenient sequential access by the image pipeline).
    image_prompts: list[str]

    # ── Validation helpers ────────────────────────────────────────────────

    def validate(
        self,
        expected_panel_count: int,
        expected_player_names: list[str] | None = None,
    ) -> list[str]:
        """
        Return a list of validation error strings.
        An empty list means the story is structurally valid.

        Checks:
          - panels count matches expected_panel_count
          - narrator_script length matches panel count
          - image_prompts length matches panel count
          - title is non-empty
          - each panel has non-empty description_ro, image_prompt_en, narrator_line_ro
          - image_prompt_en values contain only ASCII characters (English heuristic)
          - narrator_script and image_prompts are consistent with panel data
          - all expected player names appear somewhere in the story (if provided)
        """
        errors: list[str] = []

        if not self.title.strip():
            errors.append("title must not be empty")

        if len(self.panels) != expected_panel_count:
            errors.append(
                f"panels length {len(self.panels)} != expected {expected_panel_count}"
            )

        if len(self.narrator_script) != expected_panel_count:
            errors.append(
                f"narrator_script length {len(self.narrator_script)} "
                f"!= expected {expected_panel_count}"
            )

        if len(self.image_prompts) != expected_panel_count:
            errors.append(
                f"image_prompts length {len(self.image_prompts)} "
                f"!= expected {expected_panel_count}"
            )

        for i, panel in enumerate(self.panels):
            if panel.panel_index != i:
                errors.append(
                    f"panels[{i}].panel_index is {panel.panel_index}, expected {i}"
                )
            if not panel.description_ro.strip():
                errors.append(f"panels[{i}].description_ro must not be empty")
            if not panel.image_prompt_en.strip():
                errors.append(f"panels[{i}].image_prompt_en must not be empty")
            if not panel.narrator_line_ro.strip():
                errors.append(f"panels[{i}].narrator_line_ro must not be empty")
            # English heuristic: image prompts must be ASCII-only
            if panel.image_prompt_en.strip() and not _is_ascii(panel.image_prompt_en):
                errors.append(
                    f"panels[{i}].image_prompt_en contains non-ASCII characters — "
                    f"image prompts must be in English"
                )

        # Consistency between convenience lists and panel data
        for i, (script_line, panel) in enumerate(
            zip(self.narrator_script, self.panels)
        ):
            if script_line != panel.narrator_line_ro:
                errors.append(
                    f"narrator_script[{i}] does not match panels[{i}].narrator_line_ro"
                )

        for i, (img_prompt, panel) in enumerate(
            zip(self.image_prompts, self.panels)
        ):
            if img_prompt != panel.image_prompt_en:
                errors.append(
                    f"image_prompts[{i}] does not match panels[{i}].image_prompt_en"
                )

        # Player name presence check
        if expected_player_names:
            story_text = _full_story_text(self)
            for name in expected_player_names:
                if name and name.strip() not in story_text:
                    errors.append(
                        f"player name '{name}' does not appear anywhere in the story"
                    )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for story.json output."""
        return {
            "title": self.title,
            "panels": [
                {
                    "panel_index": p.panel_index,
                    "description_ro": p.description_ro,
                    "dialogue_ro": p.dialogue_ro,
                    "image_prompt_en": p.image_prompt_en,
                    "narrator_line_ro": p.narrator_line_ro,
                    "characters_in_panel": p.characters_in_panel,
                }
                for p in self.panels
            ],
            "narrator_script": self.narrator_script,
            "image_prompts": self.image_prompts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Story":
        """
        Reconstruct a Story from a plain dict (e.g. from story.json).
        Raises ValueError with a descriptive message if required fields are missing.
        """
        required = ["title", "panels", "narrator_script", "image_prompts"]
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Story.from_dict: missing required fields: {missing}")

        panels = [
            PanelDescription(
                panel_index=int(p["panel_index"]),
                description_ro=p["description_ro"],
                dialogue_ro=p.get("dialogue_ro", ""),
                image_prompt_en=p["image_prompt_en"],
                narrator_line_ro=p["narrator_line_ro"],
                characters_in_panel=list(p.get("characters_in_panel", [])),
            )
            for p in data["panels"]
        ]

        return cls(
            title=data["title"],
            panels=panels,
            narrator_script=list(data["narrator_script"]),
            image_prompts=list(data["image_prompts"]),
        )

    def sanitize_image_prompts(self) -> "Story":
        """
        Return a new Story with non-ASCII characters stripped from all
        image_prompt_en fields. Called before validate() when the LLM
        produces Romanian diacritics in image prompts despite instructions.

        Replaces diacritics with their ASCII approximations where possible,
        otherwise drops the character.
        """
        import unicodedata

        def _to_ascii(text: str) -> str:
            # Normalize to decomposed form, then encode to ASCII dropping combining chars
            normalized = unicodedata.normalize("NFKD", text)
            return normalized.encode("ascii", errors="ignore").decode("ascii")

        new_panels = []
        for panel in self.panels:
            new_panels.append(PanelDescription(
                panel_index=panel.panel_index,
                description_ro=panel.description_ro,
                dialogue_ro=panel.dialogue_ro,
                image_prompt_en=_to_ascii(panel.image_prompt_en),
                narrator_line_ro=panel.narrator_line_ro,
                characters_in_panel=list(panel.characters_in_panel),
            ))

        return Story(
            title=self.title,
            panels=new_panels,
            narrator_script=list(self.narrator_script),
            image_prompts=[_to_ascii(p) for p in self.image_prompts],
        )

    @classmethod
    def generate_fallback(
        cls,
        panel_count: int,
        player_names: list[str],
        genre_name: str = "Poveste",
    ) -> "Story":
        """
        Generate a minimal valid fallback story when the LLM fails after all
        retry attempts. This ensures the pipeline never crashes a round due to
        story generation failure.

        The fallback story is structurally valid (passes validate()) but is
        intentionally generic. Player names are embedded so the recognition
        moment still occurs.

        Parameters
        ----------
        panel_count:
            Number of panels required (must be 4–8).
        player_names:
            Display names of all active players, used to populate the story text.
        genre_name:
            Genre display name in Romanian, used in the title.
        """
        panel_count = max(4, min(8, panel_count))
        names_str = " și ".join(player_names) if player_names else "Personajele noastre"

        # Beat descriptions for each panel position
        beat_templates = [
            f"{names_str} se află într-o situație neobișnuită care nu putea fi anticipată de nimeni.",
            f"Lucrurile se complică brusc pentru {names_str}, care nu știu ce să facă.",
            f"O descoperire neașteptată schimbă totul pentru {names_str} și cei din jur.",
            f"Momentul decisiv a sosit. {names_str} trebuie să aleagă.",
            f"Consecințele deciziei sunt surprinzătoare pentru toată lumea.",
            f"Epilogul revelează că nimic nu a fost ce părea.",
            f"O ultimă răsturnare de situație îi lasă pe {names_str} fără cuvinte.",
            f"Finalul — nimeni nu l-ar fi prezis, dar toți îl meritau.",
        ]

        narrator_templates = [
            f"Și astfel a început povestea lui {names_str}.",
            f"Nimeni nu se așteptase la ce urma să se întâmple.",
            f"Dar surpriza abia acum se arăta.",
            f"Momentul adevărului a sosit în sfârșit.",
            f"Consecințele nu au întârziat să apară.",
            f"Și totuși, era doar începutul.",
            f"O nouă răsturnare în această poveste fără sfârșit.",
            f"Cortina a căzut. Pentru moment.",
        ]

        image_prompt_templates = [
            "wide establishing shot, dramatic lighting, cinematic composition",
            "medium shot, two characters, surprised expressions, dynamic framing",
            "close-up reveal shot, high contrast, dramatic shadow",
            "decisive moment, action pose, cinematic, strong composition",
            "aftermath scene, wide angle, scattered props, expressive faces",
            "epilogue tableau, warm light, reflective mood, soft focus",
            "final twist reveal, shocked expression, extreme close-up",
            "closing wide shot, all characters, symbolic ending, cinematic",
        ]

        panels = []
        for i in range(panel_count):
            desc = beat_templates[i % len(beat_templates)]
            narr = narrator_templates[i % len(narrator_templates)]
            img = image_prompt_templates[i % len(image_prompt_templates)]
            panels.append(PanelDescription(
                panel_index=i,
                description_ro=desc,
                dialogue_ro="",
                image_prompt_en=img,
                narrator_line_ro=narr,
            ))

        return cls(
            title=f"O poveste despre {names_str}",
            panels=panels,
            narrator_script=[p.narrator_line_ro for p in panels],
            image_prompts=[p.image_prompt_en for p in panels],
        )


# ── Module-level validation helpers ──────────────────────────────────────────

def _is_ascii(text: str) -> bool:
    """Return True if the string contains only ASCII characters."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _full_story_text(story: Story) -> str:
    """
    Concatenate all narrative text fields from a story into one searchable string.
    Used by the player-name presence check in Story.validate().
    """
    parts: list[str] = [story.title]
    for panel in story.panels:
        parts.append(panel.description_ro)
        parts.append(panel.dialogue_ro)
        parts.append(panel.narrator_line_ro)
    return " ".join(parts)


# ── Input dataclasses ─────────────────────────────────────────────────────────

@dataclass
class PlayerAnswerItem:
    """
    One player's single ingredient answer (prompt + response).
    """
    prompt_id: str
    category: str
    ingredient_role: str
    answer_text: str


@dataclass
class PlayerAnswers:
    """
    All ingredient answers for one player in a round, with archetype context.
    """
    player_id: str
    nickname: str
    archetype_key: str
    archetype_name_ro: str
    answers: list[PlayerAnswerItem] = field(default_factory=list)


# ── Abstract provider ─────────────────────────────────────────────────────────

class StoryLLMProvider(ABC):
    """
    Abstract base class for LLM story generation implementations.
    """

    @abstractmethod
    def generate_story(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
    ) -> Story:
        """
        Generate a structured story from a CreativeBrief and player answers.
        """
        ...

    def generate_story_with_retry(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
        max_attempts: int = 2,
    ) -> Story:
        """
        Call generate_story up to max_attempts times, retrying on validation
        failure or exception.

        On the second attempt, validation errors from the first attempt are
        available to implementations via the `_last_validation_errors` attribute
        so they can be injected into the retry prompt.

        Returns the first valid Story, or raises the last exception if all
        attempts fail.
        """
        last_exc: Exception | None = None
        last_errors: list[str] = []

        for attempt in range(1, max_attempts + 1):
            self._last_validation_errors: list[str] = last_errors
            self._attempt_number: int = attempt
            try:
                story = self.generate_story(brief, player_answers)
                panel_count = getattr(brief, "panel_count", len(story.panels))
                # Sanitize ASCII before validation — LLM sometimes outputs diacritics
                # in image_prompt_en despite instructions
                story = story.sanitize_image_prompts()
                errors = story.validate(panel_count)
                if not errors:
                    return story
                last_errors = errors
                last_exc = ValueError(
                    f"Story validation failed (attempt {attempt}): {errors}"
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                last_errors = [str(exc)]

        assert last_exc is not None
        raise last_exc