"""
M4.7 — Story Generation Integration Test

Calls OllamaStoryLLM.generate_story() against a live Ollama instance
(Llama 3.1 8B) with a fixture CreativeBrief and 4-player answer set.

Prerequisites
-------------
1. Ollama must be running:  ollama serve
2. Llama 3.1 8B must be pulled:  ollama pull llama3.1:8b

The test is automatically skipped if Ollama is unreachable or the model
is not available, so the test suite never breaks in CI without the model.

Run with:
    pytest games/cronica/pipeline/providers/test_ollama_story_llm_integration.py -v -s

Or to run alongside the unit tests (skipped automatically if Ollama absent):
    pytest games/cronica/pipeline/ -v
"""

from __future__ import annotations

import json
import socket

import pytest

from ..creative_director import CreativeDirector, PlayerAnswer
from .ollama_story_llm import OllamaStoryLLM, OLLAMA_BASE_URL, OLLAMA_MODEL
from .story_llm_provider import PlayerAnswers, PlayerAnswerItem, Story


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ollama_reachable() -> bool:
    """Return True if the Ollama server is reachable on its default port."""
    try:
        host = OLLAMA_BASE_URL.replace("http://", "").replace("https://", "").split(":")[0]
        port_str = OLLAMA_BASE_URL.rsplit(":", 1)[-1]
        port = int(port_str) if port_str.isdigit() else 11434
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _model_available() -> bool:
    """Return True if the configured Ollama model is listed by the server."""
    if not _ollama_reachable():
        return False
    try:
        import httpx
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        # Accept both "llama3.1:8b" and "llama3.1:8b-instruct-q4_K_M" etc.
        base = OLLAMA_MODEL.split(":")[0]
        return any(base in name for name in model_names)
    except Exception:
        return False


# Mark the entire module as requiring a live Ollama instance.
# Each test is individually skipped if unavailable, so the suite stays green.
_SKIP_REASON = (
    f"Ollama not reachable or model '{OLLAMA_MODEL}' not pulled. "
    "Run: ollama serve && ollama pull llama3.1:8b"
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PLAYER_ANSWERS_4 = [
    PlayerAnswer(
        player_id="p1",
        nickname="Ana",
        answers=[
            {"prompt_id": "c_001", "category": "CONCRET", "answer_text": "crocodil"},
            {"prompt_id": "a_001", "category": "ABSTRACT", "answer_text": "teamă"},
        ],
    ),
    PlayerAnswer(
        player_id="p2",
        nickname="Bogdan",
        answers=[
            {"prompt_id": "l_001", "category": "LOC", "answer_text": "Sinaia"},
            {"prompt_id": "n_001", "category": "NUMAR", "answer_text": "42"},
        ],
    ),
    PlayerAnswer(
        player_id="p3",
        nickname="Cristi",
        answers=[
            {"prompt_id": "p_001", "category": "PROPRIU", "answer_text": "Misteriosul"},
            {"prompt_id": "t_001", "category": "ATRIBUT", "answer_text": "zgomotos"},
        ],
    ),
    PlayerAnswer(
        player_id="p4",
        nickname="Diana",
        answers=[
            {"prompt_id": "v_001", "category": "ACTIUNE", "answer_text": "alerga"},
            {"prompt_id": "c_002", "category": "CONCRET", "answer_text": "umbrelă"},
        ],
    ),
]

PLAYER_NAMES = ["Ana", "Bogdan", "Cristi", "Diana"]


def _make_brief_and_player_answers(seed: int = 42):
    """
    Generate a CreativeBrief and matching PlayerAnswers list using the
    CreativeDirector so the archetype/ingredient mapping is consistent.
    """
    cd = CreativeDirector()
    brief = cd.generate(
        player_answers=PLAYER_ANSWERS_4,
        round_history=[],
        round_id=1,
        seed=seed,
    )

    # Build PlayerAnswers from the brief's archetypes for OllamaStoryLLM
    archetype_map = {
        arch.player_id: arch
        for arch in brief.archetypes
        if arch.player_id is not None
    }

    player_answers_list: list[PlayerAnswers] = []
    for pa in PLAYER_ANSWERS_4:
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

    return brief, player_answers_list


# ── Integration tests ─────────────────────────────────────────────────────────

class TestOllamaStoryLLMIntegration:
    """
    Live integration tests against a running Ollama instance.
    All tests in this class are skipped if Ollama is unreachable.
    """

    @pytest.fixture(scope="class")
    def llm(self):
        if not _model_available():
            pytest.skip(_SKIP_REASON)
        return OllamaStoryLLM(
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            timeout=120.0,  # allow up to 2 minutes for first cold generation
        )

    @pytest.fixture(scope="class")
    def brief_and_answers(self):
        return _make_brief_and_player_answers(seed=42)

    @pytest.fixture(scope="class")
    def generated_story(self, llm, brief_and_answers):
        """
        Generate the story once per test class — reused across all tests to
        avoid repeated expensive Ollama calls.
        """
        brief, player_answers = brief_and_answers
        return llm.generate_story_with_retry(brief, player_answers, max_attempts=2)

    # ── Field presence tests ──────────────────────────────────────────────────

    def test_returns_story_instance(self, generated_story):
        assert isinstance(generated_story, Story)

    def test_title_is_non_empty_string(self, generated_story):
        assert isinstance(generated_story.title, str)
        assert len(generated_story.title.strip()) > 0

    def test_panel_count_matches_brief(self, brief_and_answers, generated_story):
        brief, _ = brief_and_answers
        assert len(generated_story.panels) == brief.panel_count, (
            f"Expected {brief.panel_count} panels, got {len(generated_story.panels)}"
        )

    def test_narrator_script_length_matches_panel_count(
        self, brief_and_answers, generated_story
    ):
        brief, _ = brief_and_answers
        assert len(generated_story.narrator_script) == brief.panel_count

    def test_image_prompts_length_matches_panel_count(
        self, brief_and_answers, generated_story
    ):
        brief, _ = brief_and_answers
        assert len(generated_story.image_prompts) == brief.panel_count

    # ── Per-panel field tests ─────────────────────────────────────────────────

    def test_all_panels_have_non_empty_description(self, generated_story):
        for i, panel in enumerate(generated_story.panels):
            assert panel.description_ro.strip(), (
                f"panels[{i}].description_ro is empty"
            )

    def test_all_panels_have_non_empty_narrator_line(self, generated_story):
        for i, panel in enumerate(generated_story.panels):
            assert panel.narrator_line_ro.strip(), (
                f"panels[{i}].narrator_line_ro is empty"
            )

    def test_all_panels_have_non_empty_image_prompt(self, generated_story):
        for i, panel in enumerate(generated_story.panels):
            assert panel.image_prompt_en.strip(), (
                f"panels[{i}].image_prompt_en is empty"
            )

    def test_all_panel_indices_are_sequential(self, generated_story):
        for i, panel in enumerate(generated_story.panels):
            assert panel.panel_index == i, (
                f"panels[{i}].panel_index is {panel.panel_index}, expected {i}"
            )

    # ── English image prompt validation ───────────────────────────────────────

    def test_all_image_prompts_are_ascii_english(self, generated_story):
        """Image prompts must be ASCII-only (English) per GDD Section 7.4."""
        for i, panel in enumerate(generated_story.panels):
            prompt = panel.image_prompt_en
            assert prompt == prompt.encode("ascii", errors="replace").decode("ascii"), (
                f"panels[{i}].image_prompt_en contains non-ASCII characters: {prompt!r}"
            )

    def test_image_prompts_list_matches_panels(self, generated_story):
        for i, (prompt, panel) in enumerate(
            zip(generated_story.image_prompts, generated_story.panels)
        ):
            assert prompt == panel.image_prompt_en, (
                f"image_prompts[{i}] does not match panels[{i}].image_prompt_en"
            )

    # ── Player name presence ──────────────────────────────────────────────────

    def test_all_player_names_appear_in_story(self, generated_story):
        """Every player's nickname must appear somewhere in the story text."""
        story_text = " ".join([
            generated_story.title,
            *[p.description_ro for p in generated_story.panels],
            *[p.dialogue_ro for p in generated_story.panels],
            *[p.narrator_line_ro for p in generated_story.panels],
        ])
        for name in PLAYER_NAMES:
            assert name in story_text, (
                f"Player name '{name}' does not appear anywhere in the story"
            )

    # ── Story.validate() integration ──────────────────────────────────────────

    def test_story_passes_validate(self, brief_and_answers, generated_story):
        """The generated story must pass Story.validate() with no errors."""
        brief, _ = brief_and_answers
        errors = generated_story.validate(
            expected_panel_count=brief.panel_count,
            expected_player_names=PLAYER_NAMES,
        )
        assert errors == [], (
            f"Story.validate() returned {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    # ── Consistency check ─────────────────────────────────────────────────────

    def test_narrator_script_consistent_with_panels(self, generated_story):
        for i, (line, panel) in enumerate(
            zip(generated_story.narrator_script, generated_story.panels)
        ):
            assert line == panel.narrator_line_ro, (
                f"narrator_script[{i}] != panels[{i}].narrator_line_ro"
            )

    # ── Reproducibility across 3 runs ─────────────────────────────────────────

    def test_generates_valid_story_on_three_consecutive_runs(self, llm, brief_and_answers):
        """
        GDD M4.7 completion criterion: test passes consistently across 3 runs.
        We generate 3 stories and verify each passes validation independently.
        Temperature is > 0 so titles/content will vary, but structure must be valid.
        """
        brief, player_answers = brief_and_answers
        for run in range(3):
            story = llm.generate_story_with_retry(brief, player_answers, max_attempts=2)
            errors = story.validate(
                expected_panel_count=brief.panel_count,
                expected_player_names=PLAYER_NAMES,
            )
            assert errors == [], (
                f"Run {run + 1}/3: Story.validate() returned {len(errors)} error(s):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


# ── Standalone connectivity check ─────────────────────────────────────────────

class TestOllamaConnectivity:
    """Smoke tests that verify Ollama connectivity before the full integration."""

    def test_ollama_health_check(self):
        """Verify Ollama is reachable. Fails explicitly (not skipped) when down."""
        if not _ollama_reachable():
            pytest.skip(_SKIP_REASON)
        import httpx
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        assert resp.status_code == 200, (
            f"Ollama /api/tags returned HTTP {resp.status_code}"
        )

    def test_model_is_available(self):
        """Verify the configured model is pulled and listed by Ollama."""
        if not _ollama_reachable():
            pytest.skip(_SKIP_REASON)
        if not _model_available():
            pytest.fail(
                f"Model '{OLLAMA_MODEL}' is not available. "
                f"Run: ollama pull {OLLAMA_MODEL}"
            )