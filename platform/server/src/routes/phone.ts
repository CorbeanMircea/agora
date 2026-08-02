/**
 * Phone shell static file serving.
 * Serves the built SvelteKit phone shell from platform/phone-shell/dist
 * at the /phone path prefix.
 *
 * In development (before the phone shell is built), this route returns a
 * helpful 503 message.
 */
import type { FastifyInstance } from 'fastify';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Resolved path to the phone shell dist directory.
 * From platform/server/src/routes/ up to platform/, then into phone-shell/dist
 *
 * src/routes -> src -> platform/server -> platform -> phone-shell/dist
 *   ../           ../       ../              phone-shell/dist
 */
const PHONE_SHELL_DIST = path.resolve(__dirname, '../../../phone-shell/dist');

export async function phoneRoutes(fastify: FastifyInstance): Promise<void> {
    fastify.log.info(`Phone shell dist path: ${PHONE_SHELL_DIST}`);

    if (!fs.existsSync(PHONE_SHELL_DIST)) {
        fastify.log.warn(
            `Phone shell dist not found at ${PHONE_SHELL_DIST}. ` +
            `Run: npm run build -w platform/phone-shell`,
        );

        const notBuilt = { error: 'Phone shell not built. Run: npm run build -w platform/phone-shell' };
        fastify.get('/phone', async (_req, reply) => reply.code(503).send(notBuilt));
        fastify.get('/phone/*', async (_req, reply) => reply.code(503).send(notBuilt));
        return;
    }

    // Redirect bare /phone to /phone/ so relative asset paths resolve correctly
    fastify.get('/phone', async (_req, reply) => {
        return reply.redirect(301, '/phone/');
    });

    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const fastifyStatic = (await import('@fastify/static')).default;

    await fastify.register(fastifyStatic, {
        root: PHONE_SHELL_DIST,
        prefix: '/phone/',
        index: 'index.html',
        // Serve index.html for any path not matching a file (SPA fallback)
        wildcard: true,
        // Disable caching in dev
        cacheControl: false,
    });
}