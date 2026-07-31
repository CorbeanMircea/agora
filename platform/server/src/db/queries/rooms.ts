import type { Database } from 'better-sqlite3';
import type { RoomRow, RoomState } from '../types.js';

export function createRoom(
    db: Database,
    code: string,
): RoomRow {
    const stmt = db.prepare<[string], RoomRow>(
        `INSERT INTO rooms (code) VALUES (?) RETURNING *`,
    );
    return stmt.get(code) as RoomRow;
}

export function getRoomByCode(
    db: Database,
    code: string,
): RoomRow | undefined {
    return db
        .prepare<[string], RoomRow>(`SELECT * FROM rooms WHERE code = ?`)
        .get(code);
}

export function getRoomById(
    db: Database,
    id: number,
): RoomRow | undefined {
    return db
        .prepare<[number], RoomRow>(`SELECT * FROM rooms WHERE id = ?`)
        .get(id);
}

export function setRoomState(
    db: Database,
    id: number,
    state: RoomState,
): void {
    db.prepare(`UPDATE rooms SET state = ? WHERE id = ?`).run(state, id);
}

export function incrementRoundCount(
    db: Database,
    id: number,
): void {
    db.prepare(`UPDATE rooms SET round_count = round_count + 1 WHERE id = ?`).run(id);
}