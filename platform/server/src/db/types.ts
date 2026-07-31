/**
 * Row types that mirror the SQLite schema exactly.
 * Use these as return types from all query functions.
 */

export type RoomState =
    | 'WAITING'
    | 'PROMPTING'
    | 'GENERATING'
    | 'REVEALING'
    | 'VOTING'
    | 'SCORING'
    | 'GAME_OVER';

export type VoteCategory =
    | 'funniest_panel'
    | 'best_narrator_line'
    | 'best_portrayal';

export interface RoomRow {
    id: number;
    code: string;
    state: RoomState;
    round_count: number;
    safe_mode: 0 | 1;
    created_at: number;
}

export interface PlayerRow {
    id: string;
    room_id: number;
    nickname: string;
    active: 0 | 1;
    joined_at: number;
}

export interface RoundRow {
    id: number;
    room_id: number;
    round_number: number;
    state: RoomState;
    genre: string | null;
    started_at: number | null;
    ended_at: number | null;
    prompting_deadline: number | null;
    voting_deadline: number | null;
}

export interface RoundAnswerRow {
    id: number;
    round_id: number;
    player_id: string;
    prompt_id: string;
    answer: string;
    submitted: 0 | 1;
    created_at: number;
}

export interface VoteRow {
    id: number;
    round_id: number;
    voter_id: string;
    category: VoteCategory;
    target_id: string;
    created_at: number;
}