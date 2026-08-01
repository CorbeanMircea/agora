/**
 * M1.5 — Player Join Flow (Server Side)
 *
 * Handles the `player:join` Socket.IO event.
 * Client sends:  { roomCode: string; nickname: string }
 * Ack response:  { ok: true } | { ok: false; error: string }
 * Room broadcast: `player:joined` { players: { id: string; nickname: string }[] }
 */
import type { Server, Socket } from 'socket.io';
import { randomUUID } from 'node:crypto';
import {
    getDb,
    getRoomByCode,
    getPlayersByRoom,
    createPlayer,
    nicknameExistsInRoom,
} from '../db/index.js';

interface JoinPayload {
    roomCode: string;
    nickname: string;
}

type AckFn = (result: { ok: boolean; error?: string }) => void;

export function registerPlayerJoinHandler(io: Server, socket: Socket): void {
    socket.on('player:join', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, error?: string): void => {
            if (typeof ack === 'function') {
                if (ok) {
                    ack({ ok: true });
                } else {
                    ack({ ok: false, error: error ?? 'Unknown error' });
                }
            }
        };

        // --- Validate payload shape ---
        if (
            typeof payload !== 'object' ||
            payload === null ||
            typeof (payload as Record<string, unknown>)['roomCode'] !== 'string' ||
            typeof (payload as Record<string, unknown>)['nickname'] !== 'string'
        ) {
            reply(false, 'Invalid payload: expected { roomCode, nickname }');
            return;
        }

        const raw = payload as JoinPayload;
        const roomCode = raw.roomCode.trim().toUpperCase();
        const nickname = raw.nickname.trim();

        // --- Input validation ---
        if (roomCode.length !== 4) {
            reply(false, 'Room code must be exactly 4 characters');
            return;
        }
        if (nickname.length < 1 || nickname.length > 24) {
            reply(false, 'Nickname must be 1–24 characters');
            return;
        }

        const db = getDb();

        // --- Room must exist ---
        const room = getRoomByCode(db, roomCode);
        if (room === undefined) {
            reply(false, 'Room not found');
            return;
        }

        // --- Room must be in WAITING state ---
        if (room.state !== 'WAITING') {
            reply(false, 'Room is not accepting new players right now');
            return;
        }

        // --- Reject duplicate nicknames ---
        if (nicknameExistsInRoom(db, room.id, nickname)) {
            reply(false, 'Nickname already taken in this room');
            return;
        }

        // --- Persist new player ---
        const playerId = randomUUID();
        createPlayer(db, playerId, room.id, nickname);

        // --- Join the Socket.IO room channel ---
        void socket.join(roomCode);

        // --- Broadcast updated active player list to all room members ---
        const activePlayers = getPlayersByRoom(db, room.id)
            .filter((p) => p.active === 1)
            .map((p) => ({ id: p.id, nickname: p.nickname }));

        io.to(roomCode).emit('player:joined', { players: activePlayers });

        reply(true);
    });
}