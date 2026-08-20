"""
M3.6 — Creative Brief Generator

The CreativeDirector class combines genre selection, format selection,
archetype assignment, and all supporting data into a complete, validated
CreativeBrief ready for downstream AI components.

Entry point:
    CreativeDirector.generate(player_answers, round_history, seed=None)

Output:
    A fully populated CreativeBrief instance.
    Optionally written to brief.json in the output directory.

Sources:
    GDD v0.2.1 Section 6.1, 6.2, 6.3, 6.4
    ADR-001 (Ingredient System)
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

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
from .genre_registry import GenreDefinition, get_genre, list_genres
from .format_registry import (
    FormatDefinition,
    get_compatible_formats,
    get_layout_for_panel_count,
)
from .genre_selection import select_genre
from .archetype_assignment import (
    assign as assign_archetypes,
    validate_assignments,
    PlayerIngredient,
    AssignedArchetype,
)


# ── Input dataclasses ─────────────────────────────────────────────────────────

class PlayerAnswer:
    """
    One player's submitted ingredient answers for a round.
    """
    def __init__(
        self,
        player_id: str,
        nickname: str,
        answers: list[dict[str, str]],
    ) -> None:
        """
        Parameters
        ----------
        player_id:
            The player's UUID from SQLite.
        nickname:
            The player's display name.
        answers:
            List of dicts with keys "prompt_id", "category", "answer_text".
            Players who didn't submit will have empty answer_text.
        """
        self.player_id = player_id
        self.nickname = nickname
        self.answers = answers


# ── Validation error ──────────────────────────────────────────────────────────

class CreativeBriefValidationError(ValueError):
    """Raised when the generated brief fails validation."""
    pass


# ── CreativeDirector ──────────────────────────────────────────────────────────

class CreativeDirector:
    """
    Produces a fully populated CreativeBrief from player answers and session
    history.

    Usage
    -----
    ::
        cd = CreativeDirector()
        brief = cd.generate(
            player_answers=[...],
            round_history=["telenovela_romaneasca", "film_actiune_b"],
            round_id=3,
            seed=42,
        )
    """

    def generate(
        self,
        player_answers: list[PlayerAnswer],
        round_history: Sequence[str],
        round_id: int | None = None,
        seed: int | None = None,
        output_dir: str | None = None,
    ) -> CreativeBrief:
        """
        Generate a complete CreativeBrief.

        Parameters
        ----------
        player_answers:
            One entry per active player. Order is preserved for archetype
            assignment determinism.
        round_history:
            Ordered list of genre keys from most-recent to oldest.
            Used to avoid repeating genres.
        round_id:
            Optional SQLite round ID attached to the brief for tracing.
        seed:
            Optional integer seed for reproducibility.
        output_dir:
            If provided, brief.json is written here.

        Returns
        -------
        CreativeBrief
            Fully populated and validated.

        Raises
        ------
        ValueError
            If player_answers has fewer than 2 entries.
        CreativeBriefValidationError
            If the generated brief fails structural validation.
        """
        if len(player_answers) < 2:
            raise ValueError(
                "CreativeDirector.generate() requires at least 2 player answers, "
                f"got {len(player_answers)}"
            )

        rng = random.Random(seed)

        # ── 1. Genre selection ────────────────────────────────────────────
        genre = select_genre(round_history, seed=seed)

        # ── 2. Format selection ───────────────────────────────────────────
        fmt_def = self._select_format(genre, rng)

        # ── 3. Panel count ────────────────────────────────────────────────
        panel_count = self._select_panel_count(genre, fmt_def, rng)

        # ── 4. Comedy level ───────────────────────────────────────────────
        lo, hi = genre.comedy_level_range
        comedy_level = rng.randint(lo, hi)

        # ── 5. Build player list and ingredient map ───────────────────────
        players = [
            {"id": pa.player_id, "nickname": pa.nickname}
            for pa in player_answers
        ]
        ingredient_map = self._build_ingredient_map(player_answers)

        # ── 6. Archetype assignment (ADR-001) ─────────────────────────────
        assigned = assign_archetypes(
            genre=genre,
            players=players,
            player_ingredients=ingredient_map,
            seed=seed,
        )
        errors = validate_assignments(assigned, [p["id"] for p in players])
        if errors:
            raise CreativeBriefValidationError(
                f"Archetype assignment validation failed: {errors}"
            )
        archetypes = [a.archetype for a in assigned]

        # ── 7. Story structure (Change F: dynamic causality chain) ────────
        story_structure = self._build_story_structure(
            genre, panel_count, rng, player_answers
        )

        # ── 8. Twists (1–2 per round) ─────────────────────────────────────
        twists = self._generate_twists(panel_count, rng)

        # ── 9. Layout strategy ────────────────────────────────────────────
        panel_layout = get_layout_for_panel_count(fmt_def.format, panel_count)

        # ── 10. Camera language (trim/pad to panel_count) ─────────────────
        camera_language = self._build_camera_language(
            genre, panel_count, rng
        )

        # ── 11. Sound effects ─────────────────────────────────────────────
        sound_effects = self._build_sound_effects(genre, panel_count)

        # ── 12. Punchline panel ───────────────────────────────────────────
        punchline_panel = story_structure.climax_beat_index

        # ── 13. Assemble CreativeBrief ────────────────────────────────────
        brief = CreativeBrief(
            genre=genre.name_ro,
            genre_key=genre.key,
            subgenre=self._pick_subgenre(genre, rng),
            story_structure=story_structure,
            archetypes=archetypes,
            twists=twists,
            comedy_level=comedy_level,
            tone_keywords=list(genre.tone_keywords),
            format=fmt_def.format,
            panel_count=panel_count,
            panel_layout=panel_layout,
            visual_style=genre.visual_style,
            colour_palette=list(genre.colour_palette),
            camera_language=camera_language,
            lighting_mood=genre.lighting_mood,
            narrator_personality=genre.narrator_personality,
            narrator_voice_key=genre.narrator_personality.voice_key,
            music_direction=genre.music_direction_ro,
            sound_effects=sound_effects,
            reveal_pacing=genre.reveal_pacing,
            punchline_panel=punchline_panel,
            round_id=round_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # ── 14. Validate ──────────────────────────────────────────────────
        self._validate_brief(brief, player_answers)

        # ── 15. Persist to disk ───────────────────────────────────────────
        if output_dir is not None:
            self._write_brief_json(brief, output_dir)

        return brief

    # ── Private helpers ───────────────────────────────────────────────────────

    def _select_format(
        self,
        genre: GenreDefinition,
        rng: random.Random,
    ) -> FormatDefinition:
        """
        Select a presentation format compatible with the genre.

        Uses the genre's preferred_formats list first (ordered by preference).
        Falls back to any compatible format if preferred ones are unavailable.
        """
        compatible = get_compatible_formats(genre.key)
        compatible_map = {f.format: f for f in compatible}

        # Preferred formats in order, filtered to compatible ones
        for preferred in genre.preferred_formats:
            if preferred in compatible_map:
                return compatible_map[preferred]

        # Fallback: random compatible format
        if compatible:
            return rng.choice(compatible)

        # Should never happen (western_comic is compatible with everything)
        raise CreativeBriefValidationError(
            f"No compatible formats found for genre '{genre.key}'"
        )

    def _select_panel_count(
        self,
        genre: GenreDefinition,
        fmt_def: FormatDefinition,
        rng: random.Random,
    ) -> int:
        """
        Select a panel count from the intersection of genre and format
        supported counts, favouring the genre's preference order.
        """
        format_counts = set(fmt_def.supported_panel_counts)
        candidates = [c for c in genre.panel_counts if c in format_counts]

        if not candidates:
            candidates = genre.panel_counts or fmt_def.supported_panel_counts

        if len(candidates) == 1:
            return candidates[0]

        # 70% chance of picking the first (preferred) count, 30% any other
        if rng.random() < 0.7:
            return candidates[0]
        return rng.choice(candidates)

    def _build_ingredient_map(
        self,
        player_answers: list[PlayerAnswer],
    ) -> dict[str, list[PlayerIngredient]]:
        """Convert PlayerAnswer list to the format expected by assign_archetypes."""
        result: dict[str, list[PlayerIngredient]] = {}
        for pa in player_answers:
            ingredients = [
                PlayerIngredient(
                    prompt_id=a["prompt_id"],
                    category=a["category"],
                    answer_text=a.get("answer_text", ""),
                )
                for a in pa.answers
            ]
            result[pa.player_id] = ingredients
        return result

    def _build_story_structure(
        self,
        genre: GenreDefinition,
        panel_count: int,
        rng: random.Random,
        player_answers: list[PlayerAnswer] | None = None,
    ) -> StoryArc:
        """
        Change F: Build a StoryArc with a dynamic causality chain derived
        from actual player ingredients.

        The causality beats are constructed from the real ingredient answers
        so the story structure is always tailored to what players submitted.
        No hardcoded Romanian words or fixed panel assumptions.

        Falls back to genre template beats if player_answers is not provided.
        """
        # Collect all ingredient answer texts from all players
        all_ingredient_answers: list[str] = []
        if player_answers:
            for pa in player_answers:
                for ans in pa.answers:
                    text = ans.get("answer_text", "").strip()
                    if text:
                        all_ingredient_answers.append(text)

        if all_ingredient_answers:
            # Build causality beats from actual player ingredients
            causality_beats = [
                _build_causality_beat(i, panel_count, all_ingredient_answers)
                for i in range(panel_count)
            ]
            beats = [b["label"] for b in causality_beats]
            act_descriptions = [b["instruction"] for b in causality_beats]
        else:
            # Fallback: use genre template
            template = genre.story_structure
            beats = list(template.beats)
            act_descriptions = list(template.act_descriptions)
            causality_beats = [
                {"label": b, "instruction": d}
                for b, d in zip(beats, act_descriptions)
            ]

        # Trim or pad beats to match panel_count
        while len(beats) > panel_count:
            beats.pop()
            act_descriptions.pop()
            causality_beats.pop()
        while len(beats) < panel_count:
            i = len(beats)
            extra = _build_causality_beat(i, panel_count, all_ingredient_answers)
            beats.append(extra["label"])
            act_descriptions.append(extra["instruction"])
            causality_beats.append(extra)

        # Clamp climax index
        template = genre.story_structure
        climax = min(
            getattr(template, "climax_beat_index", panel_count - 2),
            len(beats) - 1,
        )

        return StoryArc(
            beats=beats,
            act_descriptions=act_descriptions,
            climax_beat_index=climax,
            causality_beats=causality_beats,
        )

    def _generate_twists(
        self,
        panel_count: int,
        rng: random.Random,
    ) -> list[Twist]:
        """
        Generate 1–2 twists at appropriate panel indices.
        """
        twists: list[Twist] = []

        main_twist_panel = max(0, panel_count - 2)
        twists.append(Twist(
            panel_index=main_twist_panel,
            description_ro="Răsturnarea principală de situație.",
            is_final_twist=True,
        ))

        if panel_count >= 6:
            mid_panel = panel_count // 2
            twists.append(Twist(
                panel_index=mid_panel,
                description_ro="Complicație neașteptată la mijlocul poveștii.",
                is_final_twist=False,
            ))

        return twists

    def _build_camera_language(
        self,
        genre: GenreDefinition,
        panel_count: int,
        rng: random.Random,
    ) -> list[CameraRule]:
        """
        Build camera rules for exactly panel_count panels.
        """
        templates = list(genre.camera_language_templates)

        if not templates:
            return [
                CameraRule(
                    panel_index=i,
                    description=f"Panel {i + 1} shot",
                    prompt_tokens=f"cinematic, panel {i + 1}",
                )
                for i in range(panel_count)
            ]

        result: list[CameraRule] = []
        for i in range(panel_count):
            template = templates[i % len(templates)]
            result.append(CameraRule(
                panel_index=i,
                description=template.description,
                prompt_tokens=template.prompt_tokens,
            ))

        return result

    def _build_sound_effects(
        self,
        genre: GenreDefinition,
        panel_count: int,
    ) -> list[SFXNote]:
        """
        Build sound effects clamped to valid panel indices for panel_count.
        """
        result: list[SFXNote] = []
        for sfx in genre.sfx_templates:
            if sfx.panel_index < panel_count:
                result.append(SFXNote(
                    panel_index=sfx.panel_index,
                    description=sfx.description,
                    timing=sfx.timing,
                ))
        return result

    def _pick_subgenre(
        self,
        genre: GenreDefinition,
        rng: random.Random,
    ) -> str:
        return genre.tagline_ro

    def _validate_brief(
        self,
        brief: CreativeBrief,
        player_answers: list[PlayerAnswer],
    ) -> None:
        """
        Validate that the generated brief satisfies structural requirements.
        """
        errors: list[str] = []

        required_str_fields = [
            ("genre", brief.genre),
            ("genre_key", brief.genre_key),
            ("subgenre", brief.subgenre),
            ("visual_style", brief.visual_style),
            ("lighting_mood", brief.lighting_mood),
            ("narrator_voice_key", brief.narrator_voice_key),
            ("music_direction", brief.music_direction),
        ]
        for name, value in required_str_fields:
            if not value:
                errors.append(f"Required field '{name}' is empty")

        if brief.panel_count not in (4, 5, 6, 8):
            errors.append(
                f"panel_count {brief.panel_count} must be 4, 5, 6, or 8"
            )

        if len(brief.story_structure.beats) != brief.panel_count:
            errors.append(
                f"story_structure.beats length "
                f"{len(brief.story_structure.beats)} "
                f"!= panel_count {brief.panel_count}"
            )

        if len(brief.camera_language) != brief.panel_count:
            errors.append(
                f"camera_language length {len(brief.camera_language)} "
                f"!= panel_count {brief.panel_count}"
            )

        if len(brief.archetypes) != len(player_answers):
            errors.append(
                f"archetypes count {len(brief.archetypes)} "
                f"!= player count {len(player_answers)}"
            )

        archetype_keys = [a.key for a in brief.archetypes]
        if len(archetype_keys) != len(set(archetype_keys)):
            errors.append("Duplicate archetype keys in brief")

        for twist in brief.twists:
            if not (0 <= twist.panel_index < brief.panel_count):
                errors.append(
                    f"Twist panel_index {twist.panel_index} out of range "
                    f"[0, {brief.panel_count})"
                )

        if not (0 <= brief.punchline_panel < brief.panel_count):
            errors.append(
                f"punchline_panel {brief.punchline_panel} out of range "
                f"[0, {brief.panel_count})"
            )

        if not (1 <= brief.comedy_level <= 10):
            errors.append(
                f"comedy_level {brief.comedy_level} out of range [1, 10]"
            )

        if len(brief.colour_palette) < 3:
            errors.append("colour_palette must have at least 3 colours")

        if len(brief.tone_keywords) < 1:
            errors.append("tone_keywords must have at least 1 entry")

        if errors:
            raise CreativeBriefValidationError(
                f"CreativeBrief validation failed with {len(errors)} error(s):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    def _write_brief_json(
        self,
        brief: CreativeBrief,
        output_dir: str,
    ) -> None:
        """Write brief.json to the output directory."""
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        brief_file = path / "brief.json"
        brief_file.write_text(
            brief.to_json(indent=2),
            encoding="utf-8",
        )


# ── Module-level causality beat builder ───────────────────────────────────────
# Defined at module level so it can be imported by ollama_story_llm.py
# without circular imports.

def _build_causality_beat(
    panel_index: int,
    panel_count: int,
    all_ingredient_answers: list[str],
) -> dict[str, str]:
    """
    Build a causality beat for a specific panel position.

    Fully dynamic — uses actual ingredient answers from players.
    No hardcoded Romanian words or fixed assumptions about ingredients.
    Scales to any panel count.

    Parameters
    ----------
    panel_index:
        0-based index of this panel.
    panel_count:
        Total number of panels in the strip.
    all_ingredient_answers:
        List of all player ingredient answer texts (Romanian originals).
        Used to build contextual beat instructions.
    """
    ingredient_list = ", ".join(
        f"«{a}»" for a in all_ingredient_answers
    ) if all_ingredient_answers else "(ingrediente jucători)"

    position = panel_index / max(panel_count - 1, 1)

    if panel_index == 0:
        return {
            "label": "DECLANȘATOR",
            "instruction": (
                f"Unul dintre aceste ingrediente declanșează o criză neașteptată: "
                f"{ingredient_list}. "
                "Ceva merge COMPLET greșit sau se întâmplă ceva fizic imposibil. "
                "NU o introducere liniștită — povestea începe deja în haos. "
                "Ingredientul este CAUZA directă a crizei, nu doar un element de decor. "
                "Primul panou trebuie să fie cel mai surprinzător vizual posibil."
            ),
        }

    if panel_index == panel_count - 1:
        return {
            "label": "REZOLUȚIE ABSURDĂ",
            "instruction": (
                f"Rezoluție care referențiază TOATE ingredientele vizual: "
                f"{ingredient_list}. "
                "Personajele sunt acum într-o relație complet nouă cu obiectele "
                "și unele cu altele față de panoul 0. "
                "Finalul trebuie să fie AMUZANT și ABSURD — cel puțin un detaliu "
                "vizual care nu ar fi posibil fără combinația exactă de ingrediente. "
                "Nu un final liniștit — un final care provoacă râs prin absurditate."
            ),
        }

    if position <= 0.35:
        return {
            "label": "REACȚIE",
            "instruction": (
                f"Un personaj face o alegere fizică DISPERATĂ ca răspuns direct "
                f"la criza din panoul anterior. "
                f"Legătură cauzală directă — fără salt în timp sau explicații. "
                f"Acțiunea lor implică în mod direct unul dintre: {ingredient_list}. "
                "Fug, apucă, urmăresc, confruntă sau încearcă ceva complet greșit. "
                "Consecința acțiunii lor trebuie să fie vizibilă și imediată."
            ),
        }

    if position <= 0.65:
        return {
            "label": "ESCALADARE",
            "instruction": (
                f"Consecința acțiunii anterioare înrăutățește totul exponențial. "
                f"Un ingredient diferit din {ingredient_list} intră în scenă "
                f"și complică situația în mod neașteptat. "
                "Mai multe personaje implicate, mediu mai mare, mize mult mai mari. "
                "Haosul se înmulțește — situația scapă de sub control complet. "
                "Acest panou trebuie să fie mai dinamic vizual decât cel anterior."
            ),
        }

    # position > 0.65 and not last panel → twist
    return {
        "label": "RĂSTURNARE",
        "instruction": (
            f"O utilizare complet neașteptată a unui ingredient din "
            f"{ingredient_list} schimbă totul. "
            "Ceva care părea o problemă insurmontabilă devine brusc soluția — "
            "sau invers, soluția aparentă creează o problemă și mai mare. "
            "Ingredientul face ceva ce fizic nu ar trebui să fie posibil. "
            "Panoul cu surpriza maximă — vizual cel mai dinamic și neașteptat. "
            "Personajele reacționează cu expresii și gesturi exagerate la maxim."
        ),
    }