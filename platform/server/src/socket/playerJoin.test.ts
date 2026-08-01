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
): Promise<{ ok: boolean; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

// ── tests ──────────────────────────────────────────────────────────────────

describe('M1.5 — Player Join Flow (Server Side)', () => {
    let fastify: FastifyInstance;
    let port: number;
    let roomCode: string;

    beforeAll(async () => {
        fastify = await buildServer();
        await fastify.listen({ host: '127.0.0.1', port: 0 });
        const addr = fastify.server.address();
        port = typeof addr === 'object' && addr !== null ? addr.port : 3000;

        // Create a fresh room for these tests
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        expect(res.statusCode).toBe(201);
        roomCode = (res.json() as { code: string }).code;
    });

    afterAll(async () => {
        await fastify.close();
        closeDb();
        await new Promise<void>((resolve) => setTimeout(resolve, 200));
    });

    test('valid join returns ok:true', async () => {
        const client = connect(port);
        const ack = await join(client, roomCode, 'Ana');
        expect(ack.ok).toBe(true);
        expect(ack.error).toBeUndefined();
        client.disconnect();
    });

    test('player:joined is broadcast to all room members', async () => {
        // New room so we start clean
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const code = (res.json() as { code: string }).code;

        const client1 = connect(port);
        const client2 = connect(port);

        // client1 joins first, then listens for the broadcast from client2's join
        await join(client1, code, 'Player1');

        const joinedPromise = waitFor<{ players: { id: string; nickname: string }[] }>(
            client1,
            'player:joined',
        );
        await join(client2, code, 'Player2');

        const { players } = await joinedPromise;
        expect(players.map((p) => p.nickname)).toContain('Player1');
        expect(players.map((p) => p.nickname)).toContain('Player2');

        client1.disconnect();
        client2.disconnect();
    });

    test('duplicate nickname returns ok:false with error', async () => {
        const client = connect(port);
        // 'Ana' already joined the first room in the first test
        const ack = await join(client, roomCode, 'Ana');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/taken/i);
        client.disconnect();
    });

    test('non-existent room returns ok:false', async () => {
        const client = connect(port);
        const ack = await join(client, 'ZZZZ', 'Ghost');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/not found/i);
        client.disconnect();
    });

    test('invalid payload returns ok:false', async () => {
        const client = connect(port);
        const ack = await new Promise<{ ok: boolean; error?: string }>((resolve) => {
            client.emit('player:join', { bad: 'data' }, resolve);
        });
        expect(ack.ok).toBe(false);
        client.disconnect();
    });

    test('empty nickname returns ok:false', async () => {
        const client = connect(port);
        const ack = await join(client, roomCode, '   ');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/nickname/i);
        client.disconnect();
    });
});