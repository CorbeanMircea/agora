"""
M5.3 — FluxImageGenerator

Concrete ImageGeneratorProvider that submits FLUX.1 schnell generation
jobs to ComfyUI's REST API, polls for completion, and saves the output
PNG to the round output directory.

Design constraints (TASKS.md M5.3 + GDD Section 7.1):
  - Calls ComfyUI REST API at localhost:8188 (configurable).
  - Uses FLUX.1 schnell model via a ComfyUI workflow JSON template.
  - Polls the /history endpoint until the job completes.
  - Saves the output image as panel_N.png in the output directory.
  - VRAM usage stays under 12GB (FLUX.1 schnell peak ~10-11GB).
  - Generation target: ≤20 seconds per panel on RTX 4070.
  - VRAM is cleared by the orchestrator after all panels are done.

ComfyUI API flow:
  1. POST /prompt  — submit the workflow JSON, receive a prompt_id
  2. GET  /history/{prompt_id} — poll until status is complete
  3. GET  /view?filename=...  — download the output image bytes
  4. Write bytes to output_path on disk

generate_panel() writes to a caller-supplied temp path (via output_path
kwarg) or a system temp file. generate_panel_to_file() is the primary
entry point for the orchestrator, writing to the final panel path.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .image_generator_provider import (
    ImageGeneratorProvider,
    ImagePrompt,
    PanelImage,
    VisualStyle,
    ImageGenerationError,
)

log = logging.getLogger("flux_image_generator")

# ── Configuration ─────────────────────────────────────────────────────────────

COMFYUI_BASE_URL: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")

_POLL_INTERVAL_SECS: float = 2.0
_GENERATION_TIMEOUT_SECS: float = float(os.getenv("COMFYUI_TIMEOUT_SECS", "120"))

_DEFAULT_WIDTH: int = 1024
_DEFAULT_HEIGHT: int = 1024

_DEFAULT_CFG: float = 1.0   # FLUX.1 schnell works best at low CFG
_DEFAULT_STEPS: int = 4     # schnell is a 4-step model

_DEFAULT_SAMPLER: str = "euler"
_DEFAULT_SCHEDULER: str = "simple"


# ── FluxImageGenerator ────────────────────────────────────────────────────────

class FluxImageGenerator(ImageGeneratorProvider):
    """
    Generates comic panels using FLUX.1 schnell via ComfyUI.

    Primary usage (Panel Composition Orchestrator, M5.5):
    ::
        gen = FluxImageGenerator()
        panel = gen.generate_panel_to_file(prompt, style, chars, output_path)

    generate_panel() is also callable directly; it writes to a temp file
    and returns a PanelImage whose file_path points to that temp file.
    """

    def __init__(
        self,
        base_url: str = COMFYUI_BASE_URL,
        timeout: float = _GENERATION_TIMEOUT_SECS,
        poll_interval: float = _POLL_INTERVAL_SECS,
        steps: int = _DEFAULT_STEPS,
        cfg: float = _DEFAULT_CFG,
        sampler: str = _DEFAULT_SAMPLER,
        scheduler: str = _DEFAULT_SCHEDULER,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.steps = steps
        self.cfg = cfg
        self.sampler = sampler
        self.scheduler = scheduler

    # ── ImageGeneratorProvider contract ───────────────────────────────────────

    def generate_panel(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        character_descriptions: list[str],
    ) -> PanelImage:
        """
        Generate one comic panel via ComfyUI + FLUX.1 schnell.

        Writes the PNG to a system temp file. The caller is responsible
        for moving/copying the file to the final destination. In practice,
        the orchestrator always calls generate_panel_to_file() instead.

        Returns
        -------
        PanelImage
            file_path points to a temp PNG file with the generated image.

        Raises
        ------
        ImageGenerationError
            If ComfyUI returns an error, job times out, or download fails.
        """
        # Write to a named temp file so PanelImage.exists is True immediately
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix=f"agora_panel_{prompt.panel_index}_"
        )
        tmp_path = Path(tmp.name)
        tmp.close()

        try:
            self._generate_to_path(prompt, style, tmp_path)
        except Exception:
            # Clean up temp file on failure before re-raising
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        elapsed = getattr(self, "_last_elapsed", 0.0)
        return PanelImage(
            panel_index=prompt.panel_index,
            file_path=tmp_path,
            width=style.width or _DEFAULT_WIDTH,
            height=style.height or _DEFAULT_HEIGHT,
            generation_seconds=elapsed,
            prompt_used=prompt.build_positive_prompt(),
            is_fallback=False,
        )

    def generate_panel_to_file(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        character_descriptions: list[str],
        output_path: Path,
    ) -> PanelImage:
        """
        Generate a panel and save the PNG directly to output_path.

        This is the primary method used by the Panel Composition Orchestrator
        (M5.5).

        Parameters
        ----------
        output_path:
            Destination PNG file path (e.g. output/round_1/panel_1.png).
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._generate_to_path(prompt, style, output_path)
        elapsed = getattr(self, "_last_elapsed", 0.0)
        return PanelImage(
            panel_index=prompt.panel_index,
            file_path=output_path,
            width=style.width or _DEFAULT_WIDTH,
            height=style.height or _DEFAULT_HEIGHT,
            generation_seconds=elapsed,
            prompt_used=prompt.build_positive_prompt(),
            is_fallback=False,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _generate_to_path(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        dest: Path,
    ) -> None:
        """
        Run the full ComfyUI generation cycle and write the PNG to dest.

        Stores generation duration in self._last_elapsed for the caller.

        Raises
        ------
        ImageGenerationError
        """
        positive = prompt.build_positive_prompt()
        negative = prompt.build_negative_prompt()
        width = style.width or _DEFAULT_WIDTH
        height = style.height or _DEFAULT_HEIGHT

        log.info(
            "Generating panel %d | %dx%d | prompt[:80]: %s",
            prompt.panel_index,
            width,
            height,
            positive[:80],
        )

        t0 = time.monotonic()

        try:
            workflow = _build_flux_workflow(
                positive_prompt=positive,
                negative_prompt=negative,
                width=width,
                height=height,
                steps=self.steps,
                cfg=self.cfg,
                sampler=self.sampler,
                scheduler=self.scheduler,
            )

            prompt_id = self._submit_workflow(workflow)
            log.info("Panel %d submitted — prompt_id: %s", prompt.panel_index, prompt_id)

            output_filename = self._poll_until_complete(prompt_id)
            log.info("Panel %d complete — file: %s", prompt.panel_index, output_filename)

            image_bytes = self._download_image(output_filename)

            dest.write_bytes(image_bytes)

            elapsed = time.monotonic() - t0
            self._last_elapsed = elapsed
            log.info(
                "Panel %d saved to %s in %.1fs (%d bytes)",
                prompt.panel_index,
                dest,
                elapsed,
                len(image_bytes),
            )

        except ImageGenerationError:
            raise
        except Exception as exc:
            raise ImageGenerationError(
                panel_index=prompt.panel_index,
                reason=str(exc),
            ) from exc

    def _submit_workflow(self, workflow: dict[str, Any]) -> str:
        """POST workflow to ComfyUI /prompt, return prompt_id."""
        url = f"{self.base_url}/prompt"
        payload = {
            "prompt": workflow,
            "client_id": str(uuid.uuid4()),
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)

        if resp.status_code != 200:
            raise ImageGenerationError(
                panel_index=-1,
                reason=(
                    f"ComfyUI /prompt returned HTTP {resp.status_code}: "
                    f"{resp.text[:200]}"
                ),
            )

        data = resp.json()
        prompt_id: str | None = data.get("prompt_id")
        if not prompt_id:
            raise ImageGenerationError(
                panel_index=-1,
                reason=f"ComfyUI /prompt response missing prompt_id: {data}",
            )

        return prompt_id

    def _poll_until_complete(self, prompt_id: str) -> str:
        """
        Poll GET /history/{prompt_id} until the job completes.

        Returns the output image filename.
        """
        url = f"{self.base_url}/history/{prompt_id}"
        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)

            if resp.status_code != 200:
                log.warning(
                    "Poll %s returned HTTP %d — retrying",
                    prompt_id,
                    resp.status_code,
                )
                continue

            history = resp.json()

            if prompt_id not in history:
                continue

            job = history[prompt_id]

            if job.get("status", {}).get("status_str") == "error":
                messages = job.get("status", {}).get("messages", [])
                raise ImageGenerationError(
                    panel_index=-1,
                    reason=f"ComfyUI job failed: {messages}",
                )

            outputs = job.get("outputs", {})
            filename = _extract_output_filename(outputs)
            if filename:
                return filename

        raise ImageGenerationError(
            panel_index=-1,
            reason=f"ComfyUI job {prompt_id} timed out after {self.timeout:.0f}s",
        )

    def _download_image(self, filename: str) -> bytes:
        """Download generated image from ComfyUI /view endpoint."""
        url = f"{self.base_url}/view"
        params = {"filename": filename, "type": "output"}

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code != 200:
            raise ImageGenerationError(
                panel_index=-1,
                reason=(
                    f"ComfyUI /view returned HTTP {resp.status_code} "
                    f"for filename '{filename}'"
                ),
            )

        return resp.content


# ── ComfyUI workflow builder ──────────────────────────────────────────────────

def _build_flux_workflow(
    positive_prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
) -> dict[str, Any]:
    """
    Build a ComfyUI API workflow JSON for FLUX.1 schnell.

    Model files required (already on disk):
      models/checkpoints/flux1-schnell.safetensors
      models/clip/t5xxl_fp16.safetensors
      models/clip/clip_l.safetensors
      models/vae/ae.safetensors

    Override via environment variables:
      COMFYUI_CHECKPOINT  — filename in models/checkpoints/
      COMFYUI_CLIP_NAME1  — T5 encoder filename in models/clip/ or models/text_encoders/
      COMFYUI_CLIP_NAME2  — CLIP-L filename in models/clip/ or models/text_encoders/
      COMFYUI_VAE_NAME    — VAE filename in models/vae/

    Node graph:
      1  CheckpointLoaderSimple → loads flux1-schnell (unet + clip bundled)
         -- FLUX.1 schnell is distributed as a single checkpoint file --
      OR if using split files:
      1  UNETLoader       → diffusion model
      2  DualCLIPLoader   → t5xxl + clip_l
      3  VAELoader        → ae.safetensors
      4  CLIPTextEncode   → positive prompt
      5  CLIPTextEncode   → negative prompt
      6  EmptyLatentImage → resolution
      7  KSampler         → diffusion
      8  VAEDecode        → latent to pixels
      9  SaveImage        → PNG output
    """
    checkpoint_name = os.getenv("COMFYUI_CHECKPOINT", "flux1-schnell.safetensors")
    clip_name1 = os.getenv("COMFYUI_CLIP_NAME1", "t5xxl_fp16.safetensors")
    clip_name2 = os.getenv("COMFYUI_CLIP_NAME2", "clip_l.safetensors")
    vae_name = os.getenv("COMFYUI_VAE_NAME", "ae.safetensors")
    output_prefix = f"agora_panel_{uuid.uuid4().hex[:8]}"

    workflow: dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": checkpoint_name,
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": clip_name1,
                "clip_name2": clip_name2,
                "type": "flux",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": vae_name,
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 0],
                "text": positive_prompt,
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 0],
                "text": negative_prompt or "",
            },
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": cfg,
                "denoise": 1.0,
                "latent_image": ["6", 0],
                "model": ["1", 0],
                "negative": ["5", 0],
                "positive": ["4", 0],
                "sampler_name": sampler,
                "scheduler": scheduler,
                "seed": _generate_seed(),
                "steps": steps,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["3", 0],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": output_prefix,
                "images": ["8", 0],
            },
        },
    }

    return workflow


def _generate_seed() -> int:
    """Generate a random seed for the KSampler (0–2^32-1)."""
    import random
    return random.randint(0, 2**32 - 1)


def _extract_output_filename(outputs: dict[str, Any]) -> str | None:
    """
    Extract the output image filename from a ComfyUI job's outputs dict.
    Checks all output nodes for image results (node ID may vary).
    """
    for node_output in outputs.values():
        images = node_output.get("images", [])
        for img in images:
            filename = img.get("filename")
            if filename:
                return filename
    return None