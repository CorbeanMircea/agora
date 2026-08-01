/**
 * M1.7 — Round State Machine (Socket.IO handlers)
 *
 * Handles the `round:start` event (host → server).
 * Handles the `round:advance` event (host → server) for manual phase advancement.
 *
 * Events emitted to room:
 *   round:waiting    { roundNumber, state }
 *   round:prompting  { roundNumber, state, deadline: null }
 *   round:generating { roundNumber, state }
 *   round:revealing  { roundNumber, state }
 *   round:voting     { roundNumber, state, deadline: null }
 *   round:scoring    { roundNumber, state }
 *
 * The `deadline` field is null here — M1.8 (Phase Timers) will populate it.
 */
import type { Server, Socket } from 'socket.io';
import {
    getDb,
    getRoomByCode,
    getRoomById,
    setRoomState,
    createRound,
    getCurrentRound,
    setRoundState,
    incrementRoundCount,
} from '../db/index.js';
import { nextState, isValidTransition, stateToEvent } from '../core/roundStateMachine.js';
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
 */
function broadcastStateChange(
    io: Server,
    roomCode: string,
    state: RoomState,
    roundNumber: number,
): void {
    const eventName = stateToEvent(state);
    const payload: Record<string, unknown> = { roundNumber, state };

    // M1.8 will fill in deadlines; we emit null placeholders now so clients
    // can forward-compatibly handle the field.
    if (state === 'PROMPTING' || state === 'VOTING') {
        payload['deadline'] = null;
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
                ack(ok ? { ok: true, state } : { ok: false, error: error ?? 'Unknown error' });
            }
        };

        // Validate payload
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

        // Create the next round record
        const roundNumber = room.round_count + 1;
        const round = createRound(db, room.id, roundNumber);

        // Advance room + round state to PROMPTING
        setRoomState(db, room.id, 'PROMPTING');
        setRoundState(db, round.id, 'PROMPTING');
        incrementRoundCount(db, room.id);

        broadcastStateChange(io, roomCode, 'PROMPTING', roundNumber);
        reply(true, undefined, 'PROMPTING');
    });

    /**
     * round:advance
     * Advances the current round to a specific next state.
     * The requested `toState` must be the valid next state from current.
     * This allows the host (or future automated timers) to drive phase transitions.
     */
    socket.on('round:advance', (payload: unknown, ack?: AckFn) => {
        const reply = (ok: boolean, error?: string, state?: RoomState): void => {
            if (typeof ack === 'function') {
                ack(ok ? { ok: true, state } : { ok: false, error: error ?? 'Unknown error' });
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

        // Validate the requested transition
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

        // Persist state change
        setRoomState(db, room.id, toState);
        setRoundState(db, round.id, toState);

        // If cycling back to WAITING (end of scoring), we do NOT create a new
        // round — that happens on the next round:start. Just reset room state.
        broadcastStateChange(io, roomCode, toState, round.round_number);
        reply(true, undefined, toState);
    });
}