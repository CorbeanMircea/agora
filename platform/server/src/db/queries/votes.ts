import type { Database } from 'better-sqlite3';
import type { VoteRow, VoteCategory } from '../types.js';

export function castVote(
    db: Database,
    roundId: number,
    voterId: string,
    category: VoteCategory,
    targetId: string,
): VoteRow {
    const stmt = db.prepare<[number, string, string, string], VoteRow>(`
    INSERT INTO votes (round_id, voter_id, category, target_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (round_id, voter_id, category)
    DO UPDATE SET target_id = excluded.target_id
    RETURNING *
  `);
    return stmt.get(roundId, voterId, category, targetId) as VoteRow;
}

export function getVotesByRound(
    db: Database,
    roundId: number,
): VoteRow[] {
    return db
        .prepare<[number], VoteRow>(`SELECT * FROM votes WHERE round_id = ?`)
        .all(roundId);
}

export function countVotesByRound(
    db: Database,
    roundId: number,
): number {
    const row = db
        .prepare<[number], { n: number }>(
            `SELECT COUNT(*) AS n FROM votes WHERE round_id = ?`,
        )
        .get(roundId);
    return row?.n ?? 0;
}