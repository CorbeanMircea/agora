"""
Ingredient Enforcer — deterministic post-processing step.

After the LLM generates a Story, scans each panel's image_prompt_en
and enforces that concrete player ingredients appear with exact colors.

Fixed: color+object check now requires the combined phrase, not just
both words independently anywhere in the prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("ingredient_enforcer")

_RO_COLOR_MAP: dict[str, str] = {
    "roșu": "red", "roșie": "red", "roșii": "red", "rosu": "red", "rosie": "red",
    "albastru": "blue", "albastră": "blue", "albastre": "blue",
    "verde": "green", "verzui": "greenish",
    "galben": "yellow", "galbenă": "yellow",
    "portocaliu": "orange", "portocalie": "orange",
    "mov": "purple", "violet": "purple", "violetă": "purple",
    "roz": "pink",
    "negru": "black", "neagră": "black", "negre": "black",
    "alb": "white", "albă": "white",
    "gri": "grey",
    "maro": "brown",
    "auriu": "golden", "aurie": "golden",
    "argintiu": "silver", "argintie": "silver",
    "transparent": "transparent",
}

_RO_OBJECT_MAP: dict[str, str] = {
    "bicicletă": "bicycle", "bicicleta": "bicycle", "biciclete": "bicycle",
    "papagal": "parrot",
    "cheie": "key", "cheia": "key", "chei": "key",
    "umbrelă": "umbrella", "umbrela": "umbrella",
    "tort": "birthday cake", "tortul": "birthday cake", "torturi": "birthday cake",
    "frigider": "refrigerator", "frigiderul": "refrigerator",
    "sicriu": "coffin", "sicriul": "coffin",
    "prăjitor": "toaster",
    "pajura": "eagle",
    "capra": "goat", "caprа": "goat",
    "dragon": "dragon",
    "mop": "mop",
    "sarmale": "stuffed cabbage rolls",
    "farfurie": "plate",
    "pălărie": "hat", "palarie": "hat",
    "ochelari": "glasses",
    "ceas": "watch",
    "telefon": "phone",
    "carte": "book",
    "scaun": "chair",
    "masă": "table", "masa": "table",
    "fereastră": "window", "fereastra": "window",
    "ușă": "door", "usa": "door",
    "geantă": "bag", "geanta": "bag",
    "rucsac": "backpack",
    "lampă": "lamp", "lampa": "lamp",
    "oglindă": "mirror", "oglinda": "mirror",
    "pictură": "painting", "pictura": "painting",
    "tablou": "painting", "tabloul": "painting",
}

_VISUAL_ROLES = {"OBJECT", "LOCATION", "CHARACTER", "NAME"}
_ABSTRACT_ROLES = {"ATMOSPHERE", "CONCEPT"}


@dataclass
class IngredientSpec:
    prompt_id: str
    answer_ro: str
    role: str
    english_desc: str       # canonical English e.g. "purple bicycle"
    color_en: str | None
    object_en: str | None
    is_concrete: bool
    combined_phrase: str | None  # e.g. "purple bicycle" — used for exact enforcement


def build_ingredient_specs(player_answers_llm: list) -> list[IngredientSpec]:
    specs: list[IngredientSpec] = []
    for pa in player_answers_llm:
        for ans in pa.answers:
            role = ans.ingredient_role
            answer_ro = ans.answer_text.strip()
            english_desc, color_en, object_en = _translate_ingredient(answer_ro, role)
            is_concrete = role in _VISUAL_ROLES

            # Build the combined phrase for exact matching
            if color_en and object_en:
                combined_phrase = f"{color_en} {object_en}"
            elif object_en:
                combined_phrase = object_en
            elif color_en:
                combined_phrase = color_en
            else:
                combined_phrase = english_desc

            specs.append(IngredientSpec(
                prompt_id=ans.prompt_id,
                answer_ro=answer_ro,
                role=role,
                english_desc=english_desc,
                color_en=color_en,
                object_en=object_en,
                is_concrete=is_concrete,
                combined_phrase=combined_phrase,
            ))
    return specs


def enforce_ingredients_in_story(story: any, specs: list[IngredientSpec]) -> any:
    """
    Post-process a Story to enforce ingredient presence in image_prompt_en.
    For each panel, checks description_ro + narrator_line_ro for ingredient
    mentions, then ensures they appear in image_prompt_en with correct color.
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

    from .story_llm_provider import Story
    return Story(
        title=story.title,
        panels=new_panels,
        narrator_script=[p.narrator_line_ro for p in new_panels],
        image_prompts=[p.image_prompt_en for p in new_panels],
    )


def _enforce_panel(panel: any, specs: list[IngredientSpec]) -> str:
    description_ro = panel.description_ro.lower()
    narrator_ro = panel.narrator_line_ro.lower()
    dialogue_ro = (panel.dialogue_ro or "").lower()
    combined_ro = description_ro + " " + narrator_ro + " " + dialogue_ro

    current_prompt = panel.image_prompt_en
    to_enforce: list[str] = []

    for spec in specs:
        if not spec.is_concrete:
            continue
        if not _ingredient_mentioned_in_ro(spec.answer_ro, combined_ro):
            continue
        if _ingredient_correctly_in_prompt(spec, current_prompt):
            continue

        log.info(
            "Enforcing '%s' → '%s' in panel %d",
            spec.answer_ro, spec.combined_phrase, panel.panel_index,
        )
        to_enforce.append(spec.combined_phrase)

    if to_enforce:
        # Replace wrong color references before appending
        corrected = _fix_color_in_prompt(current_prompt, specs)
        suffix = ", prominently featuring " + ", ".join(to_enforce)
        return corrected.rstrip(", .") + suffix

    # Even if no enforcement needed, fix any wrong colors
    return _fix_color_in_prompt(current_prompt, specs)


def _fix_color_in_prompt(prompt: str, specs: list[IngredientSpec]) -> str:
    """
    Replace wrong-color references in the prompt.
    e.g. if spec says "purple bicycle" but prompt says "blue bicycle", fix it.
    """
    result = prompt
    for spec in specs:
        if not (spec.color_en and spec.object_en):
            continue
        obj = spec.object_en
        correct_color = spec.color_en
        # Common wrong colors to check
        all_colors = ["red", "blue", "green", "yellow", "orange", "grey", "gray",
                      "black", "white", "brown", "pink", "golden", "silver", "purple"]
        for wrong_color in all_colors:
            if wrong_color == correct_color:
                continue
            wrong_phrase = f"{wrong_color} {obj}"
            correct_phrase = f"{correct_color} {obj}"
            if wrong_phrase in result.lower():
                # Case-insensitive replacement
                import re
                result = re.sub(
                    re.escape(wrong_phrase),
                    correct_phrase,
                    result,
                    flags=re.IGNORECASE,
                )
                log.info(
                    "Fixed color: '%s' → '%s' in prompt",
                    wrong_phrase, correct_phrase,
                )
    return result


def _ingredient_mentioned_in_ro(answer_ro: str, text_ro: str) -> bool:
    answer_lower = answer_ro.lower()
    if answer_lower in text_ro:
        return True
    words = answer_lower.split()
    if len(words) > 1:
        return all(w in text_ro for w in words)
    # Root match for Romanian declension
    normalized = _normalize_ro(answer_lower)
    if len(normalized) > 5:
        root = normalized[:len(normalized) - 2]
        if root in text_ro:
            return True
    return False


def _ingredient_correctly_in_prompt(spec: IngredientSpec, prompt: str) -> bool:
    """
    Check if the ingredient is correctly represented.
    For colored objects, the COMBINED PHRASE must appear (e.g. "purple bicycle"),
    not just the color somewhere and the object somewhere else.
    """
    prompt_lower = prompt.lower()

    if spec.combined_phrase:
        # Primary check: exact combined phrase
        if spec.combined_phrase.lower() in prompt_lower:
            return True

    # Secondary: object present but check if it has the WRONG color
    if spec.object_en and spec.color_en:
        has_object = spec.object_en.lower() in prompt_lower
        if has_object:
            # Object is present — check if it's paired with wrong color
            all_colors = ["red", "blue", "green", "yellow", "orange", "grey", "gray",
                          "black", "white", "brown", "pink", "golden", "silver", "purple"]
            correct_color = spec.color_en.lower()
            obj = spec.object_en.lower()
            # Find the object in prompt and check nearby color
            idx = prompt_lower.find(obj)
            if idx != -1:
                window = prompt_lower[max(0, idx-20):idx+len(obj)+20]
                for wrong_color in all_colors:
                    if wrong_color != correct_color and wrong_color in window:
                        # Wrong color is near the object — needs enforcement
                        return False
                if correct_color in window:
                    return True
            # Object present but no color context — needs enforcement
            return False

    if spec.object_en:
        return spec.object_en.lower() in prompt_lower

    if spec.color_en:
        return spec.color_en.lower() in prompt_lower

    return spec.english_desc.lower() in prompt_lower


def _translate_ingredient(answer_ro: str, role: str) -> tuple[str, str | None, str | None]:
    words = answer_ro.strip().lower().split()
    color_en: str | None = None
    object_en: str | None = None
    english_parts: list[str] = []

    for word in words:
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
            english_parts.append(word)

    english_desc = " ".join(english_parts) if english_parts else answer_ro

    if role == "LOCATION" and object_en is None and color_en is None:
        english_desc = f"{english_desc} setting"

    return english_desc, color_en, object_en


def _normalize_ro(word: str) -> str:
    replacements = {
        "ă": "a", "â": "a", "î": "i", "ș": "s", "ț": "t",
        "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ț": "T",
        "ş": "s", "ţ": "t",
    }
    result = word
    for ro_char, en_char in replacements.items():
        result = result.replace(ro_char, en_char)
    return result