/**
 * M1.7 — Round State Machine (Socket.IO handlers)
 * M1.8 — Phase Timers integrated.
 * M2.2 — Prompt assignment triggered on round:start.
 *
 * Handles:
 *   round:start   — host → server: start a new round (WAITING → PROMPTING)
 *   round:advance — host → server: manually advance phase
 */
import type { Server, Socket } from 'socket.io';
import {
    getDb,
    getRoomByCode,
    setRoomState,
    createRound,
    getCurrentRound,
    setRoundState,
    incrementRoundCount,
    getPlayersByRoom,
} from '../db/index.js';
import { nextState, isValidTransition, stateToEvent } from '../core/roundStateMachine.js';
import {
    startPhaseTimer,
    cancelPhaseTimer,
    isTimedPhase,
    getPhaseDuration,
} from '../core/timerManager.js';
import { assignPrompts } from '../core/promptAssignment.js';
import type { RoomState } from '../db/types.js';

// ── Prompt pack (loaded once) ───────────────────────────────────────────────

import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

// eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
const CRONICA_PACK = require('../../../../games/cronica/prompts/cronica_base.json');

// ── Types ──────────────────────────────────────────────────────────────────

interface StartPayload {
    roomCode: string;
}

interface AdvancePayload {
    roomCode: string;
    toState: RoomState;
}

type AckFn = (result: { ok: boolean; error?: string; state?: RoomState }) => void;

// ── Helpers ────────────────────────────────────────────────────────────────

function broadcastStateChange(
    io: Server,
    roomCode: string,
    state: RoomState,
    roundNumber: number,
    roundId: number,
): void {
    const eventName = stateToEvent(state);
    const payload: Record<string, unknown> = { roundNumber, state };

    if (isTimedPhase(state)) {
        startPhaseTimer(roomCode, state, roundId);
        const durationSecs = getPhaseDuration(state) ?? 0;
        payload['deadline'] = Math.floor(Date.now() / 1000) + durationSecs;
    } else {
        cancelPhaseTimer(roomCode);
        if (state === 'PROMPTING' || state === 'VOTING') {
            payload['deadline'] = null;
        }
    }

    io.to(roomCode).emit(eventName, payload);
}

// ── Handler registration ───────────────────────────────────────────────────

export function registerRoundHandlers(io: Server, socket: Socket): void {
    socket.on('round:start', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, error?: string, state?: RoomState): void => {
            if (typeof ack === 'function') {
                if (ok) {
                    ack(state !== undefined ? { ok: true, state } : { ok: true });
                } else {
                    ack({ ok: false, error: error ?? 'Unknown error' });
                }
            }
        };

        if (
            typeof payload !== 'object' ||
            payload === null ||
            typeof (payload as Record<string, unknown>)['roomCode'] !== 'string'
        ) {
            reply(false, 'Invalid payload: expected { roomCode }');
            return;
        }

        const roomCode = (payload as StartPayload).roomCode.trim().toUpperCase();

        if (roomCode.length !== 4) {
            reply(false, 'Invalid room code');
            return;
        }

        const db = getDb();
        const room = getRoomByCode(db, roomCode);

        if (room === undefined) {
            reply(false, 'Room not found');
            return;
        }

        if (room.state !== 'WAITING') {
            reply(false, `Cannot start round from state '${room.state}' — room must be WAITING`);
            return;
        }

        const roundNumber = room.round_count + 1;
        const round = createRound(db, room.id, roundNumber);

        setRoomState(db, room.id, 'PROMPTING');
        setRoundState(db, round.id, 'PROMPTING');
        incrementRoundCount(db, room.id);

        // ── M2.2: Assign prompts to all active players ──────────────────────
        const activePlayers = getPlayersByRoom(db, room.id)
            .filter((p) => p.active === 1)
            .map((p) => ({ id: p.id, nickname: p.nickname }));

        const safeMode = room.safe_mode === 1;

        try {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-argument
            assignPrompts(db, CRONICA_PACK, round.id, activePlayers, safeMode);
        } catch (err) {
            // Log but do not block the round — prompts are a best-effort in M2.2.
            // M2.3 (delivery) will handle the case of empty assignments gracefully.
            socket.log?.warn?.(
                { err },
                'Prompt assignment failed — round will proceed without prompts',
            );
        }
        // ───────────────────────────────────────────────────────────────────

        broadcastStateChange(io, roomCode, 'PROMPTING', roundNumber, round.id);
        reply(true, undefined, 'PROMPTING');
    });

    socket.on('round:advance', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, error?: string, state?: RoomState): void => {
            if (typeof ack === 'function') {
                if (ok) {
                    ack(state !== undefined ? { ok: true, state } : { ok: true });
                } else {
                    ack({ ok: false, error: error ?? 'Unknown error' });
                }
            }
        };

        if (
            typeof payload !== 'object' ||
            payload === null ||
            typeof (payload as Record<string, unknown>)['roomCode'] !== 'string' ||
            typeof (payload as Record<string, unknown>)['toState'] !== 'string'
        ) {
            reply(false, 'Invalid payload: expected { roomCode, toState }');
            return;
        }

        const { roomCode: rawCode, toState } = payload as AdvancePayload;
        const roomCode = rawCode.trim().toUpperCase();

        const db = getDb();
        const room = getRoomByCode(db, roomCode);

        if (room === undefined) {
            reply(false, 'Room not found');
            return;
        }

        if (!isValidTransition(room.state, toState)) {
            const transition = nextState(room.state);
            const expected = transition.ok ? transition.nextState : '(none)';
            reply(
                false,
                `Invalid transition: '${room.state}' → '${toState}'. Expected next state: '${expected}'`,
            );
            return;
        }

        const round = getCurrentRound(db, room.id);
        if (round === undefined) {
            reply(false, 'No active round found');
            return;
        }

        cancelPhaseTimer(roomCode);

        setRoomState(db, room.id, toState);
        setRoundState(db, round.id, toState);

        broadcastStateChange(io, roomCode, toState, round.round_number, round.id);
        reply(true, undefined, toState);
    });
}