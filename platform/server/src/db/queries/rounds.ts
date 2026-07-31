import type { Database } from 'better-sqlite3';
import type { RoundRow, RoomState } from '../types.js';

export function createRound(
    db: Database,
    roomId: number,
    roundNumber: number,
): RoundRow {
    const stmt = db.prepare<[number, number], RoundRow>(
        `INSERT INTO rounds (room_id, round_number) VALUES (?, ?) RETURNING *`,
    );
    return stmt.get(roomId, roundNumber) as RoundRow;
}

export function getRoundById(
    db: Database,
    id: number,
): RoundRow | undefined {
    return db
        .prepare<[number], RoundRow>(`SELECT * FROM rounds WHERE id = ?`)
        .get(id);
}

export function getCurrentRound(
    db: Database,
    roomId: number,
): RoundRow | undefined {
    return db
        .prepare<[number], RoundRow>(
            `SELECT * FROM rounds WHERE room_id = ? ORDER BY round_number DESC LIMIT 1`,
        )
        .get(roomId);
}

export function setRoundState(
    db: Database,
    id: number,
    state: RoomState,
): void {
    db.prepare(`UPDATE rounds SET state = ? WHERE id = ?`).run(state, id);
}

export function setRoundDeadline(
    db: Database,
    id: number,
    phase: 'prompting' | 'voting',
    deadlineEpochSec: number,
): void {
    const col = phase === 'prompting' ? 'prompting_deadline' : 'voting_deadline';
    db.prepare(`UPDATE rounds SET ${col} = ? WHERE id = ?`).run(deadlineEpochSec, id);
}

export function startRound(
    db: Database,
    id: number,
): void {
    db.prepare(
        `UPDATE rounds SET started_at = unixepoch(), state = 'PROMPTING' WHERE id = ?`,
    ).run(id);
}

export function endRound(
    db: Database,
    id: number,
): void {
    db.prepare(
        `UPDATE rounds SET ended_at = unixepoch() WHERE id = ?`,
    ).run(id);
}