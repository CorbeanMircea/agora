import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';
import { io as ioClient, type Socket } from 'socket.io-client';
import { closeDb } from '../db/index.js';

// ── helpers ────────────────────────────────────────────────────────────────

function connect(port: number): Socket {
    return ioClient(`http://127.0.0.1:${port}`, {
        transports: ['websocket'],
    });
}

function waitFor<T>(socket: Socket, event: string): Promise<T> {
    return new Promise((resolve) => socket.once(event, resolve as (v: unknown) => void));
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

function rejoin(
    socket: Socket,
    playerId: string,
    roomCode: string,
): Promise<{ ok: boolean; nickname?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:rejoin', { playerId, roomCode }, resolve);
    });
}

// ── tests ──────────────────────────────────────────────────────────────────

describe('M1.6 — Connection Resilience', () => {
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

    test('player:join ack includes playerId', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const client = connect(port);
        const ack = await join(client, code, 'TestPlayer');

        expect(ack.ok).toBe(true);
        expect(typeof ack.playerId).toBe('string');
        expect((ack.playerId ?? '').length).toBeGreaterThan(0);

        client.disconnect();
    });

    test('disconnect marks player inactive and notifies room', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const observer = connect(port);
        const joiner = connect(port);

        // observer joins first to receive broadcasts
        await join(observer, code, 'Observer');
        await join(joiner, code, 'Leaver');

        const disconnectPromise = waitFor<{ playerId: string; nickname: string }>(
            observer,
            'player:disconnected',
        );

        joiner.disconnect();

        const event = await disconnectPromise;
        expect(event.nickname).toBe('Leaver');
        expect(typeof event.playerId).toBe('string');

        observer.disconnect();
    });

    test('player:rejoin restores player and notifies room', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const observer = connect(port);
        const joiner = connect(port);

        await join(observer, code, 'Watcher');
        const joinAck = await join(joiner, code, 'Returner');
        expect(joinAck.ok).toBe(true);
        const playerId = joinAck.playerId!;

        // Disconnect joiner
        const disconnectPromise = waitFor<unknown>(observer, 'player:disconnected');
        joiner.disconnect();
        await disconnectPromise;

        // Rejoin with a new socket
        const rejoiner = connect(port);
        const reconnectPromise = waitFor<{ playerId: string; nickname: string }>(
            observer,
            'player:reconnected',
        );

        const rejoinAck = await rejoin(rejoiner, playerId, code);
        expect(rejoinAck.ok).toBe(true);
        expect(rejoinAck.nickname).toBe('Returner');

        const reconnectEvent = await reconnectPromise;
        expect(reconnectEvent.nickname).toBe('Returner');
        expect(reconnectEvent.playerId).toBe(playerId);

        observer.disconnect();
        rejoiner.disconnect();
    });

    test('player:rejoin with unknown playerId returns ok:false', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const client = connect(port);
        const ack = await rejoin(client, '00000000-0000-0000-0000-000000000000', code);
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/not found/i);
        client.disconnect();
    });

    test('player:rejoin with wrong room returns ok:false', async () => {
        // Create two rooms
        const res1 = await fastify.inject({ method: 'POST', url: '/rooms' });
        const res2 = await fastify.inject({ method: 'POST', url: '/rooms' });
        const code1 = (res1.json() as { code: string }).code;
        const code2 = (res2.json() as { code: string }).code;

        const joiner = connect(port);
        const joinAck = await join(joiner, code1, 'Confused');
        expect(joinAck.ok).toBe(true);
        const playerId = joinAck.playerId!;
        joiner.disconnect();

        // Try to rejoin into the wrong room
        const client = connect(port);
        const ack = await rejoin(client, playerId, code2);
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/does not belong/i);
        client.disconnect();
    });
});