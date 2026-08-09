/**
 * Pipeline callback routes.
 *
 * These endpoints are called by the Python pipeline orchestrator
 * when a round's pipeline completes or fails.
 *
 * POST /pipeline/complete   — pipeline finished successfully
 * POST /pipeline/failed     — pipeline failed
 *
 * Both endpoints advance (or note) the room state via Socket.IO.
 */
import type { FastifyInstance } from 'fastify';
import { getDb, getRoomByCode, getCurrentRound, setRoomState, setRoundState } from '../db/index.js';
import { isValidTransition, stateToEvent } from '../core/roundStateMachine.js';

interface PipelineCompleteBody {
    roundId: number;
    outputDir: string;
    durationSeconds: number;
}

interface PipelineFailedBody {
    roundId: number;
    reason: string;
}

export async function pipelineRoutes(fastify: FastifyInstance): Promise<void> {
    /**
     * POST /pipeline/complete
     * Called by the Python orchestrator when all pipeline steps finish.
     * Advances state GENERATING → REVEALING and broadcasts to the room.
     */
    fastify.post<{ Body: PipelineCompleteBody }>(
        '/pipeline/complete',
        {
            schema: {
                body: {
                    type: 'object',
                    required: ['roundId', 'outputDir'],
                    properties: {
                        roundId: { type: 'number' },
                        outputDir: { type: 'string' },
                        durationSeconds: { type: 'number' },
                    },
                },
            },
        },
        async (request, reply) => {
            const { roundId, outputDir, durationSeconds } = request.body;

            fastify.log.info(
                { roundId, outputDir, durationSeconds },
                'Pipeline complete callback received',
            );

            const db = getDb();

            // Find the room associated with this round
            const roundRow = db
                .prepare<[number], { id: number; room_id: number; state: string; round_number: number }>(
                    `SELECT id, room_id, state, round_number FROM rounds WHERE id = ?`,
                )
                .get(roundId);

            if (roundRow === undefined) {
                fastify.log.warn({ roundId }, 'Pipeline complete: round not found');
                return reply.code(404).send({ error: 'Round not found' });
            }

            // Find the room to get the room code (needed for Socket.IO broadcast)
            const roomRow = db
                .prepare<[number], { id: number; code: string; state: string }>(
                    `SELECT id, code, state FROM rooms WHERE id = ?`,
                )
                .get(roundRow.room_id);

            if (roomRow === undefined) {
                fastify.log.warn({ roundId }, 'Pipeline complete: room not found');
                return reply.code(404).send({ error: 'Room not found' });
            }

            // Only advance if still in GENERATING state
            if (roomRow.state !== 'GENERATING') {
                fastify.log.info(
                    { roundId, state: roomRow.state },
                    'Pipeline complete: room already advanced past GENERATING — ignoring',
                );
                return reply.code(200).send({ ok: true, message: 'State already advanced' });
            }

            if (!isValidTransition('GENERATING', 'REVEALING')) {
                return reply.code(409).send({ error: 'Invalid transition GENERATING → REVEALING' });
            }

            setRoomState(db, roomRow.id, 'REVEALING');
            setRoundState(db, roundRow.id, 'REVEALING');

            const eventName = stateToEvent('REVEALING');
            fastify.io.to(roomRow.code).emit(eventName, {
                roundNumber: roundRow.round_number,
                state: 'REVEALING',
                outputDir,
                triggeredBy: 'pipeline_complete',
            });

            fastify.log.info(
                { roundId, roomCode: roomRow.code },
                'State advanced GENERATING → REVEALING',
            );

            return reply.code(200).send({ ok: true });
        },
    );

    /**
     * POST /pipeline/failed
     * Called by the Python orchestrator when the pipeline fails.
     * Logs the error; does not automatically advance state
     * (host must manually intervene via round:advance).
     */
    fastify.post<{ Body: PipelineFailedBody }>(
        '/pipeline/failed',
        {
            schema: {
                body: {
                    type: 'object',
                    required: ['roundId', 'reason'],
                    properties: {
                        roundId: { type: 'number' },
                        reason: { type: 'string' },
                    },
                },
            },
        },
        async (request, reply) => {
            const { roundId, reason } = request.body;

            fastify.log.error(
                { roundId, reason },
                'Pipeline FAILED — manual intervention required',
            );

            // Broadcast a pipeline failure event to the room so the host dashboard
            // can display an error. We find the round's room for the broadcast.
            const db = getDb();
            const roundRow = db
                .prepare<[number], { room_id: number; round_number: number }>(
                    `SELECT room_id, round_number FROM rounds WHERE id = ?`,
                )
                .get(roundId);

            if (roundRow !== undefined) {
                const roomRow = db
                    .prepare<[number], { code: string }>(
                        `SELECT code FROM rooms WHERE id = ?`,
                    )
                    .get(roundRow.room_id);

                if (roomRow !== undefined) {
                    fastify.io.to(roomRow.code).emit('pipeline:failed', {
                        roundId,
                        reason,
                        roundNumber: roundRow.round_number,
                    });
                }
            }

            return reply.code(200).send({ ok: true });
        },
    );
}