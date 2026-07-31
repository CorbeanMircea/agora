/**
 * Room code generation.
 * 4 uppercase consonants — avoids vowels (accidental words) and
 * visually ambiguous characters (I ↔ 1, O ↔ 0).
 */
import type { Database } from 'better-sqlite3';
import { createRoom, getRoomByCode } from '../db/index.js';
import type { RoomRow } from '../db/index.js';

const CONSONANTS = 'BCDFGHJKLMNPQRSTVWXYZ';
const CODE_LENGTH = 4;
const MAX_ATTEMPTS = 10;

function generateCode(): string {
    let code = '';
    for (let i = 0; i < CODE_LENGTH; i++) {
        code += CONSONANTS[Math.floor(Math.random() * CONSONANTS.length)];
    }
    return code;
}

/**
 * Generates a unique room code and persists the room.
 * Retries up to MAX_ATTEMPTS times to handle collisions.
 */
export function createUniqueRoom(db: Database): RoomRow {
    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        const code = generateCode();

        if (getRoomByCode(db, code) !== undefined) {
            continue; // collision — try again
        }

        return createRoom(db, code);
    }

    throw new Error(
        `Unable to generate a unique room code after ${MAX_ATTEMPTS} attempts`,
    );
}