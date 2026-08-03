/**
 * Room management routes.
 *
 * POST /rooms              — create a room, return code + join URL
 * GET  /rooms/:code/qr    — return a QR PNG for the phone join URL
 */
import type { FastifyInstance } from 'fastify';
import QRCode from 'qrcode';
import { createUniqueRoom } from '../core/roomCodes.js';
import { getRoomByCode } from '../db/index.js';
import { getDb } from '../db/index.js';
import { config } from '../config/index.js';

/** Base URL phones will hit — configurable so LAN IPs work in production. */
function phoneBaseUrl(): string {
    return (
        process.env['PHONE_BASE_URL'] ??
        `http://${config.host === '0.0.0.0' ? 'localhost' : config.host}:${config.port}`
    );
}

export async function roomRoutes(fastify: FastifyInstance): Promise<void> {
    /**
     * POST /rooms
     * Creates a room. Returns the code, initial state, and the phone join URL.
     */
    fastify.post('/rooms', async (_request, reply) => {
        const db = getDb();
        const room = createUniqueRoom(db);
        const joinUrl = `${phoneBaseUrl()}/join?room=${room.code}`;

        return reply.code(201).send({
            code: room.code,
            state: room.state,
            joinUrl,
            createdAt: room.created_at,
        });
    });

    /**
     * GET /rooms/:code/qr
     * Returns a QR code PNG image encoding the phone join URL for the given room.
     */
    fastify.get<{ Params: { code: string } }>(
        '/rooms/:code/qr',
        async (request, reply) => {
            const db = getDb();
            const code = request.params.code.toUpperCase();
            const room = getRoomByCode(db, code);

            if (room === undefined) {
                return reply.code(404).send({ error: 'Room not found' });
            }

            const joinUrl = `${phoneBaseUrl()}/phone/join?room=${room.code}`;

            const png = await QRCode.toBuffer(joinUrl, {
                type: 'png',
                width: 400,
                margin: 2,
                color: { dark: '#000000', light: '#ffffff' },
            });

            return reply
                .code(200)
                .header('Content-Type', 'image/png')
                .header('Cache-Control', 'no-cache')
                .send(png);
        },
    );
}