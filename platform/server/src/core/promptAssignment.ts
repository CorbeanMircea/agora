/**
 * Prompt Assignment Engine — M2.2
 *
 * Selects and assigns prompts to players at the start of each PROMPTING phase.
 *
 * Rules (GDD Section 4.2):
 *  - Each player receives PROMPTS_PER_PLAYER (2–3) prompts.
 *  - No two players receive the exact same prompt in the same round.
 *  - At least one prompt in the round references [PLAYER2] (cross-player prompt)
 *    when the room has ≥ 3 players.
 *  - Prompt categories are varied (no category used more than once per player).
 *  - Safe Mode filters prompts where safeMode === false.
 *  - Prompts used in previous rounds of the same session are de-prioritised
 *    (exhausted packs cycle — still usable, just lower weight).
 *  - Assignments are persisted to round_answers as empty rows (submitted = 0).
 */
import type { Database } from 'better-sqlite3';
import type { PromptPack, PromptEntry } from '../interfaces/gameModule.js';
import { upsertAnswer } from '../db/index.js';

// ── Constants ───────────────────────────────────────────────────────────────

export const PROMPTS_PER_PLAYER = 2; // base; bumped to 3 when pool is large enough

// ── Types ───────────────────────────────────────────────────────────────────

export interface PlayerAssignment {
    playerId: string;
    nickname: string;
    prompts: PromptEntry[];
}

export interface AssignmentResult {
    assignments: PlayerAssignment[];
    /** IDs of all prompts used this round (for cross-round dedup in future). */
    usedPromptIds: string[];
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Assigns prompts to players and persists them as empty round_answers rows.
 *
 * @param db             - SQLite database instance
 * @param pack           - Prompt pack to draw from
 * @param roundId        - ID of the current round
 * @param players        - Array of { id, nickname } for all active players
 * @param safeMode       - Whether to filter adult prompts
 * @param usedInSession  - Set of promptIds used in previous rounds
 *                         (de-prioritised but not excluded when pool is small)
 */
export function assignPrompts(
    db: Database,
    pack: PromptPack,
    roundId: number,
    players: { id: string; nickname: string }[],
    safeMode: boolean,
    usedInSession: Set<string> = new Set(),
): AssignmentResult {
    if (players.length < 2) {
        throw new Error('Prompt assignment requires at least 2 players');
    }

    // ── Filter pool ──────────────────────────────────────────────────────────

    let pool = safeMode
        ? pack.prompts.filter((p) => p.safeMode)
        : pack.prompts.slice();

    // Only include prompts whose minPlayers requirement is satisfied
    pool = pool.filter((p) => p.minPlayers <= players.length);

    const promptsPerPlayer = pool.length >= players.length * 3 ? 3 : PROMPTS_PER_PLAYER;
    const totalNeeded = players.length * promptsPerPlayer;

    if (pool.length < totalNeeded) {
        throw new Error(
            `Prompt pool too small: need at least ${totalNeeded} prompts, ` +
            `have ${pool.length} (safeMode=${safeMode}, playerCount=${players.length})`,
        );
    }

    // ── Sort pool: unused-this-session first, then previously-used ───────────

    const sortedPool: PromptEntry[] = [
        ...pool.filter((p) => !usedInSession.has(p.id)),
        ...pool.filter((p) => usedInSession.has(p.id)),
    ];

    // Shuffle within each half to get random ordering among equal-priority prompts
    shuffleInPlace(sortedPool.slice(0, sortedPool.findIndex((p) => usedInSession.has(p.id)) === -1
        ? sortedPool.length
        : sortedPool.findIndex((p) => usedInSession.has(p.id))));

    // Re-build with proper in-place shuffle of each half
    const freshCount = sortedPool.filter((p) => !usedInSession.has(p.id)).length;
    const freshHalf = sortedPool.slice(0, freshCount);
    const staleHalf = sortedPool.slice(freshCount);
    shuffleInPlace(freshHalf);
    shuffleInPlace(staleHalf);
    const orderedPool = [...freshHalf, ...staleHalf];

    // ── Ensure at least one cross-player prompt is in the pool ───────────────

    // Move a cross-player prompt to near the front so it gets picked first
    if (players.length >= 3) {
        const crossIdx = orderedPool.findIndex((p) => p.text.includes('[PLAYER2]'));
        if (crossIdx > 0) {
            // Swap it into position 0 so it's picked in the first player's batch
            const [cross] = orderedPool.splice(crossIdx, 1);
            orderedPool.unshift(cross!);
        }
    }

    // ── Assign prompts to players ─────────────────────────────────────────────
    //
    // Global set of already-assigned prompt IDs — guarantees uniqueness across
    // all players in this round.

    const globallyAssigned = new Set<string>();
    const assignments: PlayerAssignment[] = [];

    for (const player of players) {
        const assigned: PromptEntry[] = [];
        const usedCategories = new Set<string>();

        // Pass 1: category-unique prompts not yet assigned to anyone
        for (const prompt of orderedPool) {
            if (assigned.length >= promptsPerPlayer) break;
            if (globallyAssigned.has(prompt.id)) continue;
            if (usedCategories.has(prompt.category)) continue;

            assigned.push(prompt);
            usedCategories.add(prompt.category);
            globallyAssigned.add(prompt.id);
        }

        // Pass 2 (relaxed): if still short, allow category repeats
        if (assigned.length < promptsPerPlayer) {
            for (const prompt of orderedPool) {
                if (assigned.length >= promptsPerPlayer) break;
                if (globallyAssigned.has(prompt.id)) continue;

                assigned.push(prompt);
                globallyAssigned.add(prompt.id);
            }
        }

        if (assigned.length < promptsPerPlayer) {
            throw new Error(
                `Could not assign ${promptsPerPlayer} unique prompts to player '${player.nickname}'. ` +
                `Pool exhausted after assigning ${globallyAssigned.size} prompts.`,
            );
        }

        // Substitute [PLAYER] / [PLAYER2] tokens with real nicknames
        const processedPrompts = assigned.map((p) =>
            resolvePlayerReferences(p, player, players),
        );

        assignments.push({
            playerId: player.id,
            nickname: player.nickname,
            prompts: processedPrompts,
        });
    }

    // ── Persist to SQLite ─────────────────────────────────────────────────────

    for (const assignment of assignments) {
        for (const prompt of assignment.prompts) {
            upsertAnswer(db, roundId, assignment.playerId, prompt.id, '', false);
        }
    }

    return {
        assignments,
        usedPromptIds: [...globallyAssigned],
    };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Replaces [PLAYER] with the player's own nickname and [PLAYER2] with a
 * randomly chosen OTHER player's nickname.
 *
 * Returns a new PromptEntry with the resolved text (id and metadata unchanged).
 */
export function resolvePlayerReferences(
    prompt: PromptEntry,
    self: { id: string; nickname: string },
    allPlayers: { id: string; nickname: string }[],
): PromptEntry {
    const others = allPlayers.filter((p) => p.id !== self.id);
    const other = others[Math.floor(Math.random() * others.length)];

    let text = prompt.text.replace(/\[PLAYER\]/g, self.nickname);
    if (other !== undefined) {
        text = text.replace(/\[PLAYER2\]/g, other.nickname);
    }

    return { ...prompt, text };
}

/**
 * Fisher-Yates in-place shuffle.
 */
function shuffleInPlace<T>(arr: T[]): void {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = arr[i]!;
        arr[i] = arr[j]!;
        arr[j] = tmp;
    }
}