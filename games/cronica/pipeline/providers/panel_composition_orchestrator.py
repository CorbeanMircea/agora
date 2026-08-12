"""
M5.5 — Panel Composition Orchestrator

Generates all comic panels sequentially by coordinating:
  - StyleTokenInjector (M5.4)   → per-panel ImagePrompt objects
  - CharacterDescriptionGenerator (M5.2) → CharacterRoster
  - FluxImageGenerator (M5.3)   → PNG files on disk

Design constraints (TASKS.md M5.5 + GDD Section 7.3):
  - Panels generated in order (panel 1 first, panel N last).
  - Each panel prompt combines: base style tokens + camera rule for that
    panel + character descriptions for characters in that panel + scene
    description from Story.
  - Dialogue/speech bubble text is passed as a caption note in the prompt,
    not embedded in the image.
  - Panels saved as panel_1.png ... panel_N.png in the output directory.
  - Partial failure: one panel failing retries that panel once before writing
    a placeholder stub PNG.
  - Total generation time is logged.
  - Maximum 3 characters per panel (GDD Section 7.3, enforced by
    CharacterRoster.build_panel_character_descriptions).

Usage (orchestrator._step_image_generation):
::
    orchestrator = PanelCompositionOrchestrator()
    results = orchestrator.generate_all_panels(brief, story, output_dir)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .character_description import CharacterDescriptionGenerator, CharacterRoster
from .flux_image_generator import FluxImageGenerator
from .image_generator_provider import ImagePrompt, PanelImage, VisualStyle
from .style_token_injector import StyleTokenInjector

log = logging.getLogger("panel_composition_orchestrator")

# Maximum retry attempts per panel before writing a fallback stub.
_MAX_PANEL_RETRIES: int = 1


@dataclass
class PanelResult:
    """
    The outcome of generating one comic panel.
    """
    panel_index: int
    file_path: Path
    is_fallback: bool
    generation_seconds: float
    error: str | None = None


@dataclass
class CompositionResult:
    """
    The complete outcome of a full panel generation pass.
    """
    panel_results: list[PanelResult] = field(default_factory=list)
    total_seconds: float = 0.0
    character_sheets_path: Path | None = None

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.panel_results if not r.is_fallback)

    @property
    def fallback_count(self) -> int:
        return sum(1 for r in self.panel_results if r.is_fallback)

    @property
    def all_files_exist(self) -> bool:
        return all(r.file_path.exists() for r in self.panel_results)


class PanelCompositionOrchestrator:
    """
    Coordinates the full panel generation loop for one round.

    Usage
    -----
    ::
        orchestrator = PanelCompositionOrchestrator()
        result = orchestrator.generate_all_panels(brief, story, output_dir)
    """

    def __init__(
        self,
        generator: FluxImageGenerator | None = None,
    ) -> None:
        self._generator = generator or FluxImageGenerator()
        self._injector = StyleTokenInjector()
        self._char_gen = CharacterDescriptionGenerator()

    def generate_all_panels(
        self,
        brief: Any,
        story: Any,
        output_dir: Path,
    ) -> CompositionResult:
        """
        Generate all panels for a round sequentially.

        Parameters
        ----------
        brief:
            A populated CreativeBrief instance (or its dict representation).
        story:
            A Story instance from story_llm_provider, or a dict from story.json.
        output_dir:
            Round output directory. Panels written as panel_1.png ... panel_N.png.

        Returns
        -------
        CompositionResult
            Contains per-panel results, total time, and character sheets path.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        panel_count: int = int(getattr(brief, "panel_count", 5))

        log.info(
            "Starting panel composition — %d panels → %s",
            panel_count,
            output_dir,
        )

        t_start = time.monotonic()

        # ── Step 1: Generate character roster ─────────────────────────────
        roster = self._build_roster(brief, output_dir)

        # ── Step 2: Build per-panel ImagePrompt objects ───────────────────
        image_prompts = self._build_prompts(brief, story, roster)

        # ── Step 3: Generate panels sequentially ─────────────────────────
        results: list[PanelResult] = []
        for prompt in image_prompts:
            result = self._generate_one_panel(prompt, brief, output_dir)
            results.append(result)
            log.info(
                "Panel %d/%d — %s (%.1fs)",
                prompt.panel_index + 1,
                panel_count,
                "fallback" if result.is_fallback else "ok",
                result.generation_seconds,
            )

        total = time.monotonic() - t_start
        log.info(
            "Panel composition complete — %d ok, %d fallback, %.1fs total",
            sum(1 for r in results if not r.is_fallback),
            sum(1 for r in results if r.is_fallback),
            total,
        )

        return CompositionResult(
            panel_results=results,
            total_seconds=total,
            character_sheets_path=(
                output_dir / "character_sheets.json"
                if (output_dir / "character_sheets.json").exists()
                else None
            ),
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_roster(self, brief: Any, output_dir: Path) -> CharacterRoster | None:
        """Generate and save the CharacterRoster. Returns None on failure."""
        try:
            roster = self._char_gen.generate(brief)
            roster.save(output_dir)
            log.info(
                "Character roster built — %d sheets", len(roster.sheets)
            )
            return roster
        except Exception as exc:
            log.warning("Character roster generation failed (non-fatal): %s", exc)
            return None

    def _build_prompts(
        self,
        brief: Any,
        story: Any,
        roster: CharacterRoster | None,
    ) -> list[ImagePrompt]:
        """Build ImagePrompt objects for all panels via StyleTokenInjector."""
        try:
            prompts = self._injector.build_image_prompts(
                brief, story, character_roster=roster
            )
            # Append dialogue as a caption note in the base prompt
            panels = list(getattr(story, "panels", []))
            for prompt in prompts:
                i = prompt.panel_index
                if i < len(panels):
                    dialogue = getattr(panels[i], "dialogue_ro", "")
                    if dialogue and dialogue.strip():
                        # Append as an English-safe note (not translated — presenter handles rendering)
                        prompt.base_prompt = (
                            prompt.base_prompt.rstrip(", ") +
                            f", speech bubble text: caption present"
                        )
            return prompts
        except Exception as exc:
            log.warning(
                "Prompt building failed (%s) — using bare base prompts", exc
            )
            panel_count: int = int(getattr(brief, "panel_count", 5))
            panels = list(getattr(story, "panels", []))
            return [
                ImagePrompt(
                    panel_index=i,
                    base_prompt=(
                        panels[i].image_prompt_en
                        if i < len(panels)
                        else f"wide shot panel {i + 1}, cinematic"
                    ),
                )
                for i in range(panel_count)
            ]

    def _generate_one_panel(
        self,
        prompt: ImagePrompt,
        brief: Any,
        output_dir: Path,
    ) -> PanelResult:
        """
        Generate a single panel with one retry on failure.

        Panel files are named panel_1.png ... panel_N.png (1-based).
        """
        panel_num = prompt.panel_index + 1
        output_path = output_dir / f"panel_{panel_num}.png"
        visual_style = self._injector.build_visual_style(brief)

        for attempt in range(1, _MAX_PANEL_RETRIES + 2):
            t0 = time.monotonic()
            try:
                panel_image = self._generator.generate_panel_to_file(
                    prompt=prompt,
                    style=visual_style,
                    character_descriptions=list(prompt.character_descriptions),
                    output_path=output_path,
                )
                elapsed = time.monotonic() - t0
                return PanelResult(
                    panel_index=prompt.panel_index,
                    file_path=output_path,
                    is_fallback=False,
                    generation_seconds=elapsed,
                )
            except Exception as exc:
                elapsed = time.monotonic() - t0
                log.warning(
                    "Panel %d generation failed (attempt %d/%d): %s",
                    panel_num,
                    attempt,
                    _MAX_PANEL_RETRIES + 1,
                    exc,
                )
                if attempt <= _MAX_PANEL_RETRIES:
                    log.info("Retrying panel %d...", panel_num)
                    continue

                # All attempts exhausted — write placeholder stub
                if not output_path.exists():
                    output_path.write_bytes(b"\x89PNG_FALLBACK_PANEL")
                return PanelResult(
                    panel_index=prompt.panel_index,
                    file_path=output_path,
                    is_fallback=True,
                    generation_seconds=elapsed,
                    error=str(exc),
                )

        # Should never reach here
        output_path.write_bytes(b"\x89PNG_FALLBACK_PANEL")
        return PanelResult(
            panel_index=prompt.panel_index,
            file_path=output_path,
            is_fallback=True,
            generation_seconds=0.0,
            error="Unexpected loop exit",
        )