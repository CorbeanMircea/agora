"""
M5.1 — ImageGeneratorProvider Interface

Abstract base class that all image generation implementations must satisfy.
No ComfyUI-specific code lives here — only the contract.

Sources:
    GDD v0.2.1 Section 7.1 (Provider Interface Design)
    M5.1 completion criteria
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Input dataclasses ─────────────────────────────────────────────────────────

@dataclass
class ImagePrompt:
    """
    A single image generation request for one comic panel.

    Built by the Panel Composition Orchestrator (M5.5) from the Story's
    image_prompt_en and the CreativeBrief's visual style and camera rules.
    All text fields must be in English (ASCII-only) — FLUX.1 is English-trained.
    """

    # 0-based panel index this prompt generates.
    panel_index: int

    # The LLM-generated base image prompt (English, ASCII-only).
    # From Story.image_prompts[panel_index].
    base_prompt: str

    # Style tokens from the genre + format (English, comma-separated).
    # Appended to base_prompt by the generator.
    style_tokens_positive: list[str] = field(default_factory=list)

    # Negative style tokens to guide the model away from unwanted aesthetics.
    style_tokens_negative: list[str] = field(default_factory=list)

    # Camera/composition tokens for this specific panel (from CreativeBrief.camera_language).
    camera_tokens: str = ""

    # Character visual descriptions to inject into the prompt for each
    # character appearing in this panel. Built from CharacterSheet (M5.2).
    character_descriptions: list[str] = field(default_factory=list)

    def build_positive_prompt(self) -> str:
        """
        Assemble the final positive prompt string for ComfyUI.
        Combines base_prompt, camera_tokens, character_descriptions, and style_tokens_positive.
        """
        parts: list[str] = []
        if self.base_prompt.strip():
            parts.append(self.base_prompt.strip())
        if self.camera_tokens.strip():
            parts.append(self.camera_tokens.strip())
        parts.extend(d.strip() for d in self.character_descriptions if d.strip())
        parts.extend(t.strip() for t in self.style_tokens_positive if t.strip())
        return ", ".join(parts)

    def build_negative_prompt(self) -> str:
        """Assemble the final negative prompt string for ComfyUI."""
        return ", ".join(t.strip() for t in self.style_tokens_negative if t.strip())


@dataclass
class VisualStyle:
    """
    The visual style specification extracted from a CreativeBrief.

    Passed to every image generation call so each panel is stylistically
    consistent with the genre and presentation format selected by the
    Creative Director.
    """

    # Genre machine key (e.g. "telenovela_romaneasca") for lookup/logging.
    genre_key: str

    # Prose visual style description from the CreativeBrief (English).
    visual_style: str

    # Lighting mood description (English).
    lighting_mood: str

    # Dominant hex colour palette (e.g. ["#C0392B", "#E8DAEF"]).
    colour_palette: list[str] = field(default_factory=list)

    # Genre-level positive style tokens applied to every panel.
    style_tokens_positive: list[str] = field(default_factory=list)

    # Genre-level negative style tokens applied to every panel.
    style_tokens_negative: list[str] = field(default_factory=list)

    # CSS theme key from the format definition (for presenter, not image gen).
    css_theme_key: str = ""

    # Output image width in pixels (default 1024 for FLUX.1 schnell).
    width: int = 1024

    # Output image height in pixels (default 1024 for FLUX.1 schnell).
    height: int = 1024

    @classmethod
    def from_brief(cls, brief: Any) -> "VisualStyle":
        """
        Construct a VisualStyle from a populated CreativeBrief instance.

        Parameters
        ----------
        brief:
            A CreativeBrief instance (from creative_director.models).
        """
        return cls(
            genre_key=getattr(brief, "genre_key", "unknown"),
            visual_style=getattr(brief, "visual_style", ""),
            lighting_mood=getattr(brief, "lighting_mood", ""),
            colour_palette=list(getattr(brief, "colour_palette", [])),
            style_tokens_positive=[],  # populated by StyleTokenInjector (M5.4)
            style_tokens_negative=[],  # populated by StyleTokenInjector (M5.4)
        )


@dataclass
class PanelImage:
    """
    The output of a single panel generation call.

    Wraps the path to the generated PNG file and generation metadata.
    Consumed by the Panel Composition Orchestrator (M5.5) and ultimately
    loaded by the Tauri presenter (M7.2).
    """

    # 0-based panel index this image represents.
    panel_index: int

    # Absolute path to the generated PNG file.
    file_path: Path

    # Width of the generated image in pixels.
    width: int

    # Height of the generated image in pixels.
    height: int

    # Generation duration in seconds (for performance logging).
    generation_seconds: float = 0.0

    # The final positive prompt string used for generation (for debug/logging).
    prompt_used: str = ""

    # Whether this image is a placeholder/fallback (generated on failure).
    is_fallback: bool = False

    @property
    def exists(self) -> bool:
        """Return True if the output file exists on disk."""
        return self.file_path.exists()

    @property
    def file_size_bytes(self) -> int:
        """Return the file size in bytes, or 0 if the file does not exist."""
        if self.file_path.exists():
            return self.file_path.stat().st_size
        return 0


# ── Abstract provider ─────────────────────────────────────────────────────────

class ImageGeneratorProvider(ABC):
    """
    Abstract base class for image generation implementations.

    All concrete implementations (FluxImageGenerator for ComfyUI,
    future cloud providers) must satisfy this interface. The orchestrator
    and panel composition loop call only this interface — never the
    concrete class directly.

    GDD Section 7.1.
    """

    @abstractmethod
    def generate_panel(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        character_descriptions: list[str],
    ) -> PanelImage:
        """
        Generate a single comic panel image.

        Parameters
        ----------
        prompt:
            The fully assembled image prompt for this panel (English, ASCII).
            character_descriptions within the prompt are provided here as
            well as separately for implementations that handle them differently.
        style:
            The visual style specification from the CreativeBrief.
        character_descriptions:
            Visual descriptions of characters appearing in this panel,
            derived from CharacterSheet objects (M5.2). May be empty if
            the panel has no named characters.

        Returns
        -------
        PanelImage
            Wraps the path to the generated PNG and generation metadata.
            The file must exist on disk when this method returns.

        Raises
        ------
        ImageGenerationError
            If the panel cannot be generated and no fallback is available.
        RuntimeError
            On unexpected failures from the underlying generation service.
        """
        ...

    def generate_panel_with_fallback(
        self,
        prompt: ImagePrompt,
        style: VisualStyle,
        character_descriptions: list[str],
        fallback_path: Path,
    ) -> PanelImage:
        """
        Call generate_panel and return a fallback PanelImage on failure.

        The fallback writes a 1-byte placeholder PNG stub so the pipeline
        never crashes a round due to a single panel generation failure.
        The orchestrator retries once before falling back (M5.5).

        Parameters
        ----------
        prompt:
            The image prompt for this panel.
        style:
            The visual style from the CreativeBrief.
        character_descriptions:
            Character visual descriptions for this panel.
        fallback_path:
            Path where the fallback stub file will be written if generation
            fails.

        Returns
        -------
        PanelImage
            Either the successfully generated image or a fallback stub.
        """
        try:
            return self.generate_panel(prompt, style, character_descriptions)
        except Exception:
            # Write a minimal PNG stub so downstream steps have a file to reference.
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            if not fallback_path.exists():
                fallback_path.write_bytes(b"\x89PNG_FALLBACK")
            return PanelImage(
                panel_index=prompt.panel_index,
                file_path=fallback_path,
                width=style.width,
                height=style.height,
                is_fallback=True,
            )


# ── Custom exception ──────────────────────────────────────────────────────────

class ImageGenerationError(RuntimeError):
    """
    Raised when an image generation provider cannot produce a panel.

    Wraps provider-specific errors with context about which panel failed
    so the orchestrator can log and respond appropriately.
    """

    def __init__(self, panel_index: int, reason: str) -> None:
        self.panel_index = panel_index
        self.reason = reason
        super().__init__(f"Panel {panel_index} generation failed: {reason}")