"""
Ingredient Enforcer — deterministic post-processing step.

After the LLM generates a Story, this module scans each panel's
image_prompt_en and enforces that concrete player ingredients appear
with their exact colors and names.

Problem it solves:
  The LLM frequently changes ingredient colors or omits ingredients
  from image_prompt_en even when they appear in description_ro.
  Example: «bicicletă mov» (purple bicycle) → "blue bicycle" in prompt.

Solution:
  1. Build a map of ingredient_answer_text → canonical_english_description
     for every concrete ingredient (OBJECT, LOCATION, CHARACTER, NAME role).
  2. For each panel, check if the ingredient is referenced in description_ro.
  3. If yes and it's missing or color-wrong in image_prompt_en, append
     the exact English description to the prompt.

This is entirely deterministic — no LLM call involved.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

log = logging.getLogger("ingredient_enforcer")

# Romanian color words → English translations
# Used to detect color attributes in ingredient answers
_RO_COLOR_MAP: dict[str, str] = {
    "roșu": "red",
    "roșie": "red",
    "roșii": "red",
    "rosu": "red",
    "rosie": "red",
    "albastru": "blue",
    "albastră": "blue",
    "albastre": "blue",
    "verde": "green",
    "verzui": "greenish",
    "galben": "yellow",
    "galbenă": "yellow",
    "portocaliu": "orange",
    "portocalie": "orange",
    "mov": "purple",
    "violet": "purple",
    "violetă": "purple",
    "roz": "pink",
    "negru": "black",
    "neagră": "black",
    "negre": "black",
    "alb": "white",
    "albă": "white",
    "gri": "grey",
    "maro": "brown",
    "auriu": "golden",
    "aurie": "golden",
    "argintiu": "silver",
    "argintie": "silver",
    "transparent": "transparent",
    "translucid": "translucent",
}

# Romanian noun → English translation for common objects/creatures
_RO_OBJECT_MAP: dict[str, str] = {
    "bicicletă": "bicycle",
    "bicicleta": "bicycle",
    "biciclete": "bicycle",
    "papagal": "parrot",
    "cheie": "key",
    "cheia": "key",
    "chei": "key",
    "umbrelă": "umbrella",
    "umbrela": "umbrella",
    "tort": "birthday cake",
    "tortul": "birthday cake",
    "torturi": "birthday cake",
    "frigider": "refrigerator",
    "frigiderul": "refrigerator",
    "sicriu": "coffin",
    "sicriul": "coffin",
    "prăjitor": "toaster",
    "pajura": "eagle",
    "caprа": "goat",
    "dragon": "dragon",
    "mop": "mop",
    "sarmale": "stuffed cabbage rolls",
    "farfurie": "plate",
    "pălărie": "hat",
    "palarie": "hat",
    "ochelari": "glasses",
    "ceas": "watch",
    "telefon": "phone",
    "carte": "book",
    "scaun": "chair",
    "masă": "table",
    "masa": "table",
    "fereastră": "window",
    "fereastra": "window",
    "ușă": "door",
    "usa": "door",
    "geantă": "bag",
    "geanta": "bag",
    "rucsac": "backpack",
    "lampă": "lamp",
    "lampa": "lamp",
    "oglindă": "mirror",
    "oglinda": "mirror",
}

# Roles that should be enforced in image prompts (concrete visual things)
_VISUAL_ROLES = {"OBJECT", "LOCATION", "CHARACTER", "NAME"}

# Roles that need abstract→visual translation (not direct enforcement)
_ABSTRACT_ROLES = {"ATMOSPHERE", "CONCEPT"}


@dataclass
class IngredientSpec:
    """
    The canonical English visual description for one player ingredient.
    Built once from PlayerAnswers + IngredientRoles before story generation.
    """
    prompt_id: str
    answer_ro: str          # Original Romanian answer (e.g. "bicicletă mov")
    role: str               # IngredientRole string
    english_desc: str       # Canonical English description (e.g. "purple bicycle")
    color_en: str | None    # Extracted color in English, if any
    object_en: str | None   # Extracted object in English, if any
    is_concrete: bool       # True if this should appear literally in image prompts


def build_ingredient_specs(player_answers_llm: list) -> list[IngredientSpec]:
    """
    Build IngredientSpec list from PlayerAnswers (as used by OllamaStoryLLM).

    Parameters
    ----------
    player_answers_llm:
        List of PlayerAnswers objects with .answers list of PlayerAnswerItem.
    """
    specs: list[IngredientSpec] = []
    for pa in player_answers_llm:
        for ans in pa.answers:
            role = ans.ingredient_role
            answer_ro = ans.answer_text.strip()
            english_desc, color_en, object_en = _translate_ingredient(answer_ro, role)
            is_concrete = role in _VISUAL_ROLES
            specs.append(IngredientSpec(
                prompt_id=ans.prompt_id,
                answer_ro=answer_ro,
                role=role,
                english_desc=english_desc,
                color_en=color_en,
                object_en=object_en,
                is_concrete=is_concrete,
            ))
    return specs


def enforce_ingredients_in_story(story: any, specs: list[IngredientSpec]) -> any:
    """
    Post-process a Story to enforce ingredient presence in image_prompt_en.

    For each panel:
    1. Check which ingredients are referenced in description_ro.
    2. For concrete ingredients (OBJECT/LOCATION/CHARACTER/NAME) that appear
       in description_ro but are missing or color-wrong in image_prompt_en,
       append the exact English description.

    Returns a new Story with corrected image_prompt_en fields.
    """
    from .story_llm_provider import Story, PanelDescription

    new_panels = []
    for panel in story.panels:
        new_prompt = _enforce_panel(panel, specs)
        new_panels.append(PanelDescription(
            panel_index=panel.panel_index,
            description_ro=panel.description_ro,
            dialogue_ro=panel.dialogue_ro,
            image_prompt_en=new_prompt,
            narrator_line_ro=panel.narrator_line_ro,
            characters_in_panel=list(panel.characters_in_panel),
        ))

    new_narrator = [p.narrator_line_ro for p in new_panels]
    new_image_prompts = [p.image_prompt_en for p in new_panels]

    from .story_llm_provider import Story
    return Story(
        title=story.title,
        panels=new_panels,
        narrator_script=new_narrator,
        image_prompts=new_image_prompts,
    )


def _enforce_panel(panel: any, specs: list[IngredientSpec]) -> str:
    """
    Return a corrected image_prompt_en for one panel.
    """
    description_ro = panel.description_ro.lower()
    narrator_ro = panel.narrator_line_ro.lower()
    dialogue_ro = (panel.dialogue_ro or "").lower()
    combined_ro = description_ro + " " + narrator_ro + " " + dialogue_ro

    current_prompt = panel.image_prompt_en

    appended: list[str] = []

    for spec in specs:
        if not spec.is_concrete:
            continue

        # Check if this ingredient is mentioned in the Romanian text of this panel
        if not _ingredient_mentioned_in_ro(spec.answer_ro, combined_ro):
            continue

        # Check if the ingredient is correctly represented in the image prompt
        if _ingredient_correctly_in_prompt(spec, current_prompt):
            continue

        # Need to enforce it
        log.info(
            "Enforcing ingredient '%s' → '%s' in panel %d prompt",
            spec.answer_ro,
            spec.english_desc,
            panel.panel_index,
        )
        appended.append(f"[INGREDIENT: {spec.english_desc}]")

    if appended:
        suffix = ", prominently featuring " + ", ".join(
            s.replace("[INGREDIENT: ", "").replace("]", "") for s in appended
        )
        return current_prompt.rstrip(", .") + suffix

    return current_prompt


def _ingredient_mentioned_in_ro(answer_ro: str, text_ro: str) -> bool:
    """
    Check if the ingredient answer appears in the Romanian text.
    Handles partial matches (e.g. "bicicletă" in "bicicletei").
    """
    answer_lower = answer_ro.lower()
    # Try exact match first
    if answer_lower in text_ro:
        return True
    # Try word-by-word match for multi-word ingredients
    words = answer_lower.split()
    if len(words) > 1:
        # All words must appear somewhere in the text
        return all(w in text_ro for w in words)
    # Try root match (Romanian declension: bicicletă → biciclet)
    if len(answer_lower) > 5:
        root = answer_lower[:len(answer_lower) - 2]
        if root in text_ro:
            return True
    return False


def _ingredient_correctly_in_prompt(spec: IngredientSpec, prompt: str) -> bool:
    """
    Check if the ingredient is correctly represented in the image prompt.
    For colored objects, both the color AND the object must be present near each other.
    """
    prompt_lower = prompt.lower()

    if spec.object_en and spec.color_en:
        # Both color and object must be present
        has_object = spec.object_en.lower() in prompt_lower
        has_color = spec.color_en.lower() in prompt_lower
        if has_object and has_color:
            return True
        # Also check if the combined phrase is present
        combined = f"{spec.color_en.lower()} {spec.object_en.lower()}"
        return combined in prompt_lower

    if spec.object_en:
        return spec.object_en.lower() in prompt_lower

    if spec.color_en:
        return spec.color_en.lower() in prompt_lower

    # Fallback: check if the english_desc itself appears
    return spec.english_desc.lower() in prompt_lower


def _translate_ingredient(answer_ro: str, role: str) -> tuple[str, str | None, str | None]:
    """
    Translate a Romanian ingredient answer into an English visual description.

    Returns:
        (english_desc, color_en, object_en)
    """
    words = answer_ro.strip().lower().split()

    color_en: str | None = None
    object_en: str | None = None
    english_parts: list[str] = []

    for word in words:
        # Strip Romanian diacritics for lookup
        normalized = _normalize_ro(word)
        if normalized in _RO_COLOR_MAP:
            color_en = _RO_COLOR_MAP[normalized]
            english_parts.append(color_en)
        elif word in _RO_COLOR_MAP:
            color_en = _RO_COLOR_MAP[word]
            english_parts.append(color_en)
        elif normalized in _RO_OBJECT_MAP:
            object_en = _RO_OBJECT_MAP[normalized]
            english_parts.append(object_en)
        elif word in _RO_OBJECT_MAP:
            object_en = _RO_OBJECT_MAP[word]
            english_parts.append(object_en)
        else:
            # Keep the word as-is (might be a proper noun, place name, etc.)
            english_parts.append(word)

    if english_parts:
        english_desc = " ".join(english_parts)
    else:
        english_desc = answer_ro  # fallback to original

    # For LOCATION role, add "setting" suffix to make it clearer
    if role == "LOCATION" and object_en is None and color_en is None:
        english_desc = f"{english_desc} setting"

    return english_desc, color_en, object_en


def _normalize_ro(word: str) -> str:
    """
    Normalize a Romanian word by replacing diacritics with ASCII equivalents.
    """
    replacements = {
        "ă": "a", "â": "a", "î": "i", "ș": "s", "ț": "t",
        "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ț": "T",
        "ş": "s", "ţ": "t",  # older diacritic forms
    }
    result = word
    for ro_char, en_char in replacements.items():
        result = result.replace(ro_char, en_char)
    return result