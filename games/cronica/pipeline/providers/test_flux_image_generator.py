"""
M5.3 — FluxImageGenerator Tests

Tests FluxImageGenerator without a live ComfyUI instance.
All HTTP calls are mocked via unittest.mock.

Run with:
    pytest games/cronica/pipeline/providers/test_flux_image_generator.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from .flux_image_generator import (
    FluxImageGenerator,
    _build_flux_workflow,
    _extract_output_filename,
    _generate_seed,
)
from .image_generator_provider import (
    ImagePrompt,
    VisualStyle,
    PanelImage,
    ImageGenerationError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _prompt(index: int = 0) -> ImagePrompt:
    return ImagePrompt(
        panel_index=index,
        base_prompt=f"Wide shot panel {index}, cinematic, dramatic lighting",
        style_tokens_positive=["oversaturated", "telenovela aesthetic"],
        style_tokens_negative=["horror", "dark"],
        camera_tokens="wide shot, low angle",
        character_descriptions=["Victima, short dark hair, vibrant red clothing"],
    )


def _style() -> VisualStyle:
    return VisualStyle(
        genre_key="telenovela_romaneasca",
        visual_style="Warm oversaturated colours",
        lighting_mood="warm, harsh top light",
        colour_palette=["#C0392B"],
        width=1024,
        height=1024,
    )


def _make_generator() -> FluxImageGenerator:
    return FluxImageGenerator(
        base_url="http://localhost:8188",
        timeout=10.0,
        poll_interval=0.05,
    )


def _mock_submit_response(prompt_id: str = "test-prompt-id") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"prompt_id": prompt_id}
    return resp


def _mock_history_response(prompt_id: str, filename: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        prompt_id: {
            "status": {"status_str": "success"},
            "outputs": {
                "7": {
                    "images": [
                        {"filename": filename, "subfolder": "", "type": "output"}
                    ]
                }
            },
        }
    }
    return resp


def _mock_image_response(content: bytes = b"\x89PNG_TEST") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = content
    return resp


def _setup_http_mocks(
    mock_client: MagicMock,
    prompt_id: str = "pid-001",
    filename: str = "panel_abc.png",
    image_bytes: bytes = b"\x89PNG_TEST",
) -> None:
    """Configure mock client for a complete successful generation cycle."""
    mock_client.post.return_value = _mock_submit_response(prompt_id)
    mock_client.get.side_effect = [
        _mock_history_response(prompt_id, filename),
        _mock_image_response(image_bytes),
    ]


# ── Workflow builder tests ────────────────────────────────────────────────────

class TestBuildFluxWorkflow:
    def test_workflow_has_required_nodes(self):
        wf = _build_flux_workflow(
            positive_prompt="test prompt",
            negative_prompt="",
            width=1024,
            height=1024,
            steps=4,
            cfg=1.0,
            sampler="euler",
            scheduler="simple",
        )
        assert "1" in wf  # UNETLoader
        assert "2" in wf  # DualCLIPLoader
        assert "3" in wf  # VAELoader
        assert "4" in wf  # CLIPTextEncode positive
        assert "5" in wf  # CLIPTextEncode negative
        assert "6" in wf  # EmptyLatentImage
        assert "7" in wf  # KSampler
        assert "8" in wf  # VAEDecode
        assert "9" in wf  # SaveImage

    def test_workflow_positive_prompt_set(self):
        wf = _build_flux_workflow(
            positive_prompt="cinematic wide shot",
            negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        assert wf["4"]["inputs"]["text"] == "cinematic wide shot"

    def test_workflow_negative_prompt_set(self):
        wf = _build_flux_workflow(
            positive_prompt="test",
            negative_prompt="horror, dark",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        assert wf["5"]["inputs"]["text"] == "horror, dark"

    def test_workflow_resolution_set(self):
        wf = _build_flux_workflow(
            positive_prompt="test",
            negative_prompt="",
            width=768, height=512, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        assert wf["6"]["inputs"]["width"] == 768
        assert wf["6"]["inputs"]["height"] == 512

    def test_workflow_steps_set(self):
        wf = _build_flux_workflow(
            positive_prompt="test",
            negative_prompt="",
            width=1024, height=1024, steps=8, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        assert wf["7"]["inputs"]["steps"] == 8

    def test_workflow_cfg_set(self):
        wf = _build_flux_workflow(
            positive_prompt="test",
            negative_prompt="",
            width=1024, height=1024, steps=4, cfg=2.0,
            sampler="euler", scheduler="simple",
        )
        assert wf["7"]["inputs"]["cfg"] == 2.0

    def test_workflow_sampler_set(self):
        wf = _build_flux_workflow(
            positive_prompt="test",
            negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="dpm_2", scheduler="karras",
        )
        assert wf["7"]["inputs"]["sampler_name"] == "dpm_2"
        assert wf["7"]["inputs"]["scheduler"] == "karras"

    def test_workflow_node_references_correct(self):
        wf = _build_flux_workflow(
            positive_prompt="test", negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        # CLIP text encode nodes use DualCLIPLoader output
        assert wf["4"]["inputs"]["clip"] == ["2", 0]
        assert wf["5"]["inputs"]["clip"] == ["2", 0]
        # KSampler references
        assert wf["7"]["inputs"]["model"] == ["1", 0]
        assert wf["7"]["inputs"]["positive"] == ["4", 0]
        assert wf["7"]["inputs"]["negative"] == ["5", 0]
        assert wf["7"]["inputs"]["latent_image"] == ["6", 0]
        # VAEDecode
        assert wf["8"]["inputs"]["samples"] == ["7", 0]
        assert wf["8"]["inputs"]["vae"] == ["3", 0]
        # SaveImage
        assert wf["9"]["inputs"]["images"] == ["8", 0]

    def test_workflow_is_json_serialisable(self):
        wf = _build_flux_workflow(
            positive_prompt="test", negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        json_str = json.dumps(wf)  # must not raise
        assert json_str

    def test_output_prefix_is_unique_per_call(self):
        wf_a = _build_flux_workflow(
            positive_prompt="test", negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        wf_b = _build_flux_workflow(
            positive_prompt="test", negative_prompt="",
            width=1024, height=1024, steps=4, cfg=1.0,
            sampler="euler", scheduler="simple",
        )
        prefix_a = wf_a["9"]["inputs"]["filename_prefix"]
        prefix_b = wf_b["9"]["inputs"]["filename_prefix"]
        assert prefix_a != prefix_b


# ── _extract_output_filename tests ────────────────────────────────────────────

class TestExtractOutputFilename:
    def test_extracts_filename_from_node_7(self):
        outputs = {
            "7": {
                "images": [
                    {"filename": "panel_abc.png", "subfolder": "", "type": "output"}
                ]
            }
        }
        assert _extract_output_filename(outputs) == "panel_abc.png"

    def test_returns_none_for_empty_outputs(self):
        assert _extract_output_filename({}) is None

    def test_returns_none_when_no_images(self):
        outputs = {"7": {"images": []}}
        assert _extract_output_filename(outputs) is None

    def test_returns_first_filename(self):
        outputs = {
            "7": {
                "images": [
                    {"filename": "first.png"},
                    {"filename": "second.png"},
                ]
            }
        }
        assert _extract_output_filename(outputs) == "first.png"

    def test_handles_multiple_output_nodes(self):
        outputs = {
            "6": {"images": []},
            "7": {"images": [{"filename": "panel.png"}]},
        }
        assert _extract_output_filename(outputs) == "panel.png"


# ── FluxImageGenerator individual API method tests ────────────────────────────

class TestFluxImageGeneratorAPI:
    def test_submit_workflow_posts_to_correct_url(self):
        gen = _make_generator()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = _mock_submit_response("pid-001")

            wf = _build_flux_workflow("test", "", 1024, 1024, 4, 1.0, "euler", "simple")
            result = gen._submit_workflow(wf)

        assert result == "pid-001"
        called_url = mock_client.post.call_args[0][0]
        assert "/prompt" in called_url

    def test_submit_workflow_raises_on_http_error(self):
        gen = _make_generator()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            wf = _build_flux_workflow("test", "", 1024, 1024, 4, 1.0, "euler", "simple")
            with pytest.raises(ImageGenerationError) as exc_info:
                gen._submit_workflow(wf)

        assert "500" in str(exc_info.value)

    def test_submit_workflow_raises_on_missing_prompt_id(self):
        gen = _make_generator()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            wf = _build_flux_workflow("test", "", 1024, 1024, 4, 1.0, "euler", "simple")
            with pytest.raises(ImageGenerationError):
                gen._submit_workflow(wf)

    def test_poll_until_complete_returns_filename(self):
        gen = _make_generator()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = _mock_history_response("pid-001", "panel_abc.png")

            result = gen._poll_until_complete("pid-001")

        assert result == "panel_abc.png"

    def test_poll_until_complete_retries_when_not_in_history(self):
        gen = _make_generator()

        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {}

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.side_effect = [
                empty_resp,
                _mock_history_response("pid-001", "panel_abc.png"),
            ]

            result = gen._poll_until_complete("pid-001")

        assert result == "panel_abc.png"
        assert mock_client.get.call_count == 2

    def test_poll_until_complete_raises_on_comfyui_error(self):
        gen = _make_generator()
        error_resp = MagicMock()
        error_resp.status_code = 200
        error_resp.json.return_value = {
            "pid-001": {
                "status": {"status_str": "error", "messages": ["OOM"]},
                "outputs": {},
            }
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = error_resp

            with pytest.raises(ImageGenerationError):
                gen._poll_until_complete("pid-001")

    def test_poll_until_complete_raises_on_timeout(self):
        gen = FluxImageGenerator(
            base_url="http://localhost:8188",
            timeout=0.01,
            poll_interval=0.5,
        )
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.json.return_value = {}

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = empty_resp

            with pytest.raises(ImageGenerationError, match="timed out"):
                gen._poll_until_complete("pid-001")

    def test_download_image_returns_bytes(self):
        gen = _make_generator()
        png_bytes = b"\x89PNG_TEST_CONTENT"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = _mock_image_response(png_bytes)

            result = gen._download_image("panel_abc.png")

        assert result == png_bytes

    def test_download_image_raises_on_http_error(self):
        gen = _make_generator()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.content = b""

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp

            with pytest.raises(ImageGenerationError):
                gen._download_image("missing.png")


# ── Full generate_panel (mocked, writes to temp file) ─────────────────────────

class TestGeneratePanelMocked:
    def test_generate_panel_returns_panel_image(self):
        gen = _make_generator()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            _setup_http_mocks(mock_client)

            result = gen.generate_panel(_prompt(0), _style(), [])

        assert isinstance(result, PanelImage)
        assert result.panel_index == 0
        assert result.is_fallback is False

    def test_generate_panel_file_exists_on_disk(self):
        gen = _make_generator()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            _setup_http_mocks(mock_client, image_bytes=b"\x89PNG_CONTENT")

            result = gen.generate_panel(_prompt(0), _style(), [])

        assert result.exists
        assert result.file_path.read_bytes() == b"\x89PNG_CONTENT"
        # Clean up temp file
        result.file_path.unlink(missing_ok=True)

    def test_generate_panel_uses_assembled_positive_prompt(self):
        gen = _make_generator()
        prompt = _prompt(0)
        expected_positive = prompt.build_positive_prompt()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            _setup_http_mocks(mock_client)

            result = gen.generate_panel(prompt, _style(), [])

        assert result.prompt_used == expected_positive
        result.file_path.unlink(missing_ok=True)

    def test_generate_panel_wraps_exceptions_as_image_generation_error(self):
        gen = _make_generator()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = Exception("Connection refused")

            with pytest.raises(ImageGenerationError):
                gen.generate_panel(_prompt(0), _style(), [])

    def test_generate_panel_to_file_saves_png(self, tmp_path: Path):
        gen = _make_generator()
        output_path = tmp_path / "panel_1.png"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            _setup_http_mocks(mock_client, image_bytes=b"\x89PNG_SAVED")

            result = gen.generate_panel_to_file(_prompt(0), _style(), [], output_path)

        assert output_path.exists()
        assert output_path.read_bytes() == b"\x89PNG_SAVED"
        assert result.file_path == output_path
        assert result.is_fallback is False

    def test_generate_panel_with_fallback_returns_fallback_on_failure(
        self, tmp_path: Path
    ):
        gen = _make_generator()
        fallback = tmp_path / "fallback_1.png"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = Exception("ComfyUI down")

            result = gen.generate_panel_with_fallback(
                _prompt(0), _style(), [], fallback_path=fallback
            )

        assert result.is_fallback is True
        assert fallback.exists()

    def test_generate_panel_correct_panel_index_in_result(self):
        gen = _make_generator()

        for panel_idx in [0, 1, 2, 3, 4]:
            with patch("httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value.__enter__.return_value = mock_client
                _setup_http_mocks(
                    mock_client,
                    prompt_id=f"pid-{panel_idx}",
                    filename=f"out_{panel_idx}.png",
                )

                result = gen.generate_panel(_prompt(panel_idx), _style(), [])

            assert result.panel_index == panel_idx
            result.file_path.unlink(missing_ok=True)


# ── Configuration tests ───────────────────────────────────────────────────────

class TestFluxImageGeneratorConfiguration:
    def test_default_steps_is_four(self):
        assert FluxImageGenerator().steps == 4

    def test_default_cfg_is_one(self):
        assert FluxImageGenerator().cfg == 1.0

    def test_default_sampler_is_euler(self):
        assert FluxImageGenerator().sampler == "euler"

    def test_default_scheduler_is_simple(self):
        assert FluxImageGenerator().scheduler == "simple"

    def test_custom_configuration(self):
        gen = FluxImageGenerator(
            base_url="http://192.168.1.5:8188",
            timeout=60.0,
            steps=8,
            cfg=2.0,
            sampler="dpm_2",
            scheduler="karras",
        )
        assert gen.base_url == "http://192.168.1.5:8188"
        assert gen.timeout == 60.0
        assert gen.steps == 8
        assert gen.cfg == 2.0
        assert gen.sampler == "dpm_2"
        assert gen.scheduler == "karras"

    def test_trailing_slash_stripped_from_base_url(self):
        gen = FluxImageGenerator(base_url="http://localhost:8188/")
        assert gen.base_url == "http://localhost:8188"


# ── _generate_seed tests ──────────────────────────────────────────────────────

class TestGenerateSeed:
    def test_returns_integer(self):
        assert isinstance(_generate_seed(), int)

    def test_returns_non_negative(self):
        assert _generate_seed() >= 0

    def test_returns_within_uint32_range(self):
        assert 0 <= _generate_seed() <= 2**32 - 1

    def test_seeds_differ_across_calls(self):
        seeds = {_generate_seed() for _ in range(10)}
        assert len(seeds) > 1