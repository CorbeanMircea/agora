"""
SDXL + IP-Adapter Image Generator

Replaces the previous FLUX/Z-Image-Turbo generator.

Architecture:
- Base model: JuggernautXL v9 (SDXL)
- Style: Comic Book LoRA applied at fixed strength
- Consistency: IP-Adapter reference conditioning
  - Panel 1: generated from text only (establishes character reference)
  - Panels 2-5: text + IP-Adapter conditioned on panel 1 output
- Sampler: DPM++ 2M Karras, 30 steps
- Resolution: 1024x1024

IP-Adapter weight (0.0 - 1.0):
  - 0.0 = pure text, no reference influence
  - 0.5 = balanced (recommended start)
  - 0.8 = strong reference, less creative freedom
  - 1.0 = almost a copy of reference

Config via environment variables:
  COMFYUI_BASE_URL     default: http://127.0.0.1:8188
  SDXL_CHECKPOINT      default: juggernautXL_v9Rdphoto2Lightning.safetensors
  COMIC_LORA_NAME      default: comic_book_style_xl.safetensors
  COMIC_LORA_STRENGTH  default: 0.85
  IPADAPTER_MODEL      default: ip-adapter_sdxl.bin
  IPADAPTER_WEIGHT     default: 0.5
  SDXL_STEPS           default: 30
  SDXL_CFG             default: 7.0
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .image_generator_provider import ImagePrompt, PanelImage, VisualStyle

log = logging.getLogger("sdxl_image_generator")

# ── Configuration ─────────────────────────────────────────────────────────────

COMFYUI_BASE_URL: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")

SDXL_CHECKPOINT: str = os.getenv(
    "SDXL_CHECKPOINT",
    "juggernautXL_ragnarok.safetensors",
)
COMIC_LORA_NAME: str = os.getenv(
    "COMIC_LORA_NAME",
    "Romain_Bonnet_E10.safetensors",
)
COMIC_LORA_STRENGTH: float = float(os.getenv("COMIC_LORA_STRENGTH", "0.85"))

IPADAPTER_MODEL: str = os.getenv("IPADAPTER_MODEL", "ip-adapter_sdxl.bin")
IPADAPTER_WEIGHT: float = float(os.getenv("IPADAPTER_WEIGHT", "0.5"))

SDXL_STEPS: int = int(os.getenv("SDXL_STEPS", "30"))
SDXL_CFG: float = float(os.getenv("SDXL_CFG", "7.0"))

GENERATION_TIMEOUT: float = float(os.getenv("COMFYUI_TIMEOUT", "300"))
POLL_INTERVAL: float = 2.0


class FluxImageGenerator:
    """
    SDXL + IP-Adapter panel generator.

    Despite the class name retained for import compatibility,
    this now uses JuggernautXL + Comic LoRA + IP-Adapter.

    The reference_image_path is set by PanelCompositionOrchestrator
    after panel 1 is generated, so panels 2-5 receive reference conditioning.
    """

    def __init__(
        self,
        base_url: str = COMFYUI_BASE_URL,
        checkpoint: str = SDXL_CHECKPOINT,
        lora_name: str = COMIC_LORA_NAME,
        lora_strength: float = COMIC_LORA_STRENGTH,
        ipadapter_model: str = IPADAPTER_MODEL,
        ipadapter_weight: float = IPADAPTER_WEIGHT,
        steps: int = SDXL_STEPS,
        cfg: float = SDXL_CFG,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.checkpoint = checkpoint
        self.lora_name = lora_name
        self.lora_strength = lora_strength
        self.ipadapter_model = ipadapter_model
        self.ipadapter_weight = ipadapter_weight
        self.steps = steps
        self.cfg = cfg

        # Set by PanelCompositionOrchestrator after panel 1 completes.
        # When None: text-only generation (panel 1).
        # When set: IP-Adapter reference conditioning (panels 2-5).
        self.reference_image_path: Path | None = None

    def generate_panel_to_file(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        character_descriptions: list[str],
        output_path: Path,
    ) -> PanelImage:
        """
        Generate one panel and save to output_path.
        Returns a PanelImage describing the result.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        positive = prompt.build_positive_prompt()
        negative = prompt.build_negative_prompt()

        use_ipadapter = self.reference_image_path is not None

        log.info(
            "Generating panel %d — steps=%d cfg=%.1f lora=%.2f "
            "ipadapter=%s ref=%s",
            prompt.panel_index,
            self.steps,
            self.cfg,
            self.lora_strength,
            use_ipadapter,
            str(self.reference_image_path) if use_ipadapter else "none",
        )

        t0 = time.monotonic()

        if use_ipadapter:
            workflow = self._build_ipadapter_workflow(positive, negative, output_path)
        else:
            workflow = self._build_text_only_workflow(positive, negative, output_path)

        self._submit_and_wait(workflow)

        elapsed = time.monotonic() - t0
        log.info("Panel %d generated in %.1fs", prompt.panel_index, elapsed)

        if not output_path.exists():
            raise RuntimeError(
                f"ComfyUI did not produce output file at {output_path}"
            )

        return PanelImage(
            panel_index=prompt.panel_index,
            file_path=output_path,
            width=1024,
            height=1024,
            generation_seconds=elapsed,
            prompt_used=positive,
            is_fallback=False,
        )

    # ── Workflow builders ──────────────────────────────────────────────────────

    def _build_text_only_workflow(
        self,
        positive: str,
        negative: str,
        output_path: Path,
    ) -> dict[str, Any]:
        """
        Panel 1: pure text-to-image with SDXL + Comic LoRA.
        No IP-Adapter conditioning.
        """
        seed = int(time.time() * 1000) % (2**32)
        filename_prefix = output_path.stem

        return {
            # 1. Load checkpoint
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": self.checkpoint,
                },
            },
            # 2. Apply Comic LoRA
            "2": {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["1", 0],
                    "clip": ["1", 1],
                    "lora_name": self.lora_name,
                    "strength_model": self.lora_strength,
                    "strength_clip": self.lora_strength,
                },
            },
            # 3. Positive conditioning
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": positive,
                    "clip": ["2", 1],
                },
            },
            # 4. Negative conditioning
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["2", 1],
                },
            },
            # 5. Empty latent
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1,
                },
            },
            # 6. KSampler
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["2", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0],
                    "seed": seed,
                    "steps": self.steps,
                    "cfg": self.cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                },
            },
            # 7. VAE Decode
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["1", 2],
                },
            },
            # 8. Save image
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["7", 0],
                    "filename_prefix": filename_prefix,
                },
            },
        }

    def _build_ipadapter_workflow(
        self,
        positive: str,
        negative: str,
        output_path: Path,
    ) -> dict[str, Any]:
        """
        Panels 2-5: SDXL + Comic LoRA + IP-Adapter reference conditioning.
        The reference image is self.reference_image_path (panel 1 output).
        """
        seed = int(time.time() * 1000) % (2**32)
        filename_prefix = output_path.stem

        # Load reference image and encode as base64 for ComfyUI
        ref_image_b64 = self._load_image_b64(self.reference_image_path)

        return {
            # 1. Load checkpoint
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": self.checkpoint,
                },
            },
            # 2. Apply Comic LoRA
            "2": {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["1", 0],
                    "clip": ["1", 1],
                    "lora_name": self.lora_name,
                    "strength_model": self.lora_strength,
                    "strength_clip": self.lora_strength,
                },
            },
            # 3. Load IP-Adapter model
            "3": {
                "class_type": "IPAdapterModelLoader",
                "inputs": {
                    "ipadapter_file": self.ipadapter_model,
                },
            },
            # 4. Load CLIP vision encoder
            "4": {
                "class_type": "CLIPVisionLoader",
                "inputs": {
                    "clip_name": "clip_vision_g.safetensors",
                },
            },
            # 5. Load reference image
            "5": {
                "class_type": "ETN_LoadImageBase64",
                "inputs": {
                    "image": ref_image_b64,
                },
            },
            # 6. Apply IP-Adapter
            "6": {
                "class_type": "IPAdapter",
                "inputs": {
                    "model": ["2", 0],
                    "ipadapter": ["3", 0],
                    "image": ["5", 0],
                    "clip_vision": ["4", 0],
                    "weight": self.ipadapter_weight,
                    "noise": 0.0,
                    "weight_type": "original",
                    "start_at": 0.0,
                    "end_at": 1.0,
                    "unfold_batch": False,
                },
            },
            # 7. Positive conditioning
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": positive,
                    "clip": ["2", 1],
                },
            },
            # 8. Negative conditioning
            "8": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["2", 1],
                },
            },
            # 9. Empty latent
            "9": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1,
                },
            },
            # 10. KSampler (IP-Adapter conditioned model)
            "10": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["6", 0],
                    "positive": ["7", 0],
                    "negative": ["8", 0],
                    "latent_image": ["9", 0],
                    "seed": seed,
                    "steps": self.steps,
                    "cfg": self.cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                },
            },
            # 11. VAE Decode
            "11": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["10", 0],
                    "vae": ["1", 2],
                },
            },
            # 12. Save image
            "12": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["11", 0],
                    "filename_prefix": filename_prefix,
                },
            },
        }

    # ── ComfyUI communication ─────────────────────────────────────────────────

    def _submit_and_wait(self, workflow: dict[str, Any]) -> None:
        """Submit workflow to ComfyUI and poll until complete."""
        client_id = str(uuid.uuid4())
        prompt_id = self._queue_prompt(workflow, client_id)
        self._wait_for_completion(prompt_id, client_id)

    def _queue_prompt(self, workflow: dict[str, Any], client_id: str) -> str:
        payload = {"prompt": workflow, "client_id": client_id}
        url = f"{self.base_url}/prompt"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        data = resp.json()
        prompt_id: str = data["prompt_id"]
        log.debug("Queued prompt_id=%s", prompt_id)
        return prompt_id

    def _wait_for_completion(self, prompt_id: str, client_id: str) -> None:
        """Poll /history until the prompt is complete."""
        deadline = time.monotonic() + GENERATION_TIMEOUT
        url = f"{self.base_url}/history/{prompt_id}"

        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                data = resp.json()
                if prompt_id in data:
                    status = data[prompt_id].get("status", {})
                    if status.get("completed", False):
                        return
                    if status.get("status_str") == "error":
                        messages = status.get("messages", [])
                        raise RuntimeError(
                            f"ComfyUI reported error: {messages}"
                        )
            except httpx.HTTPError as exc:
                log.warning("Poll request failed: %s", exc)

        raise TimeoutError(
            f"ComfyUI did not complete within {GENERATION_TIMEOUT}s"
        )

    def _load_image_b64(self, path: Path) -> str:
        """Load an image file and return as base64 string."""
        if path is None or not path.exists():
            raise RuntimeError(
                f"Reference image not found at {path}. "
                f"Panel 1 must be generated before IP-Adapter panels."
            )
        raw = path.read_bytes()
        return base64.b64encode(raw).decode("ascii")