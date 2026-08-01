/**
 * Socket.IO event handler registration.
 */
import type { Server as SocketIOServer } from 'socket.io';
import type { FastifyBaseLogger } from 'fastify';
import { registerPlayerJoinHandler } from './playerJoin.js';
import { registerPlayerRejoinHandler, handlePlayerDisconnect } from './playerRejoin.js';
import { registerRoundHandlers } from './roundHandlers.js';
import { initTimerManager } from '../core/timerManager.js';

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

        socket.on('disconnect', (reason) => {
            log.info({ socketId: socket.id, reason }, 'Client disconnected');
            handlePlayerDisconnect(io, socket);
        });
    });
}