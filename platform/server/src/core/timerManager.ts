/**
 * Phase Timer Manager — M1.8
 */
import type { Server as SocketIOServer } from 'socket.io';
import {
    getDb,
    getRoomByCode,
    getCurrentRound,
    setRoomState,
    setRoundState,
    setRoundDeadline,
    getPlayersByRoom,
} from '../db/index.js';
import { isValidTransition, stateToEvent } from './roundStateMachine.js';
import type { RoomState } from '../db/types.js';

// ── Duration registry ───────────────────────────────────────────────────────

/**
 * Default phase durations in seconds.
 * Read lazily at call time so tests can override via _setDurationForTest().
 */
function getDefaultDurations(): Partial<Record<RoomState, number>> {
    return {
        PROMPTING: parseInt(process.env['PROMPTING_TIMER_SECS'] ?? '90', 10),
        VOTING: parseInt(process.env['VOTING_TIMER_SECS'] ?? '30', 10),
    };
}

// Override map populated only by _setDurationForTest().
const _testOverrides: Partial<Record<RoomState, number>> = {};

/**
 * Test-only: override the duration for a specific phase.
 * Call before startPhaseTimer. Persists for the lifetime of the process
 * unless overridden again.
 */
export function _setDurationForTest(phase: RoomState, seconds: number): void {
    _testOverrides[phase] = seconds;
}

function getDuration(phase: RoomState): number | undefined {
    if (_testOverrides[phase] !== undefined) return _testOverrides[phase];
    return getDefaultDurations()[phase];
}

/** Which state each timed phase advances to on expiry. */
const EXPIRY_TRANSITIONS: Partial<Record<RoomState, RoomState>> = {
    PROMPTING: 'GENERATING',
    VOTING: 'SCORING',
};

// ── Active timer tracking ───────────────────────────────────────────────────

interface ActiveTimer {
    intervalId: ReturnType<typeof setInterval>;
    deadlineMs: number;
    roomCode: string;
    phase: RoomState;
}

const activeTimers = new Map<string, ActiveTimer>();

let _io: SocketIOServer | null = null;

export function initTimerManager(io: SocketIOServer): void {
    _io = io;
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Returns true if the named phase has a configured duration.
 */
export function isTimedPhase(phase: RoomState): boolean {
    return getDuration(phase) !== undefined;
}

/**
 * Returns the duration for the given phase (seconds), or undefined if untimed.
 * Used by roundHandlers to compute the deadline timestamp for the broadcast.
 */
export function getPhaseDuration(phase: RoomState): number | undefined {
    return getDuration(phase);
}

/**
 * Starts a countdown timer for a timed phase.
 * Cancels any existing timer for the room first.
 * Persists the deadline in SQLite.
 */
export function startPhaseTimer(
    roomCode: string,
    phase: RoomState,
    roundId: number,
): void {
    if (_io === null) throw new Error('TimerManager not initialised — call initTimerManager first');

    const durationSecs = getDuration(phase);
    if (durationSecs === undefined) return;

    cancelPhaseTimer(roomCode);

    const io = _io;
    const nowMs = Date.now();
    const deadlineMs = nowMs + durationSecs * 1000;
    const deadlineEpochSec = Math.floor(deadlineMs / 1000);

    const db = getDb();
    const dbPhase = phase === 'PROMPTING' ? 'prompting' : 'voting';
    setRoundDeadline(db, roundId, dbPhase, deadlineEpochSec);

    const intervalId = setInterval(() => {
        const remaining = Math.ceil((deadlineMs - Date.now()) / 1000);

        if (remaining > 0) {
            io.to(roomCode).emit('timer:tick', {
                phase,
                remaining,
                deadline: deadlineEpochSec,
            });
        } else {
            cancelPhaseTimer(roomCode);
            _handleTimerExpiry(io, roomCode, phase);
        }
    }, 1000);

    activeTimers.set(roomCode, { intervalId, deadlineMs, roomCode, phase });
}

/**
 * Cancels the active timer for a room, if any.
 */
export function cancelPhaseTimer(roomCode: string): void {
    const existing = activeTimers.get(roomCode);
    if (existing !== undefined) {
        clearInterval(existing.intervalId);
        activeTimers.delete(roomCode);
    }
}

// ── Internal ────────────────────────────────────────────────────────────────

function _handleTimerExpiry(
    io: SocketIOServer,
    roomCode: string,
    phase: RoomState,
): void {
    const toState = EXPIRY_TRANSITIONS[phase];
    if (toState === undefined) return;

    const db = getDb();
    const room = getRoomByCode(db, roomCode);
    if (room === undefined) return;
    if (room.state !== phase) return;
    if (!isValidTransition(phase, toState)) return;

    const round = getCurrentRound(db, room.id);
    if (round === undefined) return;

    setRoomState(db, room.id, toState);
    setRoundState(db, round.id, toState);

    const eventName = stateToEvent(toState);
    const payload: Record<string, unknown> = {
        roundNumber: round.round_number,
        state: toState,
        triggeredBy: 'timer',
    };
    if (toState === 'PROMPTING' || toState === 'VOTING') {
        payload['deadline'] = null;
    }

    io.to(roomCode).emit(eventName, payload);
    io.to(roomCode).emit('timer:expired', { phase, advancedTo: toState });

    // M2.6 — On PROMPTING expiry, notify the room of partial submission status.
    // Players who didn't submit already have empty answer rows in SQLite (seeded
    // by assignPrompts). We emit a summary so the host knows who submitted.
    if (phase === 'PROMPTING') {
        _emitPartialSubmissions(io, roomCode, room.id, round.id);
    }
}

/**
 * Emits `round:partial_submissions` to all sockets in the room.
 * Payload lists every active player with a `submitted` boolean.
 * Players who never submitted have their rows with submitted=0 already
 * in SQLite from prompt assignment seeding.
 */
function _emitPartialSubmissions(
    io: SocketIOServer,
    roomCode: string,
    roomId: number,
    roundId: number,
): void {
    const db = getDb();

    const activePlayers = getPlayersByRoom(db, roomId).filter((p) => p.active === 1);

    // Build a set of playerIds that have at least one submitted=1 answer
    const submittedRows = db
        .prepare<[number], { player_id: string }>(
            `SELECT DISTINCT player_id FROM round_answers WHERE round_id = ? AND submitted = 1`,
        )
        .all(roundId);

    const submittedIds = new Set(submittedRows.map((r) => r.player_id));

    const playerStatuses = activePlayers.map((p) => ({
        playerId: p.id,
        nickname: p.nickname,
        submitted: submittedIds.has(p.id),
    }));

    const submittedCount = playerStatuses.filter((p) => p.submitted).length;
    const totalCount = playerStatuses.length;

    io.to(roomCode).emit('round:partial_submissions', {
        players: playerStatuses,
        submittedCount,
        totalCount,
        triggeredBy: 'timer_expiry',
    });
}