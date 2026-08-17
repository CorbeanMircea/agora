"""
M4.4 — OllamaStoryLLM

Concrete StoryLLMProvider that calls Ollama (Llama 3.1 8B) to generate
a structured Romanian story from a CreativeBrief and player ingredients.

Design constraints (from TASKS.md M4.4):
  - Calls Ollama REST API at localhost:11434 (configurable via OLLAMA_BASE_URL)
  - Uses llama3.1:8b model (configurable via OLLAMA_MODEL)
  - Sends a system prompt encoding the CreativeBrief and anti-template instructions
  - Requests structured JSON output conforming to the Story schema
  - Retries once on malformed JSON before raising
  - Logs token usage
  - VRAM usage: the orchestrator calls _clear_vram("LLM") after this step

Anti-template philosophy (ADR-001):
  Ingredients are presented to the LLM with their assigned IngredientRole so
  the model knows how to integrate them organically — not as Mad Lib slots.
  Example: "ingredient: 'crocodil', role: OBJECT (poate fi un obiect, unealtă,
  trofeu, simbol — integrează-l în poveste, nu îl forța)"
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

# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECS: float = float(os.getenv("OLLAMA_TIMEOUT_SECS", "60"))

# IngredientRole → Romanian guidance for the LLM
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


# ── OllamaStoryLLM ────────────────────────────────────────────────────────────

class OllamaStoryLLM(StoryLLMProvider):
    """
    Calls Ollama (Llama 3.1 8B) to produce a structured Romanian comic story.

    Usage
    -----
    ::
        llm = OllamaStoryLLM()
        story = llm.generate_story(brief, player_answers)
        errors = story.validate(brief.panel_count,
                                expected_player_names=[pa.nickname for pa in player_answers])
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: float = OLLAMA_TIMEOUT_SECS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ── StoryLLMProvider contract ─────────────────────────────────────────────

    def generate_story(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
    ) -> Story:
        """
        Call Ollama and parse the JSON response into a Story.

        Parameters
        ----------
        brief:
            A fully populated CreativeBrief instance.
        player_answers:
            One PlayerAnswers entry per active player.

        Returns
        -------
        Story
            Parsed from the LLM JSON response. Call story.validate() after.

        Raises
        ------
        ValueError
            If the LLM response cannot be parsed into a valid Story after
            JSON extraction attempts.
        httpx.HTTPError
            On network or HTTP errors from the Ollama API.
        """
        panel_count: int = getattr(brief, "panel_count", 5)
        player_names = [pa.nickname for pa in player_answers]

        system_prompt = _build_system_prompt(brief, player_answers)
        user_prompt = _build_user_prompt(
            panel_count=panel_count,
            player_names=player_names,
            prior_errors=getattr(self, "_last_validation_errors", []),
        )

        log.info(
            "Calling Ollama model=%s panel_count=%d players=%s",
            self.model,
            panel_count,
            player_names,
        )
        t0 = time.monotonic()

        response_text = self._call_ollama(system_prompt, user_prompt)

        elapsed = time.monotonic() - t0
        log.info("Ollama responded in %.1fs", elapsed)

        story = _parse_story_response(response_text, panel_count)
        return story

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """
        POST to Ollama's /api/chat endpoint and return the assistant message text.
        Uses the non-streaming mode for simplicity.
        """
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

        # Log token usage if available
        if "eval_count" in data:
            log.info(
                "Token usage — prompt: %s, eval: %s",
                data.get("prompt_eval_count", "?"),
                data.get("eval_count", "?"),
            )

        content: str = data["message"]["content"]
        return content


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_system_prompt(brief: Any, player_answers: list[PlayerAnswers]) -> str:
    """
    Build the LLM system prompt from the CreativeBrief and player ingredients.

    The prompt follows the anti-template philosophy from ADR-001:
    - Ingredients are presented with their assigned narrative roles.
    - The LLM is instructed to write an original story where ingredients
      emerge naturally, not as fill-in-the-blank slots.
    - Story structure is driven by the genre's beat sequence.
    """
    panel_count: int = getattr(brief, "panel_count", 5)
    genre_name: str = getattr(brief, "genre", "Telenovelă Românească")
    subgenre: str = getattr(brief, "subgenre", "")
    tone_keywords: list[str] = list(getattr(brief, "tone_keywords", []))
    comedy_level: int = getattr(brief, "comedy_level", 7)
    visual_style: str = getattr(brief, "visual_style", "")

    # Story beats
    story_structure = getattr(brief, "story_structure", None)
    beats: list[str] = list(getattr(story_structure, "beats", [])) if story_structure else []
    act_descriptions: list[str] = (
        list(getattr(story_structure, "act_descriptions", [])) if story_structure else []
    )

    # Twists
    twists = list(getattr(brief, "twists", []))
    twist_lines: list[str] = []
    for tw in twists:
        idx = getattr(tw, "panel_index", 0)
        desc = getattr(tw, "description_ro", "")
        is_final = getattr(tw, "is_final_twist", False)
        label = "RĂSTURNARE FINALĂ" if is_final else "COMPLICAȚIE"
        twist_lines.append(f"  - Panou {idx}: {label} — {desc}")

    # Narrator persona
    narrator = getattr(brief, "narrator_personality", None)
    narrator_desc: str = (
        getattr(narrator, "personality_description_ro", "") if narrator else ""
    )

    # Archetypes → player mapping with visual descriptions for image prompts
    archetypes = list(getattr(brief, "archetypes", []))
    archetype_lines: list[str] = []

    # Build character visual descriptions so the LLM can include them in image_prompt_en
    try:
        from .character_description import CharacterDescriptionGenerator
        roster = CharacterDescriptionGenerator().generate(brief)
    except Exception:
        roster = None

    for arch in archetypes:
        key = getattr(arch, "key", "?")
        name_ro = getattr(arch, "name_ro", key)
        desc_ro = getattr(arch, "description_ro", "")
        nickname = getattr(arch, "player_nickname", "?")

        # Add visual description for image prompt generation
        visual = ""
        if roster is not None:
            sheet = roster.get_by_archetype_key(key)
            if sheet is not None:
                visual = (
                    f" | VISUAL for image prompts: {sheet.hair_description}, "
                    f"{sheet.clothing_colour_verbose} clothing, {sheet.distinguishing_feature}"
                )

        archetype_lines.append(
            f"  CHARACTER: {nickname}\n"
            f"    Story role: {name_ro} — {desc_ro}\n"
            f"    Visual appearance (use ONLY these in image_prompt_en): "
            f"{visual.strip(' |').strip() if visual else 'no visual data available'}\n"
            f"    Panel tag (use in characters_in_panel JSON field, nowhere else): \"{key}\"\n"
            f"    RULE: Never write '{name_ro}' or '{key}' in image_prompt_en. "
            f"    Use '{nickname}' and the visual appearance above instead."
        )

    # Player ingredients with assigned roles
    ingredient_sections: list[str] = []
    for pa in player_answers:
        lines: list[str] = [f"Jucător: {pa.nickname} (arhetip: {pa.archetype_key})"]
        for ans in pa.answers:
            role = ans.ingredient_role
            guidance = _ROLE_GUIDANCE_RO.get(role, role)
            lines.append(
                f"  • ingredient: «{ans.answer_text}» | rol: {role} ({guidance})"
            )
        ingredient_sections.append("\n".join(lines))

    ingredients_block = "\n\n".join(ingredient_sections)

    # Compose system prompt
    parts: list[str] = [
        "Ești un scenarist român de benzi desenate comice. Scrii scenarii originale, nu șabloane.",
        "",
        f"GEN: {genre_name}",
    ]
    if subgenre:
        parts.append(f"SUBGEN: {subgenre}")

    parts += [
        f"NIVEL COMEDIE: {comedy_level}/10",
        f"TON: {', '.join(tone_keywords)}",
        "",
        "STRUCTURA NARATIVĂ (câte un beat per panou):",
    ]
    for i, beat in enumerate(beats[:panel_count]):
        act_hint = ""
        if act_descriptions and i == 0:
            act_hint = f" — {act_descriptions[0]}"
        elif act_descriptions and i == panel_count - 1:
            act_hint = f" — {act_descriptions[-1] if len(act_descriptions) > 1 else ''}"
        parts.append(f"  Panou {i}: {beat}{act_hint}")

    if twist_lines:
        parts += ["", "RĂSTURNĂRI OBLIGATORII:"] + twist_lines

    if archetype_lines:
        parts += ["", "PERSONAJE (jucători reali):"] + archetype_lines

    if ingredients_block:
        parts += [
            "",
            "INGREDIENTE FURNIZATE DE JUCĂTORI:",
            "REGULĂ CRITICĂ: Integrează fiecare ingredient organic în poveste, conform rolului",
            "său narativ. NU le forța ca umplutură. Povestea trebuie să fie imposibil de",
            "ghicit doar din lista de ingrediente. Ingredientul servește povestea.",
            "",
            ingredients_block,
            "",
            "INGREDIENT VISUAL RULE pentru image_prompt_en:",
            "- Ingredientele cu rol LOCATION trebuie să apară ca loc/decor în prompt-ul de imagine al panoului relevant.",
            "- Ingredientele cu rol OBJECT/CHARACTER/NAME trebuie să apară fizic vizibil în prompt-ul panoului relevant.",
            "- Ingredientele cu rol ATMOSPHERE/CONCEPT trebuie să influențeze tonul vizual (lighting, mood, color).",
            "- Dacă un obiect este folosit activ într-o scenă, descrie explicit interacțiunea vizuală.",
        ]

    if narrator_desc:
        parts += ["", f"NARATORUL: {narrator_desc}"]

    if visual_style:
        parts += ["", f"STIL VIZUAL (pentru prompturile de imagine): {visual_style}"]

    parts += [
        "",
        "REGULI DE SCRIERE:",
        "1. Scrie în română pentru toate câmpurile EXCEPT image_prompt_en.",
        "2. image_prompt_en: MUST BE IN ENGLISH ONLY. ONLY ASCII CHARACTERS (a-z, A-Z, 0-9, punctuation).",
        "   NO Romanian letters. NO diacritics (a, a, i, s, t with accents are FORBIDDEN).",
        "3. Fiecare description_ro trebuie să aibă minimum 20 de cuvinte.",
        "4. Fiecare narrator_line_ro trebuie să sune ca vocea naratorului descris mai sus.",
        "5. Toate numele jucătorilor trebuie să apară în text (în description_ro sau dialogue_ro).",
        "6. Răspunde EXCLUSIV cu un obiect JSON valid. Fără text înaintea sau după JSON.",
        "7. NU genera câmpurile narrator_script și image_prompts la nivel de root — acestea sunt INTERZISE.",
        "   Generează DOAR câmpul panels[] cu toate sub-câmpurile.",
        "",
        "REGULI SPECIALE PENTRU image_prompt_en:",
        "image_prompt_en must be a detailed English prose sentence describing exactly what is VISUALLY happening",
        "in that panel. It is NOT a list of keywords. It IS a visual scene description for an image generator.",
        "",
        "For each panel, image_prompt_en MUST describe:",
        "- The specific action happening (not generic 'two characters talking')",
        "- Which characters are present, with their visual appearance (hair, clothing, accessories)",
        "- Which important objects/ingredients are visible and how they relate to the scene",
        "- The specific location/environment",
        "- Camera framing (wide shot, medium shot, close-up, etc.)",
        "- Lighting mood",
        "- Visual style consistent with the genre",
        "- End with: No text, no captions, no subtitles, no speech bubbles, no labels, no logos.",
        "",
        "INGREDIENT VISUAL RULE: If an ingredient (object, location, animal) is central to the action",
        "of a panel, it MUST appear explicitly in image_prompt_en with its visual role described.",
        "Example: if the story says a crocodile holds an umbrella, write:",
        "  'a large crocodile on a riverbank holding a black umbrella with its jaw, ...'",
        "Do NOT write: 'wide shot, animal, umbrella'",
        "",
        "CRITICAL TEXT RULE: image_prompt_en must end with this exact sentence on every panel:",
        "'No text, no captions, no subtitles, no speech bubbles, no dialogue bubbles,",
        " no written dialogue, no labels, no character names, no logos, no typography.'",
        "Do NOT include archetype role names (like 'Scepticul', 'Expertul') anywhere in image_prompt_en.",
        "Do NOT include player nicknames as text labels in image_prompt_en.",
        "Character identity comes from their physical description only.",
        "",
        "ARCHETYPE RULE: Archetype names (Expertul, Scepticul, Victima, etc.) are NARRATIVE ROLES,",
        "NOT visual descriptions and NOT character names.",
        "NEVER write 'an expert-looking man' or 'the skeptic' or 'Scepticul' in image_prompt_en.",
        "Instead:",
        "- Use the player's nickname and VISUAL IDENTITY attributes (hair, clothing) to identify them.",
        "- Translate the archetype into VISIBLE BEHAVIOR/POSTURE only if relevant to the scene:",
        "  Expertul → 'pointing confidently at evidence, gesturing with authority'",
        "  Scepticul → 'arms crossed, furrowed brow, skeptical expression, leaning back'",
        "  Victima → 'hunched posture, wide eyes, hands raised defensively'",
        "- The archetype key goes in characters_in_panel ONLY, never in the visual description prose.",
        "characters_in_panel: list the archetype KEYS (e.g. 'scepticul', 'expertul') of characters",
        "physically present in this panel. These keys are database identifiers ONLY.",
        "Do NOT use these keys as character names in image_prompt_en.",
        "Use the player nickname and visual description instead.",
        "DIALOGUE RULE: dialogue_ro content must NEVER appear in image_prompt_en.",
        "Dialogue is rendered by the presentation layer, not in the image.",
        "Do not translate, paraphrase, or reference dialogue_ro in image_prompt_en.",
        "",
        "MANDATORY VISUAL CHECK — apply before writing each image_prompt_en:",
        "1. Read the description_ro for this panel.",
        "2. List every ingredient from the ingredients list that appears in description_ro.",
        "3. For each such ingredient: write it explicitly into image_prompt_en.",
        "4. If an ingredient is assigned OBJECT role and appears ANYWHERE in the story",
        "   (even just mentioned), it must be VISIBLE in at least ONE panel's image_prompt_en.",
        "   Choose the panel where it appears most naturally and make it explicitly visible there.",
        "5. Never omit an OBJECT ingredient from all panels — even if it feels absurd,",
        "   include it. The absurdity is intentional and is the game's core mechanic.",
        "6. For ANIMAL ingredients: describe the animal in foreground, not background.",
        "   Do not write 'a zebra visible in the background' — write",
        "   'a zebra standing on the pavement directly in front of the characters,",
        "   black and white stripes clearly visible, looking directly at the camera'.",
        "   Foreground placement forces the model to render the animal correctly.",
        "7. Be hyper-specific about the animal's visual features.",
        "   'zebra' alone is insufficient — write 'black-and-white striped zebra,",
        "   horse-like body, distinctive black and white pattern, standing still'.",
    ]

     # Explicitly list which words must never appear in image_prompt_en
    forbidden_role_names = [
        f"'{getattr(arch, 'name_ro', '')}' or '{getattr(arch, 'key', '')}'"
        for arch in archetypes
    ]
    if forbidden_role_names:
        parts += [
            "",
            f"FORBIDDEN WORDS IN image_prompt_en: {', '.join(forbidden_role_names)}.",
            "These are narrative role names. They must NEVER appear in image_prompt_en.",
            "Use character nicknames and visual appearance descriptions instead.",
        ]

    return "\n".join(parts)


def _build_user_prompt(
    panel_count: int,
    player_names: list[str],
    prior_errors: list[str],
) -> str:
    """
    Build the user turn of the prompt requesting JSON output.
    On retry, includes the prior validation errors so the model can self-correct.
    """
    schema_example = _build_json_schema_example(panel_count)

    lines: list[str] = []

    if prior_errors:
        lines += [
            "Încercarea anterioară a eșuat validarea cu aceste erori:",
            *[f"  - {e}" for e in prior_errors],
            "Corectează aceste probleme în noul răspuns.",
            "",
        ]

    names_str = ", ".join(player_names) if player_names else "(niciun jucător)"
    lines += [
        f"Scrie o poveste comică de bandă desenată cu exact {panel_count} panouri.",
        f"OBLIGATORIU: Numele acestor jucători trebuie să apară explicit în text: {names_str}.",
        "Fiecare ingredient trebuie integrat organic conform rolului său — nu ca umplutură.",
        "",
        "CRITICAL RULES FOR image_prompt_en:",
        "1. ENGLISH ONLY. ASCII ONLY. No Romanian. No diacritics.",
        "2. Write a PROSE SENTENCE describing the SPECIFIC VISUAL SCENE, not generic keywords.",
        "3. Describe characters by appearance (clothing color, hair, accessories).",
        "4. If an ingredient/object is central to this panel's action, describe it explicitly.",
        "5. Include location, camera framing, lighting, visual style.",
        "6. End every image_prompt_en with: No text, no captions, no subtitles, no speech bubbles, no labels, no logos.",
        "",
        "Răspunde EXCLUSIV cu un obiect JSON cu această structură exactă (FĂRĂ narrator_script și image_prompts la root):",
        "",
        schema_example,
    ]

    return "\n".join(lines)


def _build_json_schema_example(panel_count: int) -> str:
    """
    Build a concrete JSON schema example to guide the LLM output.
    Uses actual panel indices so the model produces the right count.
    """
    panels = []
    for i in range(panel_count):
        if i == 0:
            example_prompt = (
                "Wide shot, documentary style. A woman in vibrant red clothing with a long red scarf "
                "holds a microphone toward a man in deep blue clothing with thick-rimmed glasses, "
                "both standing on the muddy bank of a river. Behind them a large crocodile is partially "
                "visible in the water. Overcast natural lighting, serious investigative mood. "
                "No text, no captions, no subtitles, no speech bubbles, no labels, no logos."
            )
        else:
            example_prompt = (
                f"[Panel {i}: English prose description of the specific visual scene. "
                f"Describe characters by appearance (clothing color, hair, accessories), "
                f"the specific action, important objects and their role, location/environment, "
                f"camera framing, lighting, visual style. "
                f"End with: No text, no captions, no subtitles, no speech bubbles, no labels, no logos.]"
            )
        panels.append({
            "panel_index": i,
            "description_ro": f"[Descriere scenă panou {i}, minimum 20 cuvinte, ROMÂNĂ]",
            "dialogue_ro": f"[Dialog panou {i} în română, sau șir gol dacă nu e dialog]",
            "image_prompt_en": example_prompt,
            "narrator_line_ro": f"[Linia naratorului panou {i}, în ROMÂNĂ]",
            "characters_in_panel": ["[nickname_of_player_1]", "[nickname_of_player_2]"],
        })

    schema: dict[str, Any] = {
        "title": "[Titlul poveștii în română]",
        "panels": panels,
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)

def _extract_ingredients_from_system_prompt(system_prompt: str) -> list[str]:
    """
    Extract ingredient answer texts from a system prompt for test verification.
    Returns list of answer_text values found between «» markers.
    """
    import re
    return re.findall(r"«([^»]+)»", system_prompt)

# ── Response parser ───────────────────────────────────────────────────────────

def _parse_story_response(response_text: str, panel_count: int) -> Story:
    """
    Extract and parse the JSON object from the LLM response text.

    Handles common LLM output patterns:
    - Pure JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON preceded or followed by explanatory text
    """
    text = response_text.strip()

    # Attempt 1: parse directly
    data = _try_parse_json(text)

    # Attempt 2: strip markdown code fences
    if data is None:
        stripped = _strip_code_fence(text)
        if stripped:
            data = _try_parse_json(stripped)

    # Attempt 3: find the first { … } block
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
    """Remove ```json ... ``` or ``` ... ``` fences."""
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_json_object(text: str) -> str | None:
    """Find the outermost { } block in text."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _dict_to_story(data: dict[str, Any], panel_count: int) -> Story:
    """
    Convert a parsed JSON dict to a Story dataclass.
    Raises ValueError on missing required fields.
    narrator_script and image_prompts are reconstructed from panels if absent
    (LLMs sometimes omit the convenience lists when the data is in panels).
    """
    required_core = ["title", "panels"]
    missing = [f for f in required_core if f not in data]
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

    # Always reconstruct narrator_script and image_prompts from panels.
    # This guarantees they match panels[x] exactly, satisfying Story.validate().
    # The LLM is no longer asked to generate these as separate root fields.
    narrator_script = [p.narrator_line_ro for p in panels]
    image_prompts = [p.image_prompt_en for p in panels]

    return Story(
        title=str(data.get("title", "")),
        panels=panels,
        narrator_script=narrator_script,
        image_prompts=image_prompts,
    )