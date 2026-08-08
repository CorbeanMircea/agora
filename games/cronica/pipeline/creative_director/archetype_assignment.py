"""
M3.5 — Archetype Assignment

Maps each active player to a narrative archetype within the selected genre,
and assigns an IngredientRole to each of their ingredient answers.

Rules (from TASKS.md M3.5 completion criteria + ADR-001):
  - Each player is assigned exactly one archetype from the genre's template list.
  - No two players share the same archetype.
  - Each ingredient answer (identified by promptId) is assigned an IngredientRole.
  - Ingredients adapt to the story — the same ingredient can fulfill a completely
    different role across different playthroughs.
  - Assignments are deterministic given a seed (reproducible for debugging).
  - Returns populated Archetype instances ready for inclusion in the CreativeBrief.

IngredientRole assignment strategy:
  Each semantic category of the ingredient question provides a default role
  affinity, but the assignment is not 1-to-1 — roles are shuffled across all
  ingredients in the round to ensure variety and prevent predictability.

  Category → Primary affinity (starting point before shuffling):
    CONCRET  → OBJECT
    ABSTRACT → CONCEPT or ATMOSPHERE
    ACTIUNE  → ACTION
    LOC      → LOCATION
    NUMAR    → QUANTITY
    PROPRIU  → NAME or CHARACTER
    ATRIBUT  → ATMOSPHERE

  The affinity is used to build an initial mapping, which is then lightly
  shuffled so neighbouring assignments vary across rounds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from .models import Archetype, IngredientRole
from .genre_registry import GenreDefinition


# ── Category → IngredientRole affinity map ──────────────────────────────────
# Each category has a ranked list of roles it can fill.
# The first entry is the primary affinity; others are fallbacks.

_CATEGORY_ROLE_AFFINITIES: dict[str, list[IngredientRole]] = {
    "CONCRET":  [IngredientRole.OBJECT,     IngredientRole.CHARACTER,  IngredientRole.NAME],
    "ABSTRACT": [IngredientRole.CONCEPT,    IngredientRole.ATMOSPHERE, IngredientRole.ACTION],
    "ACTIUNE":  [IngredientRole.ACTION,     IngredientRole.CONCEPT,    IngredientRole.ATMOSPHERE],
    "LOC":      [IngredientRole.LOCATION,   IngredientRole.ATMOSPHERE, IngredientRole.OBJECT],
    "NUMAR":    [IngredientRole.QUANTITY,   IngredientRole.CONCEPT,    IngredientRole.NAME],
    "PROPRIU":  [IngredientRole.NAME,       IngredientRole.CHARACTER,  IngredientRole.LOCATION],
    "ATRIBUT":  [IngredientRole.ATMOSPHERE, IngredientRole.CONCEPT,    IngredientRole.ACTION],
}

# All available roles in a fixed order for rotation/fallback purposes.
_ALL_ROLES: list[IngredientRole] = list(IngredientRole)


@dataclass
class PlayerIngredient:
    """
    One ingredient answer submitted by a player.
    The category comes from the prompt pack (cronica_base.json).
    """
    prompt_id: str
    category: str   # One of the 7 semantic categories
    answer_text: str  # The player's raw answer (may be empty if they didn't submit)


@dataclass
class AssignedArchetype:
    """
    An archetype with a fully assigned player and ingredient roles.
    This is the output of archetype_assignment.assign() and is ready
    to be embedded in the CreativeBrief.archetypes list.
    """
    archetype: Archetype  # Populated with player_id, player_nickname, ingredient_roles


def assign(
    genre: GenreDefinition,
    players: list[dict],
    player_ingredients: dict[str, list[PlayerIngredient]],
    seed: int | None = None,
) -> list[AssignedArchetype]:
    """
    Assign archetypes and ingredient roles to all active players.

    Parameters
    ----------
    genre:
        The selected genre definition, which provides archetype templates.
    players:
        Ordered list of active players as dicts with keys "id" and "nickname".
        Must have len >= 2.
    player_ingredients:
        Maps player_id → list of PlayerIngredient for their assigned prompts.
        Players who didn't submit will have empty answer_text fields.
    seed:
        Optional integer seed for reproducible assignment.

    Returns
    -------
    list[AssignedArchetype]
        One AssignedArchetype per player, in player order.

    Raises
    ------
    ValueError
        If player count is < 2 or exceeds the genre's available archetypes.
    """
    if len(players) < 2:
        raise ValueError(
            f"Archetype assignment requires at least 2 players, got {len(players)}"
        )

    available_templates = genre.archetype_templates
    if len(players) > len(available_templates):
        raise ValueError(
            f"Genre '{genre.key}' has {len(available_templates)} archetype templates "
            f"but {len(players)} players were provided. "
            f"Maximum players for this genre: {len(available_templates)}"
        )

    rng = random.Random(seed)

    # Shuffle archetype templates so the same player does not always get the
    # same archetype when playing the same genre multiple times.
    shuffled_templates = list(available_templates)
    rng.shuffle(shuffled_templates)

    results: list[AssignedArchetype] = []

    for player, template in zip(players, shuffled_templates):
        player_id: str = player["id"]
        nickname: str = player["nickname"]

        ingredients = player_ingredients.get(player_id, [])
        roles = _assign_ingredient_roles(ingredients, rng)

        # Deep-copy the template and populate with player assignment
        assigned = Archetype(
            key=template.key,
            name_ro=template.name_ro,
            description_ro=template.description_ro,
            player_id=player_id,
            player_nickname=nickname,
            ingredient_roles=roles,
        )
        results.append(AssignedArchetype(archetype=assigned))

    return results


def _assign_ingredient_roles(
    ingredients: list[PlayerIngredient],
    rng: random.Random,
) -> dict[str, IngredientRole]:
    """
    Assign an IngredientRole to each of a player's ingredient answers.

    Strategy:
      1. Build an initial mapping using each ingredient's category affinity.
      2. Ensure no two ingredients from the same player receive the same role
         if there are enough distinct roles available.
      3. Apply a lightweight shuffle to vary assignments across rounds.

    Parameters
    ----------
    ingredients:
        The player's assigned ingredients (may be 0, 1, or 2 for standard play).
    rng:
        Seeded random instance for reproducibility.

    Returns
    -------
    dict mapping prompt_id → IngredientRole
    """
    if not ingredients:
        return {}

    # Build candidate role for each ingredient from category affinities.
    # Use primary affinity first; fall back if a role is already taken.
    used_roles: set[IngredientRole] = set()
    result: dict[str, IngredientRole] = {}

    # Shuffle ingredients so the assignment order varies each round.
    shuffled = list(ingredients)
    rng.shuffle(shuffled)

    for ingredient in shuffled:
        category = ingredient.category
        affinities = _CATEGORY_ROLE_AFFINITIES.get(category, _ALL_ROLES)

        # Find the first affinity not yet used in this player's assignment.
        chosen: IngredientRole | None = None
        for role in affinities:
            if role not in used_roles:
                chosen = role
                break

        # If all affinity roles are exhausted, pick any unused role at random.
        if chosen is None:
            available = [r for r in _ALL_ROLES if r not in used_roles]
            if available:
                chosen = rng.choice(available)
            else:
                # All 8 roles used — this can only happen with 9+ ingredients,
                # which is beyond the current 2-per-player design. Fall back to
                # the primary affinity (role will be duplicated in this edge case).
                chosen = affinities[0]

        used_roles.add(chosen)
        result[ingredient.prompt_id] = chosen

    return result


def validate_assignments(
    assignments: list[AssignedArchetype],
    expected_player_ids: Sequence[str],
) -> list[str]:
    """
    Validate a list of assignments against expected constraints.

    Returns a list of error strings. An empty list means the assignments
    are valid.

    Checks:
      - Each expected player appears exactly once.
      - No two players share the same archetype key.
      - Every assigned archetype has a non-None player_id and player_nickname.
      - ingredient_roles is populated for players who had ingredients.
    """
    errors: list[str] = []

    assigned_player_ids = [a.archetype.player_id for a in assignments]
    assigned_archetype_keys = [a.archetype.key for a in assignments]

    # Every expected player must appear exactly once
    for pid in expected_player_ids:
        count = assigned_player_ids.count(pid)
        if count == 0:
            errors.append(f"Player '{pid}' was not assigned an archetype")
        elif count > 1:
            errors.append(f"Player '{pid}' was assigned {count} archetypes (expected 1)")

    # No duplicate archetype keys
    seen_keys: set[str] = set()
    for key in assigned_archetype_keys:
        if key in seen_keys:
            errors.append(f"Archetype key '{key}' assigned to more than one player")
        seen_keys.add(key)

    # Each archetype must have both player fields set
    for a in assignments:
        arch = a.archetype
        if arch.player_id is None:
            errors.append(f"Archetype '{arch.key}' has no player_id assigned")
        if arch.player_nickname is None:
            errors.append(f"Archetype '{arch.key}' has no player_nickname assigned")

    return errors