"""
M5.6 — Image Pipeline Integration Test

Runs the full image pipeline from a Story + CreativeBrief fixture through
to PNG files on disk using a live ComfyUI instance with FLUX.1 schnell.

Prerequisites
-------------
1. ComfyUI must be running:  python main.py
2. FLUX.1 schnell must be installed in ComfyUI's models/checkpoints/
   (filename: flux1-schnell.safetensors, or set COMFYUI_CHECKPOINT env var)

The test is automatically skipped if ComfyUI is unreachable, so the suite
never breaks in CI without the model.

Run with:
    pytest games/cronica/pipeline/providers/test_flux_image_generator_integration.py -v -s

Or alongside the unit tests (skipped automatically if ComfyUI absent):
    pytest games/cronica/pipeline/ -v
"""

from __future__ import annotations

import json
import socket
import struct
from pathlib import Path

import pytest

from ..creative_director import CreativeDirector, PlayerAnswer
from .character_description import CharacterDescriptionGenerator
from .flux_image_generator import FluxImageGenerator, COMFYUI_BASE_URL
from .image_generator_provider import ImagePrompt, VisualStyle, PanelImage
from .panel_composition_orchestrator import PanelCompositionOrchestrator
from .story_llm_provider import Story, PanelDescription
from .style_token_injector import StyleTokenInjector


# ── Connectivity helpers ──────────────────────────────────────────────────────

def _comfyui_reachable() -> bool:
    """Return True if ComfyUI is reachable on its default port."""
    try:
        host = COMFYUI_BASE_URL.replace("http://", "").replace("https://", "").split(":")[0]
        port_str = COMFYUI_BASE_URL.rsplit(":", 1)[-1]
        port = int(port_str) if port_str.isdigit() else 8188
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _checkpoint_available() -> bool:
    """Return True if the configured checkpoint is listed by ComfyUI."""
    if not _comfyui_reachable():
        return False
    try:
        import httpx
        resp = httpx.get(f"{COMFYUI_BASE_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        if resp.status_code != 200:
            return False
        data = resp.json()
        checkpoints = (
            data.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[]])[0]
        )
        import os
        target = os.getenv("COMFYUI_CHECKPOINT", "flux1-schnell.safetensors")
        return any(target in str(c) for c in checkpoints)
    except Exception:
        return False


_SKIP_REASON = (
    f"ComfyUI not reachable at {COMFYUI_BASE_URL} or FLUX.1 schnell checkpoint not installed. "
    "Run ComfyUI and ensure flux1-schnell.safetensors is in models/checkpoints/."
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_player(player_id: str, nickname: str) -> PlayerAnswer:
    return PlayerAnswer(
        player_id=player_id,
        nickname=nickname,
        answers=[
            {"prompt_id": f"{player_id}_p0", "category": "CONCRET", "answer_text": "crocodil"},
            {"prompt_id": f"{player_id}_p1", "category": "LOC",     "answer_text": "Sinaia"},
        ],
    )


def _make_brief_and_story(seed: int = 42):
    """
    Generate a real CreativeBrief (4 panels for speed) and a matching
    minimal Story fixture. The story uses a fixed panel count so we don't
    need a live Ollama instance for this test.
    """
    cd = CreativeDirector()
    players = [
        _make_player("p1", "Ana"),
        _make_player("p2", "Bogdan"),
    ]

    # Generate until we get a 4-panel brief for faster testing
    brief = None
    for s in range(seed, seed + 200):
        b = cd.generate(players, [], seed=s)
        if b.panel_count == 4:
            brief = b
            break
    if brief is None:
        brief = cd.generate(players, [], seed=seed)

    panel_count = brief.panel_count

    # Build a minimal valid Story fixture (no Ollama needed)
    panels = []
    for i in range(panel_count):
        archetype_keys = [brief.archetypes[i % len(brief.archetypes)].key] if brief.archetypes else []
        panels.append(PanelDescription(
            panel_index=i,
            description_ro=f"Scena {i + 1}: Ana și Bogdan se află într-o situație comică la Sinaia cu un crocodil.",
            dialogue_ro="Ce se întâmplă?" if i == 0 else "",
            image_prompt_en=(
                f"Wide shot panel {i + 1}, dramatic cinematic lighting, comic book style, "
                f"two characters, expressive faces, high contrast"
            ),
            narrator_line_ro=f"Naratorul descrie evenimentele din panoul {i + 1}.",
            characters_in_panel=archetype_keys,
        ))

    story = Story(
        title="Povestea lui Ana și Bogdan la Sinaia",
        panels=panels,
        narrator_script=[p.narrator_line_ro for p in panels],
        image_prompts=[p.image_prompt_en for p in panels],
    )

    return brief, story


def _is_valid_png(path: Path) -> bool:
    """Return True if the file starts with the PNG magic bytes."""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        return header[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


def _get_file_size_kb(path: Path) -> float:
    return path.stat().st_size / 1024


# ── ComfyUI connectivity test ─────────────────────────────────────────────────

class TestComfyUIConnectivity:
    def test_comfyui_is_reachable(self):
        if not _comfyui_reachable():
            pytest.skip(_SKIP_REASON)
        import httpx
        resp = httpx.get(f"{COMFYUI_BASE_URL}/history", timeout=5)
        assert resp.status_code == 200, f"ComfyUI /history returned HTTP {resp.status_code}"

    def test_checkpoint_is_available(self):
        if not _comfyui_reachable():
            pytest.skip(_SKIP_REASON)
        if not _checkpoint_available():
            pytest.fail(
                "FLUX.1 schnell checkpoint not found in ComfyUI. "
                "Download flux1-schnell.safetensors and place it in ComfyUI/models/checkpoints/."
            )


# ── Single panel generation ───────────────────────────────────────────────────

class TestSinglePanelGeneration:
    """Generate a single panel to verify the ComfyUI workflow before running all panels."""

    @pytest.fixture(scope="class")
    def generator(self):
        if not _checkpoint_available():
            pytest.skip(_SKIP_REASON)
        return FluxImageGenerator(timeout=120.0, poll_interval=2.0)

    @pytest.fixture(scope="class")
    def single_panel_result(self, generator, tmp_path_factory):
        tmp_path = tmp_path_factory.mktemp("single_panel")
        output_path = tmp_path / "panel_1.png"

        brief, story = _make_brief_and_story(seed=42)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)

        return generator.generate_panel_to_file(
            prompt=prompts[0],
            style=injector.build_visual_style(brief),
            character_descriptions=[],
            output_path=output_path,
        )

    def test_returns_panel_image(self, single_panel_result):
        assert isinstance(single_panel_result, PanelImage)

    def test_panel_file_exists(self, single_panel_result):
        assert single_panel_result.exists, (
            f"Panel file not found: {single_panel_result.file_path}"
        )

    def test_panel_is_valid_png(self, single_panel_result):
        assert _is_valid_png(single_panel_result.file_path), (
            "Generated file does not have PNG magic bytes"
        )

    def test_panel_size_non_trivial(self, single_panel_result):
        size_kb = _get_file_size_kb(single_panel_result.file_path)
        assert size_kb > 50, (
            f"Panel file is too small ({size_kb:.1f} KB) — likely a stub or corrupted image"
        )

    def test_panel_index_is_zero(self, single_panel_result):
        assert single_panel_result.panel_index == 0

    def test_panel_is_not_fallback(self, single_panel_result):
        assert single_panel_result.is_fallback is False

    def test_generation_time_logged(self, single_panel_result):
        assert single_panel_result.generation_seconds > 0
        assert single_panel_result.generation_seconds < 120.0, (
            f"Panel took {single_panel_result.generation_seconds:.1f}s — check VRAM/ComfyUI"
        )

    def test_prompt_is_english(self, single_panel_result):
        """Prompt used must be ASCII-only (English)."""
        prompt = single_panel_result.prompt_used
        assert prompt.encode("ascii", errors="replace").decode("ascii") == prompt


# ── Full pipeline via PanelCompositionOrchestrator ────────────────────────────

class TestFullPipelineIntegration:
    """
    Run the complete panel composition loop via PanelCompositionOrchestrator.
    Uses a real CreativeBrief + Story fixture and a live ComfyUI instance.
    """

    @pytest.fixture(scope="class")
    def composition_result(self, tmp_path_factory):
        if not _checkpoint_available():
            pytest.skip(_SKIP_REASON)

        tmp_path = tmp_path_factory.mktemp("full_pipeline")
        brief, story = _make_brief_and_story(seed=42)

        generator = FluxImageGenerator(timeout=120.0, poll_interval=2.0)
        orchestrator = PanelCompositionOrchestrator(generator=generator)
        result = orchestrator.generate_all_panels(brief, story, tmp_path)
        # Attach metadata for assertions
        result._brief = brief
        result._output_dir = tmp_path
        return result

    def test_correct_panel_count(self, composition_result):
        brief = composition_result._brief
        assert len(composition_result.panel_results) == brief.panel_count

    def test_all_panel_files_exist(self, composition_result):
        assert composition_result.all_files_exist, (
            "One or more panel files are missing from the output directory"
        )

    def test_panel_files_named_correctly(self, composition_result):
        out_dir = composition_result._output_dir
        for i, result in enumerate(composition_result.panel_results):
            expected = out_dir / f"panel_{i + 1}.png"
            assert result.file_path == expected, (
                f"Panel {i} has wrong path: {result.file_path}"
            )

    def test_all_panels_are_valid_png(self, composition_result):
        for result in composition_result.panel_results:
            assert _is_valid_png(result.file_path), (
                f"panel_{result.panel_index + 1}.png is not a valid PNG"
            )

    def test_all_panels_exceed_50kb(self, composition_result):
        for result in composition_result.panel_results:
            size_kb = _get_file_size_kb(result.file_path)
            assert size_kb > 50, (
                f"panel_{result.panel_index + 1}.png is only {size_kb:.1f} KB — likely a stub"
            )

    def test_no_fallbacks(self, composition_result):
        assert composition_result.fallback_count == 0, (
            f"{composition_result.fallback_count} panel(s) fell back to stubs. "
            "Check ComfyUI logs."
        )

    def test_all_panels_succeed(self, composition_result):
        brief = composition_result._brief
        assert composition_result.success_count == brief.panel_count

    def test_total_time_within_limit(self, composition_result):
        brief = composition_result._brief
        max_secs = brief.panel_count * 120.0  # 2 min per panel worst case
        assert composition_result.total_seconds < max_secs, (
            f"Total generation took {composition_result.total_seconds:.1f}s "
            f"(limit: {max_secs:.0f}s)"
        )

    def test_character_sheets_written(self, composition_result):
        sheets_path = composition_result._output_dir / "character_sheets.json"
        assert sheets_path.exists(), "character_sheets.json not written"
        data = json.loads(sheets_path.read_text(encoding="utf-8"))
        assert "sheets" in data
        assert len(data["sheets"]) > 0

    def test_panels_in_sequential_order(self, composition_result):
        for i, result in enumerate(composition_result.panel_results):
            assert result.panel_index == i

    def test_panels_have_non_trivial_content(self, composition_result):
        """Each PNG should be visually unique — check file sizes differ."""
        sizes = [_get_file_size_kb(r.file_path) for r in composition_result.panel_results]
        # Not all panels should be identical size (they contain different content)
        # This is a soft check — identical sizes would suggest stubs
        if len(sizes) > 1:
            assert max(sizes) != min(sizes) or max(sizes) > 100, (
                "All panels have identical file sizes — possible stub generation"
            )


# ── Style token injection validation ─────────────────────────────────────────

class TestStyleTokenIntegration:
    """Verify that style tokens from the brief reach the generated prompts."""

    def test_genre_tokens_present_in_assembled_prompt(self):
        brief, story = _make_brief_and_story(seed=42)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)

        visual_style = injector.build_visual_style(brief)
        for p in prompts:
            assembled = p.build_positive_prompt()
            # At least one genre style token should appear in each prompt
            assert any(
                token.lower() in assembled.lower()
                for token in visual_style.style_tokens_positive
            ), f"No genre style tokens found in panel {p.panel_index} prompt: {assembled}"

    def test_camera_tokens_differ_per_panel(self):
        brief, story = _make_brief_and_story(seed=42)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story)
        camera_tokens = [p.camera_tokens for p in prompts]
        # Camera rules should differ across panels (brief assigns different rules per panel)
        if len(camera_tokens) > 1:
            assert len(set(camera_tokens)) > 1, (
                "All panels have identical camera tokens — brief camera rules not injected"
            )

    def test_character_descriptions_injected_for_panels_with_characters(self):
        brief, story = _make_brief_and_story(seed=42)
        char_gen = CharacterDescriptionGenerator()
        roster = char_gen.generate(brief)
        injector = StyleTokenInjector()
        prompts = injector.build_image_prompts(brief, story, character_roster=roster)

        # Panels that have characters_in_panel set should have descriptions
        for i, p in enumerate(prompts):
            panel = story.panels[i]
            if panel.characters_in_panel:
                assert len(p.character_descriptions) > 0, (
                    f"Panel {i} has characters but no character descriptions were injected"
                )


# ── Three-run consistency check ───────────────────────────────────────────────

class TestThreeRunConsistency:
    """
    GDD M5.6 completion criterion: test passes consistently across 3 runs.
    Each run generates one panel; all must be valid non-trivial PNGs.
    Uses a single panel per run to stay within a reasonable test time.
    """

    @pytest.mark.slow
    def test_single_panel_valid_across_three_runs(self, tmp_path):
        if not _checkpoint_available():
            pytest.skip(_SKIP_REASON)

        brief, story = _make_brief_and_story(seed=42)
        injector = StyleTokenInjector()
        prompt = injector.build_image_prompts(brief, story)[0]
        style = injector.build_visual_style(brief)
        generator = FluxImageGenerator(timeout=120.0, poll_interval=2.0)

        for run in range(3):
            output_path = tmp_path / f"consistency_panel_run{run + 1}.png"
            result = generator.generate_panel_to_file(
                prompt=prompt, style=style,
                character_descriptions=[], output_path=output_path,
            )
            assert result.exists, f"Run {run + 1}: panel file not created"
            assert _is_valid_png(output_path), f"Run {run + 1}: not a valid PNG"
            size_kb = _get_file_size_kb(output_path)
            assert size_kb > 50, (
                f"Run {run + 1}: panel too small ({size_kb:.1f} KB)"
            )