/**
 * Round State Machine — M1.7
 *
 * Defines the valid state transitions for a round and enforces them.
 * States: WAITING → PROMPTING → GENERATING → REVEALING → VOTING → SCORING → WAITING
 *
 * This module is pure logic — no I/O, no Socket.IO, no DB.
 * All persistence and broadcasting is done by the caller.
 */
import type { RoomState } from '../db/types.js';

/**
 * The ordered list of states a round passes through.
 * GAME_OVER is a terminal state handled separately at the room level.
 */
export const ROUND_STATES: RoomState[] = [
    'WAITING',
    'PROMPTING',
    'GENERATING',
    'REVEALING',
    'VOTING',
    'SCORING',
];

/**
 * Valid transitions map.
 * Each key is the current state; the value is the only valid next state.
 */
const TRANSITIONS: Partial<Record<RoomState, RoomState>> = {
    WAITING: 'PROMPTING',
    PROMPTING: 'GENERATING',
    GENERATING: 'REVEALING',
    REVEALING: 'VOTING',
    VOTING: 'SCORING',
    SCORING: 'WAITING',
};

export type TransitionResult =
    | { ok: true; nextState: RoomState }
    | { ok: false; error: string };

/**
 * Returns the next valid state from `current`, or an error if the transition
 * is not permitted.
 */
export function nextState(current: RoomState): TransitionResult {
    const next = TRANSITIONS[current];
    if (next === undefined) {
        return {
            ok: false,
            error: `No valid transition from state '${current}'`,
        };
    }
    return { ok: true, nextState: next };
}

/**
 * Returns true if `from → to` is a valid transition.
 */
export function isValidTransition(from: RoomState, to: RoomState): boolean {
    return TRANSITIONS[from] === to;
}

/**
 * Returns the Socket.IO event name emitted when entering a state.
 * Defined by GDD Section 9.2.
 */
export function stateToEvent(state: RoomState): string {
    const map: Record<RoomState, string> = {
        WAITING: 'round:waiting',
        PROMPTING: 'round:prompting',
        GENERATING: 'round:generating',
        REVEALING: 'round:revealing',
        VOTING: 'round:voting',
        SCORING: 'round:scoring',
        GAME_OVER: 'round:game_over',
    };
    return map[state];
}