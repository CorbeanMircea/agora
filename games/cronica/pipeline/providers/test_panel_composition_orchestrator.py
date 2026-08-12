"""
M5.5 — Panel Composition Orchestrator Tests

All HTTP calls are mocked — no live ComfyUI required.

Run with:
    pytest games/cronica/pipeline/providers/test_panel_composition_orchestrator.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from .panel_composition_orchestrator import (
    PanelCompositionOrchestrator,
    PanelResult,
    CompositionResult,
    _MAX_PANEL_RETRIES,
)
from .image_generator_provider import ImageGenerationError, PanelImage
from ..creative_director import CreativeDirector, PlayerAnswer


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_player(player_id: str, nickname: str) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {"prompt_id": f"{player_id}_p0", "category": "CONCRET", "answer_text": "obiect"},
            {"prompt_id": f"{player_id}_p1", "category": "LOC",     "answer_text": "loc"},
        ],
    )


def _make_brief(seed: int = 0):
    cd = CreativeDirector()
    players = [_make_player("p1", "Ana"), _make_player("p2", "Bogdan")]
    return cd.generate(players, [], seed=seed)


@dataclass
class _FakePanel:
    panel_index: int
    image_prompt_en: str = "Wide shot, dramatic lighting, cinematic"
    dialogue_ro: str = ""
    characters_in_panel: list[str] = field(default_factory=list)
    description_ro: str = "Scena principala cu personajele in prim plan."
    narrator_line_ro: str = "Naratorul descrie scena."


@dataclass
class _FakeStory:
    panels: list[_FakePanel] = field(default_factory=list)
    title: str = "Povestea de test"
    narrator_script: list[str] = field(default_factory=list)
    image_prompts: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.narrator_script:
            self.narrator_script = [p.narrator_line_ro for p in self.panels]
        if not self.image_prompts:
            self.image_prompts = [p.image_prompt_en for p in self.panels]


def _make_story(brief) -> _FakeStory:
    panels = [_FakePanel(i) for i in range(brief.panel_count)]
    return _FakeStory(panels=panels)


def _mock_generator_success(tmp_path: Path):
    """Return a mock FluxImageGenerator that writes stub PNGs."""
    mock = MagicMock()
    call_count = [0]

    def fake_generate_panel_to_file(prompt, style, character_descriptions, output_path):
        call_count[0] += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"\x89PNG_MOCK_OK")
        return PanelImage(
            panel_index=prompt.panel_index,
            file_path=output_path,
            width=1024,
            height=1024,
            is_fallback=False,
        )

    mock.generate_panel_to_file.side_effect = fake_generate_panel_to_file
    mock._call_count = call_count
    return mock


def _mock_generator_always_fails():
    mock = MagicMock()
    mock.generate_panel_to_file.side_effect = ImageGenerationError(
        panel_index=0, reason="ComfyUI unavailable"
    )
    return mock


# ── PanelResult tests ─────────────────────────────────────────────────────────

class TestPanelResult:
    def test_basic_fields(self, tmp_path):
        path = tmp_path / "panel_1.png"
        path.write_bytes(b"\x89PNG")
        result = PanelResult(
            panel_index=0, file_path=path,
            is_fallback=False, generation_seconds=3.5
        )
        assert result.panel_index == 0
        assert result.is_fallback is False
        assert result.generation_seconds == 3.5
        assert result.error is None


# ── CompositionResult tests ───────────────────────────────────────────────────

class TestCompositionResult:
    def _make_results(self, tmp_path, fallback_indices: list[int], total: int):
        results = []
        for i in range(total):
            p = tmp_path / f"panel_{i+1}.png"
            p.write_bytes(b"\x89PNG")
            results.append(PanelResult(
                panel_index=i, file_path=p,
                is_fallback=(i in fallback_indices),
                generation_seconds=1.0,
            ))
        return results

    def test_success_count(self, tmp_path):
        r = CompositionResult(panel_results=self._make_results(tmp_path, [1], 4))
        assert r.success_count == 3

    def test_fallback_count(self, tmp_path):
        r = CompositionResult(panel_results=self._make_results(tmp_path, [1, 3], 4))
        assert r.fallback_count == 2

    def test_all_files_exist(self, tmp_path):
        r = CompositionResult(panel_results=self._make_results(tmp_path, [], 4))
        assert r.all_files_exist is True


# ── PanelCompositionOrchestrator tests ────────────────────────────────────────

class TestPanelCompositionOrchestrator:
    def test_generates_correct_number_of_panels(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert len(result.panel_results) == brief.panel_count

    def test_panel_files_are_named_correctly(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        for i, panel_result in enumerate(result.panel_results):
            expected = tmp_path / f"panel_{i+1}.png"
            assert panel_result.file_path == expected

    def test_all_panel_files_exist(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert result.all_files_exist

    def test_no_fallbacks_on_success(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert result.fallback_count == 0
        assert result.success_count == brief.panel_count

    def test_total_time_recorded(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert result.total_seconds >= 0.0

    def test_fallback_written_on_failure(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_always_fails()
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert result.fallback_count == brief.panel_count
        assert result.all_files_exist

    def test_fallback_result_has_error_message(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_always_fails()
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        for panel_result in result.panel_results:
            assert panel_result.error is not None

    def test_partial_failure_does_not_stop_pipeline(self, tmp_path):
        """If panel 1 fails, panels 2-N still generate."""
        brief = _make_brief(seed=0)
        story = _make_story(brief)

        call_count = [0]
        def mixed_generate(prompt, style, character_descriptions, output_path):
            call_count[0] += 1
            if prompt.panel_index == 0:
                raise ImageGenerationError(panel_index=0, reason="first panel fails")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG_OK")
            return PanelImage(
                panel_index=prompt.panel_index,
                file_path=output_path,
                width=1024, height=1024, is_fallback=False,
            )

        gen = MagicMock()
        gen.generate_panel_to_file.side_effect = mixed_generate
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)

        assert len(result.panel_results) == brief.panel_count
        assert result.panel_results[0].is_fallback is True
        assert all(
            not r.is_fallback
            for r in result.panel_results[1:]
        )

    def test_retry_attempted_on_first_failure(self, tmp_path):
        """Failed panel is retried _MAX_PANEL_RETRIES times before fallback."""
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        # Force only panel 0 to always fail
        attempt_counts: dict[int, int] = {}

        def counting_generate(prompt, style, character_descriptions, output_path):
            idx = prompt.panel_index
            attempt_counts[idx] = attempt_counts.get(idx, 0) + 1
            if idx == 0:
                raise ImageGenerationError(panel_index=0, reason="fail")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG")
            return PanelImage(
                panel_index=idx, file_path=output_path,
                width=1024, height=1024, is_fallback=False,
            )

        gen = MagicMock()
        gen.generate_panel_to_file.side_effect = counting_generate
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        orchestrator.generate_all_panels(brief, story, tmp_path)

        # Panel 0 should have been attempted _MAX_PANEL_RETRIES + 1 times
        assert attempt_counts.get(0, 0) == _MAX_PANEL_RETRIES + 1

    def test_character_sheets_written(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        assert (tmp_path / "character_sheets.json").exists()
        assert result.character_sheets_path is not None

    def test_panels_generated_in_order(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        call_order: list[int] = []

        def tracking_generate(prompt, style, character_descriptions, output_path):
            call_order.append(prompt.panel_index)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG")
            return PanelImage(
                panel_index=prompt.panel_index,
                file_path=output_path,
                width=1024, height=1024, is_fallback=False,
            )

        gen = MagicMock()
        gen.generate_panel_to_file.side_effect = tracking_generate
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        orchestrator.generate_all_panels(brief, story, tmp_path)
        assert call_order == list(range(brief.panel_count))

    def test_output_dir_created_if_missing(self, tmp_path):
        brief = _make_brief(seed=0)
        story = _make_story(brief)
        gen = _mock_generator_success(tmp_path)
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        new_dir = tmp_path / "round_999" / "subdir"
        assert not new_dir.exists()
        orchestrator.generate_all_panels(brief, story, new_dir)
        assert new_dir.exists()

    def test_dialogue_appended_to_base_prompt(self, tmp_path):
        """Panels with dialogue_ro should have a caption note in the prompt."""
        brief = _make_brief(seed=0)
        panels = []
        for i in range(brief.panel_count):
            panel = _FakePanel(i)
            if i == 0:
                panel.dialogue_ro = "Asta e imposibil!"
            panels.append(panel)
        story = _FakeStory(panels=panels)

        captured_prompts: list[str] = []

        def capturing_generate(prompt, style, character_descriptions, output_path):
            captured_prompts.append(prompt.base_prompt)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG")
            return PanelImage(
                panel_index=prompt.panel_index,
                file_path=output_path,
                width=1024, height=1024, is_fallback=False,
            )

        gen = MagicMock()
        gen.generate_panel_to_file.side_effect = capturing_generate
        orchestrator = PanelCompositionOrchestrator(generator=gen)
        orchestrator.generate_all_panels(brief, story, tmp_path)

        # Panel 0 (has dialogue) should mention caption
        assert "caption" in captured_prompts[0].lower()
        # Panel 1+ (no dialogue) should not
        assert "caption" not in captured_prompts[1].lower()