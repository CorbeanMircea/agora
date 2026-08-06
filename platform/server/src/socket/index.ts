/**
 * Socket.IO event handler registration.
 */
import type { Server as SocketIOServer } from 'socket.io';
import type { FastifyBaseLogger } from 'fastify';
import { registerPlayerJoinHandler } from './playerJoin.js';
import { registerPlayerRejoinHandler, handlePlayerDisconnect } from './playerRejoin.js';
import { registerRoundHandlers } from './roundHandlers.js';
import { registerPlayerSubmitHandler } from './playerSubmit.js';
import { initTimerManager } from '../core/timerManager.js';
import { getDb, getRoomByCode, getPlayersByRoom } from '../db/index.js';

export function registerSocketHandlers(
    io: SocketIOServer,
    log: FastifyBaseLogger,
): void {
    // Inject the Socket.IO server into the timer manager once at startup.
    initTimerManager(io);

    io.on('connection', (socket) => {
        log.info({ socketId: socket.id }, 'Client connected');

        registerPlayerJoinHandler(io, socket);
        registerPlayerRejoinHandler(io, socket);
        registerRoundHandlers(io, socket);
        registerPlayerSubmitHandler(io, socket);

        /**
         * host:watch
         * The host dashboard emits this after creating/restoring a room.
         * We join the host socket into the room's Socket.IO channel so it
         * receives all player:joined / player:disconnected / round:* events,
         * then immediately send back the current player list.
         */
        socket.on('host:watch', (payload: unknown) => {
            if (
                typeof payload !== 'object' ||
                payload === null ||
                typeof (payload as Record<string, unknown>)['roomCode'] !== 'string'
            ) {
                return;
            }

            const roomCode = ((payload as Record<string, unknown>)['roomCode'] as string)
                .trim()
                .toUpperCase();

            const db = getDb();
            const room = getRoomByCode(db, roomCode);
            if (room === undefined) {
                log.warn({ roomCode }, 'host:watch for unknown room');
                return;
            }

            // Join the Socket.IO channel so the host receives all room broadcasts
            void socket.join(roomCode);
            log.info({ socketId: socket.id, roomCode }, 'Host watching room');

            // Send the current active player list immediately so the host sees
            // anyone who joined before this socket connected / page refreshed
            const activePlayers = getPlayersByRoom(db, room.id)
                .filter(p => p.active === 1)
                .map(p => ({ id: p.id, nickname: p.nickname }));

            socket.emit('player:joined', { players: activePlayers });

            // Also sync the current room state so the badge is correct
            socket.emit('host:state', { state: room.state });
        });

        socket.on('disconnect', (reason) => {
            log.info({ socketId: socket.id, reason }, 'Client disconnected');
            handlePlayerDisconnect(io, socket);
        });
    });
}