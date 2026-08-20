"""
Full-pipeline integration test: 2 Players × 2 Ingredients each.
Tests ingredient preservation through the complete pipeline.

Ingredients chosen to be visually unambiguous and color-specific:
  Ana:   purple bicycle (CONCRET/OBJECT), Venice (LOC/LOCATION)
  Bogdan: golden key (CONCRET/OBJECT), blue parrot (CONCRET/OBJECT)

VERIFICATION CHECKLIST:
  ✓ purple bicycle → must appear as "purple bicycle" in at least one image_prompt_en
  ✓ Venice → must appear as "Venice" or "venetian" in at least one image_prompt_en
  ✓ golden key → must appear as "golden key" in at least one image_prompt_en
  ✓ blue parrot → must appear as "blue parrot" in at least one image_prompt_en
  ✗ COLOR CHANGED if "blue bicycle", "red bicycle", etc. appears instead of "purple"
  ✗ MISSING if ingredient not found in any panel's image_prompt_en

Requires:
  - Ollama running with llama3.1:8b pulled
  - ComfyUI running with z_image_turbo_nvfp4.safetensors (or configured checkpoint)

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
from pipeline.providers.ingredient_enforcer import (
    build_ingredient_specs,
    enforce_ingredients_in_story,
    IngredientSpec,
)


# ── Player inputs ─────────────────────────────────────────────────────────────
#
# 2 players × 2 ingredients = 4 total.
# All ingredients are concrete, visually distinct, with specific colors.
# All categories are valid (CONCRET, LOC — from the 7 valid categories).
#

player_answers_raw = [
    PlayerAnswer(
        player_id="p1",
        nickname="Ana",
        answers=[
            {
                "prompt_id": "p0",
                "category": "CONCRET",
                "answer_text": "bicicletă mov",   # purple bicycle
            },
            {
                "prompt_id": "p1",
                "category": "LOC",
                "answer_text": "Veneția",          # Venice
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
                "answer_text": "cheie aurie",      # golden key
            },
            {
                "prompt_id": "p3",
                "category": "CONCRET",
                "answer_text": "papagal albastru", # blue parrot
            },
        ],
    ),
]

# Expected English terms that MUST appear in image prompts
REQUIRED_INGREDIENTS = [
    {
        "ro": "bicicletă mov",
        "must_contain": ["purple bicycle", "purple bike"],
        "must_not_contain": ["blue bicycle", "red bicycle", "green bicycle"],
        "label": "purple bicycle",
    },
    {
        "ro": "Veneția",
        "must_contain": ["venice", "venetian", "canal", "gondola"],
        "must_not_contain": [],
        "label": "Venice",
    },
    {
        "ro": "cheie aurie",
        "must_contain": ["golden key", "gold key"],
        "must_not_contain": ["silver key", "iron key"],
        "label": "golden key",
    },
    {
        "ro": "papagal albastru",
        "must_contain": ["blue parrot"],
        "must_not_contain": ["red bird", "red parrot", "green parrot"],
        "label": "blue parrot",
    },
]


def check_ingredient_in_prompts(
    ingredient: dict,
    all_image_prompts: list[str],
) -> tuple[str, str]:
    """
    Returns (status, detail) where status is one of:
      ✓ PRESERVED
      ✗ MISSING
      ✗ COLOR CHANGED
    """
    combined = " ".join(all_image_prompts).lower()

    # Check wrong colors first
    for wrong in ingredient.get("must_not_contain", []):
        if wrong.lower() in combined:
            return "✗ COLOR CHANGED", f"Found '{wrong}' instead of '{ingredient['label']}'"

    # Check correct presence
    for correct in ingredient["must_contain"]:
        if correct.lower() in combined:
            return "✓ PRESERVED", f"Found '{correct}' in image prompts"

    return "✗ MISSING", f"'{ingredient['label']}' not found in any image_prompt_en"


# ── Step 1: Creative Director ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 1: Creative Director ===")
print("=" * 60)

brief: CreativeBrief = CreativeDirector().generate(
    player_answers_raw,
    [],
    seed=7,
)

print(f"Genre:       {brief.genre}")
print(f"Panel count: {brief.panel_count}")
print(f"Format:      {brief.format}")

for arch in brief.archetypes:
    print(
        f"  {arch.player_nickname} → "
        f"{arch.name_ro} | roles: {arch.ingredient_roles}"
    )


# ── Step 2: Build PlayerAnswers for OllamaStoryLLM ────────────────────────────

print("\n" + "=" * 60)
print("=== Step 2: Build PlayerAnswers for LLM ===")
print("=" * 60)

archetype_map = {
    arch.player_id: arch
    for arch in brief.archetypes
    if arch.player_id
}

player_answers_llm: list[PlayerAnswers] = []

for pa in player_answers_raw:
    arch = archetype_map.get(pa.player_id)
    archetype_key = arch.key if arch else "personaj"
    archetype_name = arch.name_ro if arch else "Personaj"
    ingredient_roles = arch.ingredient_roles if arch else {}

    items = []
    for answer in pa.answers:
        role = ingredient_roles.get(answer["prompt_id"], "OBJECT")
        ingredient_role = (
            role.value if hasattr(role, "value") else str(role)
        )
        items.append(
            PlayerAnswerItem(
                prompt_id=answer["prompt_id"],
                category=answer.get("category", "CONCRET"),
                ingredient_role=ingredient_role,
                answer_text=answer.get("answer_text", ""),
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
        f"{[i.answer_text + ' → ' + i.ingredient_role for i in items]}"
    )

# Build ingredient specs for enforcement
ingredient_specs = build_ingredient_specs(player_answers_llm)
print("\nIngredient specs (for enforcement):")
for spec in ingredient_specs:
    print(f"  [{spec.role}] «{spec.answer_ro}» → '{spec.english_desc}'"
          + (f" (color: {spec.color_en})" if spec.color_en else "")
          + (f" (object: {spec.object_en})" if spec.object_en else ""))


# ── Step 3: Story Generation ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 3: OllamaStoryLLM story generation (~20-30s) ===")
print("=" * 60)

llm = OllamaStoryLLM()

story = llm.generate_story_with_retry(
    brief,
    player_answers_llm,
    max_attempts=2,
)

print(f"Story title: {story.title}")
print(f"Panels:      {len(story.panels)}")


# ── Step 4: Ingredient enforcement ────────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 4: Ingredient Enforcement ===")
print("=" * 60)

story_before = story
story = enforce_ingredients_in_story(story, ingredient_specs)

for i, (before, after) in enumerate(zip(story_before.panels, story.panels)):
    if before.image_prompt_en != after.image_prompt_en:
        print(f"  Panel {i}: prompt was extended by enforcer")
        added = after.image_prompt_en[len(before.image_prompt_en):]
        print(f"    ADDED: {added}")
    else:
        print(f"  Panel {i}: no enforcement needed")


# ── Step 5: Verification — story-level ────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 5: Ingredient verification — Story level ===")
print("=" * 60)

all_story_text = " ".join([
    story.title,
    *[p.description_ro for p in story.panels],
    *[p.narrator_line_ro for p in story.panels],
    *[p.dialogue_ro or "" for p in story.panels],
]).lower()

for ing in REQUIRED_INGREDIENTS:
    ro = ing["ro"].lower()
    # Romanian declension — strip ending for root match
    root = ro[:max(4, len(ro) - 2)]
    found = root in all_story_text or ro in all_story_text
    status = "✓" if found else "✗"
    print(f"  {status} Story contains ingredient: {ing['label']}")


# ── Step 6: Verification — image prompt level ─────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 6: Ingredient verification — Image prompts ===")
print("=" * 60)

all_image_prompts = [p.image_prompt_en for p in story.panels]

for ing in REQUIRED_INGREDIENTS:
    status, detail = check_ingredient_in_prompts(ing, all_image_prompts)
    print(f"  {status}: {ing['label']} — {detail}")

print()
print("Per-panel image prompts:")
for panel in story.panels:
    print(f"\n  Panel {panel.panel_index}:")
    print(f"    Description: {panel.description_ro[:100]}...")
    print(f"    Image prompt: {panel.image_prompt_en[:200]}...")


# ── Step 7: Image generation ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 7: Image generation via ComfyUI (~30s per panel) ===")
print("=" * 60)

out = Path("output/test_run_2players")

result = PanelCompositionOrchestrator().generate_all_panels(
    brief,
    story,
    out,
)


# ── Step 8: Final results ─────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("=== Step 8: Final Results ===")
print("=" * 60)

print(f"Output dir: {out.resolve()}")
print(f"Panels OK:  {result.success_count}")
print(f"Fallbacks:  {result.fallback_count}")
print()

for panel_result in result.panel_results:
    status = "✓" if not panel_result.is_fallback else "✗ FALLBACK"
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
        print(f"    Error: {panel_result.error[:120]}")

print()
print("=== INGREDIENT FINAL VERIFICATION ===")
final_prompts = [p.image_prompt_en for p in story.panels]
all_pass = True
for ing in REQUIRED_INGREDIENTS:
    status, detail = check_ingredient_in_prompts(ing, final_prompts)
    print(f"  {status}: {ing['label']} — {detail}")
    if "✗" in status:
        all_pass = False

print()
if all_pass:
    print("✓ ALL INGREDIENTS PRESERVED")
else:
    print("✗ SOME INGREDIENTS MISSING OR CHANGED — review prompts above")