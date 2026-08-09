/**
 * HTTP route registrations for the AGORA platform server.
 */
import type { FastifyInstance } from 'fastify';
import { roomRoutes } from '../routes/rooms.js';
import { phoneRoutes } from '../routes/phone.js';
import { hostRoutes } from '../routes/host.js';
import { pipelineRoutes } from '../routes/pipeline.js';

export async function registerRoutes(fastify: FastifyInstance): Promise<void> {
    fastify.get('/health', async (_request, _reply) => {
        return { status: 'ok' };
    });

    await fastify.register(roomRoutes);
    await fastify.register(phoneRoutes);
    await fastify.register(hostRoutes);
    await fastify.register(pipelineRoutes);
}