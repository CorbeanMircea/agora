import 'dotenv/config';
import { buildServer } from '../index.js';
import type { FastifyInstance } from 'fastify';

describe('M1.2 — Platform Server Bootstrap', () => {
    let fastify: FastifyInstance;

    beforeAll(async () => {
        fastify = await buildServer();
        await fastify.ready();
    });

    afterAll(async () => {
        await fastify.close();
        // Give Socket.IO a moment to drain its internal timers
        await new Promise<void>((resolve) => setTimeout(resolve, 100));
    });

    test('GET /health returns 200 with { status: "ok" }', async () => {
        const response = await fastify.inject({
            method: 'GET',
            url: '/health',
        });
        expect(response.statusCode).toBe(200);
        expect(response.json()).toEqual({ status: 'ok' });
    });

    test('Socket.IO is registered on the fastify instance', () => {
        expect(fastify.io).toBeDefined();
    });
});