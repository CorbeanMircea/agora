/**
 * AGORA Platform Server — Entry Point
 *
 * Boots Fastify v4 with Socket.IO via fastify-socket.io plugin.
 * Reads HOST and PORT from environment (via .env in dev).
 */
import 'dotenv/config';
import Fastify from 'fastify';
import cors from '@fastify/cors';
import fastifySocketIO from 'fastify-socket.io';
import { config } from './config/index.js';
import { registerRoutes } from './core/routes.js';
import { registerSocketHandlers } from './socket/index.js';

async function buildServer() {
    const fastify = Fastify({
        logger: {
            level: config.nodeEnv === 'development' ? 'info' : 'warn',
            transport:
                config.nodeEnv === 'development'
                    ? { target: 'pino-pretty', options: { colorize: true } }
                    : undefined,
        },
    });

    await fastify.register(cors, {
        origin: config.corsOrigin,
        methods: ['GET', 'POST', 'OPTIONS'],
    });

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

    // Socket.IO handlers must be registered after the plugin is ready
    fastify.ready(() => {
        registerSocketHandlers(fastify.io, fastify.log);
    });

    return fastify;
}

async function start() {
    const fastify = await buildServer();
    try {
        await fastify.listen({ host: config.host, port: config.port });
    } catch (err) {
        fastify.log.error(err);
        process.exit(1);
    }
}

export { buildServer };

start();