"""
Full-pipeline integration test:
  Player answers → CreativeDirector → OllamaStoryLLM → PanelCompositionOrchestrator → PNG

Requires:
  - Ollama running with llama3.1:8b pulled
  - ComfyUI running with z_image_turbo_nvfp4.safetensors

Run from agora/games/cronica/:
  python -m pipeline.run_test_panels
"""
from pathlib import Path

from pipeline.creative_director import CreativeDirector, PlayerAnswer
from pipeline.creative_director.models import CreativeBrief
from pipeline.providers.ollama_story_llm import OllamaStoryLLM
from pipeline.providers.story_llm_provider import PlayerAnswers, PlayerAnswerItem
from pipeline.providers.panel_composition_orchestrator import PanelCompositionOrchestrator

# ── Player inputs ─────────────────────────────────────────────────────────────

player_answers_raw = [
    PlayerAnswer(
        player_id="p1",
        nickname="Ana",
        answers=[
            {"prompt_id": "p0", "category": "CONCRET",  "answer_text": "crocodil"},
            {"prompt_id": "p1", "category": "LOC",      "answer_text": "Buzău"},
        ],
    ),
    PlayerAnswer(
        player_id="p2",
        nickname="Bogdan",
        answers=[
            {"prompt_id": "p2", "category": "CONCRET",  "answer_text": "umbrelă"},
            {"prompt_id": "p3", "category": "ABSTRACT", "answer_text": "bucurie"},
        ],
    ),
]

# ── Step 1: Creative Director ─────────────────────────────────────────────────

print("=== Step 1: Creative Director ===")
brief: CreativeBrief = CreativeDirector().generate(player_answers_raw, [], seed=42)
print(f"Genre:       {brief.genre}")
print(f"Panel count: {brief.panel_count}")
for arch in brief.archetypes:
    print(f"  {arch.player_nickname} → {arch.name_ro} | roles: {arch.ingredient_roles}")

# ── Step 2: Build PlayerAnswers for OllamaStoryLLM ───────────────────────────

print("\n=== Step 2: Build PlayerAnswers for LLM ===")
archetype_map = {arch.player_id: arch for arch in brief.archetypes if arch.player_id}

player_answers_llm: list[PlayerAnswers] = []
for pa in player_answers_raw:
    arch = archetype_map.get(pa.player_id)
    archetype_key    = arch.key     if arch else "personaj"
    archetype_name   = arch.name_ro if arch else "Personaj"
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
    player_answers_llm.append(PlayerAnswers(
        player_id=pa.player_id,
        nickname=pa.nickname,
        archetype_key=archetype_key,
        archetype_name_ro=archetype_name,
        answers=items,
    ))
    print(f"  {pa.nickname}: {[i.answer_text + ' → ' + i.ingredient_role for i in items]}")

# ── Step 3: Story Generation via Ollama ──────────────────────────────────────

print("\n=== Step 3: OllamaStoryLLM story generation (this takes ~20-30s) ===")
llm = OllamaStoryLLM()
story = llm.generate_story_with_retry(brief, player_answers_llm, max_attempts=2)

print(f"Story title: {story.title}")
print(f"Panels:      {len(story.panels)}")

# ── Step 4: Print panel details before generation ────────────────────────────

print("\n=== Step 4: Panel details ===")
for panel in story.panels:
    print(f"\n--- Panel {panel.panel_index + 1} ---")
    print(f"  Description:  {panel.description_ro}")
    print(f"  Image prompt: {panel.image_prompt_en}")
    print(f"  Narrator:     {panel.narrator_line_ro}")
    print(f"  Dialogue:     {panel.dialogue_ro or '(none)'}")

# ── Step 5: Image generation via PanelCompositionOrchestrator ────────────────

print("\n=== Step 5: Generating images via ComfyUI (this takes ~30-60s per panel) ===")
out = Path("output/test_run")
result = PanelCompositionOrchestrator().generate_all_panels(brief, story, out)

# ── Results ───────────────────────────────────────────────────────────────────

print(f"\n=== Results ===")
print(f"Output dir: {out.resolve()}")
print(f"Panels OK:  {result.success_count}")
print(f"Fallbacks:  {result.fallback_count}")
for pr in result.panel_results:
    status = "✓" if not pr.is_fallback else "✗ FALLBACK"
    size = pr.file_path.stat().st_size if pr.file_path.exists() else 0
    print(f"  panel_{pr.panel_index + 1}.png  {status}  {size:,} bytes  {pr.generation_seconds:.1f}s")
    if pr.error:
        print(f"    Error: {pr.error[:120]}")