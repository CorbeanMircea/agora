/**
 * AgoraGameModule Interface — M1.13
 *
 * Defines the contract that every game module must satisfy to run on the
 * AGORA platform. CRONICĂ (and all future games) implement this interface.
 *
 * This file contains only types and interfaces — zero concrete implementation.
 * No platform code imports from specific game modules; game modules import
 * from here to verify they satisfy the platform contract.
 *
 * Fields sourced from GDD Section 1.3.
 */
export type {
    PresentationFormat,
    RevealPacing,
    IngredientRole,
    StoryArc,
    Archetype,
    Twist,
    CameraRule,
    NarratorPersona,
    SFXNote,
    LayoutStrategy,
    CreativeBrief,
} from './creativeBrief.js';
import type { RoomState } from '../db/types.js';

// ── Phase Definition ────────────────────────────────────────────────────────

/**
 * Describes a single phase in a game module's round lifecycle.
 *
 * A phase maps to one of the platform's canonical RoomState values and
 * carries the metadata the platform needs to manage timers and transitions.
 */
export interface PhaseDefinition {
    /** The platform state this phase corresponds to. */
    state: RoomState;

    /**
     * Human-readable label for host-facing UIs (Romanian).
     * e.g. "Răspunsuri", "Generare", "Dezvăluire"
     */
    label: string;

    /**
     * Duration of this phase in seconds.
     * `null` means the phase is untimed — it only advances on an explicit
     * host/server action (e.g. GENERATING, REVEALING).
     */
    durationSeconds: number | null;

    /**
     * Whether this phase is visible to players on their phones.
     * Invisible phases (e.g. GENERATING) show a waiting screen instead of
     * a dedicated phone UI.
     */
    playerVisible: boolean;
}

// ── Prompt Pack ─────────────────────────────────────────────────────────────

/**
 * A single prompt entry.
 * The full JSON schema is validated at load time in M2.1; this type captures
 * the minimum shape the platform needs to reference prompts by ID.
 */
export interface PromptEntry {
    /** Globally unique identifier within the pack, e.g. "cronica_001". */
    id: string;

    /** The prompt text shown to players (Romanian). */
    text: string;

    /** Thematic category, e.g. "relație", "muncă", "situație_absurdă". */
    category: string;

    /**
     * When `true`, this prompt is always shown even in Safe Mode.
     * When `false`, the prompt is excluded when Safe Mode is enabled.
     */
    safeMode: boolean;

    /** Minimum number of players required for this prompt to make sense. */
    minPlayers: number;
}

/**
 * A complete prompt pack shipped with a game module.
 */
export interface PromptPack {
    /** Unique identifier for this pack, e.g. "cronica_base". */
    id: string;

    /** Display name (Romanian). */
    name: string;

    /** Semantic version string, e.g. "1.0.0". */
    version: string;

    /** All prompts in this pack. */
    prompts: PromptEntry[];
}

// ── AI Pipeline ─────────────────────────────────────────────────────────────

/**
 * Describes the AI pipeline a game module uses during the GENERATING phase.
 *
 * The platform uses this to know how to start the pipeline process and where
 * to find the generated assets. All pipeline logic lives in the game module —
 * the platform only manages the lifecycle call.
 */
export interface AIPipeline {
    /**
     * HTTP base URL of the pipeline orchestrator process.
     * e.g. "http://127.0.0.1:5100"
     * The platform will POST to `{baseUrl}/pipeline/run` to start a round.
     */
    orchestratorUrl: string;

    /**
     * Absolute path to the output directory where the pipeline writes assets.
     * Panel PNGs, narration WAVs, and `story.json` are placed here.
     * The platform passes this to the presenter when the pipeline completes.
     */
    outputDir: string;

    /**
     * Timeout in milliseconds for the full pipeline run.
     * If the pipeline does not complete within this window, the platform
     * marks the round as failed and advances to the next phase.
     * Default recommendation: 120_000 (2 minutes).
     */
    timeoutMs: number;
}

// ── Presenter Module ─────────────────────────────────────────────────────────

/**
 * Describes the Tauri 2 presenter window used to display AI-generated content.
 *
 * The platform launches this window at the start of the REVEALING phase and
 * instructs it to load assets from the pipeline output directory.
 */
export interface PresenterModule {
    /**
     * Path to the Tauri 2 executable (relative to the monorepo root).
     * e.g. "games/cronica/presenter/target/release/cronica-presenter.exe"
     */
    executablePath: string;

    /**
     * IPC event name the presenter listens for to begin the reveal sequence.
     * The platform emits this via the Tauri IPC bridge once assets are ready.
     * e.g. "cronica:start_reveal"
     */
    startRevealEvent: string;

    /**
     * IPC event name the presenter emits when the reveal sequence is complete.
     * The platform listens for this to advance the state machine to VOTING.
     * e.g. "cronica:reveal_complete"
     */
    revealCompleteEvent: string;
}

// ── Phone Module ─────────────────────────────────────────────────────────────

/**
 * Describes the Svelte 5 phone UI screens contributed by the game module.
 *
 * The platform phone shell dynamically routes to game-specific screens during
 * active phases. Each entry maps a platform phase to a SvelteKit route path.
 */
export interface PhoneModule {
    /**
     * Map of RoomState → SvelteKit route path (relative to the phone shell's
     * `/phone` base path).
     *
     * Only phases that need a game-specific screen need an entry here.
     * Phases without an entry fall back to the platform's generic wait screen.
     *
     * Example:
     * ```
     * {
     *   PROMPTING: '/cronica/answer',
     *   VOTING:    '/cronica/vote',
     *   SCORING:   '/cronica/score',
     * }
     * ```
     */
    routes: Partial<Record<RoomState, string>>;

    /**
     * Path to the built static assets for the game's phone UI
     * (relative to the monorepo root), served by Fastify under `/phone`.
     * e.g. "games/cronica/phone-ui/dist"
     */
    staticDistPath: string;
}

// ── Game Module ───────────────────────────────────────────────────────────────

/**
 * The top-level interface every AGORA game module must implement.
 *
 * A game module is a self-contained description of one game that runs on the
 * AGORA platform. It carries no executable code at this layer — it is pure
 * configuration and metadata that the platform uses to orchestrate a session.
 *
 * GDD Section 1.3.
 */
export interface AgoraGameModule {
    /**
     * Unique, URL-safe identifier for this game.
     * e.g. "cronica"
     */
    id: string;

    /**
     * Display name shown in the host dashboard and UI.
     * e.g. "CRONICĂ"
     */
    name: string;

    /**
     * Minimum number of players required to start a game.
     * The platform's "Start Round" button is disabled below this threshold.
     */
    minPlayers: number;

    /**
     * Maximum number of players supported.
     * The platform rejects join attempts once this limit is reached.
     */
    maxPlayers: number;

    /**
     * Ordered list of phases that make up one complete round.
     *
     * Must include at minimum: PROMPTING, GENERATING, REVEALING, VOTING,
     * SCORING. The platform validates this list against the state machine
     * on module registration.
     */
    phases: PhaseDefinition[];

    /**
     * The prompt pack shipped with this game module.
     * Additional packs may be added in future milestones.
     */
    promptPack: PromptPack;

    /**
     * AI pipeline configuration for the GENERATING phase.
     * `null` for games that do not use an AI pipeline.
     */
    pipeline: AIPipeline | null;

    /**
     * Tauri 2 presenter window configuration for the REVEALING phase.
     * `null` for games that do not use a presenter window.
     */
    presenterUI: PresenterModule | null;

    /**
     * Svelte 5 phone UI configuration for game-specific phone screens.
     * `null` for games that rely entirely on the platform phone shell.
     */
    phoneUI: PhoneModule | null;
}