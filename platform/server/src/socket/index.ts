/**
 * Socket.IO event handler registration.
 */
import type { Server as SocketIOServer } from 'socket.io';
import type { FastifyBaseLogger } from 'fastify';
import { registerPlayerJoinHandler } from './playerJoin.js';

export function registerSocketHandlers(
    io: SocketIOServer,
    log: FastifyBaseLogger,
): void {
    io.on('connection', (socket) => {
        log.info({ socketId: socket.id }, 'Client connected');

        registerPlayerJoinHandler(io, socket);

        socket.on('disconnect', (reason) => {
            log.info({ socketId: socket.id, reason }, 'Client disconnected');
        });
    });
}