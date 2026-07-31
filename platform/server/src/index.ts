/**
 * AGORA Platform Server — Entry Point
 */
import 'dotenv/config';
import Fastify from 'fastify';
import cors from '@fastify/cors';
import { createRequire } from 'module';
import { config } from './config/index.js';
import { registerRoutes } from './core/routes.js';
import { registerSocketHandlers } from './socket/index.js';
import { getDb, closeDb } from './db/index.js';

const require = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
const fastifySocketIO = require('fastify-socket.io');

async function buildServer() {
    const fastify = Fastify({
        // Cast to any: pino-pretty transport is valid at runtime but Fastify's
        // bundled pino types don't expose the `transport` field on their logger
        // options interface. This is a known typing gap in fastify@4 + pino@8.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        logger: (config.nodeEnv === 'development'
            ? { level: 'info', transport: { target: 'pino-pretty', options: { colorize: true } } }
            : { level: 'warn' }) as any,
    });

    await fastify.register(cors, {
        origin: config.corsOrigin,
        methods: ['GET', 'POST', 'OPTIONS'],
    });

    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument
    await fastify.register(fastifySocketIO, {
        cors: {
            origin: config.corsOrigin,
            methods: ['GET', 'POST'],
        },
        connectionStateRecovery: {
            maxDisconnectionDuration: 2 * 60 * 1000,
            skipMiddlewares: true,
        },
    });

    await registerRoutes(fastify);

    fastify.ready(() => {
        registerSocketHandlers(fastify.io, fastify.log);
    });

    return fastify;
}

async function start() {
    // Initialise DB — runs migrations on first boot
    getDb();

    const fastify = await buildServer();
    try {
        await fastify.listen({ host: config.host, port: config.port });
    } catch (err) {
        fastify.log.error(err);
        closeDb();
        process.exit(1);
    }

    process.on('SIGINT', () => { closeDb(); process.exit(0); });
    process.on('SIGTERM', () => { closeDb(); process.exit(0); });
}

export { buildServer };

start();