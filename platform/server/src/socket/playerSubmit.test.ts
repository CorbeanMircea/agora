/**
 * M2.5 — Answer Submission (Server Side) Tests
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
): Promise<{ ok: boolean; playerId?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

function startRound(socket: Socket, roomCode: string): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
}

function getPrompts(socket: Socket): Promise<{ roundNumber: number; prompts: { promptId: string; text: string }[] }> {
    return waitFor(socket, 'round:prompts');
}

function submit(
    socket: Socket,
    roomCode: string,
    answers: { promptId: string; text: string }[],
): Promise<{ ok: boolean; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:submit', { roomCode, answers }, resolve);
    });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('M2.5 — Answer Submission', () => {
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

    test('valid submission returns ok:true', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Ana');
        await join(p2, code, 'Bogdan');

        const p1PromptsPromise = getPrompts(p1);
        await startRound(p1, code);
        const { prompts } = await p1PromptsPromise;

        const answers = prompts.map((p) => ({ promptId: p.promptId, text: 'un răspuns' }));
        const ack = await submit(p1, code, answers);

        expect(ack.ok).toBe(true);
        expect(ack.error).toBeUndefined();

        p1.disconnect();
        p2.disconnect();
    });

    test('submission with wrong promptId returns ok:false', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Cristi');
        await join(p2, code, 'Diana');

        const promptsPromise = getPrompts(p1);
        await startRound(p1, code);
        await promptsPromise;

        // Submit with a fake promptId
        const ack = await submit(p1, code, [
            { promptId: 'fake_id_000', text: 'răspuns' },
            { promptId: 'fake_id_001', text: 'răspuns2' },
        ]);

        expect(ack.ok).toBe(false);

        p1.disconnect();
        p2.disconnect();
    });

    test('empty answer text returns ok:false', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Elena');
        await join(p2, code, 'Florin');

        const promptsPromise = getPrompts(p1);
        await startRound(p1, code);
        const { prompts } = await promptsPromise;

        const answers = prompts.map((p) => ({ promptId: p.promptId, text: '   ' }));
        const ack = await submit(p1, code, answers);

        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/non-empty/i);

        p1.disconnect();
        p2.disconnect();
    });

    test('submission outside PROMPTING phase returns ok:false', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Gabi');
        await join(p2, code, 'Horia');

        const promptsPromise = getPrompts(p1);
        await startRound(p1, code);
        const { prompts } = await promptsPromise;

        // Manually advance to GENERATING first
        await new Promise<void>((resolve) => {
            p1.emit('round:advance', { roomCode: code, toState: 'GENERATING' }, () => resolve());
        });

        const answers = prompts.map((p) => ({ promptId: p.promptId, text: 'răspuns' }));
        const ack = await submit(p1, code, answers);

        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/closed|PROMPTING/i);

        p1.disconnect();
        p2.disconnect();
    });

    test('round:player_submitted is broadcast (not to submitter)', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Ioana');
        await join(p2, code, 'Juliana');

        const p1PromptsPromise = getPrompts(p1);
        await startRound(p1, code);
        const { prompts } = await p1PromptsPromise;

        // p2 listens for the broadcast
        const broadcastPromise = waitFor<{
            playerId: string;
            nickname: string;
            submittedCount: number;
            totalCount: number;
        }>(p2, 'round:player_submitted');

        const answers = prompts.map((p) => ({ promptId: p.promptId, text: 'un răspuns bun' }));
        await submit(p1, code, answers);

        const evt = await broadcastPromise;
        expect(evt.nickname).toBe('Ioana');
        expect(evt.submittedCount).toBe(1);
        expect(evt.totalCount).toBe(2);

        p1.disconnect();
        p2.disconnect();
    });

    test('all players submitting triggers auto-advance to GENERATING', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Kosta');
        await join(p2, code, 'Laura');

        const p1PromptsPromise = getPrompts(p1);
        const p2PromptsPromise = getPrompts(p2);
        await startRound(p1, code);

        const p1Prompts = await p1PromptsPromise;
        const p2Prompts = await p2PromptsPromise;

        // Listen for GENERATING event on p1
        const generatingPromise = waitFor<{ state: string; triggeredBy: string }>(
            p1,
            'round:generating',
        );

        // Both players submit
        const a1 = p1Prompts.prompts.map((p) => ({ promptId: p.promptId, text: 'răspuns p1' }));
        const a2 = p2Prompts.prompts.map((p) => ({ promptId: p.promptId, text: 'răspuns p2' }));

        await submit(p1, code, a1);
        await submit(p2, code, a2);

        const evt = await generatingPromise;
        expect(evt.state).toBe('GENERATING');
        expect(evt.triggeredBy).toBe('all_submitted');

        p1.disconnect();
        p2.disconnect();
    });

    test('unauthenticated socket returns ok:false', async () => {
        const client = connect(port);
        // Never join — no playerId on socket
        const ack = await submit(client, 'ZZZZ', [{ promptId: 'q1', text: 'test' }]);
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/not joined/i);
        client.disconnect();
    });

    test('invalid payload shape returns ok:false', async () => {
        const client = connect(port);
        const ack = await new Promise<{ ok: boolean; error?: string }>((resolve) => {
            client.emit('player:submit', { bad: 'data' }, resolve);
        });
        expect(ack.ok).toBe(false);
        client.disconnect();
    });
});