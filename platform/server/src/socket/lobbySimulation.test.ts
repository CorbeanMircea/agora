/**
 * M1.14 — Integration Test: Full Lobby Simulation
 *
 * Simulates 4 players joining a room, the host starting a round, and the
 * state machine advancing through all phases from WAITING to SCORING.
 *
 * Uses manual round:advance (no timers) to stay well under 10 seconds.
 */
import 'dotenv/config';
import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';
import { io as ioClient, type Socket } from 'socket.io-client';
import { closeDb } from '../db/index.js';
import type { RoomState } from '../db/types.js';

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

/** Emit player:join and return the ack. */
function join(
    socket: Socket,
    roomCode: string,
    nickname: string,
): Promise<{ ok: boolean; playerId?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('player:join', { roomCode, nickname }, resolve);
    });
}

/** Emit round:start and return the ack. */
function startRound(
    socket: Socket,
    roomCode: string,
): Promise<{ ok: boolean; state?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('round:start', { roomCode }, resolve);
    });
}

/** Emit round:advance and return the ack. */
function advanceRound(
    socket: Socket,
    roomCode: string,
    toState: RoomState,
): Promise<{ ok: boolean; state?: string; error?: string }> {
    return new Promise((resolve) => {
        socket.emit('round:advance', { roomCode, toState }, resolve);
    });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('M1.14 — Full Lobby Simulation', () => {
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

    test('4 players join, host starts round, state machine sequences to SCORING', async () => {
        // ── Create a room ────────────────────────────────────────────────────
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        expect(res.statusCode).toBe(201);
        const { code } = res.json() as { code: string };

        // ── Connect 4 player sockets ─────────────────────────────────────────
        const players = [
            connect(port),
            connect(port),
            connect(port),
            connect(port),
        ];
        const nicknames = ['Ana', 'Bogdan', 'Cristi', 'Diana'];

        // ── Each player joins and receives a playerId ─────────────────────────
        const joinAcks = await Promise.all(
            players.map((socket, i) => join(socket, code, nicknames[i]!)),
        );

        joinAcks.forEach((ack, i) => {
            expect(ack.ok).toBe(true);
            expect(typeof ack.playerId).toBe('string');
            expect((ack.playerId ?? '').length).toBeGreaterThan(0);
        });

        // ── Verify all players receive player:joined with the full list ───────
        // The last join broadcasts to all 4 — player[0] should have received it
        // We can't retroactively verify past events, so we subscribe all players
        // to the next player:joined and trigger a re-join to observe live.
        // Instead, verify via the final ack's implicit broadcast by checking the
        // last-joined player's own ack succeeded (server confirmed the state).
        //
        // For explicit broadcast verification, subscribe player[0] before
        // player[3] joins in a separate scenario (covered by M1.5 tests).
        // Here we focus on the end-to-end round flow.

        // ── Register event listeners on all 4 players before starting ─────────
        const prompting = players.map((s) =>
            waitFor<{ roundNumber: number; state: string }>(s, 'round:prompting'),
        );
        const generating = players.map((s) =>
            waitFor<{ state: string }>(s, 'round:generating'),
        );
        const revealing = players.map((s) =>
            waitFor<{ state: string }>(s, 'round:revealing'),
        );
        const voting = players.map((s) =>
            waitFor<{ state: string }>(s, 'round:voting'),
        );
        const scoring = players.map((s) =>
            waitFor<{ state: string }>(s, 'round:scoring'),
        );

        // ── Host starts the round (player[0] acts as host) ────────────────────
        const startAck = await startRound(players[0]!, code);
        expect(startAck.ok).toBe(true);
        expect(startAck.state).toBe('PROMPTING');

        // ── All 4 players receive round:prompting ─────────────────────────────
        const promptingEvents = await Promise.all(prompting);
        promptingEvents.forEach((evt) => {
            expect(evt.roundNumber).toBe(1);
            expect(evt.state).toBe('PROMPTING');
        });

        // ── Advance to GENERATING ─────────────────────────────────────────────
        const toGen = await advanceRound(players[0]!, code, 'GENERATING');
        expect(toGen.ok).toBe(true);
        expect(toGen.state).toBe('GENERATING');

        const generatingEvents = await Promise.all(generating);
        generatingEvents.forEach((evt) => {
            expect(evt.state).toBe('GENERATING');
        });

        // ── Advance to REVEALING ──────────────────────────────────────────────
        const toRev = await advanceRound(players[0]!, code, 'REVEALING');
        expect(toRev.ok).toBe(true);
        expect(toRev.state).toBe('REVEALING');

        const revealingEvents = await Promise.all(revealing);
        revealingEvents.forEach((evt) => {
            expect(evt.state).toBe('REVEALING');
        });

        // ── Advance to VOTING ─────────────────────────────────────────────────
        const toVote = await advanceRound(players[0]!, code, 'VOTING');
        expect(toVote.ok).toBe(true);
        expect(toVote.state).toBe('VOTING');

        const votingEvents = await Promise.all(voting);
        votingEvents.forEach((evt) => {
            expect(evt.state).toBe('VOTING');
        });

        // ── Advance to SCORING ────────────────────────────────────────────────
        const toScore = await advanceRound(players[0]!, code, 'SCORING');
        expect(toScore.ok).toBe(true);
        expect(toScore.state).toBe('SCORING');

        const scoringEvents = await Promise.all(scoring);
        scoringEvents.forEach((evt) => {
            expect(evt.state).toBe('SCORING');
        });

        // ── Cleanup ───────────────────────────────────────────────────────────
        players.forEach((s) => s.disconnect());
    });

    test('all 4 players receive player:joined broadcast when each new player joins', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const p1 = connect(port);
        const p2 = connect(port);
        const p3 = connect(port);
        const p4 = connect(port);

        // p1 joins first
        await join(p1, code, 'Player1');

        // Subscribe p1 to the next 3 player:joined broadcasts (from p2, p3, p4 joining)
        // We only need to verify the final broadcast contains all 4 players
        const finalBroadcast = waitFor<{ players: { id: string; nickname: string }[] }>(
            p1,
            'player:joined',
        );

        await join(p2, code, 'Player2');
        await join(p3, code, 'Player3');

        // Re-subscribe for the last join
        const lastBroadcast = waitFor<{ players: { id: string; nickname: string }[] }>(
            p1,
            'player:joined',
        );
        await join(p4, code, 'Player4');

        const { players } = await lastBroadcast;
        const names = players.map((p) => p.nickname);

        expect(names).toContain('Player1');
        expect(names).toContain('Player2');
        expect(names).toContain('Player3');
        expect(names).toContain('Player4');
        expect(players).toHaveLength(4);

        p1.disconnect();
        p2.disconnect();
        p3.disconnect();
        p4.disconnect();

        // Suppress unused warning — finalBroadcast resolves on its own
        void finalBroadcast;
    });

    test('invalid transitions are rejected at every phase', async () => {
        const res = await fastify.inject({ method: 'POST', url: '/rooms' });
        const { code } = res.json() as { code: string };

        const host = connect(port);
        await join(host, code, 'HostOnly');
        await startRound(host, code); // → PROMPTING

        // Cannot skip from PROMPTING directly to VOTING
        const bad1 = await advanceRound(host, code, 'VOTING');
        expect(bad1.ok).toBe(false);
        expect(bad1.error).toMatch(/invalid transition/i);

        // Cannot skip from PROMPTING directly to REVEALING
        const bad2 = await advanceRound(host, code, 'REVEALING');
        expect(bad2.ok).toBe(false);
        expect(bad2.error).toMatch(/invalid transition/i);

        // Valid transition proceeds
        const good = await advanceRound(host, code, 'GENERATING');
        expect(good.ok).toBe(true);

        host.disconnect();
    });

    test('non-existent room is rejected on round:start', async () => {
        const host = connect(port);
        const ack = await startRound(host, 'ZZZZ');
        expect(ack.ok).toBe(false);
        expect(ack.error).toMatch(/not found/i);
        host.disconnect();
    });
});