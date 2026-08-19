"""
Panel Composition Orchestrator — SDXL + IP-Adapter version.

Generates panels sequentially. After panel 1 completes:
- Its output path is stored as the reference image.
- Panels 2-5 receive IP-Adapter conditioning from panel 1.

This gives character/style consistency across all panels.
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

_MAX_PANEL_RETRIES: int = 1


@dataclass
class PanelResult:
    panel_index: int
    file_path: Path
    is_fallback: bool
    generation_seconds: float
    error: str | None = None


@dataclass
class CompositionResult:
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
    Coordinates sequential panel generation with IP-Adapter reference passing.

    Panel 1 → text only → saved as reference image
    Panel 2 → text + IP-Adapter(panel_1)
    Panel 3 → text + IP-Adapter(panel_1)  ← always panel 1, not drifting
    Panel 4 → text + IP-Adapter(panel_1)
    Panel 5 → text + IP-Adapter(panel_1)

    We always use panel 1 as the reference (not the previous panel) to prevent
    style drift where each panel drifts slightly further from the original.
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
        output_dir.mkdir(parents=True, exist_ok=True)
        panel_count: int = int(getattr(brief, "panel_count", 5))

        log.info(
            "Starting panel composition — %d panels → %s",
            panel_count,
            output_dir,
        )

        t_start = time.monotonic()

        roster = self._build_roster(brief, output_dir)
        image_prompts = self._build_prompts(brief, story, roster)
        results: list[PanelResult] = []

        # Reference image is None for panel 1 (text-only)
        # Set to panel 1 output path after it completes
        reference_path: Path | None = None

        for prompt in image_prompts:
            # Set reference on generator before each panel
            self._generator.reference_image_path = reference_path

            result = self._generate_one_panel(prompt, brief, output_dir)
            results.append(result)

            # After panel 1 succeeds, use it as reference for all subsequent panels
            if prompt.panel_index == 0 and not result.is_fallback:
                reference_path = result.file_path
                log.info(
                    "Panel 1 complete — setting as IP-Adapter reference: %s",
                    reference_path,
                )
            elif prompt.panel_index == 0 and result.is_fallback:
                log.warning(
                    "Panel 1 failed — subsequent panels will use text-only (no reference)"
                )

            log.info(
                "Panel %d/%d — %s (%.1fs)",
                prompt.panel_index + 1,
                panel_count,
                "fallback" if result.is_fallback else "ok",
                result.generation_seconds,
            )

        total = time.monotonic() - t_start
        log.info(
            "Composition complete — %d ok, %d fallback, %.1fs total",
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

    def _build_roster(self, brief: Any, output_dir: Path) -> CharacterRoster | None:
        try:
            roster = self._char_gen.generate(brief)
            roster.save(output_dir)
            log.info("Character roster built — %d sheets", len(roster.sheets))
            return roster
        except Exception as exc:
            log.warning("Character roster generation failed: %s", exc)
            return None

    def _build_prompts(
        self,
        brief: Any,
        story: Any,
        roster: CharacterRoster | None,
    ) -> list[ImagePrompt]:
        try:
            prompts = self._injector.build_image_prompts(
                brief, story, character_roster=roster
            )
            panels = list(getattr(story, "panels", []))
            for prompt in prompts:
                i = prompt.panel_index
                if i < len(panels):
                    dialogue = getattr(panels[i], "dialogue_ro", "")
                    if dialogue and dialogue.strip():
                        prompt.base_prompt = (
                            prompt.base_prompt.rstrip(", ") +
                            ", characters engaged in animated conversation, expressive gestures"
                        )
            return prompts
        except Exception as exc:
            log.warning("Prompt building failed (%s) — using bare base prompts", exc)
            panel_count: int = int(getattr(brief, "panel_count", 5))
            panels = list(getattr(story, "panels", []))
            return [
                ImagePrompt(
                    panel_index=i,
                    base_prompt=(
                        panels[i].image_prompt_en
                        if i < len(panels)
                        else f"wide shot panel {i + 1}, comic book illustration"
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
        panel_num = prompt.panel_index + 1
        output_path = output_dir / f"panel_{panel_num}.png"
        visual_style = self._injector.build_visual_style(brief)

        for attempt in range(1, _MAX_PANEL_RETRIES + 2):
            t0 = time.monotonic()
            try:
                self._generator.generate_panel_to_file(
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
                    "Panel %d failed (attempt %d/%d): %s",
                    panel_num, attempt, _MAX_PANEL_RETRIES + 1, exc,
                )
                if attempt <= _MAX_PANEL_RETRIES:
                    log.info("Retrying panel %d...", panel_num)
                    continue

                if not output_path.exists():
                    output_path.write_bytes(b"\x89PNG_FALLBACK_PANEL")
                return PanelResult(
                    panel_index=prompt.panel_index,
                    file_path=output_path,
                    is_fallback=True,
                    generation_seconds=elapsed,
                    error=str(exc),
                )

        output_path.write_bytes(b"\x89PNG_FALLBACK_PANEL")
        return PanelResult(
            panel_index=prompt.panel_index,
            file_path=output_path,
            is_fallback=True,
            generation_seconds=0.0,
            error="Unexpected loop exit",
        )