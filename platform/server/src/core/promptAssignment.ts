/**
 * Prompt Assignment Engine — updated for Ingredient System
 *
 * Assigns ingredient questions to players ensuring semantic diversity
 * across the round. Each round should cover as many different semantic
 * categories as possible given the player count.
 *
 * Rules:
 * - Each player receives PROMPTS_PER_PLAYER questions (default 2).
 * - No two players receive the same question in the same round.
 * - Across the round, no semantic category appears more than once
 *   unless player count × PROMPTS_PER_PLAYER exceeds category count.
 * - Questions used in previous rounds are de-prioritised.
 * - Safe Mode has no effect on ingredient questions (all are safeMode: true)
 *   but the filter is kept for forward compatibility.
 */
import type { Database } from 'better-sqlite3';
import type { PromptPack, PromptEntry } from '../interfaces/gameModule.js';
import { upsertAnswer } from '../db/index.js';

export const PROMPTS_PER_PLAYER = 2;

export interface PlayerAssignment {
    playerId: string;
    nickname: string;
    prompts: PromptEntry[];
}

export interface AssignmentResult {
    assignments: PlayerAssignment[];
    usedPromptIds: string[];
}

/**
 * Assigns ingredient questions to players with semantic category diversity.
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

    // Filter pool
    let pool = safeMode
        ? pack.prompts.filter((p) => p.safeMode)
        : pack.prompts.slice();

    pool = pool.filter((p) => p.minPlayers <= players.length);

    const totalNeeded = players.length * PROMPTS_PER_PLAYER;

    if (pool.length < totalNeeded) {
        throw new Error(
            `Prompt pool too small: need ${totalNeeded}, have ${pool.length}`,
        );
    }

    // Split into fresh and stale, shuffle each half
    const fresh = shuffle(pool.filter((p) => !usedInSession.has(p.id)));
    const stale = shuffle(pool.filter((p) => usedInSession.has(p.id)));
    const orderedPool = [...fresh, ...stale];

    // Build a category → questions map for diversity-aware selection
    const byCategory = new Map<string, PromptEntry[]>();
    for (const p of orderedPool) {
        if (!byCategory.has(p.category)) byCategory.set(p.category, []);
        byCategory.get(p.category)!.push(p);
    }

    // Determine the round-level category sequence.
    // We want totalNeeded slots filled with maximum category diversity.
    const categories = [...byCategory.keys()];
    const roundCategories = buildDiverseCategorySequence(
        categories,
        totalNeeded,
    );

    // Assign slots to players: player 0 gets slots 0,1 — player 1 gets slots 2,3 etc.
    const globallyAssigned = new Set<string>();
    const assignments: PlayerAssignment[] = [];

    for (let pi = 0; pi < players.length; pi++) {
        const player = players[pi]!;
        const slotStart = pi * PROMPTS_PER_PLAYER;
        const assigned: PromptEntry[] = [];

        for (let slot = slotStart; slot < slotStart + PROMPTS_PER_PLAYER; slot++) {
            const category = roundCategories[slot];
            if (category === undefined) break;

            const candidates = (byCategory.get(category) ?? [])
                .filter((p) => !globallyAssigned.has(p.id));

            if (candidates.length === 0) {
                // Fallback: pick any unassigned question
                const fallback = orderedPool.find((p) => !globallyAssigned.has(p.id));
                if (fallback !== undefined) {
                    assigned.push(fallback);
                    globallyAssigned.add(fallback.id);
                }
                continue;
            }

            const picked = candidates[0]!;
            assigned.push(picked);
            globallyAssigned.add(picked.id);
        }

        if (assigned.length < PROMPTS_PER_PLAYER) {
            throw new Error(
                `Could not assign ${PROMPTS_PER_PLAYER} questions to '${player.nickname}'. Pool exhausted.`,
            );
        }

        // Ingredient questions use the player's nickname as the [PLAYER] token
        // (kept for compatibility — ingredient texts don't use [PLAYER] but the
        // field is part of the PromptEntry type)
        assignments.push({
            playerId: player.id,
            nickname: player.nickname,
            prompts: assigned,
        });
    }

    // Persist to SQLite
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

/**
 * Kept for compatibility with tests and future LLM prompt building.
 * Ingredient questions don't use [PLAYER] tokens, so this is a no-op
 * on the text, but the function signature is preserved.
 */
export function resolvePlayerReferences(
    prompt: PromptEntry,
    self: { id: string; nickname: string },
    allPlayers: { id: string; nickname: string }[],
): PromptEntry {
    // Ingredient questions are player-agnostic — return unchanged
    return prompt;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Builds a sequence of `count` categories with maximum diversity.
 * Cycles through all available categories before repeating any.
 *
 * Example: 3 categories [A,B,C], count=7 → [A,B,C,A,B,C,A]
 */
function buildDiverseCategorySequence(
    categories: string[],
    count: number,
): string[] {
    const shuffled = shuffle([...categories]);
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
        result.push(shuffled[i % shuffled.length]!);
    }
    return result;
}

/**
 * Fisher-Yates shuffle — returns a new array.
 */
function shuffle<T>(arr: T[]): T[] {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = a[i]!;
        a[i] = a[j]!;
        a[j] = tmp;
    }
    return a;
}