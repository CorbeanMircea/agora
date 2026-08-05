/**
 * M2.2 — Prompt Assignment Engine Tests (updated for Ingredient System)
 */
import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import Database from 'better-sqlite3';
import { SCHEMA_SQL } from '../db/schema.js';
import { createRoom, createRound, createPlayer } from '../db/index.js';
import { assignPrompts, resolvePlayerReferences, PROMPTS_PER_PLAYER } from './promptAssignment.js';
import type { PromptPack } from '../interfaces/gameModule.js';

const INGREDIENT_CATEGORIES = [
    'CONCRET', 'ABSTRACT', 'ACTIUNE', 'LOC', 'NUMAR', 'PROPRIU', 'ATRIBUT',
] as const;

function makeDb(): Database.Database {
    const db = new Database(':memory:');
    db.exec(SCHEMA_SQL);
    return db;
}

function makePack(countPerCategory = 5): PromptPack {
    const prompts = [];
    let idx = 0;
    for (const cat of INGREDIENT_CATEGORIES) {
        for (let i = 0; i < countPerCategory; i++) {
            prompts.push({
                id: `q${String(idx).padStart(3, '0')}`,
                text: `Spune un ingredient din categoria ${cat} numarul ${i}.`,
                category: cat,
                safeMode: true,
                minPlayers: 2,
            });
            idx++;
        }
    }
    return { id: 'test_pack', name: 'Test', version: '1.0.0', prompts };
}

describe('M2.2 — Prompt Assignment Engine (Ingredient System)', () => {
    let db: Database.Database;

    beforeEach(() => { db = makeDb(); });
    afterEach(() => { db.close(); });

    it('assigns PROMPTS_PER_PLAYER questions per player', () => {
        const pack = makePack(5);
        const room = createRoom(db, 'AAAA');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');

        const result = assignPrompts(db, pack, round.id, [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ], false);

        expect(result.assignments).toHaveLength(2);
        for (const a of result.assignments) {
            expect(a.prompts).toHaveLength(PROMPTS_PER_PLAYER);
        }
    });

    it('no two players receive the same question', () => {
        const pack = makePack(5);
        const room = createRoom(db, 'BBBB');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3', 'p4'].map((id, i) => {
            createPlayer(db, id, room.id, `Player${i + 1}`);
            return { id, nickname: `Player${i + 1}` };
        });

        const result = assignPrompts(db, pack, round.id, players, false);

        const allIds = result.assignments.flatMap((a) => a.prompts.map((p) => p.id));
        expect(new Set(allIds).size).toBe(allIds.length);
    });

    it('round covers multiple semantic categories', () => {
        const pack = makePack(5);
        const room = createRoom(db, 'CCCC');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3', 'p4'].map((id, i) => {
            createPlayer(db, id, room.id, `P${i}`);
            return { id, nickname: `P${i}` };
        });

        const result = assignPrompts(db, pack, round.id, players, false);

        const categories = new Set(
            result.assignments.flatMap((a) => a.prompts.map((p) => p.category)),
        );
        // 4 players × 2 prompts = 8 slots across 7 categories — should hit most
        expect(categories.size).toBeGreaterThanOrEqual(4);
    });

    it('assignments are persisted to round_answers', () => {
        const pack = makePack(5);
        const room = createRoom(db, 'DDDD');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');

        const result = assignPrompts(db, pack, round.id, [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ], false);

        const rows = db
            .prepare<[number], { submitted: number }>(
                'SELECT * FROM round_answers WHERE round_id = ?',
            )
            .all(round.id);

        const total = result.assignments.reduce((s, a) => s + a.prompts.length, 0);
        expect(rows).toHaveLength(total);
        rows.forEach((r) => expect(r.submitted).toBe(0));
    });

    it('de-prioritises questions used in previous rounds', () => {
        const pack = makePack(5);
        const room = createRoom(db, 'EEEE');
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');
        const players = [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ];

        const round1 = createRound(db, room.id, 1);
        const r1 = assignPrompts(db, pack, round1.id, players, false);
        const usedInR1 = new Set(r1.usedPromptIds);

        const round2 = createRound(db, room.id, 2);
        const r2 = assignPrompts(db, pack, round2.id, players, false, usedInR1);

        const repeated = r2.usedPromptIds.filter((id) => usedInR1.has(id));
        // With 35 questions (5 per category × 7) and only 4 used in r1, none should repeat
        expect(repeated).toHaveLength(0);
    });

    it('resolvePlayerReferences returns prompt unchanged for ingredient questions', () => {
        const prompt = {
            id: 'q001',
            text: 'Spune un animal neobișnuit.',
            category: 'CONCRET',
            safeMode: true,
            minPlayers: 2,
        };
        const resolved = resolvePlayerReferences(
            prompt,
            { id: 'p1', nickname: 'Ana' },
            [{ id: 'p1', nickname: 'Ana' }, { id: 'p2', nickname: 'Bogdan' }],
        );
        expect(resolved.text).toBe(prompt.text);
        expect(resolved.id).toBe(prompt.id);
    });

    it('throws when pool is too small', () => {
        const tinyPack: PromptPack = {
            id: 'tiny', name: 'Tiny', version: '1.0.0',
            prompts: [
                { id: 'q1', text: 'Spune un animal neobișnuit.', category: 'CONCRET', safeMode: true, minPlayers: 2 },
                { id: 'q2', text: 'Spune o emoție.', category: 'ABSTRACT', safeMode: true, minPlayers: 2 },
            ],
        };
        const room = createRoom(db, 'FFFF');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3', 'p4'].map((id, i) => {
            createPlayer(db, id, room.id, `P${i}`);
            return { id, nickname: `P${i}` };
        });

        expect(() => assignPrompts(db, tinyPack, round.id, players, false)).toThrow();
    });
});