/**
 * Host Dashboard route.
 * Serves the self-contained host control page at GET /host.
 * The HTML file lives at src/host/dashboard.html and is read once at
 * startup (or on each request in development) so Fastify can serve it
 * without the @fastify/static dependency on this specific path.
 */
import type { FastifyInstance } from 'fastify';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Resolved path to the dashboard HTML file.
 * From src/routes/ → src/ → host/dashboard.html
 */
const DASHBOARD_PATH = path.resolve(__dirname, '../host/dashboard.html');

export async function hostRoutes(fastify: FastifyInstance): Promise<void> {
    if (!fs.existsSync(DASHBOARD_PATH)) {
        fastify.log.error(`Host dashboard not found at ${DASHBOARD_PATH}`);
        fastify.get('/host', async (_req, reply) =>
            reply.code(500).send({ error: 'Host dashboard file missing' }),
        );
        return;
    }

    // Read once at plugin registration. In dev you can change to readFileSync
    // per-request for live reload, but startup-time read is fine for M1.
    const html = fs.readFileSync(DASHBOARD_PATH, 'utf-8');

    fastify.get('/host', async (_request, reply) => {
        return reply
            .code(200)
            .header('Content-Type', 'text/html; charset=utf-8')
            .header('Cache-Control', 'no-cache')
            .send(html);
    });
}