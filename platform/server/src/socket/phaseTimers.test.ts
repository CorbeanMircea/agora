import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { io as ioClient, type Socket } from 'socket.io-client';
import type { FastifyInstance } from 'fastify';
import { buildServer } from '../index.js';
import { closeDb } from '../db/index.js';
import { _setDurationForTest } from '../core/timerManager.js';

// Shorten timers before any test runs.
_setDurationForTest('PROMPTING', 3);
_setDurationForTest('VOTING', 2);

// ── helpers ────────────────────────────────────────────────────────────────

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

function join(socket: Socket, roomCode: string, nickname: string): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

function startRound(socket: Socket, roomCode: string): Promise<{ ok: boolean; state?: string }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
}

function advanceRound(socket: Socket, roomCode: string, toState: string): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('round:advance', { roomCode, toState }, resolve);
    });
}

// ── tests ──────────────────────────────────────────────────────────────────

describe('M1.8 — Phase Timers', () => {
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

    test('round:prompting event includes a numeric deadline', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host');

        const eventPromise = waitFor<{ deadline: number; state: string }>(host, 'round:prompting');
        await startRound(host, code);
        const event = await eventPromise;

        expect(typeof event.deadline).toBe('number');
        expect(event.deadline).toBeGreaterThan(Math.floor(Date.now() / 1000));

        host.disconnect();
    });

    test('timer:tick fires with correct shape during PROMPTING', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host');
        await startRound(host, code);

        const tick = await waitFor<{ phase: string; remaining: number; deadline: number }>(
            host,
            'timer:tick',
        );

        expect(tick.phase).toBe('PROMPTING');
        expect(tick.remaining).toBeGreaterThan(0);
        expect(typeof tick.deadline).toBe('number');

        host.disconnect();
    });

    test('timer:expired fires and state advances after PROMPTING expires', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host');
        await startRound(host, code);

        // 3s timer + 4s slack = 7s total
        const expired = await waitFor<{ phase: string; advancedTo: string }>(
            host,
            'timer:expired',
            7000,
        );

        expect(expired.phase).toBe('PROMPTING');
        expect(expired.advancedTo).toBe('GENERATING');

        host.disconnect();
    }, 12000);

    test('manual advance cancels timer — no timer:expired fired', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host');
        await startRound(host, code);

        // Advance manually within the 3s window
        await advanceRound(host, code, 'GENERATING');

        const result = await waitFor<unknown>(host, 'timer:expired', 5000)
            .then(() => 'fired')
            .catch(() => 'not_fired');
        expect(result).toBe('not_fired');

        host.disconnect();
    }, 12000);

    test('round:voting includes deadline and VOTING timer fires', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host');
        await startRound(host, code);

        await advanceRound(host, code, 'GENERATING');
        await advanceRound(host, code, 'REVEALING');

        const votingEventPromise = waitFor<{ deadline: number; state: string }>(
            host,
            'round:voting',
        );
        await advanceRound(host, code, 'VOTING');
        const votingEvent = await votingEventPromise;

        expect(typeof votingEvent.deadline).toBe('number');
        expect(votingEvent.deadline).toBeGreaterThan(Math.floor(Date.now() / 1000));

        // 2s timer + 4s slack = 6s total
        const expired = await waitFor<{ phase: string; advancedTo: string }>(
            host,
            'timer:expired',
            6000,
        );
        expect(expired.phase).toBe('VOTING');
        expect(expired.advancedTo).toBe('SCORING');

        host.disconnect();
    }, 15000);
});