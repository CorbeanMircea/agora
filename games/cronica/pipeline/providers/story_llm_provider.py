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
            # (Romanian diacritics indicate the prompt was accidentally written in Romanian)
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


# ── Module-level validation helpers ──────────────────────────────────────────
# These must live at module level so Story.validate() can reference them.

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

    The category and assigned role come from the CreativeBrief archetypes;
    they are passed here so the LLM receives the full context without having
    to re-parse the brief.
    """

    # Prompt ID from the ingredient pack (e.g. "c_001").
    prompt_id: str

    # Semantic category of the ingredient question (e.g. "CONCRET").
    category: str

    # The role assigned by the Creative Director (e.g. "OBJECT").
    # This is the key insight that drives organic ingredient integration.
    ingredient_role: str

    # The player's raw answer text (may be empty if they did not submit).
    answer_text: str


@dataclass
class PlayerAnswers:
    """
    All ingredient answers for one player in a round, with archetype context.

    Passed to the LLM alongside the CreativeBrief so the story generator
    knows which player maps to which archetype and what ingredients they provided.
    """

    # Player UUID from SQLite.
    player_id: str

    # Display name shown in the story.
    nickname: str

    # Archetype key from the CreativeBrief (e.g. "victima").
    archetype_key: str

    # Archetype display name in Romanian (e.g. "Victima").
    archetype_name_ro: str

    # All ingredient answers for this player.
    answers: list[PlayerAnswerItem] = field(default_factory=list)


# ── Abstract provider ─────────────────────────────────────────────────────────

class StoryLLMProvider(ABC):
    """
    Abstract base class for LLM story generation implementations.

    Concrete implementations (e.g. OllamaStoryLLM in M4.4) must subclass
    this and implement `generate_story`. All Ollama-specific, OpenAI-specific,
    or other LLM-specific code lives in the concrete implementation only.

    Usage
    -----
    ::
        class OllamaStoryLLM(StoryLLMProvider):
            def generate_story(self, brief, player_answers):
                ...

        llm = OllamaStoryLLM()
        story = llm.generate_story(brief, answers)
    """

    @abstractmethod
    def generate_story(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
    ) -> Story:
        """
        Generate a structured story from a CreativeBrief and player answers.

        Parameters
        ----------
        brief:
            A fully populated CreativeBrief instance (typed as Any here to
            avoid a circular import; callers pass a CreativeBrief from
            creative_director.models). The implementation may type-narrow
            to CreativeBrief internally.
        player_answers:
            One PlayerAnswers entry per active player. Players who did not
            submit have answers with empty answer_text fields.

        Returns
        -------
        Story
            A fully populated Story. Callers should call story.validate()
            to verify structural correctness before downstream use.

        Raises
        ------
        Exception
            Implementations may raise any exception on generation failure.
            The orchestrator catches all exceptions and reports them as
            pipeline failures.
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