"""
M4.4 / M4.5 — OllamaStoryLLM

Concrete StoryLLMProvider that calls Ollama (Llama 3.1 8B) to generate
a structured Romanian story from a CreativeBrief and player ingredients.

Key design principles (ADR-001):
- Ingredients are presented to the LLM with their assigned IngredientRole.
- Character visual identities are injected from CharacterRoster so the LLM
  writes accurate image_prompt_en descriptions for consistent characters.
- image_prompt_en describes WHAT TO DRAW — pure visual scene description.
  Text overlays (narration boxes, speech bubbles) are added by a separate
  PIL renderer in Part B. The image prompt should NOT say "no text" because
  that suppresses the comic-book artwork style.
- Archetype names (Expertul, Victima) are narrative roles only — never
  visual descriptions.
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

# How abstract roles translate into VISUAL representations
_ROLE_VISUAL_GUIDANCE_EN: dict[str, str] = {
    "ATMOSPHERE": (
        "Translate this into VISIBLE SIGNS: facial expressions, body language, "
        "environmental effects, lighting, colors, weather, surrounding details. "
        "Example: 'fear' → character with wide eyes, defensive posture, cold sweat, "
        "dramatic shadows; 'jealousy' → character glaring with clenched fists, "
        "watching another character with suspicious narrowed eyes."
    ),
    "CONCEPT": (
        "Translate this into a VISUAL SITUATION or physical metaphor. "
        "Make it visible through character behavior, objects, or environment."
    ),
    "ACTION": (
        "Show this action HAPPENING — capture the motion, the moment, "
        "the physical consequence of the action."
    ),
}


class OllamaStoryLLM(StoryLLMProvider):
    """
    Calls Ollama (Llama 3.1 8B) to produce a structured Romanian comic story.
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

    def generate_story(
        self,
        brief: Any,
        player_answers: list[PlayerAnswers],
    ) -> Story:
        """
        Call Ollama and parse the JSON response into a Story.
        """
        panel_count: int = getattr(brief, "panel_count", 5)
        player_names = [pa.nickname for pa in player_answers]

        # Build character roster for visual identity injection
        roster = _build_roster_from_brief(brief)

        system_prompt = _build_system_prompt(brief, player_answers, roster)
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
            log.info(
                "Token usage — prompt: %s, eval: %s",
                data.get("prompt_eval_count", "?"),
                data.get("eval_count", "?"),
            )

        content: str = data["message"]["content"]
        return content


# ── Roster helper ─────────────────────────────────────────────────────────────

def _build_roster_from_brief(brief: Any):
    """Build a CharacterRoster from the brief for system prompt injection."""
    try:
        from .character_description import CharacterDescriptionGenerator
        return CharacterDescriptionGenerator().generate(brief)
    except Exception as exc:
        log.warning("Could not build character roster: %s", exc)
        return None


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_system_prompt(
    brief: Any,
    player_answers: list[PlayerAnswers],
    roster: Any | None,
) -> str:
    """
    Build the LLM system prompt.

    Structure:
    1. Role declaration
    2. Genre/tone/structure
    3. CHARACTER VISUAL IDENTITIES (from roster) — injected early
    4. Archetypes with narrative roles (separate from visual identities)
    5. Ingredients with assigned roles
    6. image_prompt_en rules (comic artwork, no literal text embedding)
    7. Output format rules
    """
    panel_count: int = getattr(brief, "panel_count", 5)
    genre_name: str = getattr(brief, "genre", "Telenovelă Românească")
    subgenre: str = getattr(brief, "subgenre", "")
    tone_keywords: list[str] = list(getattr(brief, "tone_keywords", []))
    comedy_level: int = getattr(brief, "comedy_level", 7)
    visual_style: str = getattr(brief, "visual_style", "")

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
    narrator_desc: str = (
        getattr(narrator, "personality_description_ro", "") if narrator else ""
    )

    archetypes = list(getattr(brief, "archetypes", []))

    parts: list[str] = [
        "Ești un scenarist român de benzi desenate comice. Scrii scenarii originale, nu șabloane.",
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

    # ── CHARACTER VISUAL IDENTITIES — injected early ─────────────────────────
    # This must come BEFORE archetype narrative roles so the LLM understands
    # visual identity is separate from story role.
    if roster is not None:
        roster_section = roster.build_system_prompt_section()
        if roster_section:
            parts += [
                "=" * 60,
                roster_section,
                "=" * 60,
                "",
                "CRITICAL: The visual descriptions above define how each character LOOKS.",
                "Use these EXACT visual descriptions in every image_prompt_en.",
                "Do NOT invent different clothing, hair or features.",
                "The CHARACTER VISUAL IDENTITY must remain IDENTICAL across all panels.",
                "",
            ]

    # ── Narrative archetypes (story roles, NOT visual descriptions) ───────────
    parts += ["ROLURI NARATIVE (story roles only, NOT visual descriptions):"]
    for arch in archetypes:
        key = getattr(arch, "key", "?")
        name_ro = getattr(arch, "name_ro", key)
        desc_ro = getattr(arch, "description_ro", "")
        nickname = getattr(arch, "player_nickname", "?")
        parts.append(
            f"  {nickname} → rol narativ: {name_ro} — {desc_ro}"
        )
        parts.append(
            f"    NOTE: '{name_ro}' and '{key}' are STORY ROLES. "
            f"In image_prompt_en, always refer to this character as '{nickname}' "
            f"with the visual description from CHARACTER VISUAL IDENTITIES above."
        )

    parts += [""]

    # ── Story structure ───────────────────────────────────────────────────────
    parts += ["STRUCTURA NARATIVĂ (câte un beat per panou):"]
    for i, beat in enumerate(beats[:panel_count]):
        act_hint = ""
        if act_descriptions and i == 0:
            act_hint = f" — {act_descriptions[0]}"
        elif act_descriptions and i == panel_count - 1 and len(act_descriptions) > 1:
            act_hint = f" — {act_descriptions[-1]}"
        parts.append(f"  Panou {i}: {beat}{act_hint}")

    if twist_lines:
        parts += ["", "RĂSTURNĂRI OBLIGATORII:"] + twist_lines

    if narrator_desc:
        parts += ["", f"NARATORUL: {narrator_desc}"]

    # ── Ingredients with roles ────────────────────────────────────────────────
    ingredient_sections: list[str] = []
    for pa in player_answers:
        lines: list[str] = [f"Jucător: {pa.nickname} (rol narativ: {pa.archetype_key})"]
        for ans in pa.answers:
            role = ans.ingredient_role
            guidance_ro = _ROLE_GUIDANCE_RO.get(role, role)
            visual_guidance = _ROLE_VISUAL_GUIDANCE_EN.get(role, "")
            line = f"  • ingredient: «{ans.answer_text}» | rol: {role} ({guidance_ro})"
            if visual_guidance:
                line += f"\n    VISUAL: {visual_guidance}"
            lines.append(line)
        ingredient_sections.append("\n".join(lines))

    if ingredient_sections:
        parts += [
            "",
            "INGREDIENTE FURNIZATE DE JUCĂTORI:",
            "REGULĂ CRITICĂ: Integrează fiecare ingredient organic în poveste, conform rolului",
            "său narativ. Povestea trebuie să fie imposibil de ghicit doar din lista de ingrediente.",
            "Ingredientul servește povestea — NU forța ingredientele ca umplutură.",
            "",
            *ingredient_sections,
        ]

    # ── image_prompt_en rules ────────────────────────────────────────────────
    parts += [
        "",
        "=" * 60,
        "REGULI PENTRU image_prompt_en:",
        "=" * 60,
        "",
        "image_prompt_en descrie CE SĂ SE DESENEZE în acel panou.",
        "Este o specificație vizuală completă pentru un ilustrator de benzi desenate.",
        "",
        "STILUL VIZUAL OBLIGATORIU:",
        "Fiecare image_prompt_en trebuie să înceapă cu:",
        "  'highly detailed comic book illustration, bold dark ink outlines, "
        "exaggerated expressive characters, vibrant saturated colors, dramatic lighting,'",
        "Apoi continuă cu descrierea scenei specifice.",
        "",
        "REGULI DE CONȚINUT:",
        "1. ENGLISH ONLY. ASCII ONLY. No Romanian diacritics.",
        "2. Describe the SPECIFIC ACTION happening in the panel.",
        "3. Name each character by their NICKNAME and describe their appearance",
        "   using EXACTLY the visual identity from CHARACTER VISUAL IDENTITIES.",
        "   Example: 'Ana (mid-30s, short dark brown hair, vibrant red outfit, "
        "large round glasses) stands looking shocked'",
        "4. Every OBJECT ingredient visible in this panel must be explicitly described.",
        "   Include COLOR if the ingredient has one (e.g. 'bright red umbrella', not just 'umbrella').",
        "5. LOCATION ingredients must appear as the environment/background.",
        "6. ATMOSPHERE/CONCEPT ingredients must be shown through:",
        "   - Character expressions and body language",
        "   - Environmental effects (lighting, weather, chaos)",
        "   - Visual metaphors",
        "   Example: 'gelozie' → 'character with narrowed suspicious eyes, "
        "clenched fists, watching another character jealously'",
        "7. Do NOT embed literal text into the scene description.",
        "   The narration and dialogue will be added as overlays separately.",
        "   Do NOT say 'speech bubble saying...' or 'text reading...'",
        "   Simply describe what is VISUALLY HAPPENING.",
        "8. The panel should feel like a dynamic, expressive comic book panel.",
        "",
        "ARCHETYPE RULE:",
        "NEVER use archetype names (Expertul, Victima, Scepticul, etc.) as visual descriptions.",
        "Use the character's NICKNAME and their visual identity description instead.",
        "",
        "INGREDIENT COMPLETENESS CHECK (do this before writing each image_prompt_en):",
        "  For each panel, ask: which ingredients appear in this panel's description_ro?",
        "  Every such ingredient MUST appear in image_prompt_en explicitly.",
        "  OBJECT ingredients must be named with their full description including color.",
        "  At least one panel must show EVERY ingredient from the full list.",
        "",
        "REGULI GENERALE:",
        "1. Scrie în română pentru description_ro, dialogue_ro, narrator_line_ro.",
        "2. image_prompt_en: ENGLISH ONLY, ASCII ONLY.",
        "3. Fiecare description_ro trebuie să aibă minimum 20 de cuvinte.",
        "4. Toate numele jucătorilor trebuie să apară în text.",
        "5. Răspunde EXCLUSIV cu un obiect JSON valid. Fără text înainte sau după JSON.",
        "6. NU genera câmpurile narrator_script și image_prompts la nivel de root.",
        "   Generează DOAR câmpul panels[] cu toate sub-câmpurile.",
    ]

    return "\n".join(parts)


def _build_user_prompt(
    panel_count: int,
    player_names: list[str],
    prior_errors: list[str],
) -> str:
    """Build the user turn requesting JSON output."""
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
        "Fiecare ingredient trebuie integrat organic conform rolului său narativ.",
        "",
        "PENTRU FIECARE PANOU — image_prompt_en TREBUIE să:",
        "1. Înceapă cu stilul comic: 'highly detailed comic book illustration, bold dark ink outlines,'",
        "2. Descrie personajele prin nume și aspect vizual (din CHARACTER VISUAL IDENTITIES).",
        "3. Descrie explicit fiecare ingredient vizibil în acel panou.",
        "4. Fie o propoziție completă în engleză, nu o listă de cuvinte cheie.",
        "",
        "Răspunde EXCLUSIV cu un obiect JSON cu această structură exactă:",
        "",
        schema_example,
    ]

    return "\n".join(lines)


def _build_json_schema_example(panel_count: int) -> str:
    """Build a concrete JSON schema example to guide the LLM output."""
    panels = []
    for i in range(panel_count):
        if i == 0:
            example_prompt = (
                "highly detailed comic book illustration, bold dark ink outlines, "
                "exaggerated expressive characters, vibrant saturated colors, dramatic lighting, "
                "Ana (mid-30s, short dark brown hair, vibrant red outfit, large round glasses) "
                "stands in a grand hall holding a bright golden key, her expression shocked, "
                "wide eyes, mouth open, while Bogdan (late 20s, curly black hair, deep blue outfit, "
                "thick black moustache) watches from behind a purple bicycle propped against the wall, "
                "jealous expression with narrowed eyes and clenched fists, "
                "Venice canal visible through arched windows in background, "
                "warm dramatic lighting, strong contrast, detailed architectural environment"
            )
        else:
            example_prompt = (
                f"highly detailed comic book illustration, bold dark ink outlines, "
                f"exaggerated expressive characters, vibrant saturated colors, dramatic lighting, "
                f"[describe specific scene for panel {i}: which characters are present with their "
                f"visual appearance, what action is happening, which ingredients are visible "
                f"and how, what is the environment/location, camera angle and composition]"
            )
        panels.append({
            "panel_index": i,
            "description_ro": f"[Descriere scenă panou {i}, minimum 20 cuvinte, ROMÂNĂ]",
            "dialogue_ro": f"[Dialog panou {i} în română, sau șir gol dacă nu e dialog]",
            "image_prompt_en": example_prompt,
            "narrator_line_ro": f"[Linia naratorului panou {i}, în ROMÂNĂ]",
            "characters_in_panel": ["[archetype_key_of_character_1]", "[archetype_key_of_character_2]"],
        })

    schema: dict[str, Any] = {
        "title": "[Titlul poveștii în română]",
        "panels": panels,
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def _extract_ingredients_from_system_prompt(system_prompt: str) -> list[str]:
    """Extract ingredient answer texts from a system prompt."""
    import re
    return re.findall(r"«([^»]+)»", system_prompt)


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_story_response(response_text: str, panel_count: int) -> Story:
    """Extract and parse the JSON object from the LLM response text."""
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
    if match:
        return match.group(1).strip()
    return None


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _dict_to_story(data: dict[str, Any], panel_count: int) -> Story:
    """Convert a parsed JSON dict to a Story dataclass."""
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
    narrator_script = [p.narrator_line_ro for p in panels]
    image_prompts = [p.image_prompt_en for p in panels]

    return Story(
        title=str(data.get("title", "")),
        panels=panels,
        narrator_script=narrator_script,
        image_prompts=image_prompts,
    )