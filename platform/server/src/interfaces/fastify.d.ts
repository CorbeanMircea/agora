import type { Server as SocketIOServer } from 'socket.io';

declare module 'fastify' {
    interface FastifyInstance {
        /** The Socket.IO server instance, attached at startup. */
        io: SocketIOServer;
    }
}