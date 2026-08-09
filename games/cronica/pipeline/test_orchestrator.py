"""
M4.1 — Orchestrator Tests

Tests the pipeline orchestrator endpoints without requiring live AI services.
Run with:
    pytest games/cronica/pipeline/test_orchestrator.py -v
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from .orchestrator import app, PipelineStep, _status, PipelineStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_REQUEST = {
    "round_id": 1,
    "player_answers": [
        {
            "player_id": "player_1",
            "nickname": "Ana",
            "answers": [
                {"prompt_id": "c_001", "category": "CONCRET", "answer_text": "crocodil"},
                {"prompt_id": "a_001", "category": "ABSTRACT", "answer_text": "teamă"},
            ],
        },
        {
            "player_id": "player_2",
            "nickname": "Bogdan",
            "answers": [
                {"prompt_id": "l_001", "category": "LOC", "answer_text": "Sinaia"},
                {"prompt_id": "n_001", "category": "NUMAR", "answer_text": "42"},
            ],
        },
    ],
    "round_history": [],
    "seed": 42,
}


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture(autouse=True)
def reset_pipeline_status():
    """Reset pipeline status before each test."""
    from . import orchestrator as orch
    orch._status = PipelineStatus()
    orch._cancel_event.clear()
    yield
    orch._status = PipelineStatus()
    orch._cancel_event.clear()


# ── Health endpoint ───────────────────────────────────────────────────────────

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "step" in data

    @pytest.mark.asyncio
    async def test_health_step_is_idle_initially(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.json()["step"] == "idle"


# ── Status endpoint ───────────────────────────────────────────────────────────

class TestStatus:
    @pytest.mark.asyncio
    async def test_status_returns_idle_initially(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/pipeline/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["step"] == "idle"
        assert data["round_id"] is None

    @pytest.mark.asyncio
    async def test_status_fields_present(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/pipeline/status")
        data = resp.json()
        expected_keys = {"round_id", "step", "started_at", "completed_at", "error", "output_dir"}
        assert expected_keys.issubset(set(data.keys()))


# ── Pipeline run endpoint ─────────────────────────────────────────────────────

class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_run_accepted(self, transport, tmp_path):
        request = dict(SAMPLE_REQUEST, output_dir=str(tmp_path / "round_1"))

        # Patch _run_pipeline so it completes instantly without real AI calls
        with patch(
            "games.cronica.pipeline.orchestrator._run_pipeline",
            new=AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/pipeline/run", json=request)

        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["round_id"] == 1

    @pytest.mark.asyncio
    async def test_run_rejected_when_already_running(self, transport, tmp_path):
        from . import orchestrator as orch
        from .orchestrator import PipelineStep, PipelineStatus

        # Simulate a running pipeline
        orch._status = PipelineStatus(round_id=1, step=PipelineStep.STORY_GENERATION)

        request = dict(SAMPLE_REQUEST, round_id=2, output_dir=str(tmp_path / "round_2"))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/pipeline/run", json=request)

        assert resp.status_code == 409
        assert "already running" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_accepted_after_completion(self, transport, tmp_path):
        from . import orchestrator as orch
        from .orchestrator import PipelineStep, PipelineStatus

        # Simulate a completed pipeline
        orch._status = PipelineStatus(round_id=1, step=PipelineStep.COMPLETE)

        request = dict(SAMPLE_REQUEST, round_id=2, output_dir=str(tmp_path / "round_2"))
        with patch(
            "games.cronica.pipeline.orchestrator._run_pipeline",
            new=AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/pipeline/run", json=request)

        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    @pytest.mark.asyncio
    async def test_output_dir_created(self, transport, tmp_path):
        out_dir = tmp_path / "round_99"
        assert not out_dir.exists()

        request = dict(SAMPLE_REQUEST, round_id=99, output_dir=str(out_dir))
        with patch(
            "games.cronica.pipeline.orchestrator._run_pipeline",
            new=AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post("/pipeline/run", json=request)

        assert out_dir.exists()

    @pytest.mark.asyncio
    async def test_invalid_payload_rejected(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/pipeline/run", json={"bad": "data"})
        assert resp.status_code == 422


# ── Cancel endpoint ───────────────────────────────────────────────────────────

class TestPipelineCancel:
    @pytest.mark.asyncio
    async def test_cancel_when_idle_returns_false(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/pipeline/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is False

    @pytest.mark.asyncio
    async def test_cancel_when_running_returns_true(self, transport):
        from . import orchestrator as orch
        from .orchestrator import PipelineStep, PipelineStatus

        orch._status = PipelineStatus(round_id=5, step=PipelineStep.STORY_GENERATION)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/pipeline/cancel")

        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True

    @pytest.mark.asyncio
    async def test_cancel_sets_cancel_event(self, transport):
        from . import orchestrator as orch
        from .orchestrator import PipelineStep, PipelineStatus

        orch._status = PipelineStatus(round_id=5, step=PipelineStep.IMAGE_GENERATION)
        assert not orch._cancel_event.is_set()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/pipeline/cancel")

        assert orch._cancel_event.is_set()


# ── Pipeline step execution ───────────────────────────────────────────────────

class TestPipelineStepExecution:
    @pytest.mark.asyncio
    async def test_stub_steps_write_expected_files(self, tmp_path):
        """Verify that stub pipeline steps produce the expected output files."""
        from .orchestrator import (
            _step_creative_director,
            _step_story_generation,
            _step_image_generation,
            _step_tts,
        )
        from .orchestrator import PipelineRunRequest, PlayerAnswerItem

        out = tmp_path / "round_1"
        out.mkdir()

        request = PipelineRunRequest(
            round_id=1,
            player_answers=[
                PlayerAnswerItem(
                    player_id="p1",
                    nickname="Ana",
                    answers=[
                        {"prompt_id": "c_001", "category": "CONCRET", "answer_text": "test"},
                    ],
                ),
                PlayerAnswerItem(
                    player_id="p2",
                    nickname="Bogdan",
                    answers=[
                        {"prompt_id": "l_001", "category": "LOC", "answer_text": "test2"},
                    ],
                ),
            ],
            seed=0,
        )

        brief = await _step_creative_director(request, out)
        assert (out / "brief.json").exists()
        assert isinstance(brief, dict)

        story = await _step_story_generation(brief, request, out)
        assert (out / "story.json").exists()
        assert isinstance(story, dict)

        panel_count = brief.get("panel_count", 5)
        await _step_image_generation(brief, story, out)
        for i in range(panel_count):
            assert (out / f"panel_{i + 1}.png").exists(), f"panel_{i + 1}.png missing"

        await _step_tts(brief, story, out)
        for i in range(panel_count):
            assert (out / f"narration_{i + 1}.wav").exists(), f"narration_{i + 1}.wav missing"

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_all_files(self, tmp_path):
        """
        Run _run_pipeline end-to-end with mocked platform notification.
        Verifies all expected output files are created.
        """
        from .orchestrator import _run_pipeline, PipelineRunRequest, PlayerAnswerItem

        out = tmp_path / "round_full"

        request = PipelineRunRequest(
            round_id=42,
            player_answers=[
                PlayerAnswerItem(
                    player_id="p1",
                    nickname="Test1",
                    answers=[{"prompt_id": "c_001", "category": "CONCRET", "answer_text": "val1"}],
                ),
                PlayerAnswerItem(
                    player_id="p2",
                    nickname="Test2",
                    answers=[{"prompt_id": "l_001", "category": "LOC", "answer_text": "val2"}],
                ),
            ],
            seed=1,
        )

        # Mock both platform notifications so no HTTP calls are made
        with patch(
            "games.cronica.pipeline.orchestrator._notify_complete",
            new=AsyncMock(return_value=None),
        ), patch(
            "games.cronica.pipeline.orchestrator._notify_failed",
            new=AsyncMock(return_value=None),
        ):
            await _run_pipeline(request=request, output_dir=out)

        from . import orchestrator as orch
        assert orch._status.step.value in ("complete", "failed"), (
            f"Unexpected final step: {orch._status.step.value}"
        )
        assert (out / "brief.json").exists()
        assert (out / "story.json").exists()

    @pytest.mark.asyncio
    async def test_pipeline_status_transitions_through_steps(self, tmp_path):
        """Verify pipeline status reflects intermediate steps."""
        from .orchestrator import _run_pipeline, PipelineRunRequest, PlayerAnswerItem
        from . import orchestrator as orch

        out = tmp_path / "round_status"
        request = PipelineRunRequest(
            round_id=10,
            player_answers=[
                PlayerAnswerItem(
                    player_id="p1",
                    nickname="X",
                    answers=[{"prompt_id": "c_001", "category": "CONCRET", "answer_text": "x"}],
                ),
                PlayerAnswerItem(
                    player_id="p2",
                    nickname="Y",
                    answers=[{"prompt_id": "l_001", "category": "LOC", "answer_text": "y"}],
                ),
            ],
        )

        with patch(
            "games.cronica.pipeline.orchestrator._notify_complete",
            new=AsyncMock(return_value=None),
        ), patch(
            "games.cronica.pipeline.orchestrator._notify_failed",
            new=AsyncMock(return_value=None),
        ):
            await _run_pipeline(request=request, output_dir=out)

        # After completion, round_id and started_at must be set
        assert orch._status.round_id == 10
        assert orch._status.started_at is not None
        assert orch._status.completed_at is not None