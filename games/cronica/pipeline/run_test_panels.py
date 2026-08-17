"""
Full-pipeline integration test:
  4 Players × 2 Ingredients
  → CreativeDirector
  → OllamaStoryLLM
  → PanelCompositionOrchestrator
  → ComfyUI → PNG

PURPOSE:
- Test 8 player ingredients simultaneously.
- Verify all ingredients survive into the story.
- Verify ingredients are visually represented in image_prompt_en.
- Verify concrete ingredients remain visually recognizable.
- Verify abstract ingredients are translated into visible behavior/emotion.
- Verify different players remain distinguishable.
- Verify comic/illustrated visual style.
- Stress-test the story → image pipeline with more players.

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
from pipeline.providers.story_llm_provider import (
    PlayerAnswers,
    PlayerAnswerItem,
)
from pipeline.providers.panel_composition_orchestrator import (
    PanelCompositionOrchestrator,
)


# ── Player inputs ─────────────────────────────────────────────────────────────
#
# 4 players × 2 ingredients = 8 total ingredients.
#
# The ingredients are deliberately visually distinct.
#
# Ana:
#   OBJECT   = purple bicycle
#   LOCATION = Venice
#
# Bogdan:
#   OBJECT   = golden key
#   CONCEPT  = jealousy
#
# Carmen:
#   OBJECT   = blue parrot
#   PROFESSION = magician
#
# David:
#   OBJECT   = birthday cake
#   CONCEPT  = fear
#
# The goal is to see whether ALL EIGHT survive into the story
# and become visible elements of the generated panels.
#

player_answers_raw = [

    PlayerAnswer(
        player_id="p1",
        nickname="Ana",
        answers=[
            {
                "prompt_id": "p0",
                "category": "CONCRET",
                "answer_text": "bicicletă mov",
            },
            {
                "prompt_id": "p1",
                "category": "LOC",
                "answer_text": "Veneția",
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
                "answer_text": "cheie aurie",
            },
            {
                "prompt_id": "p3",
                "category": "ABSTRACT",
                "answer_text": "gelozie",
            },
        ],
    ),

    PlayerAnswer(
        player_id="p3",
        nickname="Carmen",
        answers=[
            {
                "prompt_id": "p4",
                "category": "CONCRET",
                "answer_text": "papagal albastru",
            },
            {
                "prompt_id": "p5",
                "category": "PROFESSION",
                "answer_text": "magician",
            },
        ],
    ),

    PlayerAnswer(
        player_id="p4",
        nickname="David",
        answers=[
            {
                "prompt_id": "p6",
                "category": "CONCRET",
                "answer_text": "tort de ziua de naștere",
            },
            {
                "prompt_id": "p7",
                "category": "ABSTRACT",
                "answer_text": "frică",
            },
        ],
    ),
]


# ── Step 1: Creative Director ─────────────────────────────────────────────────

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


# ── Step 2: Build PlayerAnswers for OllamaStoryLLM ────────────────────────────

print("\n=== Step 2: Build PlayerAnswers for LLM ===")

archetype_map = {
    arch.player_id: arch
    for arch in brief.archetypes
    if arch.player_id
}

player_answers_llm: list[PlayerAnswers] = []


for pa in player_answers_raw:

    arch = archetype_map.get(pa.player_id)

    archetype_key = (
        arch.key
        if arch
        else "personaj"
    )

    archetype_name = (
        arch.name_ro
        if arch
        else "Personaj"
    )

    ingredient_roles = (
        arch.ingredient_roles
        if arch
        else {}
    )

    items = []

    for answer in pa.answers:

        role = ingredient_roles.get(
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
                category=answer.get(
                    "category",
                    "CONCRET",
                ),
                ingredient_role=ingredient_role,
                answer_text=answer.get(
                    "answer_text",
                    "",
                ),
            )
        )

    player_answers_llm.append(
        PlayerAnswers(
            player_id=pa.player_id,
            nickname=pa.nickname,
            archetype_key=archetype_key,
            archetype_name_ro=archetype_name,
            answers=items,
        )
    )

    print(
        f"  {pa.nickname}: "
        f"{[
            i.answer_text + ' → ' + i.ingredient_role
            for i in items
        ]}"
    )


# ── Step 3: Story Generation ─────────────────────────────────────────────────

print(
    "\n=== Step 3: OllamaStoryLLM story generation "
    "(this takes ~20-30s) ==="
)

llm = OllamaStoryLLM()

story = llm.generate_story_with_retry(
    brief,
    player_answers_llm,
    max_attempts=2,
)

print(f"Story title: {story.title}")
print(f"Panels:      {len(story.panels)}")


# ── Step 4: Ingredient preservation check ────────────────────────────────────

print("\n=== Step 4: Ingredient preservation check ===")

all_story_text = " ".join(
    [
        story.title,

        *[
            panel.description_ro
            for panel in story.panels
        ],

        *[
            panel.narrator_line_ro
            for panel in story.panels
        ],

        *[
            panel.dialogue_ro or ""
            for panel in story.panels
        ],
    ]
).lower()


required_ingredients = {
    "bicicletă": "purple bicycle",
    "veneția": "Venice",
    "cheie aurie": "golden key",
    "gelozie": "jealousy",
    "papagal albastru": "blue parrot",
    "magician": "magician",
    "tort de ziua de naștere": "birthday cake",
    "frică": "fear",
}


print("\nStory-level ingredient preservation:")

for ingredient, label in required_ingredients.items():

    found = ingredient.lower() in all_story_text

    status = (
        "✓ FOUND"
        if found
        else "✗ MISSING"
    )

    print(
        f"  {status}: {label}"
    )


# ── Step 5: Image-prompt ingredient check ────────────────────────────────────

print(
    "\n=== Step 5: Image-prompt ingredient check ==="
)

all_image_prompts = " ".join(
    [
        panel.image_prompt_en
        for panel in story.panels
    ]
).lower()


# These are intentionally broad visual checks.
# The exact English wording may vary depending on Ollama.
#
# We mainly want to know whether the concept is reaching
# the image prompts at all.

visual_checks = {
    "bicicletă": [
        "bicycle",
        "bike",
    ],

    "veneția": [
        "venice",
        "venetian",
        "canal",
        "gondola",
    ],

    "cheie aurie": [
        "golden key",
        "gold key",
    ],

    "gelozie": [
        "jealous",
        "jealousy",
        "jealous expression",
    ],

    "papagal albastru": [
        "blue parrot",
        "parrot",
    ],

    "magician": [
        "magician",
        "magical",
        "magic",
    ],

    "tort de ziua de naștere": [
        "birthday cake",
        "cake",
    ],

    "frică": [
        "fear",
        "fearful",
        "frightened",
        "afraid",
        "terrified",
    ],
}


for ingredient, keywords in visual_checks.items():

    found_keyword = next(
        (
            keyword
            for keyword in keywords
            if keyword.lower() in all_image_prompts
        ),
        None,
    )

    if found_keyword:
        print(
            f"  ✓ VISUALIZED: "
            f"{ingredient} → {found_keyword}"
        )
    else:
        print(
            f"  ✗ NOT VISUALIZED: "
            f"{ingredient}"
        )


# ── Step 6: Panel details ────────────────────────────────────────────────────

print("\n=== Step 6: Panel details ===")

for panel in story.panels:

    print(
        f"\n--- Panel {panel.panel_index + 1} ---"
    )

    print(
        f"  Description:\n"
        f"    {panel.description_ro}"
    )

    print(
        f"  Image prompt:\n"
        f"    {panel.image_prompt_en}"
    )

    print(
        f"  Narrator:\n"
        f"    {panel.narrator_line_ro}"
    )

    print(
        f"  Dialogue:\n"
        f"    {panel.dialogue_ro or '(none)'}"
    )


# ── Step 7: Image generation ─────────────────────────────────────────────────

print(
    "\n=== Step 7: Generating images via ComfyUI "
    "(this takes ~30-60s per panel) ==="
)

out = Path(
    "output/test_run_4players"
)

result = (
    PanelCompositionOrchestrator()
    .generate_all_panels(
        brief,
        story,
        out,
    )
)


# ── Results ───────────────────────────────────────────────────────────────────

print("\n=== Results ===")

print(
    f"Output dir: "
    f"{out.resolve()}"
)

print(
    f"Panels OK:  "
    f"{result.success_count}"
)

print(
    f"Fallbacks:  "
    f"{result.fallback_count}"
)

for panel_result in result.panel_results:

    status = (
        "✓"
        if not panel_result.is_fallback
        else "✗ FALLBACK"
    )

    size = (
        panel_result.file_path.stat().st_size
        if panel_result.file_path.exists()
        else 0
    )

    print(
        f"  panel_{panel_result.panel_index + 1}.png  "
        f"{status}  "
        f"{size:,} bytes  "
        f"{panel_result.generation_seconds:.1f}s"
    )

    if panel_result.error:
        print(
            f"    Error: "
            f"{panel_result.error[:120]}"
        )