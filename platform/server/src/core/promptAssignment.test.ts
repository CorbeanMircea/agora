/**
 * M2.2 — Prompt Assignment Engine Tests
 */
import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import Database from 'better-sqlite3';
import { SCHEMA_SQL } from '../db/schema.js';
import { createRoom, createRound, createPlayer } from '../db/index.js';
import { assignPrompts, resolvePlayerReferences, PROMPTS_PER_PLAYER } from './promptAssignment.js';
import type { PromptPack } from '../interfaces/gameModule.js';

// ── Fixture helpers ────────────────────────────────────────────────────────

function makeDb(): Database.Database {
    const db = new Database(':memory:');
    db.exec(SCHEMA_SQL);
    return db;
}

/**
 * Builds a minimal PromptPack with the specified number of prompts.
 * Prompts cycle through all 10 categories; every 5th gets [PLAYER2].
 */
function makePack(count: number, allSafe = true): PromptPack {
    const categories = [
        'relatie', 'munca', 'familie', 'situatie_absurda', 'scandal_de_bloc',
        'decizie_proasta', 'secret', 'aventura', 'ambitie', 'infuntare',
    ] as const;

    return {
        id: 'test_pack',
        name: 'Test Pack',
        version: '1.0.0',
        prompts: Array.from({ length: count }, (_, i) => ({
            id: `p${String(i).padStart(3, '0')}`,
            text: i % 5 === 0
                ? `Prompt ${i} about [PLAYER] and [PLAYER2].`
                : `Prompt ${i} about [PLAYER].`,
            category: categories[i % categories.length]!,
            safeMode: allSafe ? true : i % 7 !== 0, // every 7th is unsafe
            minPlayers: i % 5 === 0 ? 3 : 2,
        })),
    };
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('M2.2 — Prompt Assignment Engine', () => {
    let db: Database.Database;

    beforeEach(() => { db = makeDb(); });
    afterEach(() => { db.close(); });

    it('assigns the correct number of prompts per player (2 players)', () => {
        const pack = makePack(30);
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
            expect(a.prompts.length).toBeGreaterThanOrEqual(PROMPTS_PER_PLAYER);
        }
    });

    it('no two players receive the same prompt ID in one round', () => {
        const pack = makePack(40);
        const room = createRoom(db, 'BBBB');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3', 'p4'].map((id, i) => {
            createPlayer(db, id, room.id, `Player${i + 1}`);
            return { id, nickname: `Player${i + 1}` };
        });

        const result = assignPrompts(db, pack, round.id, players, false);

        const allIds = result.assignments.flatMap((a) => a.prompts.map((p) => p.id));
        const uniqueIds = new Set(allIds);
        expect(uniqueIds.size).toBe(allIds.length); // all unique
    });

    it('resolves [PLAYER] with player nickname', () => {
        const prompt = {
            id: 'x001',
            text: 'Ce a facut [PLAYER] ieri?',
            category: 'munca' as const,
            safeMode: true,
            minPlayers: 2,
        };
        const resolved = resolvePlayerReferences(
            prompt,
            { id: 'p1', nickname: 'Ana' },
            [{ id: 'p1', nickname: 'Ana' }, { id: 'p2', nickname: 'Bogdan' }],
        );
        expect(resolved.text).toContain('Ana');
        expect(resolved.text).not.toContain('[PLAYER]');
    });

    it('resolves [PLAYER2] with a different player nickname', () => {
        const prompt = {
            id: 'x002',
            text: '[PLAYER] si [PLAYER2] s-au certat.',
            category: 'relatie' as const,
            safeMode: true,
            minPlayers: 3,
        };
        const resolved = resolvePlayerReferences(
            prompt,
            { id: 'p1', nickname: 'Ana' },
            [
                { id: 'p1', nickname: 'Ana' },
                { id: 'p2', nickname: 'Bogdan' },
                { id: 'p3', nickname: 'Cristi' },
            ],
        );
        expect(resolved.text).not.toContain('[PLAYER2]');
        // [PLAYER2] should be replaced with Bogdan or Cristi, not Ana
        const hasOther = resolved.text.includes('Bogdan') || resolved.text.includes('Cristi');
        expect(hasOther).toBe(true);
    });

    it('safeMode filters out unsafe prompts', () => {
        const pack = makePack(40, false); // some unsafe prompts
        const room = createRoom(db, 'CCCC');
        const round = createRound(db, room.id, 1);
        const players = [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ];
        players.forEach(({ id, nickname }) => createPlayer(db, id, room.id, nickname));

        const result = assignPrompts(db, pack, round.id, players, true);

        for (const a of result.assignments) {
            for (const p of a.prompts) {
                // safeMode prompts in our fixture have safeMode: true
                expect(p.safeMode).toBe(true);
            }
        }
    });

    it('assignments are persisted to round_answers in SQLite', () => {
        const pack = makePack(30);
        const room = createRoom(db, 'DDDD');
        const round = createRound(db, room.id, 1);
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');

        const result = assignPrompts(db, pack, round.id, [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ], false);

        const rows = db
            .prepare<[number], { round_id: number; player_id: string; prompt_id: string; submitted: number }>(
                'SELECT * FROM round_answers WHERE round_id = ?',
            )
            .all(round.id);

        const totalPrompts = result.assignments.reduce((s, a) => s + a.prompts.length, 0);
        expect(rows).toHaveLength(totalPrompts);
        rows.forEach((r) => expect(r.submitted).toBe(0));
    });

    it('with 3+ players, at least one prompt references a second player', () => {
        const pack = makePack(60);
        const room = createRoom(db, 'EEEE');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3'].map((id, i) => {
            createPlayer(db, id, room.id, `Player${i + 1}`);
            return { id, nickname: `Player${i + 1}` };
        });

        const result = assignPrompts(db, pack, round.id, players, false);

        // At least one resolved prompt text should contain a second player's nickname
        const allTexts = result.assignments.flatMap((a) => a.prompts.map((p) => p.text));
        const otherNicknames = players.map((p) => p.nickname);
        const hasCrossRef = allTexts.some((text) =>
            otherNicknames.some((nick) =>
                // text contains a nickname that is NOT [PLAYER] (already resolved)
                text.includes(nick) && !text.includes('[PLAYER2]'),
            ),
        );
        // All [PLAYER] and [PLAYER2] tokens should be resolved
        const noUnresolvedTokens = allTexts.every(
            (t) => !t.includes('[PLAYER]') && !t.includes('[PLAYER2]'),
        );
        expect(noUnresolvedTokens).toBe(true);
        expect(hasCrossRef).toBe(true);
    });

    it('throws when pool is too small for player count', () => {
        const pack = makePack(2); // only 2 prompts for 4 players needing 8
        const room = createRoom(db, 'FFFF');
        const round = createRound(db, room.id, 1);
        const players = ['p1', 'p2', 'p3', 'p4'].map((id, i) => {
            createPlayer(db, id, room.id, `P${i}`);
            return { id, nickname: `P${i}` };
        });

        expect(() =>
            assignPrompts(db, pack, round.id, players, false),
        ).toThrow();
    });

    it('de-prioritises prompts used in previous rounds', () => {
        const pack = makePack(40);
        const room = createRoom(db, 'GGGG');
        const round1 = createRound(db, room.id, 1);
        createPlayer(db, 'p1', room.id, 'Ana');
        createPlayer(db, 'p2', room.id, 'Bogdan');

        const players = [
            { id: 'p1', nickname: 'Ana' },
            { id: 'p2', nickname: 'Bogdan' },
        ];

        const r1 = assignPrompts(db, pack, round1.id, players, false);
        const usedInR1 = new Set(r1.usedPromptIds);

        const round2 = createRound(db, room.id, 2);
        const r2 = assignPrompts(db, pack, round2.id, players, false, usedInR1);

        // Prefer fresh prompts in round 2
        const r2Ids = new Set(r2.usedPromptIds);
        const repeated = [...r2Ids].filter((id) => usedInR1.has(id));
        // With 40 prompts and only 4 used in r1, we should be able to pick all fresh
        expect(repeated.length).toBe(0);
    });
});