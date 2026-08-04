/**
 * M2.3 — Prompt Delivery: Server to Phone
 *
 * Verifies that each player receives exactly their own prompts via
 * round:prompts immediately after round:start transitions to PROMPTING.
 */
import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';
import { io as ioClient, type Socket } from 'socket.io-client';
import { closeDb } from '../db/index.js';

// ── Helpers ────────────────────────────────────────────────────────────────

function connect(port: number): Socket {
    return ioClient(`http://127.0.0.1:${port}`, { transports: ['websocket'] });
}

function waitFor<T>(socket: Socket, event: string, timeoutMs = 5000): Promise<T> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(
            () => reject(new Error(`Timed out waiting for '${event}'`)),
            timeoutMs,
        );
        socket.once(event, (data: unknown) => {
            clearTimeout(timer);
            resolve(data as T);
        });
    });
}

function join(
    socket: Socket,
    roomCode: string,
    nickname: string,
): Promise<{ ok: boolean; playerId?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

function startRound(
    socket: Socket,
    roomCode: string,
): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('M2.3 — Prompt Delivery', () => {
    let fastify: FastifyInstance;
    let port: number;

    beforeAll(async () => {
        fastify = await buildServer();
        await fastify.listen({ host: '127.0.0.1', port: 0 });
        const addr = fastify.server.address();
        port = typeof addr === 'object' && addr !== null ? addr.port : 3000;
    });

    afterAll(async () => {
        await fastify.close();
        closeDb();
        await new Promise<void>((resolve) => setTimeout(resolve, 200));
    });

    test('each player receives round:prompts with non-empty prompts after round:start', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Ana');
        await join(p2, code, 'Bogdan');

        // Subscribe both players before starting
        const p1PromptsPromise = waitFor<{ roundNumber: number; prompts: { promptId: string; text: string }[] }>(
            p1, 'round:prompts',
        );
        const p2PromptsPromise = waitFor<{ roundNumber: number; prompts: { promptId: string; text: string }[] }>(
            p2, 'round:prompts',
        );

        await startRound(p1, code);

        const p1Prompts = await p1PromptsPromise;
        const p2Prompts = await p2PromptsPromise;

        // Both players receive prompts
        expect(p1Prompts.roundNumber).toBe(1);
        expect(p1Prompts.prompts.length).toBeGreaterThanOrEqual(2);
        expect(p2Prompts.roundNumber).toBe(1);
        expect(p2Prompts.prompts.length).toBeGreaterThanOrEqual(2);

        // Each prompt has id and non-empty text
        for (const p of [...p1Prompts.prompts, ...p2Prompts.prompts]) {
            expect(typeof p.promptId).toBe('string');
            expect(p.promptId.length).toBeGreaterThan(0);
            expect(typeof p.text).toBe('string');
            expect(p.text.length).toBeGreaterThan(0);
        }

        p1.disconnect();
        p2.disconnect();
    });

    test('players do not receive each other\'s prompt IDs', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Cristi');
        await join(p2, code, 'Diana');

        const p1PromptsPromise = waitFor<{ prompts: { promptId: string }[] }>(p1, 'round:prompts');
        const p2PromptsPromise = waitFor<{ prompts: { promptId: string }[] }>(p2, 'round:prompts');

        await startRound(p1, code);

        const p1Prompts = await p1PromptsPromise;
        const p2Prompts = await p2PromptsPromise;

        const p1Ids = new Set(p1Prompts.prompts.map((p) => p.promptId));
        const p2Ids = new Set(p2Prompts.prompts.map((p) => p.promptId));

        // No overlap in prompt IDs (each player gets unique prompts)
        for (const id of p1Ids) {
            expect(p2Ids.has(id)).toBe(false);
        }

        p1.disconnect();
        p2.disconnect();
    });

    test('prompt text has [PLAYER] tokens resolved (contains player nickname)', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);
        const p3 = connect(port);

        await join(p1, code, 'Elena');
        await join(p2, code, 'Florin');
        await join(p3, code, 'Gabi');

        const p1PromptsPromise = waitFor<{ prompts: { text: string }[] }>(p1, 'round:prompts');
        const p2PromptsPromise = waitFor<{ prompts: { text: string }[] }>(p2, 'round:prompts');
        const p3PromptsPromise = waitFor<{ prompts: { text: string }[] }>(p3, 'round:prompts');

        await startRound(p1, code);

        const [p1Data, p2Data, p3Data] = await Promise.all([
            p1PromptsPromise,
            p2PromptsPromise,
            p3PromptsPromise,
        ]);

        // No unresolved tokens remain
        for (const { prompts } of [p1Data, p2Data, p3Data]) {
            for (const { text } of prompts) {
                expect(text).not.toContain('[PLAYER]');
                expect(text).not.toContain('[PLAYER2]');
            }
        }

        // Each player's prompts contain their own nickname
        const checkNickname = (prompts: { text: string }[], nick: string): void => {
            const hasNick = prompts.some((p) => p.text.includes(nick));
            expect(hasNick).toBe(true);
        };

        checkNickname(p1Data.prompts, 'Elena');
        checkNickname(p2Data.prompts, 'Florin');
        checkNickname(p3Data.prompts, 'Gabi');

        p1.disconnect();
        p2.disconnect();
        p3.disconnect();
    });

    test('host socket (no playerId) does not receive round:prompts', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        // Host socket: emits host:watch, no player:join
        const host = connect(port);
        const player1 = connect(port);
        const player2 = connect(port);

        // Host watches the room
        await new Promise<void>((resolve) => {
            host.emit('host:watch', { roomCode: code });
            setTimeout(resolve, 100);
        });

        await join(player1, code, 'Horia');
        await join(player2, code, 'Ioana');

        // Host must NOT receive round:prompts
        const hostReceivedPrompts = waitFor(host, 'round:prompts', 1500)
            .then(() => true)
            .catch(() => false);

        await startRound(player1, code);

        const received = await hostReceivedPrompts;
        expect(received).toBe(false);

        host.disconnect();
        player1.disconnect();
        player2.disconnect();
    });

    test('round:prompts is delivered even when round:prompting arrives first', async () => {
        // Verifies ordering: prompting broadcast fires before per-player delivery,
        // but both arrive in the same event loop cycle.
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Juliana');
        await join(p2, code, 'Kosta');

        const events: string[] = [];

        p1.on('round:prompting', () => { events.push('prompting'); });

        const promptsPromise = waitFor<unknown>(p1, 'round:prompts');
        await startRound(p1, code);
        await promptsPromise;

        // round:prompting must have fired (it was registered before startRound)
        expect(events).toContain('prompting');

        p1.disconnect();
        p2.disconnect();
    });
});