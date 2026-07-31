/**
 * HTTP route registrations for the AGORA platform server.
 * M1.2 scope: health endpoint only.
 * Future milestones add room management, phone shell serving, etc.
 */
import type { FastifyInstance } from 'fastify';

export async function registerRoutes(fastify: FastifyInstance): Promise<void> {
    fastify.get('/health', async (_request, _reply) => {
        return { status: 'ok' };
    });
}