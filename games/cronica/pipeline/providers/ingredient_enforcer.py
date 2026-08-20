"""
Ingredient Enforcer — Changes B and G.

B: Abstract ingredients get principle-based visual action translation.
   No hardcoded Romanian emotion words — works for any player input.
G: Kinetic verb verification — appends action if prompt is static.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

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
    "tort": "birthday cake", "tortul": "birthday cake",
    "frigider": "refrigerator", "frigiderul": "refrigerator",
    "sicriu": "coffin", "sicriul": "coffin",
    "prăjitor": "toaster",
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
    "masă": "table", "masa": "table",
    "geantă": "bag", "geanta": "bag",
    "rucsac": "backpack",
    "lampă": "lamp", "lampa": "lamp",
    "oglindă": "mirror", "oglinda": "mirror",
    "pictură": "painting", "pictura": "painting",
    "tablou": "painting", "tabloul": "painting",
    "magician": "magician",
    "dragon": "dragon",
    "zmeu": "kite",
    "tren": "train",
    "avion": "airplane",
    "pistol": "gun",
    "sabie": "sword",
    "coroană": "crown", "coroana": "crown",
    "valiză": "suitcase", "valiza": "suitcase",
}

_VISUAL_ROLES = {"OBJECT", "LOCATION", "CHARACTER", "NAME"}

# Change G: Kinetic verbs for detection
_KINETIC_VERBS: set[str] = {
    "crashes", "crash", "crashing",
    "grabs", "grab", "grabbing",
    "flees", "flee", "fleeing",
    "shoves", "shove", "shoving",
    "launches", "launch", "launching",
    "tumbles", "tumble", "tumbling",
    "dodges", "dodge", "dodging",
    "spins", "spin", "spinning",
    "slams", "slam", "slamming",
    "leaps", "leap", "leaping",
    "sprints", "sprint", "sprinting",
    "snatches", "snatch", "snatching",
    "collides", "collide", "colliding",
    "throws", "throw", "throwing",
    "catches", "catch", "catching",
    "yanks", "yank", "yanking",
    "careens", "careen", "careening",
    "stumbles", "stumble", "stumbling",
    "tackles", "tackle", "tackling",
    "swings", "swing", "swinging",
    "lunges", "lunge", "lunging",
    "topples", "topple", "toppling",
    "skids", "skid", "skidding",
    "hurls", "hurl", "hurling",
    "bolts", "bolt", "bolting",
    "plunges", "plunge", "plunging",
    "wrenches", "wrench", "wrenching",
    "flings", "fling", "flinging",
    "barrels", "barrel", "barreling",
    "explodes", "explode", "exploding",
    "loses control", "lose control",
    "careens toward", "slams into",
    "flailing", "diving", "skidding",
    "recoils", "recoil", "recoiling",
    "charges", "charge", "charging",
    "knocks", "knock", "knocking",
    "breaks", "break", "breaking",
    "shatters", "shatter", "shattering",
    "tears", "tear", "tearing",
    "rips", "rip", "ripping",
    "drags", "drag", "dragging",
    "pulls", "pull", "pulling",
    "pushes", "push", "pushing",
    "kicks", "kick", "kicking",
    "punches", "punch", "punching",
    "bounces", "bounce", "bouncing",
    "rolls", "roll", "rolling",
    "falls", "fall", "falling",
    "drops", "drop", "dropping",
    "flies", "fly", "flying",
    "soars", "soar", "soaring",
}


@dataclass
class IngredientSpec:
    prompt_id: str
    answer_ro: str
    role: str
    english_desc: str
    color_en: str | None
    object_en: str | None
    is_concrete: bool
    combined_phrase: str | None
    is_abstract: bool = False


def build_ingredient_specs(player_answers_llm: list) -> list[IngredientSpec]:
    specs: list[IngredientSpec] = []
    for pa in player_answers_llm:
        for ans in pa.answers:
            role = ans.ingredient_role
            answer_ro = ans.answer_text.strip()
            english_desc, color_en, object_en = _translate_ingredient(
                answer_ro, role
            )
            is_concrete = role in _VISUAL_ROLES
            is_abstract = role in ("ATMOSPHERE", "CONCEPT")

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
                is_abstract=is_abstract,
            ))
    return specs


def enforce_ingredients_in_story(story: any, specs: list[IngredientSpec]) -> any:
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

    current_prompt = _fix_color_in_prompt(panel.image_prompt_en, specs)

    to_prepend: list[str] = []
    to_append: list[str] = []

    for spec in specs:
        if not _ingredient_mentioned_in_ro(spec.answer_ro, combined_ro):
            continue

        if spec.is_concrete:
            if not _ingredient_correctly_in_prompt(spec, current_prompt):
                log.info(
                    "Enforcing '%s' → '%s' in panel %d",
                    spec.answer_ro, spec.combined_phrase, panel.panel_index
                )
                to_prepend.append(spec.combined_phrase)

        elif spec.is_abstract:
            # Change B: Principle-based abstract visual enforcement
            # Works for ANY abstract word — no dictionary lookup needed
            abstract_action = _build_abstract_visual_action(
                spec.english_desc, current_prompt
            )
            if abstract_action:
                to_append.append(abstract_action)

    result = current_prompt

    if to_prepend:
        result = ", ".join(to_prepend) + ", " + result

    if to_append:
        result = result.rstrip(", .") + ", " + ", ".join(to_append)

    # Change G: kinetic verb check
    result = _ensure_kinetic_action(result, specs, combined_ro)

    return result


def _build_abstract_visual_action(
    english_desc: str,
    current_prompt: str,
) -> str | None:
    """
    Change B: Generate a visual action suffix for any abstract ingredient.

    Principle-based — does not need a dictionary of Romanian words.
    Works by detecting whether the concept already has physical manifestation
    in the prompt, and if not, appends a generic physical-action directive.

    The LLM system prompt handles specific translation; the enforcer is
    a safety net for when the LLM fails to translate an abstract ingredient.
    """
    prompt_lower = current_prompt.lower()
    desc_lower = english_desc.lower()

    # Check if the abstract concept already has physical manifestation
    # by looking for kinetic verbs near the concept word
    if desc_lower in prompt_lower:
        # Concept is mentioned — check if it's near a kinetic verb
        idx = prompt_lower.find(desc_lower)
        window = prompt_lower[max(0, idx - 60):idx + len(desc_lower) + 60]
        if any(v in window for v in _KINETIC_VERBS):
            return None  # Already has physical manifestation

    # Abstract ingredient has no physical manifestation — append principle-based action
    # Generic physical manifestation that works for any abstract concept
    return (
        f"physical manifestation of {english_desc}: "
        f"character body reacting with extreme exaggerated motion, "
        f"surrounding objects affected by the force of the emotion or concept, "
        f"dynamic physical consequence visible in environment"
    )


def _ensure_kinetic_action(
    prompt: str,
    specs: list[IngredientSpec],
    combined_ro: str,
) -> str:
    """
    Change G: If no kinetic verb found, append a dynamic action suffix.
    Uses the most relevant ingredient found in this panel for context.
    """
    if _has_kinetic_action(prompt):
        return prompt

    # Find most relevant ingredient for context
    relevant_phrase = None
    for spec in specs:
        if _ingredient_mentioned_in_ro(spec.answer_ro, combined_ro):
            relevant_phrase = spec.combined_phrase or spec.english_desc
            break

    if relevant_phrase:
        log.info("No kinetic verb — appending dynamic action for: %s", relevant_phrase)
        return (
            prompt.rstrip(", .") +
            f", {relevant_phrase} causing explosive chain reaction, "
            f"characters in mid-action dynamic poses, "
            f"objects flying in multiple directions, "
            f"extreme kinetic energy"
        )

    log.info("No kinetic verb and no matching ingredient — appending generic action")
    return (
        prompt.rstrip(", .") +
        ", explosive dynamic action scene, "
        "characters caught mid-motion, "
        "extreme kinetic energy, objects in flight"
    )


def _has_kinetic_action(prompt: str) -> bool:
    prompt_lower = prompt.lower()
    # Strip brackets so [stands] doesn't bypass the check
    prompt_stripped = prompt_lower.replace("[", "").replace("]", "")
    return any(verb in prompt_stripped for verb in _KINETIC_VERBS)


def _fix_color_in_prompt(prompt: str, specs: list[IngredientSpec]) -> str:
    result = prompt
    all_colors = [
        "red", "blue", "green", "yellow", "orange", "grey", "gray",
        "black", "white", "brown", "pink", "golden", "silver", "purple",
        "teal", "cyan", "magenta", "violet",
    ]
    for spec in specs:
        if not (spec.color_en and spec.object_en):
            continue
        obj = spec.object_en
        correct_color = spec.color_en
        for wrong_color in all_colors:
            if wrong_color == correct_color:
                continue
            wrong_phrase = f"{wrong_color} {obj}"
            correct_phrase = f"{correct_color} {obj}"
            if wrong_phrase in result.lower():
                result = re.sub(
                    re.escape(wrong_phrase),
                    correct_phrase,
                    result,
                    flags=re.IGNORECASE,
                )
                log.info(
                    "Fixed color: '%s' → '%s'", wrong_phrase, correct_phrase
                )
    return result


def _ingredient_mentioned_in_ro(answer_ro: str, text_ro: str) -> bool:
    """
    Check if the ingredient answer appears in the Romanian story text.
    Handles:
    - Exact match
    - Case-insensitive match (for proper nouns like Veneția)
    - Multi-word partial match
    - Romanian declension root match
    """
    answer_lower = answer_ro.lower()
    text_lower = text_ro.lower()

    # Exact case-insensitive match
    if answer_lower in text_lower:
        return True

    # Multi-word: all words must appear
    words = answer_lower.split()
    if len(words) > 1:
        if all(w in text_lower for w in words):
            return True
        # Also try normalized (diacritics stripped)
        words_norm = [_normalize_ro(w) for w in words]
        text_norm = _normalize_ro(text_lower)
        if all(w in text_norm for w in words_norm):
            return True

    # Root match for Romanian declension
    normalized = _normalize_ro(answer_lower)
    if len(normalized) > 5:
        root = normalized[:len(normalized) - 2]
        text_norm = _normalize_ro(text_lower)
        if root in text_norm:
            return True

    # Single word normalized match
    if _normalize_ro(answer_lower) in _normalize_ro(text_lower):
        return True

    return False


def _ingredient_correctly_in_prompt(
    spec: IngredientSpec, prompt: str
) -> bool:
    prompt_lower = prompt.lower()
    if spec.combined_phrase and spec.combined_phrase.lower() in prompt_lower:
        return True
    if spec.object_en and spec.color_en:
        obj = spec.object_en.lower()
        if obj in prompt_lower:
            idx = prompt_lower.find(obj)
            window = prompt_lower[max(0, idx - 20): idx + len(obj) + 20]
            correct_color = spec.color_en.lower()
            all_colors = [
                "red", "blue", "green", "yellow", "orange", "grey", "gray",
                "black", "white", "brown", "pink", "golden", "silver", "purple",
            ]
            for wrong_color in all_colors:
                if wrong_color != correct_color and wrong_color in window:
                    return False
            if correct_color in window:
                return True
        return False
    if spec.object_en:
        return spec.object_en.lower() in prompt_lower
    if spec.color_en:
        return spec.color_en.lower() in prompt_lower
    return spec.english_desc.lower() in prompt_lower


def _translate_ingredient(
    answer_ro: str, role: str
) -> tuple[str, str | None, str | None]:
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

    if color_en and object_en:
        english_desc = f"{color_en} {object_en}"
    else:
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