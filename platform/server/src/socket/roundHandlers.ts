/**
 * M1.7 — Round State Machine (Socket.IO handlers)
 * M1.8 — Phase Timers integrated: timed phases start/cancel timers and
 *         populate the `deadline` field in their broadcast events.
 *
 * Handles:
 *   round:start   — host → server: start a new round (WAITING → PROMPTING)
 *   round:advance — host → server: manually advance phase
 *
 * Events emitted to room:
 *   round:waiting    { roundNumber, state }
 *   round:prompting  { roundNumber, state, deadline: number (epoch sec) | null }
 *   round:generating { roundNumber, state }
 *   round:revealing  { roundNumber, state }
 *   round:voting     { roundNumber, state, deadline: number (epoch sec) | null }
 *   round:scoring    { roundNumber, state }
 *   timer:tick       { phase, remaining, deadline }   — every second while timed phase active
 *   timer:expired    { phase, advancedTo }             — when timer fires
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
} from '../db/index.js';
import { nextState, isValidTransition, stateToEvent } from '../core/roundStateMachine.js';
import {
    startPhaseTimer,
    cancelPhaseTimer,
    isTimedPhase,
    getPhaseDuration,
} from '../core/timerManager.js';
import type { RoomState } from '../db/types.js';

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

/**
 * Broadcast a state-change event to every socket in the room channel.
 * If the new state is a timed phase, starts a timer and includes the deadline.
 */
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
        // Compute deadline the same way startPhaseTimer does — at call time.
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
    /**
     * round:start
     * Creates a new round and transitions from WAITING → PROMPTING.
     * Only valid when the room is in WAITING state.
     */
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

        broadcastStateChange(io, roomCode, 'PROMPTING', roundNumber, round.id);
        reply(true, undefined, 'PROMPTING');
    });

    /**
     * round:advance
     * Advances the current round to a specific next state.
     * Cancels any active timer before advancing.
     */
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

        // Cancel any active timer before persisting the new state.
        cancelPhaseTimer(roomCode);

        setRoomState(db, room.id, toState);
        setRoundState(db, round.id, toState);

        broadcastStateChange(io, roomCode, toState, round.round_number, round.id);
        reply(true, undefined, toState);
    });
}