import type { Database } from 'better-sqlite3';
import type { RoundAnswerRow } from '../types.js';

export function upsertAnswer(
    db: Database,
    roundId: number,
    playerId: string,
    promptId: string,
    answer: string,
    submitted: boolean,
): RoundAnswerRow {
    const stmt = db.prepare<[number, string, string, string, number], RoundAnswerRow>(`
    INSERT INTO round_answers (round_id, player_id, prompt_id, answer, submitted)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (round_id, player_id, prompt_id)
    DO UPDATE SET answer = excluded.answer, submitted = excluded.submitted
    RETURNING *
  `);
    return stmt.get(roundId, playerId, promptId, answer, submitted ? 1 : 0) as RoundAnswerRow;
}

export function getAnswersByRound(
    db: Database,
    roundId: number,
): RoundAnswerRow[] {
    return db
        .prepare<[number], RoundAnswerRow>(
            `SELECT * FROM round_answers WHERE round_id = ?`,
        )
        .all(roundId);
}

export function getAnswersByPlayer(
    db: Database,
    roundId: number,
    playerId: string,
): RoundAnswerRow[] {
    return db
        .prepare<[number, string], RoundAnswerRow>(
            `SELECT * FROM round_answers WHERE round_id = ? AND player_id = ?`,
        )
        .all(roundId, playerId);
}

export function countSubmittedPlayers(
    db: Database,
    roundId: number,
): number {
    const row = db
        .prepare<[number], { n: number }>(
            `SELECT COUNT(DISTINCT player_id) AS n FROM round_answers WHERE round_id = ? AND submitted = 1`,
        )
        .get(roundId);
    return row?.n ?? 0;
}

/**
 * Returns all prompt assignments for a player in a round.
 * These are round_answer rows seeded by the prompt assignment engine
 * (submitted = 0, answer = '').
 */
export function getPromptAssignmentsByPlayer(
    db: Database,
    roundId: number,
    playerId: string,
): RoundAnswerRow[] {
    return db
        .prepare<[number, string], RoundAnswerRow>(
            `SELECT * FROM round_answers WHERE round_id = ? AND player_id = ?`,
        )
        .all(roundId, playerId);
}