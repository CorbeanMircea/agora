/**
 * Prompt pack validation utility — M2.1
 *
 * Provides TypeScript types (re-exported from the platform interface) and a
 * runtime validation function that checks a prompt pack JSON object against
 * the schema defined in schema.json.
 *
 * Usage:
 *   import { validatePromptPack } from './validate.js';
 *   const result = validatePromptPack(json);
 *   if (!result.ok) console.error(result.errors);
 */

// Re-export the canonical types from the platform interface so game modules
// import from one place.
export type { PromptPack, PromptEntry } from '../../platform/server/src/interfaces/gameModule.js';

// ── Category ────────────────────────────────────────────────────────────────

/**
 * The 10 thematic categories a prompt may belong to.
 * Must match the enum in schema.json exactly.
 */
export const PROMPT_CATEGORIES = [
    'relatie',
    'munca',
    'familie',
    'situatie_absurda',
    'scandal_de_bloc',
    'decizie_proasta',
    'secret',
    'aventura',
    'ambitie',
    'infuntare',
] as const;

export type PromptCategory = (typeof PROMPT_CATEGORIES)[number];

// ── Validation result ────────────────────────────────────────────────────────

export type ValidationResult =
    | { ok: true }
    | { ok: false; errors: string[] };

// ── Runtime validator ────────────────────────────────────────────────────────

/**
 * Validates a raw JSON object against the PromptPack schema.
 *
 * This is a manual validator — no external schema library required so the
 * game module has zero extra runtime dependencies.
 */
export function validatePromptPack(data: unknown): ValidationResult {
    const errors: string[] = [];

    if (typeof data !== 'object' || data === null) {
        return { ok: false, errors: ['Root value must be an object'] };
    }

    const pack = data as Record<string, unknown>;

    // ── Top-level fields ──────────────────────────────────────────────────

    if (typeof pack['id'] !== 'string' || !/^[a-z0-9_]+$/.test(pack['id'])) {
        errors.push('id: must be a lowercase alphanumeric/underscore string');
    }
    if (typeof pack['name'] !== 'string' || pack['name'].length === 0) {
        errors.push('name: must be a non-empty string');
    }
    if (typeof pack['version'] !== 'string' || !/^\d+\.\d+\.\d+$/.test(pack['version'])) {
        errors.push('version: must be a semver string (e.g. "1.0.0")');
    }
    if (!Array.isArray(pack['prompts'])) {
        errors.push('prompts: must be an array');
        return { ok: false, errors };
    }
    if ((pack['prompts'] as unknown[]).length === 0) {
        errors.push('prompts: must contain at least one entry');
    }

    // ── Prompt entries ────────────────────────────────────────────────────

    const seenIds = new Set<string>();

    for (let i = 0; i < (pack['prompts'] as unknown[]).length; i++) {
        const entry = (pack['prompts'] as unknown[])[i];
        const prefix = `prompts[${i}]`;

        if (typeof entry !== 'object' || entry === null) {
            errors.push(`${prefix}: must be an object`);
            continue;
        }

        const p = entry as Record<string, unknown>;

        if (typeof p['id'] !== 'string' || !/^[a-z0-9_]+$/.test(p['id'])) {
            errors.push(`${prefix}.id: must be a lowercase alphanumeric/underscore string`);
        } else if (seenIds.has(p['id'] as string)) {
            errors.push(`${prefix}.id: duplicate id '${p['id'] as string}'`);
        } else {
            seenIds.add(p['id'] as string);
        }

        if (
            typeof p['text'] !== 'string' ||
            p['text'].length < 10 ||
            p['text'].length > 300
        ) {
            errors.push(`${prefix}.text: must be a string between 10 and 300 characters`);
        }

        if (
            typeof p['category'] !== 'string' ||
            !(PROMPT_CATEGORIES as readonly string[]).includes(p['category'])
        ) {
            errors.push(
                `${prefix}.category: must be one of: ${PROMPT_CATEGORIES.join(', ')}`,
            );
        }

        if (typeof p['safeMode'] !== 'boolean') {
            errors.push(`${prefix}.safeMode: must be a boolean`);
        }

        if (
            typeof p['minPlayers'] !== 'number' ||
            !Number.isInteger(p['minPlayers']) ||
            (p['minPlayers'] as number) < 2 ||
            (p['minPlayers'] as number) > 8
        ) {
            errors.push(`${prefix}.minPlayers: must be an integer between 2 and 8`);
        }
    }

    // ── Category coverage check ───────────────────────────────────────────

    if (Array.isArray(pack['prompts'])) {
        const categoriesPresent = new Set(
            (pack['prompts'] as Record<string, unknown>[])
                .map((p) => p['category'])
                .filter((c) => typeof c === 'string'),
        );
        for (const required of PROMPT_CATEGORIES) {
            if (!categoriesPresent.has(required)) {
                errors.push(`Missing required category: '${required}'`);
            }
        }
    }

    return errors.length === 0 ? { ok: true } : { ok: false, errors };
}