/**
 * M2.6 — Partial Submission Handling
 *
 * Verifies that when the PROMPTING timer expires, the server:
 * 1. Advances state to GENERATING regardless of submission count.
 * 2. Emits round:partial_submissions with correct per-player status.
 * 3. Players who did not submit retain empty answer rows in SQLite.
 */
import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';
import { io as ioClient, type Socket } from 'socket.io-client';
import { closeDb } from '../db/index.js';
import { _setDurationForTest } from '../core/timerManager.js';

// Very short PROMPTING timer so tests complete quickly.
_setDurationForTest('PROMPTING', 3);

// ── Helpers ────────────────────────────────────────────────────────────────

function connect(port: number): Socket {
    return ioClient(`http://127.0.0.1:${port}`, { transports: ['websocket'] });
}

function waitFor<T>(socket: Socket, event: string, timeoutMs = 8000): Promise<T> {
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

function startRound(socket: Socket, roomCode: string): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
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

describe('M2.6 — Partial Submission Handling', () => {
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

    test('timer expiry advances PROMPTING → GENERATING when no one submits', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Ana');
        await join(p2, code, 'Bogdan');
        await startRound(p1, code);

        // Neither player submits — wait for timer to expire (3s + slack)
        const generatingEvt = await waitFor<{ state: string; triggeredBy: string }>(
            p1,
            'round:generating',
            7000,
        );

        expect(generatingEvt.state).toBe('GENERATING');
        expect(generatingEvt.triggeredBy).toBe('timer');

        p1.disconnect();
        p2.disconnect();
    }, 12000);

    test('round:partial_submissions is emitted on timer expiry', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Cristi');
        await join(p2, code, 'Diana');
        await startRound(p1, code);

        const partialEvt = await waitFor<{
            players: { playerId: string; nickname: string; submitted: boolean }[];
            submittedCount: number;
            totalCount: number;
            triggeredBy: string;
        }>(p1, 'round:partial_submissions', 7000);

        expect(partialEvt.triggeredBy).toBe('timer_expiry');
        expect(partialEvt.totalCount).toBe(2);
        expect(partialEvt.submittedCount).toBe(0);
        expect(partialEvt.players).toHaveLength(2);

        const nicknames = partialEvt.players.map((p) => p.nickname);
        expect(nicknames).toContain('Cristi');
        expect(nicknames).toContain('Diana');

        for (const p of partialEvt.players) {
            expect(p.submitted).toBe(false);
        }

        p1.disconnect();
        p2.disconnect();
    }, 12000);

    test('partial_submissions correctly marks who submitted before expiry', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Elena');
        await join(p2, code, 'Florin');

        // Capture p1's prompts before starting
        const p1PromptsPromise = new Promise<{ prompts: { promptId: string; text: string }[] }>(
            (resolve) => {
                p1.once('round:prompts', resolve as (v: unknown) => void);
            },
        );

        await startRound(p1, code);
        const { prompts } = await p1PromptsPromise;

        // p1 submits, p2 does not
        const answers = prompts.map((p) => ({ promptId: p.promptId, text: 'răspuns Elena' }));
        await submit(p1, code, answers);

        const partialEvt = await waitFor<{
            players: { playerId: string; nickname: string; submitted: boolean }[];
            submittedCount: number;
            totalCount: number;
        }>(p1, 'round:partial_submissions', 7000);

        expect(partialEvt.submittedCount).toBe(1);
        expect(partialEvt.totalCount).toBe(2);

        const elenaStatus = partialEvt.players.find((p) => p.nickname === 'Elena');
        const florinStatus = partialEvt.players.find((p) => p.nickname === 'Florin');

        expect(elenaStatus?.submitted).toBe(true);
        expect(florinStatus?.submitted).toBe(false);

        p1.disconnect();
        p2.disconnect();
    }, 12000);

    test('state is GENERATING after partial expiry — late submission is rejected', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);

        await join(p1, code, 'Gabi');
        await join(p2, code, 'Horia');

        const p1PromptsPromise = new Promise<{ prompts: { promptId: string; text: string }[] }>(
            (resolve) => {
                p1.once('round:prompts', resolve as (v: unknown) => void);
            },
        );

        await startRound(p1, code);
        const { prompts } = await p1PromptsPromise;

        // Wait for timer to expire
        await waitFor(p1, 'round:generating', 7000);

        // Try to submit after expiry
        const answers = prompts.map((p) => ({ promptId: p.promptId, text: 'prea târziu' }));
        const ack = await submit(p1, code, answers);

        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/closed|PROMPTING/i);

        p1.disconnect();
        p2.disconnect();
    }, 12000);
});