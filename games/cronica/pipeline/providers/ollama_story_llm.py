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

    # Archetypes → player mapping
    archetypes = list(getattr(brief, "archetypes", []))
    archetype_lines: list[str] = []
    for arch in archetypes:
        key = getattr(arch, "key", "?")
        name_ro = getattr(arch, "name_ro", key)
        desc_ro = getattr(arch, "description_ro", "")
        nickname = getattr(arch, "player_nickname", "?")
        archetype_lines.append(
            f"  - {nickname} joacă rolul «{name_ro}» ({key}): {desc_ro}"
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
        ]

    if narrator_desc:
        parts += ["", f"NARATORUL: {narrator_desc}"]

    if visual_style:
        parts += ["", f"STIL VIZUAL (pentru prompturile de imagine): {visual_style}"]

    parts += [
        "",
        "REGULI DE SCRIERE:",
        "1. Scrie în română. Prompturile de imagine (image_prompt_en) OBLIGATORIU în engleză.",
        "2. Fiecare description_ro trebuie să aibă minimum 20 de cuvinte.",
        "3. Fiecare narrator_line_ro trebuie să sune ca vocea naratorului descris mai sus.",
        "4. Toate numele jucătorilor trebuie să apară în text (în description_ro sau dialogue_ro).",
        "5. image_prompt_en: doar caractere ASCII, în engleză, stil ComfyUI (tokens separate prin virgulă).",
        "6. Răspunde EXCLUSIV cu un obiect JSON valid. Fără text înaintea sau după JSON.",
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

    lines += [
        f"Scrie o poveste comică de bandă desenată cu exact {panel_count} panouri.",
        f"Jucători care TREBUIE să apară în text: {', '.join(player_names)}.",
        "",
        "Răspunde EXCLUSIV cu un obiect JSON cu această structură exactă:",
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
        panels.append({
            "panel_index": i,
            "description_ro": f"[Descriere scenă panou {i}, minimum 20 cuvinte, română]",
            "dialogue_ro": f"[Dialog sau caption panou {i}, sau șir gol dacă nu e dialog]",
            "image_prompt_en": f"[English ComfyUI tokens for panel {i}, ASCII only]",
            "narrator_line_ro": f"[Linia naratorului pentru panou {i}, în română]",
            "characters_in_panel": ["[archetype_key1]"],
        })

    schema: dict[str, Any] = {
        "title": "[Titlul poveștii în română]",
        "panels": panels,
        "narrator_script": [f"[Linia naratorului panou {i}]" for i in range(panel_count)],
        "image_prompts": [f"[English prompt panou {i}]" for i in range(panel_count)],
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


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
    """
    required = ["title", "panels", "narrator_script", "image_prompts"]
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

    narrator_script: list[str] = [str(x) for x in data.get("narrator_script", [])]
    image_prompts: list[str] = [str(x) for x in data.get("image_prompts", [])]

    # If narrator_script / image_prompts are missing, reconstruct from panels
    if not narrator_script and panels:
        narrator_script = [p.narrator_line_ro for p in panels]
    if not image_prompts and panels:
        image_prompts = [p.image_prompt_en for p in panels]

    return Story(
        title=str(data.get("title", "")),
        panels=panels,
        narrator_script=narrator_script,
        image_prompts=image_prompts,
    )