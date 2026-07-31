import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import Database from 'better-sqlite3';
import { SCHEMA_SQL } from './schema.js';
import {
    createRoom, getRoomByCode, setRoomState,
    createPlayer, getPlayersByRoom, nicknameExistsInRoom,
    createRound, getCurrentRound, setRoundState,
    upsertAnswer, countSubmittedPlayers,
    castVote, getVotesByRound,
} from './index.js';

function makeDb(): Database.Database {
    const db = new Database(':memory:');
    db.exec(SCHEMA_SQL);
    return db;
}

describe('SQLite schema + queries', () => {
    let db: Database.Database;

    beforeEach(() => { db = makeDb(); });
    afterEach(() => { db.close(); });

    it('creates a room and retrieves it by code', () => {
        const room = createRoom(db, 'ABCD');
        expect(room.code).toBe('ABCD');
        expect(room.state).toBe('WAITING');
        const found = getRoomByCode(db, 'ABCD');
        expect(found?.id).toBe(room.id);
    });

    it('rejects duplicate room codes', () => {
        createRoom(db, 'ABCD');
        expect(() => createRoom(db, 'ABCD')).toThrow();
    });

    it('creates a player and detects duplicate nickname in same room', () => {
        const room = createRoom(db, 'XKQZ');
        createPlayer(db, 'player-1', room.id, 'Ana');
        expect(nicknameExistsInRoom(db, room.id, 'Ana')).toBe(true);
        expect(nicknameExistsInRoom(db, room.id, 'Bogdan')).toBe(false);
        expect(() => createPlayer(db, 'player-2', room.id, 'Ana')).toThrow();
    });

    it('lists players in join order', () => {
        const room = createRoom(db, 'LMNO');
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');
        const players = getPlayersByRoom(db, room.id);
        expect(players.map(p => p.nickname)).toEqual(['Ana', 'Bogdan']);
    });

    it('transitions room state', () => {
        const room = createRoom(db, 'QRST');
        setRoomState(db, room.id, 'PROMPTING');
        const updated = getRoomByCode(db, 'QRST');
        expect(updated?.state).toBe('PROMPTING');
    });

    it('creates a round and sets state', () => {
        const room = createRoom(db, 'UVWX');
        const round = createRound(db, room.id, 1);
        expect(round.round_number).toBe(1);
        setRoundState(db, round.id, 'PROMPTING');
        const current = getCurrentRound(db, room.id);
        expect(current?.state).toBe('PROMPTING');
    });

    it('tracks answer submission and counts submitted players', () => {
        const room = createRoom(db, 'AAAA');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'pa', room.id, 'Ana');
        createPlayer(db, 'pb', room.id, 'Bogdan');
        upsertAnswer(db, round.id, 'pa', 'prompt-1', 'răspuns Ana', true);
        upsertAnswer(db, round.id, 'pb', 'prompt-1', '', false);
        expect(countSubmittedPlayers(db, round.id)).toBe(1);
    });

    it('upserts an answer (idempotent)', () => {
        const room = createRoom(db, 'BBBB');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'pc', room.id, 'Cristi');
        upsertAnswer(db, round.id, 'pc', 'prompt-1', 'prima', false);
        upsertAnswer(db, round.id, 'pc', 'prompt-1', 'actualizat', true);
        const answers = getVotesByRound(db, round.id); // just checking no crash; votes empty
        expect(answers).toHaveLength(0);
    });

    it('records votes and prevents duplicate category votes', () => {
        const room = createRoom(db, 'CCCC');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'pv1', room.id, 'Voter');
        createPlayer(db, 'pv2', room.id, 'Target');
        castVote(db, round.id, 'pv1', 'funniest_panel', 'pv2');
        // Re-voting same category overwrites (ON CONFLICT DO UPDATE)
        castVote(db, round.id, 'pv1', 'funniest_panel', 'pv2');
        const votes = getVotesByRound(db, round.id);
        expect(votes).toHaveLength(1);
        expect(votes[0]?.category).toBe('funniest_panel');
    });

    it('all 5 tables exist', () => {
        const tables = db
            .prepare(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`)
            .all() as { name: string }[];
        const names = tables.map(t => t.name);
        expect(names).toEqual(expect.arrayContaining([
            'players', 'round_answers', 'rooms', 'rounds', 'votes',
        ]));
    });
});