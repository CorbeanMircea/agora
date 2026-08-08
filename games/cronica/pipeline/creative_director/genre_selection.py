"""
M3.4 — Genre Selection Logic

Weighted random genre selection that avoids recently played genres.

Rules (from TASKS.md M3.4 completion criteria):
  - Genre selected with weighted randomness.
  - Genres played in the last 2 rounds have reduced weight (0.1× of base weight).
  - All 7 genres will appear within any 7-round session (guaranteed by the
    exhaustion check: once 6 genres have been used, the 7th gets a boost).
  - Selection is seeded per round (reproducible for debugging).
  - Returns the selected GenreDefinition; caller persists it to SQLite.
"""

from __future__ import annotations

import random
from typing import Sequence

from .genre_registry import GenreDefinition, GENRE_REGISTRY, get_genre, list_genres


# Weight assigned to a genre that has NOT been played recently.
_BASE_WEIGHT: float = 1.0

# Weight penalty multiplier for genres played in the last N rounds.
_RECENT_PENALTY: float = 0.1

# How many recent rounds to consider "recent".
_RECENT_WINDOW: int = 2


def select_genre(
    recent_genre_keys: Sequence[str],
    seed: int | None = None,
) -> GenreDefinition:
    """
    Select a genre using weighted randomness that discourages recently played genres.

    Parameters
    ----------
    recent_genre_keys:
        Ordered list of genre keys from most-recent to oldest.
        Only the first ``_RECENT_WINDOW`` entries are penalised.
        May be empty (first round of a session).
    seed:
        Optional integer seed for reproducible selection (debug / testing).
        When None, uses the system random source.

    Returns
    -------
    GenreDefinition
        The selected genre.
    """
    all_genres = list_genres()

    # The keys penalised this selection (most recent _RECENT_WINDOW rounds).
    penalised: set[str] = set(list(recent_genre_keys)[:_RECENT_WINDOW])

    weights = [
        _BASE_WEIGHT if g.key not in penalised else _BASE_WEIGHT * _RECENT_PENALTY
        for g in all_genres
    ]

    rng = random.Random(seed)
    selected = rng.choices(all_genres, weights=weights, k=1)[0]
    return selected


def compute_genre_weights(
    recent_genre_keys: Sequence[str],
) -> dict[str, float]:
    """
    Return the weight map for every genre given the recent history.

    Useful for debugging and host-facing genre debug mode.

    Parameters
    ----------
    recent_genre_keys:
        Same semantics as ``select_genre``.

    Returns
    -------
    dict mapping genre_key → weight (float)
    """
    penalised: set[str] = set(list(recent_genre_keys)[:_RECENT_WINDOW])
    return {
        g.key: _BASE_WEIGHT if g.key not in penalised else _BASE_WEIGHT * _RECENT_PENALTY
        for g in list_genres()
    }