"""
M5.1 — ImageGeneratorProvider Interface Tests

Run with:
    pytest games/cronica/pipeline/providers/test_image_generator_provider.py -v
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any

import pytest

from .image_generator_provider import (
    ImageGeneratorProvider,
    ImagePrompt,
    VisualStyle,
    PanelImage,
    ImageGenerationError,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prompt(index: int = 0) -> ImagePrompt:
    return ImagePrompt(
        panel_index=index,
        base_prompt=f"Wide shot panel {index}, cinematic, dramatic lighting",
        style_tokens_positive=["oversaturated", "telenovela aesthetic"],
        style_tokens_negative=["horror", "dark"],
        camera_tokens="wide shot, low angle",
        character_descriptions=["Ana: red dress, dark hair", "Bogdan: blue suit"],
    )


def _style() -> VisualStyle:
    return VisualStyle(
        genre_key="telenovela_romaneasca",
        visual_style="Warm oversaturated colours, extreme close-ups",
        lighting_mood="warm, harsh top light",
        colour_palette=["#C0392B", "#E8DAEF"],
        style_tokens_positive=["dramatic", "soap opera"],
        style_tokens_negative=["minimalist"],
    )


# ── ImagePrompt tests ─────────────────────────────────────────────────────────

class TestImagePrompt:
    def test_build_positive_prompt_combines_all_parts(self):
        p = _prompt(0)
        result = p.build_positive_prompt()
        assert "Wide shot panel 0" in result
        assert "wide shot, low angle" in result
        assert "Ana: red dress" in result
        assert "oversaturated" in result

    def test_build_positive_prompt_skips_empty_parts(self):
        p = ImagePrompt(
            panel_index=0,
            base_prompt="base prompt",
            style_tokens_positive=[],
            style_tokens_negative=[],
            camera_tokens="",
            character_descriptions=[],
        )
        result = p.build_positive_prompt()
        assert result == "base prompt"

    def test_build_negative_prompt_joins_tokens(self):
        p = _prompt()
        result = p.build_negative_prompt()
        assert "horror" in result
        assert "dark" in result

    def test_build_negative_prompt_empty_when_no_tokens(self):
        p = ImagePrompt(panel_index=0, base_prompt="test")
        assert p.build_negative_prompt() == ""

    def test_default_fields(self):
        p = ImagePrompt(panel_index=2, base_prompt="test")
        assert p.style_tokens_positive == []
        assert p.style_tokens_negative == []
        assert p.camera_tokens == ""
        assert p.character_descriptions == []


# ── VisualStyle tests ─────────────────────────────────────────────────────────

class TestVisualStyle:
    def test_basic_instantiation(self):
        style = _style()
        assert style.genre_key == "telenovela_romaneasca"
        assert style.width == 1024
        assert style.height == 1024

    def test_from_brief(self):
        @dataclass
        class MiniBrief:
            genre_key: str = "film_actiune_b"
            visual_style: str = "High contrast, lens flare"
            lighting_mood: str = "orange explosion glow"
            colour_palette: list = None

            def __post_init__(self):
                if self.colour_palette is None:
                    self.colour_palette = ["#E74C3C", "#2C3E50"]

        style = VisualStyle.from_brief(MiniBrief())
        assert style.genre_key == "film_actiune_b"
        assert style.visual_style == "High contrast, lens flare"
        assert len(style.colour_palette) == 2

    def test_default_resolution(self):
        style = VisualStyle(
            genre_key="test",
            visual_style="test style",
            lighting_mood="test light",
        )
        assert style.width == 1024
        assert style.height == 1024


# ── PanelImage tests ──────────────────────────────────────────────────────────

class TestPanelImage:
    def test_exists_returns_false_for_missing_file(self, tmp_path):
        img = PanelImage(
            panel_index=0,
            file_path=tmp_path / "missing.png",
            width=1024,
            height=1024,
        )
        assert img.exists is False

    def test_exists_returns_true_for_real_file(self, tmp_path):
        path = tmp_path / "panel_1.png"
        path.write_bytes(b"\x89PNG_TEST")
        img = PanelImage(panel_index=0, file_path=path, width=1024, height=1024)
        assert img.exists is True

    def test_file_size_bytes_zero_for_missing(self, tmp_path):
        img = PanelImage(
            panel_index=0,
            file_path=tmp_path / "missing.png",
            width=1024,
            height=1024,
        )
        assert img.file_size_bytes == 0

    def test_file_size_bytes_for_existing_file(self, tmp_path):
        path = tmp_path / "panel_1.png"
        path.write_bytes(b"X" * 100)
        img = PanelImage(panel_index=0, file_path=path, width=1024, height=1024)
        assert img.file_size_bytes == 100

    def test_is_fallback_default_false(self, tmp_path):
        img = PanelImage(
            panel_index=0,
            file_path=tmp_path / "p.png",
            width=1024,
            height=1024,
        )
        assert img.is_fallback is False


# ── Abstract provider contract tests ─────────────────────────────────────────

class TestImageGeneratorProviderContract:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            ImageGeneratorProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_generate_panel(self):
        class Incomplete(ImageGeneratorProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_is_instantiable(self, tmp_path):
        class MinimalGenerator(ImageGeneratorProvider):
            def generate_panel(self, prompt, style, character_descriptions):
                path = tmp_path / f"panel_{prompt.panel_index}.png"
                path.write_bytes(b"\x89PNG")
                return PanelImage(
                    panel_index=prompt.panel_index,
                    file_path=path,
                    width=style.width,
                    height=style.height,
                )

        gen = MinimalGenerator()
        assert isinstance(gen, ImageGeneratorProvider)

    def test_generate_panel_is_callable(self, tmp_path):
        class EchoGenerator(ImageGeneratorProvider):
            def generate_panel(self, prompt, style, character_descriptions):
                path = tmp_path / f"panel_{prompt.panel_index + 1}.png"
                path.write_bytes(b"\x89PNG")
                return PanelImage(
                    panel_index=prompt.panel_index,
                    file_path=path,
                    width=style.width,
                    height=style.height,
                    prompt_used=prompt.build_positive_prompt(),
                )

        gen = EchoGenerator()
        result = gen.generate_panel(_prompt(0), _style(), [])
        assert isinstance(result, PanelImage)
        assert result.panel_index == 0
        assert result.exists


# ── generate_panel_with_fallback tests ───────────────────────────────────────

class TestGeneratePanelWithFallback:
    def test_returns_real_image_on_success(self, tmp_path):
        class SuccessGenerator(ImageGeneratorProvider):
            def generate_panel(self, prompt, style, character_descriptions):
                path = tmp_path / f"panel_{prompt.panel_index + 1}.png"
                path.write_bytes(b"\x89PNG_REAL")
                return PanelImage(
                    panel_index=prompt.panel_index,
                    file_path=path,
                    width=1024,
                    height=1024,
                    is_fallback=False,
                )

        gen = SuccessGenerator()
        result = gen.generate_panel_with_fallback(
            _prompt(0), _style(), [],
            fallback_path=tmp_path / "fallback_1.png",
        )
        assert result.is_fallback is False
        assert b"REAL" in result.file_path.read_bytes()

    def test_returns_fallback_stub_on_failure(self, tmp_path):
        class FailingGenerator(ImageGeneratorProvider):
            def generate_panel(self, prompt, style, character_descriptions):
                raise RuntimeError("ComfyUI unavailable")

        gen = FailingGenerator()
        fallback = tmp_path / "fallback_1.png"
        result = gen.generate_panel_with_fallback(
            _prompt(0), _style(), [], fallback_path=fallback,
        )
        assert result.is_fallback is True
        assert result.file_path == fallback
        assert fallback.exists()

    def test_fallback_does_not_overwrite_existing_file(self, tmp_path):
        class FailingGenerator(ImageGeneratorProvider):
            def generate_panel(self, prompt, style, character_descriptions):
                raise RuntimeError("fail")

        existing = tmp_path / "existing_fallback.png"
        existing.write_bytes(b"EXISTING")

        gen = FailingGenerator()
        gen.generate_panel_with_fallback(_prompt(0), _style(), [], fallback_path=existing)
        assert existing.read_bytes() == b"EXISTING"


# ── ImageGenerationError tests ────────────────────────────────────────────────

class TestImageGenerationError:
    def test_error_message_includes_panel_index(self):
        err = ImageGenerationError(panel_index=3, reason="timeout")
        assert "3" in str(err)
        assert "timeout" in str(err)

    def test_attributes_accessible(self):
        err = ImageGenerationError(panel_index=5, reason="VRAM OOM")
        assert err.panel_index == 5
        assert err.reason == "VRAM OOM"

    def test_is_runtime_error(self):
        err = ImageGenerationError(panel_index=0, reason="test")
        assert isinstance(err, RuntimeError)