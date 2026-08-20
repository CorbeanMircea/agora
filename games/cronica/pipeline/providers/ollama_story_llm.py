"""
M4.4 / M4.5 — OllamaStoryLLM

Cinematic story generation with fully dynamic adaptation to player inputs.
No hardcoded Romanian words, ingredient names, or panel counts.

Priority 3 fix: LLM schema example uses actual character sheet data
so the model generates correct appearance descriptions from the start.
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
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral-nemo:12b")
OLLAMA_TIMEOUT_SECS: float = float(os.getenv("OLLAMA_TIMEOUT_SECS", "120"))

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

_KINETIC_VERBS_EXAMPLES = (
    "crashes, grabs, flees, shoves, launches, tumbles, dodges, spins, "
    "slams, leaps, sprints, snatches, collides, throws, catches, yanks, "
    "careens, stumbles, tackles, swings, lunges, topples, skids, hurls, "
    "bolts, plunges, wrenches, flings, barrels, explodes, loses control, "
    "careens toward, slams into, flailing, diving, skidding"
)

_BANNED_VERBS = (
    "stands, stand, standing, sits, sit, sitting, looks, look, looking, "
    "holds, hold, holding, walks, walk, walking, talks, talk, talking, "
    "watches, watch, watching, waits, wait, waiting, poses, pose, posing"
)

_CAMERA_ANGLE_POOL: list[str] = [
    (
        "extreme low angle shot, worm's eye view, "
        "character looms large against dramatic sky, "
        "ground-level perspective creates imposing scale"
    ),
    (
        "Dutch angle tilted frame, diagonal composition, "
        "sense of instability and impending chaos, "
        "strong diagonal lines cutting through background"
    ),
    (
        "extreme tight close-up filling entire frame, "
        "face and hands only, extreme facial detail, "
        "background completely cropped — only subject visible"
    ),
    (
        "extreme wide establishing shot, "
        "characters appear tiny against massive environment, "
        "strong foreground element partially blocks view, creating depth"
    ),
    (
        "over-the-shoulder shot, "
        "dominant character fills left third of frame from behind, "
        "second character reacts in background right third"
    ),
    (
        "bird's eye view looking straight down, "
        "characters seen from above, "
        "environment becomes abstract pattern below them"
    ),
    (
        "extreme close-up on a single object in sharp focus, "
        "characters blurred in background reacting, "
        "object fills center of frame"
    ),
    (
        "low three-quarter angle, "
        "character caught mid-action at dynamic diagonal, "
        "motion blur on moving elements, "
        "strong foreground shadow"
    ),
]


def _get_camera_angle(panel_index: int, panel_count: int) -> str:
    if panel_index == 0:
        return _CAMERA_ANGLE_POOL[0]
    if panel_index == panel_count - 1:
        return _CAMERA_ANGLE_POOL[3]
    middle_pool = [_CAMERA_ANGLE_POOL[i] for i in [1, 2, 4, 5, 6, 7]]
    middle_index = (panel_index - 1) % len(middle_pool)
    return middle_pool[middle_index]


def _build_causality_beat(
    panel_index: int,
    panel_count: int,
    all_ingredient_phrases: list[str],
) -> dict[str, str]:
    ingredient_list = ", ".join(f"«{p}»" for p in all_ingredient_phrases)
    position = panel_index / max(panel_count - 1, 1)

    if panel_index == 0:
        return {
            "label": "DECLANȘATOR",
            "instruction": (
                f"Unul dintre aceste ingrediente declanșează o criză neașteptată: {ingredient_list}. "
                "Ceva merge prost SAU se întâmplă ceva imposibil. "
                "NU o introducere liniștită — începe în mijlocul haosului. "
                "Ingredientul CAUZEAZĂ situația, nu este doar prezent."
            ),
        }

    if panel_index == panel_count - 1:
        return {
            "label": "REZOLUȚIE ABSURDĂ",
            "instruction": (
                f"Rezoluție care referențiază TOATE ingredientele vizual: {ingredient_list}. "
                "Personajele sunt acum într-o relație nouă cu obiectele și unele cu altele. "
                "Final amuzant — cel puțin un detaliu vizual absurd care nu ar fi posibil "
                "fără combinația exactă de ingrediente."
            ),
        }

    if position <= 0.35:
        return {
            "label": "REACȚIE",
            "instruction": (
                f"Un personaj face o alegere fizică disperată DIN CAUZA crizei din panoul anterior. "
                f"Legătură cauzală directă — fără salt în timp. "
                f"Acțiunile lor implică unul din: {ingredient_list}. "
                "Fug, apucă, urmăresc, confruntă sau încearcă ceva disperat."
            ),
        }

    if position <= 0.65:
        return {
            "label": "ESCALADARE",
            "instruction": (
                f"Consecința acțiunii anterioare înrăutățește totul. "
                f"Un al doilea ingredient din {ingredient_list} intră și complică situația. "
                "Mai multe personaje implicate, mediu mai mare, mize mai mari. "
                "Haosul se înmulțește exponențial."
            ),
        }

    return {
        "label": "RĂSTURNARE",
        "instruction": (
            f"O utilizare neașteptată a unui ingredient din {ingredient_list} schimbă totul. "
            "Ceva care părea o problemă devine soluția — sau invers. "
            "Panoul cel mai dinamic vizual — surpriză maximă. "
            "Ingredientul face ceva ce nu ar trebui să fie posibil."
        ),
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
            roster=roster,
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
                "temperature": 0.9,
                "top_p": 0.92,
                "num_predict": 6000,
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
                     data.get("prompt_eval_count", "?"),
                     data.get("eval_count", "?"))
        return data["message"]["content"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_roster_from_brief(brief: Any):
    try:
        from .character_description import CharacterDescriptionGenerator
        return CharacterDescriptionGenerator().generate(brief)
    except Exception as exc:
        log.warning("Could not build character roster: %s", exc)
        return None


def _build_ingredient_english_map(
    player_answers: list[PlayerAnswers],
) -> dict[str, str]:
    from .ingredient_enforcer import _translate_ingredient
    result: dict[str, str] = {}
    for pa in player_answers:
        for ans in pa.answers:
            en, color, obj = _translate_ingredient(
                ans.answer_text, ans.ingredient_role
            )
            result[ans.answer_text] = (
                f"{color} {obj}" if (color and obj) else en
            )
    return result


def _collect_all_ingredient_phrases(
    player_answers: list[PlayerAnswers],
    ingredient_en_map: dict[str, str],
) -> list[str]:
    return [
        ans.answer_text
        for pa in player_answers
        for ans in pa.answers
    ]


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

    twists = list(getattr(brief, "twists", []))
    twist_lines: list[str] = []
    for tw in twists:
        idx = getattr(tw, "panel_index", 0)
        desc = getattr(tw, "description_ro", "")
        is_final = getattr(tw, "is_final_twist", False)
        label = "RĂSTURNARE FINALĂ" if is_final else "COMPLICAȚIE"
        twist_lines.append(f"  Panou {idx}: {label} — {desc}")

    narrator = getattr(brief, "narrator_personality", None)
    narrator_desc: str = (
        getattr(narrator, "personality_description_ro", "") if narrator else ""
    )
    archetypes = list(getattr(brief, "archetypes", []))

    ingredient_en_map = _build_ingredient_english_map(player_answers)
    all_ingredient_phrases = _collect_all_ingredient_phrases(
        player_answers, ingredient_en_map
    )

    parts: list[str] = [
        "Ești un scenarist român de benzi desenate COMICE și DINAMICE.",
        "Scrii scenarii cu acțiune fizică, consecințe absurde și umor vizual.",
        "Fiecare panou trebuie să fie mai haotic decât cel anterior.",
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

    # CHARACTER VISUAL IDENTITIES — injected early and referenced explicitly
    if roster is not None:
        roster_section = roster.build_system_prompt_section()
        if roster_section:
            parts += [
                "=" * 60,
                roster_section,
                "=" * 60,
                "",
                "IDENTITATE VIZUALĂ OBLIGATORIE:",
                "Folosește EXACT aceste descrieri în fiecare image_prompt_en.",
                "Culorile hainelor, părul și trăsăturile NU se schimbă între panouri.",
                "",
                "FORMAT OBLIGATORIU pentru descrierea fiecărui personaj în image_prompt_en:",
            ]
            # Show exact format for each character using real data
            for sheet in roster.sheets:
                fragment = sheet.to_prompt_fragment()
                parts.append(
                    f"  {sheet.nickname}: scriei exact → "
                    f"\"{sheet.nickname} ({fragment})\""
                )
            parts += [
                "",
                "NICIODATĂ nu inventa altă vârstă, culoare de păr sau trăsătură.",
                "Dacă scrie '16 ani' sau 'red hair' în loc de ce e mai sus → GREȘIT.",
                "",
                "REGULA ARHETIPURILOR — CRITICĂ:",
                "NICIODATĂ nu scrie numele arhetipului (Scepticul, Expertul, Victima,",
                "Naratorul, Martorul, Ileana Necajita, Eroul Prost etc.) în image_prompt_en.",
                "Aceste sunt roluri INTERNE, invizibile în imagini.",
                "Folosește EXCLUSIV nickname-ul jucătorului + descrierea vizuală de mai sus.",
                "",
            ]

    # Narrative archetypes
    if archetypes:
        parts += ["ROLURI NARATIVE (EXCLUSIV pentru poveste, NU în image_prompt_en):"]
        for arch in archetypes:
            key = getattr(arch, "key", "?")
            name_ro = getattr(arch, "name_ro", key)
            desc_ro = getattr(arch, "description_ro", "")
            nickname = getattr(arch, "player_nickname", "?")
            parts.append(f"  {nickname} → {name_ro}: {desc_ro}")
            parts.append(
                f"  În image_prompt_en: DOAR '{nickname}' + aspect vizual. "
                f"NICIODATĂ '{name_ro}' sau '{key}'."
            )
        parts += [""]

    # Dynamic causality chain
    parts += [
        "=" * 60,
        "STRUCTURA CAUZALĂ — fiecare panou CAUZEAZĂ următorul:",
        "=" * 60,
        "",
        "REGULA DE AUR: Fiecare ingredient trebuie să CAUZEZE sau să SCHIMBE ceva.",
        "Ingredientul nu este decor — este MOTIVUL pentru care se întâmplă acțiunea.",
        "",
    ]

    for i in range(panel_count):
        beat = _build_causality_beat(i, panel_count, all_ingredient_phrases)
        camera = _get_camera_angle(i, panel_count)
        parts.append(f"PANOU {i} — {beat['label']}:")
        parts.append(f"  {beat['instruction']}")
        parts.append(f"  UNGHI CAMERĂ OBLIGATORIU: {camera}")
        parts.append("")

    if twist_lines:
        parts += ["RĂSTURNĂRI OBLIGATORII:"] + twist_lines + [""]
    if narrator_desc:
        parts += [f"NARATORUL: {narrator_desc}", ""]

    # Ingredients with causality rules
    parts += [
        "=" * 60,
        "INGREDIENTE — REGULI DE CAUZALITATE:",
        "=" * 60,
        "",
    ]

    for pa in player_answers:
        parts.append(f"Jucător: {pa.nickname}")
        for ans in pa.answers:
            role = ans.ingredient_role
            guidance_ro = _ROLE_GUIDANCE_RO.get(role, role)
            en_translation = ingredient_en_map.get(
                ans.answer_text, ans.answer_text
            )

            parts.append(
                f"  • «{ans.answer_text}» | rol: {role} ({guidance_ro})"
            )
            parts.append(
                f"    → Engleză exactă pentru image_prompt_en: \"{en_translation}\""
            )

            if role == "OBJECT":
                parts.append(
                    f"    → CAUZALITATE: Ce se întâmplă DIN CAUZA «{ans.answer_text}»? "
                    f"Obiectul trebuie să provoace o reacție în lanț."
                )
            elif role == "LOCATION":
                parts.append(
                    f"    → CAUZALITATE: «{ans.answer_text}» creează o CONSTRÂNGERE fizică "
                    f"specifică acestui loc."
                )
            elif role == "CHARACTER":
                parts.append(
                    f"    → CAUZALITATE: «{ans.answer_text}» trebuie să ACȚIONEZE activ. "
                    f"Ce vrea? Cu cine intră în conflict?"
                )
            elif role in ("ATMOSPHERE", "CONCEPT"):
                parts.append(
                    f"    → TRADUCERE VIZUALĂ OBLIGATORIE pentru «{ans.answer_text}»:"
                )
                parts.append(
                    f"       Traduce în ACȚIUNE FIZICĂ — ce face un actor de pantomimă "
                    f"pentru a exprima «{ans.answer_text}» fără cuvinte?"
                )
                parts.append(
                    f"       Nu descrie fața. Descrie CORPUL, MIȘCAREA, CONSECINȚA fizică."
                )
                parts.append(
                    f"       Emoție pozitivă → corp se extinde, sare, brațe larg"
                )
                parts.append(
                    f"       Emoție negativă → corp explodează sau se contractă, obiecte zboară"
                )
                parts.append(
                    f"       Concept abstract → obiect care se comportă imposibil"
                )
            elif role == "ACTION":
                parts.append(
                    f"    → CAUZALITATE: «{ans.answer_text}» trebuie să se ÎNTÂMPLE "
                    f"vizibil — capturează momentul maxim al acțiunii."
                )
            elif role == "NAME":
                parts.append(
                    f"    → CAUZALITATE: «{ans.answer_text}» trebuie să apară ca element "
                    f"vizual recognoscibil în scenă."
                )

            parts.append("")

    # Cinematic constraints
    parts += [
        "=" * 60,
        "REGULI CINEMATICE — OBLIGATORII pentru fiecare image_prompt_en:",
        "=" * 60,
        "",
        "ÎNAINTE de a scrie image_prompt_en, răspunde la aceste 5 întrebări:",
        "  1. Ce ACȚIUNE FIZICĂ se întâmplă în acest panou?",
        "  2. Ce ingredient specific CAUZEAZĂ această acțiune?",
        "  3. Care este UNGHIUL CAMEREI specificat pentru acest panou?",
        "  4. Ce exprimă CORPUL fiecărui personaj? (nu doar fața)",
        "  5. Ce este în PRIM-PLAN (mare, aproape) vs FUNDAL (mic, departe)?",
        "",
        "VERBE INTERZISE în image_prompt_en:",
        f"  {_BANNED_VERBS}",
        "",
        "VERBE CINETICE OBLIGATORII — folosește cel puțin unul:",
        f"  {_KINETIC_VERBS_EXAMPLES}",
        "",
        "COMPOZIȚIE OBLIGATORIE în fiecare image_prompt_en:",
        "  FOREGROUND: [element mare, aproape de cameră, parțial tăiat de cadru]",
        "  BACKGROUND: [element mic, departe, stabilește locul]",
        "",
        "UNGHI CAMERĂ: copiază textul exact din structura cauzală de mai sus.",
        "",
        "FORMAT OBLIGATORIU image_prompt_en:",
        "  COMIC BOOK, [style tokens],",
        "  [nickname] ([exact fragment din CHARACTER VISUAL IDENTITIES]),",
        "  [KINETIC ACTION — ce se întâmplă fizic],",
        "  [ingredient cu culoarea EXACTĂ],",
        "  [body language ALL characters],",
        "  FOREGROUND: [element specific],",
        "  BACKGROUND: [element specific stabilind locul],",
        "  [unghi cameră exact]",
        "",
        "CULORI EXACTE — CRITIC:",
        "Dacă ingredient are culoare specificată → culoarea TREBUIE să apară exact.",
        "Nu schimba culorile. purple bicycle → purple bicycle. golden key → golden key.",
        "",
        "REGULI FINALE:",
        "- description_ro, dialogue_ro, narrator_line_ro: ROMÂNĂ.",
        "- image_prompt_en: ENGLISH ONLY, ASCII ONLY, fără diacritice.",
        "- description_ro: minimum 30 cuvinte, acțiune dinamică.",
        "- Toate nickname-urile jucătorilor trebuie să apară în text.",
        "- Răspunde EXCLUSIV cu JSON valid. Prima linie: {. Ultima linie: }.",
        "- INTERZIS: Nu folosi paranteze pătrate [] în image_prompt_en.",
        "  GREȘIT: 'Ana [grabs] the bicycle'  CORECT: 'Ana grabs the bicycle'",
        "- VENICE RULE: Dacă «Veneția» este ingredient LOCATION, TREBUIE să apară",
        "  'Venice' în image_prompt_en pentru cel puțin un panou.",
        "- Niciun text înainte sau după JSON. Niciun markdown.",
    ]

    return "\n".join(parts)


def _build_user_prompt(
    panel_count: int,
    player_names: list[str],
    player_answers: list[PlayerAnswers],
    roster: Any | None,
    prior_errors: list[str],
) -> str:
    schema_example = _build_json_schema_example(
        panel_count, player_answers, roster
    )
    lines: list[str] = []

    if prior_errors:
        lines += [
            "ERORI din încercarea anterioară — corectează-le:",
            *[f"  - {e}" for e in prior_errors],
            "",
        ]

    names_str = ", ".join(player_names) if player_names else "(niciun jucător)"

    from .ingredient_enforcer import _translate_ingredient
    ingredient_checks: list[str] = []
    for pa in player_answers:
        for ans in pa.answers:
            en, color, obj = _translate_ingredient(
                ans.answer_text, ans.ingredient_role
            )
            phrase = f"{color} {obj}" if (color and obj) else en
            ingredient_checks.append(f"    «{ans.answer_text}» → \"{phrase}\"")

    # Build character appearance checklist from actual roster
    char_checks: list[str] = []
    if roster is not None:
        for sheet in roster.sheets:
            fragment = sheet.to_prompt_fragment()
            char_checks.append(
                f"    {sheet.nickname} → \"{sheet.nickname} ({fragment})\""
            )

    lines += [
        f"Scrie o poveste comică de bandă desenată cu exact {panel_count} panouri.",
        f"Personaje: {names_str}.",
        "",
        "VERIFICARE OBLIGATORIE înainte de fiecare image_prompt_en:",
        "  ✓ Verb cinetic prezent (crashes, grabs, flees, slams, etc.)?",
        "  ✓ Unghi cameră specificat pentru acest panou?",
        "  ✓ FOREGROUND și BACKGROUND separate și explicite?",
        "  ✓ Culorile exacte ale ingredientelor prezente?",
        *ingredient_checks,
        "  ✓ Descrierile EXACTE ale personajelor din CHARACTER VISUAL IDENTITIES?",
        *char_checks,
        "  ✓ Zero verbe statice (stands, holds, looks, walks)?",
        "  ✓ Zero bracket placeholders [like this] în image_prompt_en?",
        "  ✓ Zero nume de arhetipuri în image_prompt_en?",
        "",
        "Răspunde EXCLUSIV cu JSON. Prima linie: {. Ultima linie: }.",
        "",
        schema_example,
    ]
    return "\n".join(lines)


def _build_json_schema_example(
    panel_count: int,
    player_answers: list[PlayerAnswers],
    roster: Any | None,
) -> str:
    """
    Priority 3 fix: schema example uses actual character sheet data.
    The LLM sees the correct age/hair/clothing format from the start.
    """
    from .ingredient_enforcer import _translate_ingredient

    all_ingredients: list[tuple[str, str]] = []
    for pa in player_answers:
        for ans in pa.answers:
            en, color, obj = _translate_ingredient(
                ans.answer_text, ans.ingredient_role
            )
            phrase = f"{color} {obj}" if (color and obj) else en
            all_ingredients.append((ans.answer_text, phrase))

    first_en = all_ingredients[0][1] if all_ingredients else "ingredient"
    second_en = all_ingredients[1][1] if len(all_ingredients) > 1 else "second ingredient"
    player_name = player_answers[0].nickname if player_answers else "Character"
    second_player = player_answers[1].nickname if len(player_answers) > 1 else "Other"

    # Priority 3: use actual character sheet data in the example
    char1_fragment = "early 30s, short dark brown hair, wearing vibrant red outfit, with large round glasses"
    char2_fragment = "early 30s, short dark brown hair, wearing deep blue outfit, with long colourful scarf"

    if roster is not None:
        sheets = list(getattr(roster, "sheets", []))
        if len(sheets) >= 1:
            char1_fragment = sheets[0].to_prompt_fragment()
            player_name = sheets[0].nickname
        if len(sheets) >= 2:
            char2_fragment = sheets[1].to_prompt_fragment()
            second_player = sheets[1].nickname

    panels = []
    for i in range(panel_count):
        camera = _get_camera_angle(i, panel_count)
        beat = _build_causality_beat(i, panel_count, [ro for ro, _ in all_ingredients])

        if i == 0:
            prompt = (
                f"COMIC BOOK, highly detailed comic book illustration, bold ink outlines, "
                f"vibrant saturated colors, dramatic lighting, "
                f"{player_name} ({char1_fragment}) loses control of the {first_en} "
                f"which careens toward canal edge, arms flailing wildly, face twisted in panic, "
                f"mouth open in a scream, {second_player} ({char2_fragment}) diving sideways to dodge, "
                f"FOREGROUND: {first_en} skidding toward camera close-up filling bottom third, "
                f"BACKGROUND: Venice canal buildings and gondolas, bystanders reacting in shock, "
                f"{camera}"
            )
        else:
            prompt = (
                f"COMIC BOOK, highly detailed comic book illustration, bold ink outlines, "
                f"vibrant saturated colors, dramatic lighting, "
                f"{player_name} ({char1_fragment}) "
                f"crashes into / grabs / flees from / slams against "
                f"[describe specific kinetic action involving {second_en if i % 2 else first_en}], "
                f"{second_player} ({char2_fragment}) reacting with exaggerated expression, "
                f"FOREGROUND: [large close element directly in action], "
                f"BACKGROUND: [small distant location element], "
                f"{camera}"
            )

        panels.append({
            "panel_index": i,
            "description_ro": (
                f"[Descriere DINAMICĂ panou {i} — {beat['label']}, "
                f"minimum 30 cuvinte, acțiune fizică cauzată de ingrediente, ROMÂNĂ]"
            ),
            "dialogue_ro": (
                "[Dialog expresiv în ROMÂNĂ — sau șir gol dacă nu e dialog]"
            ),
            "image_prompt_en": prompt,
            "narrator_line_ro": (
                "[Narator ironic, scurt, în ROMÂNĂ]"
            ),
            "characters_in_panel": ["[archetype_key_1]", "[archetype_key_2]"],
        })

    return json.dumps(
        {
            "title": "[Titlul poveștii — specific, amuzant, referențiază ingredientele]",
            "panels": panels,
        },
        ensure_ascii=False,
        indent=2,
    )


# ── Response parser ───────────────────────────────────────────────────────────

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
    missing = [f for f in ["title", "panels"] if f not in data]
    if missing:
        raise ValueError(f"LLM response missing: {missing}")
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
    return Story(
        title=str(data.get("title", "")),
        panels=panels,
        narrator_script=[p.narrator_line_ro for p in panels],
        image_prompts=[p.image_prompt_en for p in panels],
    )