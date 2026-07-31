import Database from 'better-sqlite3';
import path from 'node:path';
import fs from 'node:fs';
import { SCHEMA_SQL } from './schema.js';

let _db: Database.Database | null = null;

/**
 * Returns the singleton better-sqlite3 instance.
 * Creates and migrates the database on first call.
 */
export function getDb(): Database.Database {
    if (_db) return _db;

    const dbPath = process.env['DB_PATH'] ?? path.resolve('agora.sqlite');
    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    _db = new Database(dbPath);

    // Apply schema (all statements are CREATE IF NOT EXISTS — safe to run every startup)
    _db.exec(SCHEMA_SQL);

    return _db;
}

/**
 * Closes the database connection. Call during graceful shutdown.
 */
export function closeDb(): void {
    _db?.close();
    _db = null;
}