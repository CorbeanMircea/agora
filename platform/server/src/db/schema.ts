/**
 * AGORA Platform – SQLite schema
 * All DDL lives here. Executed via connection.ts on startup.
 */

export const SCHEMA_SQL = /* sql */ `
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  -- ------------------------------------------------------------------ rooms
  CREATE TABLE IF NOT EXISTS rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    state       TEXT    NOT NULL DEFAULT 'WAITING',
    round_count INTEGER NOT NULL DEFAULT 0,
    safe_mode   INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch())
  );

  -- ----------------------------------------------------------------- players
  CREATE TABLE IF NOT EXISTS players (
    id          TEXT    PRIMARY KEY,
    room_id     INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    nickname    TEXT    NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    joined_at   INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (room_id, nickname)
  );

  -- ------------------------------------------------------------------ rounds
  CREATE TABLE IF NOT EXISTS rounds (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id            INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    round_number       INTEGER NOT NULL,
    state              TEXT    NOT NULL DEFAULT 'WAITING',
    genre              TEXT,
    started_at         INTEGER,
    ended_at           INTEGER,
    prompting_deadline INTEGER,
    voting_deadline    INTEGER,
    UNIQUE (room_id, round_number)
  );

  -- ------------------------------------------------------------ round_answers
  CREATE TABLE IF NOT EXISTS round_answers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id   INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    player_id  TEXT    NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    prompt_id  TEXT    NOT NULL,
    answer     TEXT    NOT NULL DEFAULT '',
    submitted  INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (round_id, player_id, prompt_id)
  );

  -- ------------------------------------------------------------------- votes
  CREATE TABLE IF NOT EXISTS votes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id   INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    voter_id   TEXT    NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    category   TEXT    NOT NULL,
    target_id  TEXT    NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (round_id, voter_id, category)
  );

  CREATE INDEX IF NOT EXISTS idx_players_room   ON players(room_id);
  CREATE INDEX IF NOT EXISTS idx_rounds_room    ON rounds(room_id);
  CREATE INDEX IF NOT EXISTS idx_answers_round  ON round_answers(round_id);
  CREATE INDEX IF NOT EXISTS idx_answers_player ON round_answers(player_id);
  CREATE INDEX IF NOT EXISTS idx_votes_round    ON votes(round_id);
  CREATE INDEX IF NOT EXISTS idx_votes_voter    ON votes(voter_id);
`;