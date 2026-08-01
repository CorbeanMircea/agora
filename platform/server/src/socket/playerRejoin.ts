/**
 * M1.6 — Connection Resilience
 *
 * Handles the `player:rejoin` Socket.IO event.
 * Client sends:  { playerId: string; roomCode: string }
 * Ack response:  { ok: true; nickname: string } | { ok: false; error: string }
 * Room broadcast (on rejoin):       `player:reconnected` { playerId, nickname }
 * Room broadcast (on disconnect):   `player:disconnected` { playerId, nickname }
 *
 * On socket disconnect, the player is marked inactive in SQLite and the room
 * is notified. The player record is never deleted — a rejoin restores it.
 */
import type { Server, Socket } from 'socket.io';
import {
    getDb,
    getRoomByCode,
    getPlayerById,
    getPlayersByRoom,
    setPlayerActive,
} from '../db/index.js';

interface RejoinPayload {
    playerId: string;
    roomCode: string;
}

type AckFn = (result: { ok: boolean; nickname?: string; error?: string }) => void;

export function registerPlayerRejoinHandler(io: Server, socket: Socket): void {
    socket.on('player:rejoin', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, nickname?: string, error?: string): void => {
            if (typeof ack === 'function') {
                if (ok && nickname !== undefined) {
                    ack({ ok: true, nickname });
                } else {
                    ack({ ok: false, error: error ?? 'Unknown error' });
                }
            }
        };

        // --- Validate payload shape ---
        if (
            typeof payload !== 'object' ||
            payload === null ||
            typeof (payload as Record<string, unknown>)['playerId'] !== 'string' ||
            typeof (payload as Record<string, unknown>)['roomCode'] !== 'string'
        ) {
            reply(false, undefined, 'Invalid payload: expected { playerId, roomCode }');
            return;
        }

        const raw = payload as RejoinPayload;
        const playerId = raw.playerId.trim();
        const roomCode = raw.roomCode.trim().toUpperCase();

        if (playerId.length === 0 || roomCode.length !== 4) {
            reply(false, undefined, 'Invalid playerId or roomCode');
            return;
        }

        const db = getDb();

        // --- Room must exist ---
        const room = getRoomByCode(db, roomCode);
        if (room === undefined) {
            reply(false, undefined, 'Room not found');
            return;
        }

        // --- Player must exist ---
        const player = getPlayerById(db, playerId);
        if (player === undefined) {
            reply(false, undefined, 'Player not found');
            return;
        }

        // --- Player must belong to this room ---
        if (player.room_id !== room.id) {
            reply(false, undefined, 'Player does not belong to this room');
            return;
        }

        // --- Restore player as active ---
        setPlayerActive(db, playerId, true);

        // --- Join the Socket.IO room channel ---
        void socket.join(roomCode);

        // --- Store identity on socket for disconnect handling ---
        socket.data['playerId'] = playerId;
        socket.data['roomCode'] = roomCode;

        // --- Broadcast reconnection to room ---
        io.to(roomCode).emit('player:reconnected', {
            playerId,
            nickname: player.nickname,
        });

        // --- Also send updated full player list ---
        const activePlayers = getPlayersByRoom(db, room.id)
            .filter((p) => p.active === 1)
            .map((p) => ({ id: p.id, nickname: p.nickname }));

        io.to(roomCode).emit('player:joined', { players: activePlayers });

        reply(true, player.nickname);
    });
}

/**
 * Called from the central disconnect handler in socket/index.ts.
 * Marks the player inactive and notifies the room.
 */
export function handlePlayerDisconnect(io: Server, socket: Socket): void {
    const playerId = socket.data['playerId'] as string | undefined;
    const roomCode = socket.data['roomCode'] as string | undefined;

    if (playerId === undefined || roomCode === undefined) {
        // Socket never completed a join — nothing to clean up.
        return;
    }

    const db = getDb();
    const player = getPlayerById(db, playerId);

    if (player === undefined) return;

    setPlayerActive(db, playerId, false);

    io.to(roomCode).emit('player:disconnected', {
        playerId,
        nickname: player.nickname,
    });
}