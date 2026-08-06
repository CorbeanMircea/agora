/**
 * M3.1 — CreativeBrief TypeScript Types
 *
 * TypeScript equivalents of the Python dataclasses in
 * games/cronica/pipeline/creative_director/models.py.
 *
 * These types are used by:
 *   - The platform server when reading brief.json from the output directory
 *   - The Tauri presenter (via IPC) to configure the reveal sequence
 *   - Any TypeScript tool that needs to inspect a generated brief
 *
 * Sources: GDD v0.2.1 Section 6.2, 6.3 · ADR-001
 */

// ── Enums ─────────────────────────────────────────────────────────────────────

/**
 * The visual presentation format for the generated comic.
 * Genre determines the *story*; format determines *how it is visually presented*.
 * These are independent axes (GDD Section 6.4).
 */
export type PresentationFormat =
    | 'western_comic'
    | 'fake_news_broadcast'
    | 'police_report'
    | 'documentary_film'
    | 'folk_tale_illustration'
    | 'instagram_story_sequence'
    | 'interpol_dossier';

/**
 * Controls the rhythm of the cinematic panel reveal in the Tauri presenter.
 * GDD Section 6.2: revealPacing field.
 */
export type RevealPacing =
    | 'slow-burn'
    | 'rapid-fire'
    | 'deliberate'
    | 'chaotic';

/**
 * The structural narrative role assigned to a player's ingredient answer
 * by the Creative Director. An ingredient adapts to the story, not the
 * reverse (ADR-001).
 */
export type IngredientRole =
    | 'CHARACTER'
    | 'LOCATION'
    | 'OBJECT'
    | 'CONCEPT'
    | 'NAME'
    | 'QUANTITY'
    | 'ACTION'
    | 'ATMOSPHERE';

// ── Supporting Types ──────────────────────────────────────────────────────────

/**
 * The act structure and beat map for the generated story.
 * Each genre defines a canonical StoryArc; the CD populates it from
 * the genre's template (GDD Section 6.3).
 */
export interface StoryArc {
    /** Ordered list of narrative beat labels, one per panel. */
    beats: string[];
    /** Short prose description of each act. */
    actDescriptions: string[];
    /** 0-based index of the climax/punchline beat. */
    climaxBeatIndex: number;
}

/**
 * A character role that one player's answers will fill in the story.
 * Each genre defines its own archetype set (GDD Section 6.3).
 */
export interface Archetype {
    /** Machine-readable key, e.g. "vinovatul" */
    key: string;
    /** Display name in Romanian, e.g. "Vinovatul" */
    nameRo: string;
    /** One-sentence description of this archetype's role. */
    descriptionRo: string;
    /** The playerId assigned to this archetype (set in M3.5). */
    playerId: string | null;
    /** The player's nickname at assignment time. */
    playerNickname: string | null;
    /**
     * Maps promptId → IngredientRole for this player's ingredient answers.
     * e.g. { "c_001": "OBJECT", "a_003": "ATMOSPHERE" }
     */
    ingredientRoles: Record<string, IngredientRole>;
}

/**
 * A mandatory story twist injected at a specific panel.
 * The CD generates 1–2 twists per round (GDD Section 6.2).
 */
export interface Twist {
    /** 0-based panel index at which this twist is revealed. */
    panelIndex: number;
    /** Short description of the twist for the LLM prompt. */
    descriptionRo: string;
    /** Whether this is the final/main reveal or a mid-story complication. */
    isFinalTwist: boolean;
}

/**
 * A per-panel camera/composition instruction.
 * Translates into ComfyUI prompt tokens by the Style Token Injector (M5.4).
 */
export interface CameraRule {
    /** 0-based panel index this rule applies to. */
    panelIndex: number;
    /** Human-readable shot description, e.g. "wide establishing shot, low angle" */
    description: string;
    /** ComfyUI-ready English token string. */
    promptTokens: string;
}

/**
 * The narrator's voice and personality specification.
 * Maps to ElevenLabs voice parameters or a Piper model (GDD Section 6.2, M6.4).
 */
export interface NarratorPersona {
    /** ElevenLabs voice ID or Piper model filename. */
    voiceKey: string;
    /** Prose description of the narrator's personality (for LLM prompt). */
    personalityDescriptionRo: string;
    /** ElevenLabs stability (0–1). */
    stability: number;
    /** ElevenLabs similarity_boost (0–1). */
    similarityBoost: number;
    /** ElevenLabs style exaggeration (0–1). */
    styleExaggeration: number;
    /** Speaking rate multiplier (1.0 = normal). */
    speakingRate: number;
}

/**
 * A per-panel sound effect instruction for the Tauri presenter.
 */
export interface SFXNote {
    /** 0-based panel index. */
    panelIndex: number;
    /** Description, e.g. "dramatic violin sting" */
    description: string;
    /** Timing: "on_reveal" | "during" | "on_exit" */
    timing: 'on_reveal' | 'during' | 'on_exit';
}

/**
 * How panels are arranged in the presentation format.
 * Used by the Tauri presenter to select the correct CSS grid layout.
 */
export interface LayoutStrategy {
    /** Total panel count for this round: 4, 5, 6, or 8. */
    panelCount: 4 | 5 | 6 | 8;
    /** CSS grid template identifier, e.g. "2x2", "3x2", "2x4" */
    gridTemplate: string;
    /** 0-based index of the featured/full-width panel, or null. */
    featuredPanelIndex: number | null;
    /** "horizontal" (TV) or "vertical" (phone-native). */
    orientation: 'horizontal' | 'vertical';
}

// ── Root Brief ────────────────────────────────────────────────────────────────

/**
 * The complete creative specification produced by the Creative Director.
 * Every downstream AI component receives this and uses it to shape output.
 * Written as brief.json to output/round_XXX/ by the pipeline.
 *
 * GDD Section 6.1, 6.2.
 *
 * Note: Python field names use snake_case; this TypeScript interface uses
 * camelCase as per TS convention. The JSON keys in brief.json use snake_case
 * (Python's dataclass default). Use a camelCase/snake_case adapter when
 * reading brief.json in TS if needed.
 */
export interface CreativeBrief {
    // ── Narrative ────────────────────────────────────────────────────────

    /** Genre name in Romanian, e.g. "Telenovelă Românească" */
    genre: string;
    /** Genre machine key, e.g. "telenovela_romaneasca" */
    genreKey: string;
    /** Subgenre label, e.g. "Răzbunarea neașteptată" */
    subgenre: string;
    /** Ordered act/beat structure for the round. */
    storyStructure: StoryArc;
    /** One archetype per player, populated by M3.5. */
    archetypes: Archetype[];
    /** 1–2 mandatory twists injected at specific panels. */
    twists: Twist[];
    /** Comedy level 1–10; 1 = dry/dark, 10 = pure slapstick. */
    comedyLevel: number;
    /** Short tone-defining keywords for the LLM system prompt. */
    toneKeywords: string[];

    // ── Presentation ─────────────────────────────────────────────────────

    /** Visual presentation format (independent of genre). */
    format: PresentationFormat;
    /** Number of panels: 4, 5, 6, or 8. */
    panelCount: 4 | 5 | 6 | 8;
    /** Panel arrangement strategy for the presenter. */
    panelLayout: LayoutStrategy;

    // ── Visual ───────────────────────────────────────────────────────────

    /** Prose visual style description fed to ComfyUI. */
    visualStyle: string;
    /** Dominant hex colours for panel generation. */
    colourPalette: string[];
    /** Per-panel camera and composition rules. */
    cameraLanguage: CameraRule[];
    /** Lighting mood description fed to ComfyUI. */
    lightingMood: string;

    // ── Audio ─────────────────────────────────────────────────────────────

    /** Narrator personality and TTS voice mapping. */
    narratorPersonality: NarratorPersona;
    /** Direct key into ElevenLabs voice ID map or Piper model filename. */
    narratorVoiceKey: string;
    /** Music direction description for the presenter. */
    musicDirection: string;
    /** Per-panel sound effect notes. */
    soundEffects: SFXNote[];

    // ── Pacing ────────────────────────────────────────────────────────────

    /** Controls cinematic reveal rhythm in the Tauri presenter. */
    revealPacing: RevealPacing;
    /** 0-based index of the panel that delivers the main punchline. */
    punchlinePanel: number;

    // ── Metadata ──────────────────────────────────────────────────────────

    /** Round ID from SQLite. */
    roundId?: number | null;
    /** ISO 8601 timestamp of brief generation. */
    generatedAt?: string | null;
}