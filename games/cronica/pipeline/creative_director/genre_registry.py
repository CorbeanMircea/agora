"""
M3.2 — Genre Registry

All 7 CRONICĂ genres as structured data. Each genre encodes the complete
creative specification the Creative Director needs to build a CreativeBrief.

Sources:
  GDD v0.2.1 Section 6.3 (Genre Registry)
  ADR-001 (Ingredient System — archetypes receive ingredient roles, not raw answers)

Design principles:
  - Genres are pure data (no executable logic).
  - Each genre is a GenreDefinition dataclass — extensible without breaking callers.
  - Archetype templates carry no playerId; assignment happens in M3.5.
  - All narrative copy is in Romanian. All ComfyUI tokens are in English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import (
    StoryArc,
    Archetype,
    CameraRule,
    NarratorPersona,
    SFXNote,
    LayoutStrategy,
    PresentationFormat,
    RevealPacing,
)


# ── GenreDefinition ──────────────────────────────────────────────────────────

@dataclass
class GenreDefinition:
    """
    Complete creative specification for one CRONICĂ genre.

    A GenreDefinition is the template from which the Creative Director
    populates a CreativeBrief. Fields map 1-to-1 with CreativeBrief fields
    wherever the genre is the sole determinant; ranges are used where
    randomness is appropriate (comedy_level, panel_count).
    """

    # ── Identity ──────────────────────────────────────────────────────────

    # Machine-readable key used throughout the codebase.
    key: str

    # Display name in Romanian, shown to the host during debug.
    name_ro: str

    # Short tagline describing the genre's atmosphere (Romanian).
    tagline_ro: str

    # ── Narrative ─────────────────────────────────────────────────────────

    # The canonical story structure for this genre.
    story_structure: StoryArc

    # Archetype templates — one per player slot (populated with playerId in M3.5).
    # Minimum 2 archetypes; maximum 8.
    archetype_templates: list[Archetype]

    # Inclusive comedy level range [min, max] on a 1–10 scale.
    # 1 = dry/dark, 10 = pure slapstick.
    comedy_level_range: tuple[int, int]

    # Tone keywords fed directly into the LLM system prompt (English).
    tone_keywords: list[str]

    # ── Presentation ─────────────────────────────────────────────────────

    # Allowed panel counts for this genre, in order of preference.
    # The Creative Director picks from this list (e.g. based on player count).
    panel_counts: list[int]

    # Preferred presentation formats for this genre (ordered by preference).
    # The Creative Director selects one, respecting the compatibility matrix.
    preferred_formats: list[PresentationFormat]

    # ── Visual ────────────────────────────────────────────────────────────

    # Prose visual style description fed to ComfyUI (English).
    visual_style: str

    # Dominant hex colours for panel generation (3–5 colours).
    colour_palette: list[str]

    # Per-panel camera rule templates.
    # The Creative Director maps these to actual panel indices at brief time.
    # Length should match the maximum panel count.
    camera_language_templates: list[CameraRule]

    # Lighting mood fed to ComfyUI (English).
    lighting_mood: str

    # ComfyUI positive style tokens (English) applied to every panel.
    style_tokens_positive: list[str]

    # ComfyUI negative style tokens (English) applied to every panel.
    style_tokens_negative: list[str]

    # ── Audio ─────────────────────────────────────────────────────────────

    # The narrator persona for this genre.
    narrator_personality: NarratorPersona

    # Music direction description for the Tauri presenter (Romanian).
    music_direction_ro: str

    # Per-panel sound effect templates (index is relative, not absolute).
    sfx_templates: list[SFXNote]

    # ── Pacing ────────────────────────────────────────────────────────────

    # How panels are revealed in the Tauri presenter.
    reveal_pacing: RevealPacing

    # ── Meta ──────────────────────────────────────────────────────────────

    # Minimum number of players required for this genre (some archetypes
    # require specific player counts).
    min_players: int = 2

    # Maximum players (bounded by archetype count).
    max_players: int = 8


# ── Helper: build camera language templates ──────────────────────────────────

def _cam(panel_index: int, description: str, tokens: str) -> CameraRule:
    return CameraRule(
        panel_index=panel_index,
        description=description,
        prompt_tokens=tokens,
    )


def _sfx(panel_index: int, description: str, timing: str = "on_reveal") -> SFXNote:
    return SFXNote(
        panel_index=panel_index,
        description=description,
        timing=timing,
    )


def _archetype(key: str, name_ro: str, description_ro: str) -> Archetype:
    return Archetype(
        key=key,
        name_ro=name_ro,
        description_ro=description_ro,
        player_id=None,
        player_nickname=None,
        ingredient_roles={},
    )


def _narrator(
    voice_key: str,
    personality_ro: str,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style_exaggeration: float = 0.5,
    speaking_rate: float = 1.0,
) -> NarratorPersona:
    return NarratorPersona(
        voice_key=voice_key,
        personality_description_ro=personality_ro,
        stability=stability,
        similarity_boost=similarity_boost,
        style_exaggeration=style_exaggeration,
        speaking_rate=speaking_rate,
    )


# ── Genre 1: Telenovelă Românească ───────────────────────────────────────────

TELENOVELA = GenreDefinition(
    key="telenovela_romaneasca",
    name_ro="Telenovelă Românească",
    tagline_ro="Dragoste, trădare și lacrimi de crocodil",

    story_structure=StoryArc(
        beats=[
            "revelatie_soc",        # Shocking revelation
            "negare_dramatica",     # Dramatic denial
            "confruntare_lacrimi",  # Tearful confrontation
            "rasucire_neasteptata", # Unexpected twist
            "cadere_teatrala",      # Theatrical collapse
            "reconciliere_dubioasa",# Dubious reconciliation
        ],
        act_descriptions=[
            "Un secret murdar iese la iveală în cel mai prost moment posibil.",
            "Personajele se confruntă într-un vârtej de acuzații și lacrimi false.",
            "O răsturnare neașteptată schimbă totul — dar nimeni nu pare fericit.",
        ],
        climax_beat_index=3,
    ),

    archetype_templates=[
        _archetype("victima",   "Victima",   "Cel care suferă în tăcere dar nu ratează nicio oportunitate de a dramatiza."),
        _archetype("tradatorul","Trădătorul", "Cel care a comis fapta — sau măcar pare că a comis-o."),
        _archetype("razbunator","Răzbunătorul","Cel care știe tot și așteaptă momentul potrivit."),
        _archetype("martorul",  "Martorul",  "Cel care vede totul dar intervine mereu la momentul nepotrivit."),
        _archetype("confidentul","Confidentul","Cel în care toată lumea are încredere, în mod nejustificat."),
        _archetype("rivalul",   "Rivalul",   "Cel care transformă orice situație într-o competiție."),
    ],

    comedy_level_range=(5, 9),
    tone_keywords=["melodramatic", "breathless", "overwrought", "sincere-but-absurd"],

    panel_counts=[5, 6],
    preferred_formats=[
        PresentationFormat.WESTERN_COMIC,
        PresentationFormat.FAKE_NEWS_BROADCAST,
    ],

    visual_style=(
        "Romanian telenovela aesthetic, oversaturated warm colours, dramatic close-ups "
        "on faces mid-emotion, heavy eye shadow, theatrical lighting, soap opera framing"
    ),
    colour_palette=["#C0392B", "#E8DAEF", "#F39C12", "#1A1A2E", "#D4AC0D"],
    camera_language_templates=[
        _cam(0, "Extreme close-up on a shocked face",         "extreme close-up, shocked expression, dramatic lighting, telenovela"),
        _cam(1, "Over-the-shoulder confrontation",            "over the shoulder shot, confrontation, two people, telenovela framing"),
        _cam(2, "Low angle looking up at standing figure",    "low angle shot, power stance, looking up, dramatic"),
        _cam(3, "Dutch angle during the twist reveal",        "dutch angle, twist reveal, disorienting, cinematic"),
        _cam(4, "Wide shot of chaotic room aftermath",        "wide shot, chaotic room, aftermath, multiple characters"),
        _cam(5, "Close-up on a meaningful object or letter",  "close-up, prop detail, meaningful object, soft focus background"),
    ],
    lighting_mood="warm, harsh top light, theatrical shadows, telenovela studio look",
    style_tokens_positive=["telenovela aesthetic", "oversaturated", "dramatic lighting", "soap opera", "emotional faces"],
    style_tokens_negative=["horror", "dark", "desaturated", "minimalist", "cold tones"],

    narrator_personality=_narrator(
        voice_key="ro_telenovela_dramatic",
        personality_ro="Voce melodramatică, pauze interminabile, adresare directă la spectator, întrebări retorice frecvente.",
        stability=0.35,
        similarity_boost=0.80,
        style_exaggeration=0.85,
        speaking_rate=0.9,
    ),
    music_direction_ro="Vioară dramatică, crescendo înainte de răsturnare, tăcere bruscă la twist.",
    sfx_templates=[
        _sfx(0, "Sting dramatic de vioară",          "on_reveal"),
        _sfx(3, "Lovitură orchestrală de șoc",        "on_reveal"),
        _sfx(4, "Muzică melancolică de pian",         "during"),
    ],
    reveal_pacing=RevealPacing.DELIBERATE,
    min_players=2,
    max_players=6,
)


# ── Genre 2: Film de Acțiune B ───────────────────────────────────────────────

ACTIUNE_B = GenreDefinition(
    key="film_actiune_b",
    name_ro="Film de Acțiune B",
    tagline_ro="Explozii, one-linere și logică opțională",

    story_structure=StoryArc(
        beats=[
            "misiune_imposibila",   # Impossible mission briefing
            "actiune_imediat",      # Immediate action, no explanation
            "tradare_neasteptata",  # Unexpected betrayal
            "one_liner",            # The one-liner moment
            "explozie_finala",      # Final explosion
        ],
        act_descriptions=[
            "Misiunea e clară, nimeni nu pune întrebări, toată lumea are o armă.",
            "Totul merge bine până când nu mai merge. Cineva trădează. Explozii.",
            "Eroul supraviețuiește împotriva oricărei logici și spune ceva memorabil.",
        ],
        climax_beat_index=4,
    ),

    archetype_templates=[
        _archetype("eroul",       "Eroul",        "Cel care face totul singur și nu are nevoie de ajutor — dar îl acceptă totuși."),
        _archetype("tradatorul",  "Trădătorul",   "Cel care a fost de partea lor tot timpul. Surpriză."),
        _archetype("expertul",    "Expertul",     "Cel cu o abilitate specifică inexplicabilă, prezentă exact când e nevoie."),
        _archetype("antagonistul","Antagonistul", "Cel cu un plan elaborat care ignoră soluțiile simple."),
        _archetype("aliatul",     "Aliatul",      "Cel care apare la mijloc și salvează situația prin accident."),
        _archetype("informatorul","Informatorul", "Cel care știe totul dar comunică în ghicitori."),
    ],

    comedy_level_range=(6, 10),
    tone_keywords=["over-the-top", "action-movie clichés", "unironic confidence", "explosive"],

    panel_counts=[4, 5, 6],
    preferred_formats=[
        PresentationFormat.WESTERN_COMIC,
        PresentationFormat.POLICE_REPORT,
    ],

    visual_style=(
        "B-movie action film aesthetic, high contrast, lens flare, explosion backgrounds, "
        "muscular poses, American action movie comic style, bold outlines"
    ),
    colour_palette=["#E74C3C", "#2C3E50", "#F39C12", "#ECF0F1", "#E67E22"],
    camera_language_templates=[
        _cam(0, "Extreme low angle hero shot",        "extreme low angle, hero pose, action movie, lens flare, dynamic"),
        _cam(1, "Fast motion blur action sequence",   "motion blur, action, fast movement, dynamic lines, comic book"),
        _cam(2, "Close-up on the betrayal face",      "close-up, betrayal expression, shocked, dramatic reveal"),
        _cam(3, "The one-liner wide shot",            "wide shot, cool pose, aftermath, rubble, confident stance"),
        _cam(4, "Explosion wide establishing shot",   "wide shot, explosion, fire, action climax, orange smoke"),
        _cam(5, "Victory freeze frame",               "freeze frame, victory pose, triumphant, sunset background"),
    ],
    lighting_mood="high contrast, explosion orange glow, strong rim lighting, dramatic shadows",
    style_tokens_positive=["action movie aesthetic", "high contrast", "dynamic poses", "comic book style", "bold colors"],
    style_tokens_negative=["soft lighting", "quiet", "introspective", "pastel colors", "slow paced"],

    narrator_personality=_narrator(
        voice_key="ro_actiune_badass",
        personality_ro="Voce gravă, autoritate maximă, fraze scurte. Pauzele dramatice sunt obligatorii. Niciun cuvânt în plus.",
        stability=0.65,
        similarity_boost=0.70,
        style_exaggeration=0.60,
        speaking_rate=0.85,
    ),
    music_direction_ro="Chitară electrică agresivă, percuție puternică, tăcere bruscă înainte de one-liner.",
    sfx_templates=[
        _sfx(0, "Sunet de explozie la distanță",          "on_reveal"),
        _sfx(3, "Rimshot comic după one-liner",            "on_reveal"),
        _sfx(4, "Explozie mare cu reverberație",           "on_reveal"),
    ],
    reveal_pacing=RevealPacing.RAPID_FIRE,
    min_players=2,
    max_players=6,
)


# ── Genre 3: Basm Românesc Absurd ────────────────────────────────────────────

BASM_ABSURD = GenreDefinition(
    key="basm_romanesc_absurd",
    name_ro="Basm Românesc Absurd",
    tagline_ro="A fost odată ca niciodată... și s-a terminat prost",

    story_structure=StoryArc(
        beats=[
            "a_fost_odata",         # Once upon a time setup
            "problema_ciudata",     # The strange problem
            "calatoria_absurda",    # Absurd quest begins
            "intalnire_magica",     # Magical encounter
            "rasucire_basm",        # Fairy tale twist
            "moral_invers",         # The inverted moral
        ],
        act_descriptions=[
            "A fost odată o problemă care nu ar fi trebuit să existe, dar exista.",
            "Eroii pornesc la drum și întâlnesc lucruri pe care nu le-au cerut.",
            "Totul se termină, dar nu cum se așteptau nici eroii, nici spectatorii.",
        ],
        climax_beat_index=4,
    ),

    archetype_templates=[
        _archetype("eroul_prost",   "Eroul Prost",     "Cel trimis în misiune pentru că nimeni altcineva nu a vrut."),
        _archetype("mos_inteleput", "Moșul Înțelept",  "Cel care dă sfaturi inutile în cel mai ornamentat mod posibil."),
        _archetype("duhul_rau",     "Duhul Rău",       "Cel al cărui plan ar funcționa dacă toată lumea ar coopera."),
        _archetype("fat_frumos",    "Fătul Frumos",    "Cel care arată bine și nu face mare lucru, dar e apreciat."),
        _archetype("ileana",        "Ileana Necajita",  "Cel care are o problemă și toți ceilalți trebuie să o rezolve."),
        _archetype("zana_absurda",  "Zâna Absurdă",    "Cel cu puteri magice pe care le folosește în moduri irelevante."),
    ],

    comedy_level_range=(7, 10),
    tone_keywords=["deadpan absurdism", "fairy tale cadence", "Romanian folklore", "surreal"],

    panel_counts=[5, 6],
    preferred_formats=[
        PresentationFormat.FOLK_TALE_ILLUSTRATION,
        PresentationFormat.WESTERN_COMIC,
    ],

    visual_style=(
        "Romanian folk tale illustration style, flat colours, ornamental borders, "
        "peasant costumes mixed with anachronistic objects, Naive art aesthetic, "
        "warm earthy tones, hand-drawn quality"
    ),
    colour_palette=["#8B4513", "#DAA520", "#228B22", "#DC143C", "#F5DEB3"],
    camera_language_templates=[
        _cam(0, "Establishing wide shot of a village or forest", "wide shot, village, Romanian landscape, folk art style, establishing"),
        _cam(1, "Character introduction portrait",              "portrait shot, character introduction, folk costume, ornamental border"),
        _cam(2, "Journey montage panel",                        "journey, path through forest, multiple small figures, overhead view"),
        _cam(3, "Magical encounter mid-shot",                   "mid shot, magical creature, surprised expression, glowing effect"),
        _cam(4, "The twist moment close-up",                    "close-up, twist reveal, wide eyes, folk art dramatic"),
        _cam(5, "Final moral tableau",                          "wide shot, all characters, tableau composition, symbolic ending"),
    ],
    lighting_mood="warm daylight, golden hour, flat even lighting, folk illustration feel",
    style_tokens_positive=["folk art style", "Romanian aesthetic", "flat colors", "ornamental", "naive art", "warm earthy tones"],
    style_tokens_negative=["photorealistic", "dark horror", "urban", "modern technology", "cold colors"],

    narrator_personality=_narrator(
        voice_key="ro_basm_povestitor",
        personality_ro="Ritmul unui povestitor bătrân la gura sobei. Formule consacrate folosite incorect. Digresiuni inutile dar savuroase.",
        stability=0.55,
        similarity_boost=0.65,
        style_exaggeration=0.40,
        speaking_rate=0.85,
    ),
    music_direction_ro="Nai și acordeon, melodie simplă repetitivă, ritm de poveste.",
    sfx_templates=[
        _sfx(0, "Sunet magic de clopoțel la deschidere",  "on_reveal"),
        _sfx(3, "Efect magic de zână",                     "on_reveal"),
        _sfx(5, "Acord final de acordeon",                 "on_reveal"),
    ],
    reveal_pacing=RevealPacing.SLOW_BURN,
    min_players=2,
    max_players=6,
)


# ── Genre 4: Scandal de Bloc ─────────────────────────────────────────────────

SCANDAL_BLOC = GenreDefinition(
    key="scandal_de_bloc",
    name_ro="Scandal de Bloc",
    tagline_ro="Vecini, note la ușă și drepturi imaginare",

    story_structure=StoryArc(
        beats=[
            "nemultumire_initiala",
            "nota_la_usa",
            "escaladare_inutila",
            "adunare_generala",
            "interventie_neasteptata",
            "rezolvare_nesatisfacatoare",
        ],
        act_descriptions=[
            "O problemă minoră devine imediat un conflict de principii.",
            "Toată lumea are dreptate și nimeni nu ascultă.",
            "Se rezolvă ceva, dar toată lumea e la fel de nemulțumită ca la început.",
        ],
        climax_beat_index=3,
    ),

    archetype_templates=[
        _archetype("reclamantul",    "Reclamantul",    "Cel cu o problemă și timp nelimitat să o exprime în scris."),
        _archetype("acuzatul",       "Acuzatul",       "Cel care nu a făcut nimic dar se comportă ca și cum ar fi vinovat."),
        _archetype("administratorul","Administratorul","Cel cu putere limitată pe care o exercită maximal."),
        _archetype("noului_vecin",   "Noul Vecin",     "Cel care a greșit bloc și nu știe încă."),
        _archetype("aliatul_secret", "Aliatul Secret", "Cel care pretinde că e neutru dar are agenda lui."),
        _archetype("batrana_etaj3",  "Bâtrâna de la 3","Cel care știe tot ce se întâmplă de 40 de ani și are opinii."),
    ],

    comedy_level_range=(6, 9),
    tone_keywords=["passive-aggressive", "petty bureaucracy", "Romanian apartment block", "mundane conflict"],

    panel_counts=[4, 5, 6],
    preferred_formats=[
        PresentationFormat.POLICE_REPORT,
        PresentationFormat.WESTERN_COMIC,
        PresentationFormat.FAKE_NEWS_BROADCAST,
    ],

    visual_style=(
        "Romanian communist-era apartment block aesthetic, grey concrete, fluorescent lights, "
        "handwritten notes on doors, 1970s-1990s interior design, realistic mundane setting"
    ),
    colour_palette=["#808080", "#F5F5DC", "#8B8000", "#A0522D", "#2F4F4F"],
    camera_language_templates=[
        _cam(0, "Wide shot of apartment hallway",            "wide shot, apartment hallway, grey concrete, fluorescent light, realistic"),
        _cam(1, "Close-up on a note taped to a door",        "close-up, handwritten note, door, Romanian apartment"),
        _cam(2, "Confrontation in stairwell",                "mid shot, stairwell confrontation, two neighbors, dramatic"),
        _cam(3, "Chaos of building meeting overhead view",   "overhead shot, crowded meeting, chaos, multiple people gesturing"),
        _cam(4, "The unexpected arrival",                    "door opening shot, surprise entrance, backlit silhouette"),
        _cam(5, "Final note on the door",                    "extreme close-up, final note, taped to door, resigned atmosphere"),
    ],
    lighting_mood="harsh fluorescent, grey concrete shadows, occasionally warm kitchen light",
    style_tokens_positive=["apartment block aesthetic", "mundane realism", "Romanian setting", "grey concrete", "everyday objects"],
    style_tokens_negative=["fantasy", "magical", "vibrant colors", "outdoor nature", "sci-fi"],

    narrator_personality=_narrator(
        voice_key="ro_scandal_bloc_neutru",
        personality_ro="Ton de știri locale. Neutralitate exagerată care subliniază absurdul. Citire impecabilă din proces-verbal.",
        stability=0.70,
        similarity_boost=0.65,
        style_exaggeration=0.30,
        speaking_rate=1.0,
    ),
    music_direction_ro="Muzică de lift veche, eventual întreruptă brusc. Tăcere incomodă la momente cheie.",
    sfx_templates=[
        _sfx(0, "Sunet de interfon vechi",                "on_reveal"),
        _sfx(3, "Voci suprapuse în dezacord",              "during"),
        _sfx(5, "Scârțâit de ușă urmată de liniște",       "on_reveal"),
    ],
    reveal_pacing=RevealPacing.DELIBERATE,
    min_players=2,
    max_players=6,
)


# ── Genre 5: Documentar Fals ─────────────────────────────────────────────────

DOCUMENTAR_FALS = GenreDefinition(
    key="documentar_fals",
    name_ro="Documentar Fals",
    tagline_ro="Bazat pe o poveste adevărată. Probabil.",

    story_structure=StoryArc(
        beats=[
            "prezentare_subiect",
            "martor_expert",
            "dovada_dubioasa",
            "interviu_contradictie",
            "revelatie_finala",
        ],
        act_descriptions=[
            "Un subiect complet banal este prezentat ca misterul secolului.",
            "Experți inexistenți și martori dubioși confirmă o teorie elaborată.",
            "Concluzia documentarului nu rezolvă nimic dar ridică noi întrebări.",
        ],
        climax_beat_index=4,
    ),

    archetype_templates=[
        _archetype("subiectul",    "Subiectul",     "Cel despre care e documentarul și care nu știe exact ce se întâmplă."),
        _archetype("expertul",     "Expertul",       "Cel cu titlu dubios care vorbește cu convingere maximă."),
        _archetype("martorul",     "Martorul",       "Cel care a văzut totul și nimeni nu îl crede."),
        _archetype("scepticul",    "Scepticul",      "Cel care are dreptate dar e prezentat ca antagonist."),
        _archetype("naratorul_off","Naratorul Off",  "Cel care leagă totul cu fraze dramatice între interviuri."),
    ],

    comedy_level_range=(4, 8),
    tone_keywords=["mock-documentary", "serious tone about absurd subject", "Romanian conspiracy", "deadpan"],

    panel_counts=[5, 6],
    preferred_formats=[
        PresentationFormat.DOCUMENTARY_FILM,
        PresentationFormat.FAKE_NEWS_BROADCAST,
        PresentationFormat.POLICE_REPORT,
    ],

    visual_style=(
        "Documentary film aesthetic, handheld camera feel, interview talking head shots, "
        "lower thirds text overlays, archival footage look, slightly desaturated, "
        "serious journalistic framing"
    ),
    colour_palette=["#2C3E50", "#95A5A6", "#E8D5B7", "#1A1A2E", "#BDC3C7"],
    camera_language_templates=[
        _cam(0, "Establishing shot with title card",          "establishing shot, documentary title card, serious, slightly desaturated"),
        _cam(1, "Talking head interview medium shot",          "medium shot, interview, talking head, documentary, lower third overlay"),
        _cam(2, "Close-up on dubious evidence",               "extreme close-up, evidence item, dramatic lighting, documentary"),
        _cam(3, "Confrontational interview over-shoulder",    "over the shoulder, confrontational interview, documentary style"),
        _cam(4, "Dramatic pan to empty space (revelation)",   "slow pan, empty space, revelation, documentary drama"),
        _cam(5, "Final interview medium shot",                "medium shot, final statement, interview, documentary ending"),
    ],
    lighting_mood="documentary natural light, slightly underexposed, interview key light only",
    style_tokens_positive=["documentary film aesthetic", "handheld camera", "desaturated", 
                        "realistic", "journalistic", "16mm film grain", "archival footage look",
                        "observational framing"],
    style_tokens_negative=["comic book", "animation", "bright saturated", "fantasy", "folk art",
                        "action movie", "dramatic studio lighting"],
    narrator_personality=_narrator(
        voice_key="ro_documentar_grav",
        personality_ro="Gravitate absolută față de subiecte banale. Pauze semnificative înainte de fraze evidente. Ton de descoperire permanentă.",
        stability=0.75,
        similarity_boost=0.70,
        style_exaggeration=0.25,
        speaking_rate=0.90,
    ),
    music_direction_ro="Dronă ambientală minimalistă, crescendo lent la momente cheie, tăcere la revelație.",
    sfx_templates=[
        _sfx(0, "Sunet de cameră de film pornind",         "on_reveal"),
        _sfx(2, "Clic de cameră foto pentru dovadă",        "on_reveal"),
        _sfx(4, "Dronă muzicală la revelație",              "during"),
    ],
    reveal_pacing=RevealPacing.SLOW_BURN,
    min_players=2,
    max_players=5,
)


# ── Genre 6: Horror Mioritic ─────────────────────────────────────────────────

HORROR_MIORITIC = GenreDefinition(
    key="horror_mioritic",
    name_ro="Horror Mioritic",
    tagline_ro="Spaima de la sat, prezentată cu seninătate",

    story_structure=StoryArc(
        beats=[
            "semn_rau",             # Bad omen
            "avertiznament_ignorat",# Ignored warning
            "aparitia",             # The apparition
            "logica_absurda",       # Absurd logic applied to horror
            "sfarsit_senin",        # Inexplicably serene ending
        ],
        act_descriptions=[
            "Cineva ignoră semnele clare că ceva e în neregulă.",
            "Lucruri înfricoșătoare se întâmplă, dar personajele reacționează inadecvat.",
            "Totul se termină mai bine decât ar fi trebuit, fără explicații.",
        ],
        climax_beat_index=3,
    ),

    archetype_templates=[
        _archetype("necredinciosul", "Necredinciosul", "Cel care ignoră toate avertismentele și e surprins de consecințe."),
        _archetype("batranica",      "Bătrânica",      "Cel care știe tot despre blestem dar nu zice tot."),
        _archetype("spiritul",       "Spiritul",       "Cel care nu mai e printre cei vii dar are probleme de comunicare."),
        _archetype("scepticul",      "Scepticul",      "Cel cu explicații raționale pentru tot, greșite în mod invariabil."),
        _archetype("supravietuitorul","Supraviețuitorul","Cel care scapă și nu înțelege de ce."),
    ],

    comedy_level_range=(3, 7),
    tone_keywords=["folk horror", "Romanian countryside", "serene dread", "bureaucratic supernatural"],

    panel_counts=[4, 5],
    preferred_formats=[
        PresentationFormat.FOLK_TALE_ILLUSTRATION,
        PresentationFormat.WESTERN_COMIC,
        PresentationFormat.DOCUMENTARY_FILM,
    ],

    visual_style=(
        "Romanian rural horror aesthetic, muted foggy colours, traditional village setting, "
        "old architecture, candle light, folklore creature design, ominous but beautiful, "
        "inspired by Romanian folk art with dark undertones"
    ),
    colour_palette=["#2C1810", "#5D4E37", "#8B9DC3", "#C8B89A", "#1A1A2E"],
    camera_language_templates=[
        _cam(0, "Foggy establishing shot of village",         "wide establishing, foggy village, ominous, muted colors, Romanian setting"),
        _cam(1, "Medium shot of ignored warning",             "medium shot, warning sign, character ignoring, ominous atmosphere"),
        _cam(2, "The apparition sudden reveal",               "sudden reveal, apparition, horror beat, shocked reaction"),
        _cam(3, "Absurd reaction close-up",                   "close-up, absurd calm reaction to horror, deadpan expression"),
        _cam(4, "Serene wide shot of aftermath",              "wide shot, peaceful aftermath, inexplicable serenity, morning light"),
    ],
    lighting_mood="candlelight, foggy moonlight, cold blue outdoor, warm amber indoor, chiaroscuro",
    style_tokens_positive=["folk horror", "Romanian village", "foggy", "candlelight", "muted colors", "ominous"],
    style_tokens_negative=["bright", "cheerful", "modern", "urban", "saturated colors", "action"],

    narrator_personality=_narrator(
        voice_key="ro_horror_senin",
        personality_ro="Calm absolut față de situații terifiante. Ton de buletinul meteo la raportarea evenimentelor supranaturale.",
        stability=0.80,
        similarity_boost=0.60,
        style_exaggeration=0.15,
        speaking_rate=0.80,
    ),
    music_direction_ro="Doină distorsionată, instrumente tradiționale în ritmuri incomode, absența muzicii la aparițe.",
    sfx_templates=[
        _sfx(0, "Vânt și bufniță la deschidere",          "on_reveal"),
        _sfx(2, "Tăcere absolută la apariție",              "on_reveal"),
        _sfx(4, "Pasăre cântând a doua zi dimineața",       "on_reveal"),
    ],
    reveal_pacing=RevealPacing.SLOW_BURN,
    min_players=2,
    max_players=5,
)


# ── Genre 7: Știri Rupte din Realitate ───────────────────────────────────────

STIRI_RUPTE = GenreDefinition(
    key="stiri_rupte_din_realitate",
    name_ro="Știri Rupte din Realitate",
    tagline_ro="Breaking news din România profundă",

    story_structure=StoryArc(
        beats=[
            "breaking_news",        # Breaking news alert
            "reporter_teren",       # Field reporter update
            "reactie_oficial",      # Official reaction (missing the point)
            "complicatie_noua",     # New complication breaks
            "concluzie_nesatisfacatoare",  # Unsatisfying conclusion
        ],
        act_descriptions=[
            "Un eveniment local devine inexplicabil de important la nivel național.",
            "Oficialii și reporterii complică situația mai mult decât o clarifică.",
            "Totul se termină fără rezolvare, urmând să revenim cu detalii.",
        ],
        climax_beat_index=3,
    ),

    archetype_templates=[
        _archetype("reporterul",    "Reporterul",   "Cel care e acolo live și nu înțelege ce se întâmplă."),
        _archetype("oficialul",     "Oficialul",    "Cel cu declarație pregătită pentru orice situație, irelevantă pentru aceasta."),
        _archetype("martorul",      "Martorul",     "Cel care a văzut totul și ce a văzut nu are sens."),
        _archetype("expertul",      "Expertul TV",  "Cel chemat să comenteze un subiect pe care nu îl cunoaște."),
        _archetype("protagonistul", "Protagonistul","Cel despre care e știrea și care încearcă să explice."),
        _archetype("prezentatorul", "Prezentatorul","Cel care leagă toate intervențiile și agravează situația cu întrebări."),
    ],

    comedy_level_range=(6, 10),
    tone_keywords=["breaking news energy", "Romanian local news", "bureaucratic absurdism", "live TV chaos"],

    panel_counts=[4, 5, 6],
    preferred_formats=[
        PresentationFormat.FAKE_NEWS_BROADCAST,
        PresentationFormat.POLICE_REPORT,
        PresentationFormat.INTERPOL_DOSSIER,
    ],

    visual_style=(
        "Romanian local news broadcast aesthetic, lower thirds breaking news graphics, "
        "talking head interviews, urgent chyron text overlays, studio lighting, "
        "field reporter in front of mundane location, news channel visual grammar"
    ),
    colour_palette=["#C0392B", "#2C3E50", "#ECF0F1", "#E74C3C", "#F39C12"],
    camera_language_templates=[
        _cam(0, "News studio wide shot with anchor",          "wide shot, news studio, anchor desk, breaking news graphics, urgency"),
        _cam(1, "Field reporter live shot in front of scene", "medium shot, field reporter, live shot, mundane location background"),
        _cam(2, "Official press conference podium",           "medium shot, podium, press conference, official, crowd of microphones"),
        _cam(3, "Witness interview handheld",                 "handheld, witness interview, street, documentary news style"),
        _cam(4, "Studio close-up during breaking development","close-up, anchor reacting, breaking news, live update"),
        _cam(5, "Split screen chaos final",                   "split screen composition, multiple feeds, news channel, chaos"),
    ],
    lighting_mood="harsh studio lighting, news broadcast flat light, field natural light with fill",
    style_tokens_positive=["news broadcast aesthetic", "lower thirds graphics", "journalism", "live TV", "Romanian setting"],
    style_tokens_negative=["fantasy", "animation", "folk art", "dark horror", "quiet"],

    narrator_personality=_narrator(
        voice_key="ro_stiri_prezentator",
        personality_ro="Urgență continuă indiferent de subiect. Fiecare poveste e Breaking News. Tranziții abrupte și voce de prezentator TV.",
        stability=0.45,
        similarity_boost=0.75,
        style_exaggeration=0.70,
        speaking_rate=1.15,
    ),
    music_direction_ro="Jingle urgent de știri, tobe rapide la breaking news, muzică de fundal continuă și agasantă.",
    sfx_templates=[
        _sfx(0, "Jingle breaking news",                   "on_reveal"),
        _sfx(2, "Sunet de microfoane multiple",            "on_reveal"),
        _sfx(4, "Alertă nouă de breaking news",            "on_reveal"),
    ],
    reveal_pacing=RevealPacing.RAPID_FIRE,
    min_players=2,
    max_players=6,
)


# ── Registry ─────────────────────────────────────────────────────────────────

GENRE_REGISTRY: dict[str, GenreDefinition] = {
    TELENOVELA.key:    TELENOVELA,
    ACTIUNE_B.key:     ACTIUNE_B,
    BASM_ABSURD.key:   BASM_ABSURD,
    SCANDAL_BLOC.key:  SCANDAL_BLOC,
    DOCUMENTAR_FALS.key: DOCUMENTAR_FALS,
    HORROR_MIORITIC.key: HORROR_MIORITIC,
    STIRI_RUPTE.key:   STIRI_RUPTE,
}

GENRE_KEYS: list[str] = list(GENRE_REGISTRY.keys())


def get_genre(key: str) -> GenreDefinition:
    """
    Retrieve a genre by its machine-readable key.
    Raises KeyError with a helpful message if the genre does not exist.
    """
    if key not in GENRE_REGISTRY:
        available = ", ".join(GENRE_KEYS)
        raise KeyError(f"Genre '{key}' not found. Available genres: {available}")
    return GENRE_REGISTRY[key]


def list_genres() -> list[GenreDefinition]:
    """Return all genres in registration order."""
    return list(GENRE_REGISTRY.values())