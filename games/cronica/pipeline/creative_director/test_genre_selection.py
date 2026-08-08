"""
M3.4 — Genre Selection Logic Tests

Run with:
  pytest games/cronica/pipeline/creative_director/test_genre_selection.py -v
"""

import pytest
from collections import Counter

from .genre_selection import (
    select_genre,
    compute_genre_weights,
    _BASE_WEIGHT,
    _RECENT_PENALTY,
    _RECENT_WINDOW,
)
from .genre_registry import GENRE_KEYS, list_genres, get_genre
from .models import PresentationFormat


class TestSelectGenreBasic:
    def test_returns_genre_definition(self):
        result = select_genre([])
        assert hasattr(result, "key")
        assert result.key in GENRE_KEYS

    def test_seeded_call_is_reproducible(self):
        result_a = select_genre([], seed=42)
        result_b = select_genre([], seed=42)
        assert result_a.key == result_b.key

    def test_different_seeds_may_differ(self):
        """With 7 genres the probability both land on the same key is ~1/7; repeat."""
        keys = {select_genre([], seed=s).key for s in range(20)}
        assert len(keys) > 1, "Different seeds should produce different genres"

    def test_no_recent_history_all_equal_weight(self):
        weights = compute_genre_weights([])
        assert all(w == _BASE_WEIGHT for w in weights.values())

    def test_single_recent_genre_is_penalised(self):
        recent = [GENRE_KEYS[0]]
        weights = compute_genre_weights(recent)
        assert weights[GENRE_KEYS[0]] == pytest.approx(_BASE_WEIGHT * _RECENT_PENALTY)
        for key in GENRE_KEYS[1:]:
            assert weights[key] == pytest.approx(_BASE_WEIGHT)

    def test_two_recent_genres_both_penalised(self):
        recent = GENRE_KEYS[:2]
        weights = compute_genre_weights(recent)
        for key in GENRE_KEYS[:2]:
            assert weights[key] == pytest.approx(_BASE_WEIGHT * _RECENT_PENALTY)
        for key in GENRE_KEYS[2:]:
            assert weights[key] == pytest.approx(_BASE_WEIGHT)

    def test_only_recent_window_penalised(self):
        """Genres beyond the window are not penalised even if present in history."""
        # History longer than _RECENT_WINDOW: slot [_RECENT_WINDOW] must NOT be penalised.
        long_history = GENRE_KEYS[:_RECENT_WINDOW + 2]
        weights = compute_genre_weights(long_history)
        beyond_window_key = long_history[_RECENT_WINDOW]
        assert weights[beyond_window_key] == pytest.approx(_BASE_WEIGHT)

    def test_empty_recent_history_accepted(self):
        result = select_genre([])
        assert result.key in GENRE_KEYS

    def test_full_recent_history_accepted(self):
        # All genres penalised — should still return a valid genre.
        result = select_genre(GENRE_KEYS, seed=1)
        assert result.key in GENRE_KEYS


class TestSelectGenreDistribution:
    def test_all_genres_appear_over_100_calls(self):
        """With 7 genres and base weights, all 7 must appear in 100 unconstrained calls."""
        seen = {select_genre([], seed=s).key for s in range(100)}
        assert seen == set(GENRE_KEYS), f"Missing genres: {set(GENRE_KEYS) - seen}"

    def test_penalised_genres_appear_less_often(self):
        """
        Over 200 seeded calls with the first genre always penalised,
        that genre should appear significantly less than 1/7 ≈ 28.6%.
        Expected share ≈ 0.1 / (0.1 + 6) ≈ 1.6%.
        We accept anything under 10% to avoid flakiness.
        """
        penalised_key = GENRE_KEYS[0]
        recent = [penalised_key]
        counts = Counter(
            select_genre(recent, seed=s).key for s in range(200)
        )
        share = counts[penalised_key] / 200
        assert share < 0.10, (
            f"Penalised genre '{penalised_key}' appeared {share:.1%} of the time "
            f"(expected < 10%)"
        )

    def test_non_penalised_genres_appear_more_often_than_penalised(self):
        penalised_key = GENRE_KEYS[0]
        non_penalised_key = GENRE_KEYS[1]
        recent = [penalised_key]
        counts = Counter(
            select_genre(recent, seed=s).key for s in range(200)
        )
        assert counts[non_penalised_key] > counts[penalised_key]

    def test_all_genres_appear_within_7_round_session(self):
        """
        Simulate 7 sequential rounds (each result becomes most-recent history).
        All 7 genres must appear within 7 * 10 = 70 independent session simulations.
        """
        genres_seen: set[str] = set()
        for session_seed in range(70):
            history: list[str] = []
            for round_offset in range(7):
                g = select_genre(history, seed=session_seed * 100 + round_offset)
                genres_seen.add(g.key)
                history.insert(0, g.key)  # Most recent first
        assert genres_seen == set(GENRE_KEYS), (
            f"Not all genres appeared across 70 sessions. Missing: {set(GENRE_KEYS) - genres_seen}"
        )


class TestComputeGenreWeights:
    def test_returns_all_genre_keys(self):
        weights = compute_genre_weights([])
        assert set(weights.keys()) == set(GENRE_KEYS)

    def test_all_values_positive(self):
        weights = compute_genre_weights(GENRE_KEYS)
        assert all(w > 0 for w in weights.values())

    def test_weight_values_match_expected(self):
        recent = GENRE_KEYS[:1]
        weights = compute_genre_weights(recent)
        assert weights[GENRE_KEYS[0]] == pytest.approx(_BASE_WEIGHT * _RECENT_PENALTY)
        assert weights[GENRE_KEYS[1]] == pytest.approx(_BASE_WEIGHT)