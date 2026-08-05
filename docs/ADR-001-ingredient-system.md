# ADR-001: Ingredient System (replaces narrative prompt pack)

**Date:** 2026-08-05  
**Status:** Accepted  
**Supersedes:** GDD v0.2.1 Section 4.2 (Prompt Categories)

## Decision

Replace the narrative prompt system (Mad Libs-style sentence completion) with
a semantic Ingredient System where players answer generic questions that collect
raw creative material without hinting at the story.

## Motivation

The original prompt pack (cronica_base.json v1.0.0) used narrative questions
like "Descrie momentul în care [PLAYER] a intrat în lift cu fostul său șef."
These revealed story structure before generation, making outcomes predictable
and reducing the reveal surprise — the core emotional payoff of CRONICĂ.

## New Design

Players answer 2 questions per round from 7 semantic categories:

| Category | Collects |
|---|---|
| CONCRET | A physical object or creature |
| ABSTRACT | An emotion, concept, or quality |
| ACTIUNE | A verb or action |
| LOC | A place, real or imagined |
| NUMAR | A number or quantity |
| PROPRIU | A name, brand, or title |
| ATRIBUT | An adjective or descriptor |

Questions never reference plot, characters, conflict, genre, or ending.

## Ingredient Role Assignment (Creative Director)

The Creative Director assigns each ingredient a structural narrative role
*after* all answers are collected and *after* genre selection. The same
ingredient can fulfill completely different roles across playthroughs:

- "crocodil" → villain, pet, lawyer, restaurant name, spaceship name, password
- "birocrație" → protagonist's motivation, obstacle, theme, or MacGuffin

Ingredients adapt to the story. The story does not adapt to the ingredients.

## Impact on existing tasks

| Task | Change |
|---|---|
| M2.1 | Prompt pack reformatted to ingredient questions (done) |
| M2.2 | Assignment engine uses semantic diversity instead of narrative variety (done) |
| M3.5 | Archetype assignment must also assign IngredientRole per answer |
| M4.5 | LLM prompt receives ingredients with roles, not as a bare list |

## Files changed

- `games/cronica/prompts/cronica_base.json` (v1.0.0 → v2.0.0)
- `games/cronica/prompts/schema.json`
- `games/cronica/prompts/validate.ts`
- `platform/server/src/core/promptAssignment.ts`
- `platform/server/src/core/promptAssignment.test.ts`
- `platform/phone-shell/src/routes/answer/+page.svelte`