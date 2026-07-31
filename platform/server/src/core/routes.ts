/**
 * HTTP route registrations for the AGORA platform server.
 */
import type { FastifyInstance } from 'fastify';
import { roomRoutes } from '../routes/rooms.js';

export async function registerRoutes(fastify: FastifyInstance): Promise<void> {
    fastify.get('/health', async (_request, _reply) => {
        return { status: 'ok' };
    });

    await fastify.register(roomRoutes);
}