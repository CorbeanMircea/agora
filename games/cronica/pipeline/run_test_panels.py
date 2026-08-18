"""
Simple 2-player integration test.

Run from:
  agora/games/cronica/

Command:
  python -m pipeline.run_test_panels

Tests:
  Player answers
  → Creative Director
  → Ollama story
  → image prompts
  → ComfyUI images
"""

from pathlib import Path

from pipeline.creative_director import CreativeDirector, PlayerAnswer
from pipeline.creative_director.models import CreativeBrief
from pipeline.providers.ollama_story_llm import OllamaStoryLLM
from pipeline.providers.story_llm_provider import PlayerAnswers, PlayerAnswerItem
from pipeline.providers.panel_composition_orchestrator import (
    PanelCompositionOrchestrator,
)


# ─────────────────────────────────────────────────────────────────────────────
# TEST INPUT
# ─────────────────────────────────────────────────────────────────────────────

player_answers_raw = [
    PlayerAnswer(
        player_id="p1",
        nickname="Ana",
        answers=[
            {
                "prompt_id": "p0",
                "category": "CONCRET",
                "answer_text": "umbrela roșie",
            },
            {
                "prompt_id": "p1",
                "category": "CONCRET",
                "answer_text": "bicicletă mov",
            },
        ],
    ),
    PlayerAnswer(
        player_id="p2",
        nickname="Bogdan",
        answers=[
            {
                "prompt_id": "p2",
                "category": "CONCRET",
                "answer_text": "papagal albastru",
            },
            {
                "prompt_id": "p3",
                "category": "CONCRET",
                "answer_text": "cheie aurie",
            },
        ],
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. CREATIVE DIRECTOR
# ─────────────────────────────────────────────────────────────────────────────

print("=== Step 1: Creative Director ===")

brief: CreativeBrief = CreativeDirector().generate(
    player_answers_raw,
    [],
    seed=42,
)

print(f"Genre:       {brief.genre}")
print(f"Panel count: {brief.panel_count}")

for arch in brief.archetypes:
    print(
        f"  {arch.player_nickname} → "
        f"{arch.name_ro} | roles: {arch.ingredient_roles}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. BUILD LLM INPUT
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 2: Build PlayerAnswers ===")

archetype_map = {
    arch.player_id: arch
    for arch in brief.archetypes
    if arch.player_id
}

player_answers_llm = []

for pa in player_answers_raw:

    arch = archetype_map.get(pa.player_id)

    roles = arch.ingredient_roles if arch else {}

    items = []

    for answer in pa.answers:

        role = roles.get(
            answer["prompt_id"],
            "OBJECT",
        )

        ingredient_role = (
            role.value
            if hasattr(role, "value")
            else str(role)
        )

        items.append(
            PlayerAnswerItem(
                prompt_id=answer["prompt_id"],
                category=answer.get("category", "CONCRET"),
                ingredient_role=ingredient_role,
                answer_text=answer["answer_text"],
            )
        )

    player_answers_llm.append(
        PlayerAnswers(
            player_id=pa.player_id,
            nickname=pa.nickname,
            archetype_key=arch.key if arch else "personaj",
            archetype_name_ro=arch.name_ro if arch else "Personaj",
            answers=items,
        )
    )

    print(
        f"  {pa.nickname}: "
        f"{[i.answer_text for i in items]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. STORY GENERATION
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 3: Story Generation ===")

llm = OllamaStoryLLM()

story = llm.generate_story_with_retry(
    brief,
    player_answers_llm,
    max_attempts=2,
)

print(f"Title:  {story.title}")
print(f"Panels: {len(story.panels)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. INGREDIENT CHECK
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 4: Ingredient Check ===")

ingredients = [
    ("umbrela roșie", "red umbrella"),
    ("bicicletă mov", "purple bicycle"),
    ("papagal albastru", "blue parrot"),
    ("cheie aurie", "golden key"),
]

story_text = " ".join(
    [
        story.title,
        *[p.description_ro for p in story.panels],
        *[p.narrator_line_ro for p in story.panels],
        *[
            p.dialogue_ro or ""
            for p in story.panels
        ],
    ]
).lower()

for ro, label in ingredients:

    found = ro.lower() in story_text

    print(
        f"  {'✓' if found else '✗'} "
        f"{label}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. IMAGE PROMPT CHECK
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 5: Image Prompt Check ===")

all_image_prompts = " ".join(
    p.image_prompt_en
    for p in story.panels
).lower()

checks = [
    ("umbrela", "red umbrella"),
    ("bicicletă", "purple bicycle"),
    ("papagal", "blue parrot"),
    ("cheie", "golden key"),
]

for keyword, label in checks:

    found = keyword.lower() in all_image_prompts

    print(
        f"  {'✓ VISUALIZED' if found else '✗ NOT VISUALIZED'}: "
        f"{label}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. PRINT PANELS
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 6: Panels ===")

for panel in story.panels:

    print(f"\n--- Panel {panel.panel_index + 1} ---")

    print(f"Description:")
    print(f"  {panel.description_ro}")

    print(f"Image prompt:")
    print(f"  {panel.image_prompt_en}")

    print(f"Narrator:")
    print(f"  {panel.narrator_line_ro}")

    print(f"Dialogue:")
    print(f"  {panel.dialogue_ro or '(none)'}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. GENERATE IMAGES
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 7: Generating Images ===")

out = Path("output/test_run_ingredients")

result = PanelCompositionOrchestrator().generate_all_panels(
    brief,
    story,
    out,
)


# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Results ===")

print(f"Output:   {out.resolve()}")
print(f"Success:  {result.success_count}")
print(f"Fallback: {result.fallback_count}")

for panel_result in result.panel_results:

    status = (
        "✓"
        if not panel_result.is_fallback
        else "✗ FALLBACK"
    )

    print(
        f"  panel_{panel_result.panel_index + 1}.png "
        f"{status} "
        f"{panel_result.generation_seconds:.1f}s"
    )

    if panel_result.error:
        print(
            f"    Error: {panel_result.error[:120]}"
        )