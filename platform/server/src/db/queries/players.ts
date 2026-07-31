import type { Database } from 'better-sqlite3';
import type { PlayerRow } from '../types.js';

export function createPlayer(
    db: Database,
    id: string,
    roomId: number,
    nickname: string,
): PlayerRow {
    const stmt = db.prepare<[string, number, string], PlayerRow>(
        `INSERT INTO players (id, room_id, nickname) VALUES (?, ?, ?) RETURNING *`,
    );
    return stmt.get(id, roomId, nickname) as PlayerRow;
}

export function getPlayerById(
    db: Database,
    id: string,
): PlayerRow | undefined {
    return db
        .prepare<[string], PlayerRow>(`SELECT * FROM players WHERE id = ?`)
        .get(id);
}

export function getPlayersByRoom(
    db: Database,
    roomId: number,
): PlayerRow[] {
    return db
        .prepare<[number], PlayerRow>(`SELECT * FROM players WHERE room_id = ? ORDER BY joined_at`)
        .all(roomId);
}

export function setPlayerActive(
    db: Database,
    id: string,
    active: boolean,
): void {
    db.prepare(`UPDATE players SET active = ? WHERE id = ?`).run(active ? 1 : 0, id);
}

export function nicknameExistsInRoom(
    db: Database,
    roomId: number,
    nickname: string,
): boolean {
    const row = db
        .prepare<[number, string]>(
            `SELECT 1 FROM players WHERE room_id = ? AND nickname = ?`,
        )
        .get(roomId, nickname);
    return row !== undefined;
}