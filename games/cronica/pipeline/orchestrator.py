"""
M4.1 — AI Pipeline Orchestrator Shell

HTTP server that the Node.js platform server calls to run the AI pipeline
for a single round. Coordinates all pipeline steps sequentially and reports
completion (or failure) back to the Node.js server.

Endpoints:
    POST /pipeline/run      — start the pipeline for a round
    POST /pipeline/cancel   — cancel a running pipeline (best-effort)
    GET  /pipeline/status   — query current pipeline status
    GET  /health            — liveness check

The pipeline runs steps sequentially to manage VRAM:
    1. Creative Director (pure Python — no VRAM)
    2. Story generation via LLM (Ollama — uses VRAM, then released)
    3. Image generation via ComfyUI (FLUX.1 — uses VRAM, then released)
    4. TTS via ElevenLabs / Piper (CPU or API)

When all steps complete, this service POSTs to the Node.js server at
PLATFORM_BASE_URL/pipeline/complete with the round ID and output directory.

Environment variables (all optional with sensible defaults):
    PLATFORM_BASE_URL       Node.js server URL (default: http://127.0.0.1:3000)
    ORCHESTRATOR_PORT       Port for this service (default: 5100)
    OUTPUT_BASE_DIR         Root directory for pipeline output (default: ./output)
    OLLAMA_BASE_URL         Ollama API URL (default: http://127.0.0.1:11434)
    COMFYUI_BASE_URL        ComfyUI API URL (default: http://127.0.0.1:8188)
    ELEVENLABS_API_KEY      ElevenLabs key (optional; falls back to Piper if missing)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

# ── Configuration ─────────────────────────────────────────────────────────────

PLATFORM_BASE_URL: str = os.getenv("PLATFORM_BASE_URL", "http://127.0.0.1:3000")
ORCHESTRATOR_PORT: int = int(os.getenv("ORCHESTRATOR_PORT", "5100"))
OUTPUT_BASE_DIR: Path = Path(os.getenv("OUTPUT_BASE_DIR", "./output"))
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
COMFYUI_BASE_URL: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")


# ── Pipeline state ─────────────────────────────────────────────────────────────

class PipelineStep(str, Enum):
    IDLE = "idle"
    CREATIVE_DIRECTOR = "creative_director"
    STORY_GENERATION = "story_generation"
    IMAGE_GENERATION = "image_generation"
    TTS = "tts"
    NOTIFYING = "notifying"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStatus(BaseModel):
    round_id: int | None = None
    step: PipelineStep = PipelineStep.IDLE
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    output_dir: str | None = None
    duration_seconds: float | None = None


# Singleton pipeline state — only one pipeline runs at a time.
_status = PipelineStatus()
_cancel_event: asyncio.Event = asyncio.Event()


# ── Request / Response models ─────────────────────────────────────────────────

class PlayerAnswerItem(BaseModel):
    """One player's submitted ingredient answers."""
    player_id: str
    nickname: str
    answers: list[dict[str, str]] = Field(
        description="List of {prompt_id, category, answer_text} dicts"
    )


class PipelineRunRequest(BaseModel):
    round_id: int = Field(description="SQLite round ID from the platform server")
    player_answers: list[PlayerAnswerItem] = Field(
        description="All active players' answers for this round"
    )
    round_history: list[str] = Field(
        default_factory=list,
        description="Genre keys from most-recent to oldest (for genre avoidance)"
    )
    output_dir: str | None = Field(
        default=None,
        description="Override output directory. Defaults to OUTPUT_BASE_DIR/round_{round_id}"
    )
    seed: int | None = Field(
        default=None,
        description="Optional seed for reproducible pipeline runs (debugging)"
    )


class PipelineRunResponse(BaseModel):
    accepted: bool
    round_id: int
    output_dir: str
    message: str


class PipelineCancelResponse(BaseModel):
    cancelled: bool
    message: str


# ── Application lifecycle ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("CRONICĂ Pipeline Orchestrator starting up")
    log.info("  Platform URL : %s", PLATFORM_BASE_URL)
    log.info("  Ollama URL   : %s", OLLAMA_BASE_URL)
    log.info("  ComfyUI URL  : %s", COMFYUI_BASE_URL)
    log.info("  Output dir   : %s", OUTPUT_BASE_DIR.resolve())
    yield
    log.info("Orchestrator shutting down")


app = FastAPI(
    title="CRONICĂ Pipeline Orchestrator",
    description="Sequential AI pipeline for AGORA/CRONICĂ round generation.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness check — always returns 200 if the process is running."""
    return {"status": "ok", "step": _status.step.value}


@app.get("/pipeline/status", response_model=PipelineStatus)
async def pipeline_status() -> PipelineStatus:
    """Return the current pipeline status."""
    return _status


@app.post("/pipeline/run", response_model=PipelineRunResponse)
async def pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
) -> PipelineRunResponse:
    """
    Start the pipeline for a round.

    Returns 409 if a pipeline is already running.
    Returns 202 (via response body accepted=True) when the pipeline is accepted.
    The pipeline runs asynchronously; completion is reported via the platform
    server's POST /pipeline/complete endpoint.
    """
    if _status.step not in (
        PipelineStep.IDLE,
        PipelineStep.COMPLETE,
        PipelineStep.FAILED,
        PipelineStep.CANCELLED,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pipeline is already running for round {_status.round_id} "
                f"(step: {_status.step.value}). "
                "Cancel it first or wait for completion."
            ),
        )

    # Resolve output directory
    out_dir = Path(request.output_dir) if request.output_dir else (
        OUTPUT_BASE_DIR / f"round_{request.round_id}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # Reset cancel flag and start the pipeline
    _cancel_event.clear()
    background_tasks.add_task(
        _run_pipeline,
        request=request,
        output_dir=out_dir,
    )

    log.info(
        "Pipeline accepted for round %d → %s",
        request.round_id,
        out_dir,
    )

    return PipelineRunResponse(
        accepted=True,
        round_id=request.round_id,
        output_dir=str(out_dir),
        message=f"Pipeline started for round {request.round_id}",
    )


@app.post("/pipeline/cancel", response_model=PipelineCancelResponse)
async def pipeline_cancel() -> PipelineCancelResponse:
    """
    Request cancellation of the currently running pipeline.
    Cancellation is best-effort — steps that have already started may complete.
    """
    if _status.step in (
        PipelineStep.IDLE,
        PipelineStep.COMPLETE,
        PipelineStep.FAILED,
        PipelineStep.CANCELLED,
    ):
        return PipelineCancelResponse(
            cancelled=False,
            message="No pipeline is currently running.",
        )

    _cancel_event.set()
    log.info("Pipeline cancel requested for round %s", _status.round_id)
    return PipelineCancelResponse(
        cancelled=True,
        message=f"Cancellation requested for round {_status.round_id}.",
    )


# ── Pipeline runner ───────────────────────────────────────────────────────────

async def _run_pipeline(
    request: PipelineRunRequest,
    output_dir: Path,
) -> None:
    """
    Execute all pipeline steps sequentially.
    Updates _status at each step boundary.
    Reports completion to the platform server when done.
    """
    global _status

    _status = PipelineStatus(
        round_id=request.round_id,
        step=PipelineStep.IDLE,
        started_at=_now(),
        output_dir=str(output_dir),
    )
    start_time = time.monotonic()

    try:
        # ── Step 1: Creative Director ────────────────────────────────────
        await _set_step(PipelineStep.CREATIVE_DIRECTOR)
        brief = await _step_creative_director(request, output_dir)
        _check_cancel()

        # ── Step 2: Story Generation (LLM) ───────────────────────────────
        await _set_step(PipelineStep.STORY_GENERATION)
        story = await _step_story_generation(brief, request, output_dir)
        await _clear_vram("LLM")
        _check_cancel()

        # ── Step 3: Image Generation (ComfyUI) ───────────────────────────
        await _set_step(PipelineStep.IMAGE_GENERATION)
        await _step_image_generation(brief, story, output_dir)
        await _clear_vram("ComfyUI")
        _check_cancel()

        # ── Step 4: TTS ───────────────────────────────────────────────────
        await _set_step(PipelineStep.TTS)
        await _step_tts(brief, story, output_dir)
        _check_cancel()

        # ── Notify platform server ────────────────────────────────────────
        await _set_step(PipelineStep.NOTIFYING)
        duration = time.monotonic() - start_time
        await _notify_complete(
            round_id=request.round_id,
            output_dir=output_dir,
            duration=duration,
        )

        _status.step = PipelineStep.COMPLETE
        _status.completed_at = _now()
        _status.duration_seconds = duration
        log.info(
            "Pipeline complete for round %d in %.1fs",
            request.round_id,
            duration,
        )

    except _CancelledError:
        _status.step = PipelineStep.CANCELLED
        _status.completed_at = _now()
        log.warning("Pipeline cancelled for round %d", request.round_id)
        await _notify_failed(
            round_id=request.round_id,
            reason="Pipeline cancelled by request.",
        )

    except Exception as exc:  # noqa: BLE001
        duration = time.monotonic() - start_time
        _status.step = PipelineStep.FAILED
        _status.completed_at = _now()
        _status.duration_seconds = duration
        _status.error = str(exc)
        log.exception("Pipeline FAILED for round %d: %s", request.round_id, exc)
        await _notify_failed(
            round_id=request.round_id,
            reason=str(exc),
        )


# ── Pipeline step stubs ───────────────────────────────────────────────────────
# Each stub is a placeholder that will be replaced in M4.4–M6.2.
# They log their invocation and write a marker file so the integration test
# can verify the step was reached.

async def _step_creative_director(
    request: PipelineRunRequest,
    output_dir: Path,
) -> dict[str, Any]:
    """
    M3.6 — Creative Director.
    Runs the CreativeDirector.generate() and writes brief.json.
    Full implementation wired in when M4.1 is integrated with M3.6.
    """
    log.info("[Step 1] Creative Director — round %d", request.round_id)

    # Import here to avoid circular dependency issues during testing
    # when the creative_director package is not yet on the path.
    try:
        from .creative_director import CreativeDirector, PlayerAnswer

        player_answers = [
            PlayerAnswer(
                player_id=pa.player_id,
                nickname=pa.nickname,
                answers=pa.answers,
            )
            for pa in request.player_answers
        ]

        cd = CreativeDirector()
        brief_obj = cd.generate(
            player_answers=player_answers,
            round_history=request.round_history,
            round_id=request.round_id,
            seed=request.seed,
            output_dir=str(output_dir),
        )
        log.info(
            "[Step 1] Brief generated — genre: %s, panels: %d",
            brief_obj.genre_key,
            brief_obj.panel_count,
        )
        return brief_obj.to_dict()

    except ImportError:
        # Running in isolated test environment without the full package
        log.warning("[Step 1] CreativeDirector not available — writing stub brief.json")
        stub: dict[str, Any] = {
            "genre": "Telenovelă Românească",
            "genre_key": "telenovela_romaneasca",
            "panel_count": 5,
            "_stub": True,
        }
        (output_dir / "brief.json").write_text(
            __import__("json").dumps(stub, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return stub


async def _step_story_generation(
    brief: dict[str, Any],
    request: PipelineRunRequest,
    output_dir: Path,
) -> dict[str, Any]:
    """
    M4.4 / M4.6 — Ollama LLM story generation with post-generation validation.

    Calls OllamaStoryLLM.generate_story_with_retry() which:
      1. Builds the system prompt from the CreativeBrief (M4.5).
      2. Calls Ollama's /api/chat endpoint.
      3. Validates the response; retries once with error feedback on failure.

    M4.6 validation layer:
      - All player names must appear in the story.
      - All image prompts must be ASCII-only English strings.
      - Panel count must match brief.panel_count.
      - Each panel must have non-empty description, image prompt, and narrator line.
      - On two consecutive failures, a fallback minimal story is generated so
        the pipeline never crashes a round due to LLM failure.

    The final story (LLM-generated or fallback) is written to story.json.
    """
    import json as _json

    genre_key = brief.get("genre_key", "unknown")
    panel_count: int = int(brief.get("panel_count", 5))
    log.info("[Step 2] Story Generation — genre: %s, panels: %d", genre_key, panel_count)

    player_names = [pa.nickname for pa in request.player_answers]

    try:
        from .providers.ollama_story_llm import OllamaStoryLLM
        from .providers.story_llm_provider import PlayerAnswers, PlayerAnswerItem, Story
        from .creative_director.models import CreativeBrief

        # Reconstruct a CreativeBrief from the dict produced by Step 1.
        # Falls back gracefully if brief is a stub (missing required fields).
        brief_obj: Any = None
        if not brief.get("_stub"):
            try:
                brief_obj = CreativeBrief.from_dict(brief)
            except Exception as exc:
                log.warning(
                    "[Step 2] Could not reconstruct CreativeBrief from dict: %s — "
                    "generating fallback story",
                    exc,
                )

        if brief_obj is None:
            # brief is a stub or unparseable — generate fallback immediately
            story = Story.generate_fallback(
                panel_count=panel_count,
                player_names=player_names,
                genre_name=brief.get("genre", "Poveste"),
            )
            log.warning("[Step 2] Using fallback story (brief unavailable)")
        else:
            # Build PlayerAnswers list from the pipeline request.
            # The orchestrator receives flat dicts; we map them to PlayerAnswers
            # using the archetype assignments already in the CreativeBrief.
            archetype_map = {
                arch.player_id: arch
                for arch in brief_obj.archetypes
                if arch.player_id is not None
            }

            player_answers_list: list[PlayerAnswers] = []
            for pa in request.player_answers:
                arch = archetype_map.get(pa.player_id)
                archetype_key = arch.key if arch else "personaj"
                archetype_name_ro = arch.name_ro if arch else "Personaj"
                ingredient_roles = arch.ingredient_roles if arch else {}

                items = [
                    PlayerAnswerItem(
                        prompt_id=a["prompt_id"],
                        category=a.get("category", "CONCRET"),
                        ingredient_role=(
                            ingredient_roles.get(a["prompt_id"], "OBJECT").value
                            if hasattr(ingredient_roles.get(a["prompt_id"], "OBJECT"), "value")
                            else str(ingredient_roles.get(a["prompt_id"], "OBJECT"))
                        ),
                        answer_text=a.get("answer_text", ""),
                    )
                    for a in pa.answers
                ]

                player_answers_list.append(PlayerAnswers(
                    player_id=pa.player_id,
                    nickname=pa.nickname,
                    archetype_key=archetype_key,
                    archetype_name_ro=archetype_name_ro,
                    answers=items,
                ))

            llm = OllamaStoryLLM()
            story: Story

            try:
                story = llm.generate_story_with_retry(
                    brief_obj,
                    player_answers_list,
                    max_attempts=2,
                )
                # M4.6: final validation with player name check
                final_errors = story.validate(
                    panel_count,
                    expected_player_names=player_names,
                )
                if final_errors:
                    log.warning(
                        "[Step 2] Story passed retry but failed final validation "
                        "(%d error(s)) — using fallback. Errors: %s",
                        len(final_errors),
                        final_errors,
                    )
                    story = Story.generate_fallback(
                        panel_count=panel_count,
                        player_names=player_names,
                        genre_name=brief_obj.genre,
                    )
                else:
                    log.info("[Step 2] Story validated successfully")

            except Exception as exc:
                log.warning(
                    "[Step 2] LLM generation failed after all attempts: %s — "
                    "using fallback story",
                    exc,
                )
                story = Story.generate_fallback(
                    panel_count=panel_count,
                    player_names=player_names,
                    genre_name=getattr(brief_obj, "genre", "Poveste"),
                )

        story_dict = story.to_dict()
        (output_dir / "story.json").write_text(
            _json.dumps(story_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info(
            "[Step 2] story.json written — title: %s, panels: %d",
            story_dict.get("title", "?"),
            len(story_dict.get("panels", [])),
        )
        return story_dict

    except ImportError as exc:
        # Running in a test environment without the full AI stack.
        log.warning("[Step 2] OllamaStoryLLM not available (%s) — writing stub story.json", exc)
        stub_story: dict[str, Any] = {
            "title": "Povestea de test",
            "panels": [],
            "narrator_script": [],
            "image_prompts": [],
            "_stub": True,
        }
        (output_dir / "story.json").write_text(
            _json.dumps(stub_story, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return stub_story


async def _step_image_generation(
    brief: dict[str, Any],
    story: dict[str, Any],
    output_dir: Path,
) -> None:
    """
    M5.5 — Panel Composition Orchestrator.

    Runs the full panel generation loop:
      - Builds CharacterRoster (M5.2)
      - Builds per-panel ImagePrompts via StyleTokenInjector (M5.4)
      - Generates each panel via FluxImageGenerator (M5.3) sequentially
      - Retries each panel once on failure; writes a stub on repeated failure
      - Saves panel_1.png … panel_N.png and character_sheets.json

    If ComfyUI / FluxImageGenerator is unavailable, falls back to writing
    stub PNG marker files so the pipeline does not crash.
    """
    panel_count: int = int(brief.get("panel_count", 5))
    log.info("[Step 3] Panel Composition — %d panels", panel_count)

    try:
        from .providers.panel_composition_orchestrator import PanelCompositionOrchestrator
        from .providers.story_llm_provider import Story

        # Reconstruct Story object from the dict produced by Step 2.
        story_obj: Any = None
        if not story.get("_stub"):
            try:
                story_obj = Story.from_dict(story)
            except Exception as exc:
                log.warning(
                    "[Step 3] Could not reconstruct Story from dict: %s — "
                    "using stub panels",
                    exc,
                )

        if story_obj is None:
            # Story is a stub or unparseable — write placeholder PNGs
            _write_stub_panels(output_dir, panel_count)
            return

        # Reconstruct CreativeBrief if available; otherwise pass the dict
        # directly (PanelCompositionOrchestrator uses getattr with defaults).
        brief_obj: Any = brief
        if not brief.get("_stub"):
            try:
                from .creative_director.models import CreativeBrief
                brief_obj = CreativeBrief.from_dict(brief)
            except Exception as exc:
                log.warning(
                    "[Step 3] Could not reconstruct CreativeBrief: %s — "
                    "using dict fallback",
                    exc,
                )
                brief_obj = brief

        orchestrator = PanelCompositionOrchestrator()
        result = orchestrator.generate_all_panels(
            brief=brief_obj,
            story=story_obj,
            output_dir=output_dir,
        )

        log.info(
            "[Step 3] Panel composition done — %d ok, %d fallback, %.1fs",
            result.success_count,
            result.fallback_count,
            result.total_seconds,
        )

    except ImportError as exc:
        log.warning(
            "[Step 3] PanelCompositionOrchestrator not available (%s) — "
            "writing stub panels",
            exc,
        )
        _write_stub_panels(output_dir, panel_count)


def _write_stub_panels(output_dir: Path, panel_count: int) -> None:
    """Write minimal stub PNG marker files when image generation is unavailable."""
    for i in range(panel_count):
        stub = output_dir / f"panel_{i + 1}.png"
        if not stub.exists():
            stub.write_bytes(b"\x89PNG_STUB")
    log.info("[Step 3] %d stub panels written", panel_count)


async def _step_tts(
    brief: dict[str, Any],
    story: dict[str, Any],
    output_dir: Path,
) -> None:
    """
    M6.2 / M6.3 — ElevenLabs / Piper TTS.
    Placeholder: writes stub narration_N.wav marker files.
    """
    panel_count: int = brief.get("panel_count", 5)
    log.info("[Step 4] TTS — %d narration lines", panel_count)
    for i in range(panel_count):
        stub_wav = output_dir / f"narration_{i + 1}.wav"
        if not stub_wav.exists():
            stub_wav.write_bytes(b"RIFF_STUB")
    log.info("[Step 4] %d stub WAV files written", panel_count)


# ── VRAM management ───────────────────────────────────────────────────────────

async def _clear_vram(source: str) -> None:
    """
    Explicitly release VRAM after a GPU-intensive step.

    For Ollama: calls the Ollama REST API to unload the model from VRAM.
    For ComfyUI: no explicit API; relies on ComfyUI's own memory management.
    This is a best-effort call — failures are logged but do not abort the pipeline.
    """
    if source == "LLM":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Ollama: set keep_alive=0 to unload model immediately
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={"model": "llama3.1:8b", "keep_alive": 0},
                )
                if resp.status_code == 200:
                    log.info("VRAM cleared: Ollama model unloaded")
                else:
                    log.warning(
                        "VRAM clear (Ollama) returned HTTP %d", resp.status_code
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("VRAM clear (Ollama) failed (non-fatal): %s", exc)

    elif source == "ComfyUI":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # ComfyUI: free memory endpoint
                resp = await client.post(
                    f"{COMFYUI_BASE_URL}/free",
                    json={"unload_models": True, "free_memory": True},
                )
                if resp.status_code == 200:
                    log.info("VRAM cleared: ComfyUI memory freed")
                else:
                    log.warning(
                        "VRAM clear (ComfyUI) returned HTTP %d", resp.status_code
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("VRAM clear (ComfyUI) failed (non-fatal): %s", exc)


# ── Platform server notification ──────────────────────────────────────────────

async def _notify_complete(
    round_id: int,
    output_dir: Path,
    duration: float,
) -> None:
    """
    POST to the Node.js platform server to signal pipeline completion.
    Retries once on network failure.
    """
    url = f"{PLATFORM_BASE_URL}/pipeline/complete"
    payload = {
        "roundId": round_id,
        "outputDir": str(output_dir),
        "durationSeconds": round(duration, 1),
    }
    await _post_with_retry(url, payload, label="pipeline/complete")


async def _notify_failed(round_id: int, reason: str) -> None:
    """
    POST to the Node.js platform server to signal pipeline failure.
    Retries once on network failure.
    """
    url = f"{PLATFORM_BASE_URL}/pipeline/failed"
    payload = {"roundId": round_id, "reason": reason}
    await _post_with_retry(url, payload, label="pipeline/failed")


async def _post_with_retry(
    url: str,
    payload: dict[str, Any],
    label: str,
    max_attempts: int = 2,
) -> None:
    """POST JSON to url, retrying once on failure."""
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code < 300:
                    log.info("Notified platform: %s (HTTP %d)", label, resp.status_code)
                    return
                log.warning(
                    "Notification %s returned HTTP %d (attempt %d)",
                    label,
                    resp.status_code,
                    attempt,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Notification %s failed (attempt %d): %s",
                label,
                attempt,
                exc,
            )
        if attempt < max_attempts:
            await asyncio.sleep(2.0)

    log.error("All notification attempts failed for %s", label)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _CancelledError(Exception):
    """Raised when a cancel is requested between pipeline steps."""


def _check_cancel() -> None:
    """Raise _CancelledError if a cancel was requested."""
    if _cancel_event.is_set():
        raise _CancelledError("Pipeline cancelled")


async def _set_step(step: PipelineStep) -> None:
    """Update the current pipeline step in the shared status object."""
    global _status
    _status.step = step
    log.info("Pipeline step: %s (round %s)", step.value, _status.round_id)


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "games.cronica.pipeline.orchestrator:app",
        host="127.0.0.1",
        port=ORCHESTRATOR_PORT,
        reload=False,
        log_level="info",
    )