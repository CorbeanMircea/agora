export type { PromptPack, PromptEntry } from '../../platform/server/src/interfaces/gameModule.js';

/**
 * The 7 semantic ingredient categories.
 * These replace the old narrative categories.
 */
export const PROMPT_CATEGORIES = [
    'CONCRET',
    'ABSTRACT',
    'ACTIUNE',
    'LOC',
    'NUMAR',
    'PROPRIU',
    'ATRIBUT',
] as const;

export type PromptCategory = (typeof PROMPT_CATEGORIES)[number];

export type ValidationResult =
    | { ok: true }
    | { ok: false; errors: string[] };

export function validatePromptPack(data: unknown): ValidationResult {
    const errors: string[] = [];

    if (typeof data !== 'object' || data === null) {
        return { ok: false, errors: ['Root value must be an object'] };
    }

    const pack = data as Record<string, unknown>;

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

    // Every category must have at least 3 questions (ensures rotation variety)
    if (Array.isArray(pack['prompts'])) {
        const countPerCategory = new Map<string, number>();
        for (const cat of PROMPT_CATEGORIES) countPerCategory.set(cat, 0);

        for (const p of pack['prompts'] as Record<string, unknown>[]) {
            if (typeof p['category'] === 'string' && countPerCategory.has(p['category'])) {
                countPerCategory.set(p['category'], (countPerCategory.get(p['category']) ?? 0) + 1);
            }
        }

        for (const [cat, count] of countPerCategory) {
            if (count < 3) {
                errors.push(`Category '${cat}' has only ${count} question(s) — minimum 3 required for rotation`);
            }
        }
    }

    return errors.length === 0 ? { ok: true } : { ok: false, errors };
}