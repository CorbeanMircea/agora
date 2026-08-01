import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';
import { io as ioClient, type Socket } from 'socket.io-client';
import { closeDb } from '../db/index.js';

// ── helpers ────────────────────────────────────────────────────────────────

function connect(port: number): Socket {
    return ioClient(`http://127.0.0.1:${port}`, { transports: ['websocket'] });
}

function waitFor<T>(socket: Socket, event: string): Promise<T> {
    return new Promise((resolve) => socket.once(event, resolve as (v: unknown) => void));
}

function join(socket: Socket, roomCode: string, nickname: string): Promise<{ ok: boolean }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

function startRound(
    socket: Socket,
    roomCode: string,
): Promise<{ ok: boolean; state?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
}

function advanceRound(
    socket: Socket,
    roomCode: string,
    toState: string,
): Promise<{ ok: boolean; state?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('round:advance', { roomCode, toState }, resolve);
    });
}

// ── tests ──────────────────────────────────────────────────────────────────

describe('M1.7 — Round State Machine', () => {
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

    test('round:start transitions WAITING → PROMPTING and broadcasts event', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        const player = connect(port);

        await join(host, code, 'Host');
        await join(player, code, 'Player');

        const eventPromise = waitFor<{ roundNumber: number; state: string }>(
            player,
            'round:prompting',
        );

        const ack = await startRound(host, code);
        expect(ack.ok).toBe(true);
        expect(ack.state).toBe('PROMPTING');

        const event = await eventPromise;
        expect(event.roundNumber).toBe(1);
        expect(event.state).toBe('PROMPTING');

        host.disconnect();
        player.disconnect();
    });

    test('round:start fails when room is not WAITING', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'Host2');

        // Start once — now PROMPTING
        await startRound(host, code);

        // Try to start again — should fail
        const ack = await startRound(host, code);
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/WAITING/i);

        host.disconnect();
    });

    test('round:start fails for non-existent room', async () => {
        const host = connect(port);
        const ack = await startRound(host, 'ZZZZ');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/not found/i);
        host.disconnect();
    });

    test('round:advance sequences through all states', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'HostAdvance');

        await startRound(host, code); // → PROMPTING

        const states = ['GENERATING', 'REVEALING', 'VOTING', 'SCORING', 'WAITING'] as const;

        for (const toState of states) {
            const ack = await advanceRound(host, code, toState);
            expect(ack.ok).toBe(true);
            expect(ack.state).toBe(toState);
        }

        host.disconnect();
    });

    test('round:advance rejects invalid transition', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'HostSkip');

        await startRound(host, code); // → PROMPTING

        // Try to skip from PROMPTING directly to VOTING (invalid)
        const ack = await advanceRound(host, code, 'VOTING');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/invalid transition/i);

        host.disconnect();
    });

    test('round:advance broadcasts event to all room members', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        const observer = connect(port);

        await join(host, code, 'HostBroadcast');
        await join(observer, code, 'Observer');

        await startRound(host, code);

        const eventPromise = waitFor<{ state: string }>(observer, 'round:generating');
        await advanceRound(host, code, 'GENERATING');

        const event = await eventPromise;
        expect(event.state).toBe('GENERATING');

        host.disconnect();
        observer.disconnect();
    });

    test('round:start invalid payload returns ok:false', async () => {
        const host = connect(port);
        const ack = await new Promise<{ ok: boolean; error?: string }>((resolve) => {
            host.emit('round:start', { bad: 'data' }, resolve);
        });
        expect(ack.ok).toBe(false);
        host.disconnect();
    });

    test('second round:start after SCORING → WAITING creates round 2', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'HostR2');

        // Complete round 1
        await startRound(host, code);
        await advanceRound(host, code, 'GENERATING');
        await advanceRound(host, code, 'REVEALING');
        await advanceRound(host, code, 'VOTING');
        await advanceRound(host, code, 'SCORING');
        await advanceRound(host, code, 'WAITING');

        // Start round 2
        const r2Promise = waitFor<{ roundNumber: number }>(host, 'round:prompting');
        const ack = await startRound(host, code);
        expect(ack.ok).toBe(true);

        const r2Event = await r2Promise;
        expect(r2Event.roundNumber).toBe(2);

        host.disconnect();
    });
});