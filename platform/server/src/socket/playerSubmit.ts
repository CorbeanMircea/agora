/**
 * M2.5 — Answer Submission (Server Side)
 *
 * Handles the `player:submit` Socket.IO event.
 *
 * Client sends:
 *   { roomCode: string; answers: { promptId: string; text: string }[] }
 *
 * Ack response:
 *   { ok: true } | { ok: false; error: string }
 *
 * Host broadcast (not other players):
 *   `round:player_submitted` { playerId, nickname, submittedCount, totalCount }
 *
 * When all active players have submitted:
 *   State advances PROMPTING → GENERATING (broadcast to entire room).
 */
import type { Server, Socket } from 'socket.io';
import {
    getDb,
    getRoomByCode,
    getPlayerById,
    getPlayersByRoom,
    getCurrentRound,
    setRoomState,
    setRoundState,
    upsertAnswer,
    countSubmittedPlayers,
    getPromptAssignmentsByPlayer,
} from '../db/index.js';
import { isValidTransition, stateToEvent } from '../core/roundStateMachine.js';
import { cancelPhaseTimer } from '../core/timerManager.js';

const MAX_ANSWER_LENGTH = 120;

interface SubmitPayload {
    roomCode: string;
    answers: { promptId: string; text: string }[];
}

type AckFn = (result: { ok: boolean; error?: string }) => void;

export function registerPlayerSubmitHandler(io: Server, socket: Socket): void {
    socket.on('player:submit', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, error?: string): void => {
            if (typeof ack === 'function') {
                ack(ok ? { ok: true } : { ok: false, error: error ?? 'Unknown error' });
            }
        };

        // ── Validate payload shape ────────────────────────────────────────
        if (
            typeof payload !== 'object' ||
            payload === null ||
            typeof (payload as Record<string, unknown>)['roomCode'] !== 'string' ||
            !Array.isArray((payload as Record<string, unknown>)['answers'])
        ) {
            reply(false, 'Invalid payload: expected { roomCode, answers[] }');
            return;
        }

        const raw = payload as SubmitPayload;
        const roomCode = raw.roomCode.trim().toUpperCase();
        const answers = raw.answers;

        if (roomCode.length !== 4) {
            reply(false, 'Invalid room code');
            return;
        }

        // Validate each answer entry shape
        for (const a of answers) {
            if (
                typeof a !== 'object' || a === null ||
                typeof a.promptId !== 'string' ||
                typeof a.text !== 'string'
            ) {
                reply(false, 'Invalid answer entry: expected { promptId, text }');
                return;
            }
            if (a.text.trim().length === 0) {
                reply(false, 'All answers must be non-empty');
                return;
            }
            if (a.text.length > MAX_ANSWER_LENGTH) {
                reply(false, `Answer exceeds maximum length of ${MAX_ANSWER_LENGTH} characters`);
                return;
            }
        }

        // ── Require a joined player identity ──────────────────────────────
        const playerId = socket.data['playerId'] as string | undefined;
        if (playerId === undefined) {
            reply(false, 'You have not joined a room');
            return;
        }

        const db = getDb();

        // ── Room must exist and be in PROMPTING state ─────────────────────
        const room = getRoomByCode(db, roomCode);
        if (room === undefined) {
            reply(false, 'Room not found');
            return;
        }

        if (room.state !== 'PROMPTING') {
            reply(false, 'Submission window is closed — round is no longer in PROMPTING phase');
            return;
        }

        // ── Player must belong to this room ───────────────────────────────
        const player = getPlayerById(db, playerId);
        if (player === undefined || player.room_id !== room.id) {
            reply(false, 'Player not found in this room');
            return;
        }

        // ── Get active round ──────────────────────────────────────────────
        const round = getCurrentRound(db, room.id);
        if (round === undefined || round.state !== 'PROMPTING') {
            reply(false, 'No active PROMPTING round');
            return;
        }

        // ── Validate that submitted promptIds match assigned prompts ──────
        const assignments = getPromptAssignmentsByPlayer(db, round.id, playerId);
        const assignedIds = new Set(assignments.map((a) => a.prompt_id));

        if (assignedIds.size === 0) {
            reply(false, 'No prompts assigned to this player for the current round');
            return;
        }

        const submittedIds = new Set(answers.map((a) => a.promptId));

        // Every assigned prompt must be answered
        for (const id of assignedIds) {
            if (!submittedIds.has(id)) {
                reply(false, `Missing answer for prompt '${id}'`);
                return;
            }
        }

        // No extra / unrecognised prompt IDs allowed
        for (const id of submittedIds) {
            if (!assignedIds.has(id)) {
                reply(false, `Unrecognised prompt ID '${id}'`);
                return;
            }
        }

        // ── Persist answers ───────────────────────────────────────────────
        for (const { promptId, text } of answers) {
            upsertAnswer(db, round.id, playerId, promptId, text.trim(), true);
        }

        // ── Acknowledge success to the submitting player ──────────────────
        reply(true);

        // ── Notify host of submission progress (private — not room-wide) ──
        const activePlayers = getPlayersByRoom(db, room.id).filter((p) => p.active === 1);
        const submittedCount = countSubmittedPlayers(db, round.id);
        const totalCount = activePlayers.length;

        // Emit only to sockets in the room that are NOT the submitter.
        // The host socket has no playerId so it receives this; other players do not.
        socket.to(roomCode).emit('round:player_submitted', {
            playerId,
            nickname: player.nickname,
            submittedCount,
            totalCount,
        });

        // ── Auto-advance when all active players have submitted ───────────
        if (submittedCount >= totalCount && totalCount > 0) {
            if (isValidTransition(room.state, 'GENERATING')) {
                cancelPhaseTimer(roomCode);

                setRoomState(db, room.id, 'GENERATING');
                setRoundState(db, round.id, 'GENERATING');

                const eventName = stateToEvent('GENERATING');
                io.to(roomCode).emit(eventName, {
                    roundNumber: round.round_number,
                    state: 'GENERATING',
                    triggeredBy: 'all_submitted',
                });
            }
        }
    });
}