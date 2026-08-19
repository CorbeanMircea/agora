"""
M4.4 / M4.5 — OllamaStoryLLM

Calls Ollama (Llama 3.1 8B) to generate a structured Romanian comic story.

Key principles (ADR-001):
- Character visual identities injected from CharacterRoster.
- Ingredients presented with roles — model must integrate organically.
- image_prompt_en is a visual scene spec: concrete, English, ASCII-only.
- No "no text" instruction in image_prompt_en — negative prompts handle that.
- Archetype names are narrative roles only, never visual descriptions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from .story_llm_provider import (
    StoryLLMProvider,
    Story,
    PanelDescription,
    PlayerAnswers,
)

log = logging.getLogger("ollama_story_llm")

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECS: float = float(os.getenv("OLLAMA_TIMEOUT_SECS", "60"))

_ROLE_GUIDANCE_RO: dict[str, str] = {
    "CHARACTER":  "un personaj, ființă sau entitate care poate acționa",
    "LOCATION":   "un loc, spațiu sau ambient al acțiunii",
    "OBJECT":     "un obiect, unealtă, trofeu sau element fizic",
    "CONCEPT":    "o idee, temă sau forță abstractă care ghidează povestea",
    "NAME":       "un nume propriu (persoană, loc, organizație, titlu)",
    "QUANTITY":   "o cantitate, valoare sau măsură cu semnificație în poveste",
    "ACTION":     "o acțiune, eveniment sau verb care propulsează narațiunea",
    "ATMOSPHERE": "o calitate senzorială, emoție sau ton care colorează scena",
}

_ROLE_VISUAL_GUIDANCE_EN: dict[str, str] = {
    "ATMOSPHERE": (
        "Show through VISIBLE SIGNS: facial expressions, body language, "
        "environmental effects, lighting. Example: 'fear' → wide eyes, defensive posture, "
        "cold sweat; 'jealousy' → glaring with clenched fists."
    ),
    "CONCEPT": "Translate into a VISUAL SITUATION or physical metaphor.",
    "ACTION": "Show the action HAPPENING — capture the motion and consequence.",
}

# English translations for common Romanian ingredients
# Used to build concrete examples in the schema
_INGREDIENT_TRANSLATIONS: dict[str, str] = {
    "bicicletă mov": "purple bicycle",
    "papagal albastru": "blue parrot",
    "cheie aurie": "golden key",
    "umbrelă roșie": "red umbrella",
    "tort de ziua de naștere": "birthday cake",
    "frică": "fear (shown as trembling hands, wide eyes, defensive crouch)",
    "gelozie": "jealousy (shown as narrowed eyes, clenched jaw, suspicious glare)",
}


class OllamaStoryLLM(StoryLLMProvider):

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: float = OLLAMA_TIMEOUT_SECS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate_story(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
    ) -> Story:
        panel_count: int = getattr(brief, "panel_count", 5)
        player_names = [pa.nickname for pa in player_answers]
        roster = _build_roster_from_brief(brief)
        system_prompt = _build_system_prompt(brief, player_answers, roster)
        user_prompt = _build_user_prompt(
            panel_count=panel_count,
            player_names=player_names,
            player_answers=player_answers,
            prior_errors=getattr(self, "_last_validation_errors", []),
        )

        log.info("Calling Ollama model=%s panel_count=%d players=%s",
                 self.model, panel_count, player_names)
        t0 = time.monotonic()
        response_text = self._call_ollama(system_prompt, user_prompt)
        log.info("Ollama responded in %.1fs", time.monotonic() - t0)

        return _parse_story_response(response_text, panel_count)

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": 0.85,
                "top_p": 0.9,
                "num_predict": 4096,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        }
        url = f"{self.base_url}/api/chat"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        data = resp.json()
        if "eval_count" in data:
            log.info("Tokens — prompt: %s, eval: %s",
                     data.get("prompt_eval_count", "?"), data.get("eval_count", "?"))
        return data["message"]["content"]


def _build_roster_from_brief(brief: Any):
    try:
        from .character_description import CharacterDescriptionGenerator
        return CharacterDescriptionGenerator().generate(brief)
    except Exception as exc:
        log.warning("Could not build character roster: %s", exc)
        return None


def _build_ingredient_english_map(player_answers: list[PlayerAnswers]) -> dict[str, str]:
    """
    Build a map of Romanian ingredient → English equivalent for all ingredients.
    Used to give the LLM concrete translation examples in the prompt.
    """
    from .ingredient_enforcer import _translate_ingredient
    result = {}
    for pa in player_answers:
        for ans in pa.answers:
            en, color, obj = _translate_ingredient(ans.answer_text, ans.ingredient_role)
            if color and obj:
                result[ans.answer_text] = f"{color} {obj}"
            else:
                result[ans.answer_text] = en
    return result


def _build_system_prompt(
    brief: Any,
    player_answers: list[PlayerAnswers],
    roster: Any | None,
) -> str:
    panel_count: int = getattr(brief, "panel_count", 5)
    genre_name: str = getattr(brief, "genre", "Telenovelă Românească")
    subgenre: str = getattr(brief, "subgenre", "")
    tone_keywords: list[str] = list(getattr(brief, "tone_keywords", []))
    comedy_level: int = getattr(brief, "comedy_level", 7)

    story_structure = getattr(brief, "story_structure", None)
    beats: list[str] = list(getattr(story_structure, "beats", [])) if story_structure else []
    act_descriptions: list[str] = (
        list(getattr(story_structure, "act_descriptions", [])) if story_structure else []
    )

    twists = list(getattr(brief, "twists", []))
    twist_lines: list[str] = []
    for tw in twists:
        idx = getattr(tw, "panel_index", 0)
        desc = getattr(tw, "description_ro", "")
        is_final = getattr(tw, "is_final_twist", False)
        label = "RĂSTURNARE FINALĂ" if is_final else "COMPLICAȚIE"
        twist_lines.append(f"  - Panou {idx}: {label} — {desc}")

    narrator = getattr(brief, "narrator_personality", None)
    narrator_desc: str = getattr(narrator, "personality_description_ro", "") if narrator else ""
    archetypes = list(getattr(brief, "archetypes", []))

    # Build English ingredient map for concrete examples
    ingredient_en_map = _build_ingredient_english_map(player_answers)

    parts: list[str] = [
        "Ești un scenarist român de benzi desenate comice. Scrii scenarii originale.",
        "Povestea ta va fi desenată ca o bandă desenată românească în stil comic book.",
        "",
        f"GEN: {genre_name}",
    ]
    if subgenre:
        parts.append(f"SUBGEN: {subgenre}")
    parts += [
        f"NIVEL COMEDIE: {comedy_level}/10",
        f"TON: {', '.join(tone_keywords)}",
        "",
    ]

    # CHARACTER VISUAL IDENTITIES
    if roster is not None:
        roster_section = roster.build_system_prompt_section()
        if roster_section:
            parts += [
                "=" * 60,
                roster_section,
                "=" * 60,
                "",
                "CRITICAL: Use EXACTLY these visual descriptions in every image_prompt_en.",
                "Do NOT change clothing color, hair, or features between panels.",
                "",
            ]

    # Narrative archetypes
    parts += ["ROLURI NARATIVE (story roles only, NOT visual descriptions):"]
    for arch in archetypes:
        key = getattr(arch, "key", "?")
        name_ro = getattr(arch, "name_ro", key)
        desc_ro = getattr(arch, "description_ro", "")
        nickname = getattr(arch, "player_nickname", "?")
        parts.append(f"  {nickname} → rol: {name_ro} — {desc_ro}")
        parts.append(
            f"    In image_prompt_en: call this character '{nickname}' + visual description. "
            f"NEVER write '{name_ro}' or '{key}' in image descriptions."
        )
    parts += [""]

    # Story structure
    parts += ["STRUCTURA NARATIVĂ:"]
    for i, beat in enumerate(beats[:panel_count]):
        hint = ""
        if act_descriptions and i == 0:
            hint = f" — {act_descriptions[0]}"
        elif act_descriptions and i == panel_count - 1 and len(act_descriptions) > 1:
            hint = f" — {act_descriptions[-1]}"
        parts.append(f"  Panou {i}: {beat}{hint}")

    if twist_lines:
        parts += ["", "RĂSTURNĂRI OBLIGATORII:"] + twist_lines
    if narrator_desc:
        parts += ["", f"NARATORUL: {narrator_desc}"]

    # Ingredients with English translation shown explicitly
    parts += [
        "",
        "INGREDIENTE FURNIZATE DE JUCĂTORI:",
        "IMPORTANT: Tabelul de mai jos arată traducerea exactă în engleză pe care",
        "trebuie să o folosești în image_prompt_en. NU schimba culorile.",
        "",
    ]
    for pa in player_answers:
        parts.append(f"Jucător: {pa.nickname} (rol: {pa.archetype_key})")
        for ans in pa.answers:
            role = ans.ingredient_role
            guidance_ro = _ROLE_GUIDANCE_RO.get(role, role)
            visual_guidance = _ROLE_VISUAL_GUIDANCE_EN.get(role, "")
            en_translation = ingredient_en_map.get(ans.answer_text, ans.answer_text)
            line = (
                f"  • «{ans.answer_text}» | rol: {role} ({guidance_ro})\n"
                f"    → English for image_prompt_en: \"{en_translation}\""
            )
            if visual_guidance:
                line += f"\n    → Visual: {visual_guidance}"
            parts.append(line)

    parts += [
        "",
        "REGULĂ CRITICĂ: Integrează fiecare ingredient organic. NU forța ca umplutură.",
        "NU adăuga obiecte care nu sunt în lista de ingrediente (umbrele, crocodili,",
        "animale aleatorii etc.) — dacă nu e în lista de mai sus, nu apare în imagine.",
        "",
    ]

    # image_prompt_en rules
    parts += [
        "=" * 60,
        "REGULI PENTRU image_prompt_en:",
        "=" * 60,
        "",
        "STILUL VIZUAL OBLIGATORIU — fiecare image_prompt_en TREBUIE să înceapă cu:",
        "  'highly detailed comic book illustration, bold dark ink outlines,",
        "  exaggerated expressive characters, vibrant saturated colors, dramatic lighting,'",
        "",
        "CONȚINUT — pentru fiecare panou:",
        "1. ENGLISH ONLY. ASCII ONLY. No Romanian.",
        "2. Descrie acțiunea specifică care se întâmplă.",
        "3. Numește fiecare personaj prin NICKNAME + descriere vizuală din CHARACTER VISUAL IDENTITIES.",
        "4. INGREDIENT COMPLETENESS — OBLIGATORIU înainte de a scrie image_prompt_en:",
        "   a) Citește description_ro al acestui panou.",
        "   b) Identifică ingredientele din lista de mai sus care apar în description_ro.",
        "   c) Copiază traducerea EXACTĂ din coloana 'English for image_prompt_en'.",
        "      Exemplu: dacă apare 'bicicletă mov' → scrie 'purple bicycle' (nu 'blue bicycle').",
        "   d) NU adăuga obiecte care nu sunt în lista de ingrediente.",
        "5. LOCAȚIE: descrie mediul vizual (Venice canal, cobblestone street, etc.).",
        "6. FĂRĂ TEXT IN IMAGINE: nu descrie speech bubbles, captions, text.",
        "   Textul e adăugat separat de sistemul de prezentare.",
        "",
        "ARCHETYPE RULE: NICIODATĂ nu folosi nume de arhetipuri ca descrieri vizuale.",
        "Exemplu GREȘIT: 'the Skeptic looks skeptical'",
        "Exemplu CORECT: 'Ana, wearing vibrant red outfit and long colourful scarf,",
        "  leans forward with narrowed eyes and crossed arms'",
        "",
        "REGULI GENERALE:",
        "- description_ro, dialogue_ro, narrator_line_ro: ROMÂNĂ.",
        "- image_prompt_en: ENGLISH ONLY, ASCII ONLY.",
        "- description_ro: minimum 20 cuvinte.",
        "- Toate nickname-urile jucătorilor trebuie să apară în text.",
        "- Răspunde EXCLUSIV cu JSON valid. Fără text înainte sau după.",
        "- NU genera narrator_script sau image_prompts la root level.",
    ]

    return "\n".join(parts)


def _build_user_prompt(
    panel_count: int,
    player_names: list[str],
    player_answers: list[PlayerAnswers],
    prior_errors: list[str],
) -> str:
    schema_example = _build_json_schema_example(panel_count, player_answers)
    lines: list[str] = []

    if prior_errors:
        lines += [
            "Încercarea anterioară a eșuat validarea:",
            *[f"  - {e}" for e in prior_errors],
            "Corectează aceste probleme.",
            "",
        ]

    names_str = ", ".join(player_names) if player_names else "(niciun jucător)"
    lines += [
        f"Scrie o poveste comică de bandă desenată cu exact {panel_count} panouri.",
        f"Personajele sunt: {names_str}.",
        "Fiecare ingredient trebuie integrat organic.",
        "",
        "PENTRU FIECARE image_prompt_en:",
        "1. Începe cu: 'highly detailed comic book illustration, bold dark ink outlines,'",
        "2. Descrie personajele prin nickname + aspect vizual exact.",
        "3. Include EXACT traducerile din lista de ingrediente (cu culorile corecte).",
        "4. NU adăuga obiecte care nu sunt în lista de ingrediente.",
        "",
        "JSON:",
        "",
        schema_example,
    ]
    return "\n".join(lines)


def _build_json_schema_example(
    panel_count: int,
    player_answers: list[PlayerAnswers],
) -> str:
    """Build schema example using actual ingredient translations as examples."""
    from .ingredient_enforcer import _translate_ingredient

    # Collect actual ingredient English translations
    ingredient_examples: list[str] = []
    for pa in player_answers:
        for ans in pa.answers[:1]:  # just first ingredient of each player for example
            en, color, obj = _translate_ingredient(ans.answer_text, ans.ingredient_role)
            if color and obj:
                ingredient_examples.append(f"{color} {obj}")
            else:
                ingredient_examples.append(en)

    example_objects = ", ".join(ingredient_examples) if ingredient_examples else "specific ingredient"

    panels = []
    for i in range(panel_count):
        if i == 0:
            # First panel: show concrete example with actual ingredients
            example_prompt = (
                "highly detailed comic book illustration, bold dark ink outlines, "
                "exaggerated expressive characters, vibrant saturated colors, dramatic lighting, "
                f"[Character1Name] (early 30s, [hair], wearing [clothing color] outfit, [feature]) "
                f"holding a {example_objects}, shocked expression, wide eyes, "
                "[Character2Name] ([age], [hair], wearing [clothing color] outfit, [feature]) "
                "watching with raised eyebrows, "
                "[environment description], dramatic lighting, strong contrast"
            )
        else:
            example_prompt = (
                "highly detailed comic book illustration, bold dark ink outlines, "
                "exaggerated expressive characters, vibrant saturated colors, dramatic lighting, "
                f"[describe panel {i} scene with character nicknames, visual appearances, "
                f"specific ingredients with exact colors, environment, camera angle]"
            )
        panels.append({
            "panel_index": i,
            "description_ro": f"[Descriere scenă panou {i}, minimum 20 cuvinte]",
            "dialogue_ro": f"[Dialog panou {i} sau șir gol]",
            "image_prompt_en": example_prompt,
            "narrator_line_ro": f"[Linia naratorului panou {i}]",
            "characters_in_panel": ["[archetype_key_1]", "[archetype_key_2]"],
        })

    schema: dict[str, Any] = {
        "title": "[Titlul poveștii]",
        "panels": panels,
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def _extract_ingredients_from_system_prompt(system_prompt: str) -> list[str]:
    import re
    return re.findall(r"«([^»]+)»", system_prompt)


def _parse_story_response(response_text: str, panel_count: int) -> Story:
    text = response_text.strip()
    data = _try_parse_json(text)
    if data is None:
        stripped = _strip_code_fence(text)
        if stripped:
            data = _try_parse_json(stripped)
    if data is None:
        extracted = _extract_json_object(text)
        if extracted:
            data = _try_parse_json(extracted)
    if data is None:
        raise ValueError(
            f"Could not extract valid JSON from LLM response. "
            f"First 200 chars: {text[:200]!r}"
        )
    return _dict_to_story(data, panel_count)


def _try_parse_json(text: str) -> dict[str, Any] | None:
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None


def _strip_code_fence(text: str) -> str | None:
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _dict_to_story(data: dict[str, Any], panel_count: int) -> Story:
    required = ["title", "panels"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"LLM response missing required Story fields: {missing}")

    raw_panels: list[dict[str, Any]] = data["panels"]
    panels: list[PanelDescription] = []
    for i, p in enumerate(raw_panels):
        panels.append(PanelDescription(
            panel_index=int(p.get("panel_index", i)),
            description_ro=str(p.get("description_ro", "")),
            dialogue_ro=str(p.get("dialogue_ro", "")),
            image_prompt_en=str(p.get("image_prompt_en", "")),
            narrator_line_ro=str(p.get("narrator_line_ro", "")),
            characters_in_panel=list(p.get("characters_in_panel", [])),
        ))

    narrator_script = [p.narrator_line_ro for p in panels]
    image_prompts = [p.image_prompt_en for p in panels]

    return Story(
        title=str(data.get("title", "")),
        panels=panels,
        narrator_script=narrator_script,
        image_prompts=image_prompts,
    )