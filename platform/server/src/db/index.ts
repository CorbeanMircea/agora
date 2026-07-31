/**
 * Public API of the db module.
 * All other code imports from here — never from sub-files directly.
 */

export { getDb, closeDb } from './connection.js';
export type {
    RoomRow,
    PlayerRow,
    RoundRow,
    RoundAnswerRow,
    VoteRow,
    RoomState,
    VoteCategory,
} from './types.js';

export * from './queries/rooms.js';
export * from './queries/players.js';
export * from './queries/rounds.js';
export * from './queries/answers.js';
export * from './queries/votes.js';