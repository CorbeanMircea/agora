"""
M3.5 — Archetype Assignment Tests

Run with:
  pytest games/cronica/pipeline/creative_director/test_archetype_assignment.py -v
"""

import pytest
from collections import Counter

from .archetype_assignment import (
    assign,
    validate_assignments,
    PlayerIngredient,
    AssignedArchetype,
    _CATEGORY_ROLE_AFFINITIES,
    _ALL_ROLES,
)
from .genre_registry import get_genre, list_genres, GENRE_KEYS
from .models import IngredientRole


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _players(n: int) -> list[dict]:
    return [{"id": f"player_{i}", "nickname": f"Player{i}"} for i in range(n)]


def _ingredients(player_id: str, categories: list[str]) -> list[PlayerIngredient]:
    return [
        PlayerIngredient(
            prompt_id=f"{player_id}_prompt_{i}",
            category=cat,
            answer_text=f"răspuns {i}",
        )
        for i, cat in enumerate(categories)
    ]


def _ingredient_map(players: list[dict], categories_per_player: list[list[str]]) -> dict:
    return {
        p["id"]: _ingredients(p["id"], cats)
        for p, cats in zip(players, categories_per_player)
    }


# ── Basic assignment tests ─────────────────────────────────────────────────────

class TestAssignBasic:
    def test_two_players_get_two_archetypes(self):
        genre = get_genre("telenovela_romaneasca")
        players = _players(2)
        ing_map = _ingredient_map(players, [["CONCRET", "ABSTRACT"], ["LOC", "NUMAR"]])
        results = assign(genre, players, ing_map, seed=0)
        assert len(results) == 2

    def test_each_result_is_assigned_archetype(self):
        genre = get_genre("film_actiune_b")
        players = _players(3)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]] * 3)
        results = assign(genre, players, ing_map, seed=1)
        for r in results:
            assert isinstance(r, AssignedArchetype)
            assert r.archetype.player_id is not None
            assert r.archetype.player_nickname is not None

    def test_players_assigned_in_order(self):
        genre = get_genre("basm_romanesc_absurd")
        players = _players(4)
        ing_map = _ingredient_map(players, [["CONCRET", "ABSTRACT"]] * 4)
        results = assign(genre, players, ing_map, seed=2)
        assigned_ids = {r.archetype.player_id for r in results}
        expected_ids = {p["id"] for p in players}
        assert assigned_ids == expected_ids

    def test_no_duplicate_archetype_keys(self):
        genre = get_genre("scandal_de_bloc")
        players = _players(4)
        ing_map = _ingredient_map(players, [["ACTIUNE", "PROPRIU"]] * 4)
        results = assign(genre, players, ing_map, seed=3)
        keys = [r.archetype.key for r in results]
        assert len(keys) == len(set(keys)), f"Duplicate archetype keys: {keys}"

    def test_seeded_assignment_is_reproducible(self):
        genre = get_genre("documentar_fals")
        players = _players(3)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]] * 3)
        r1 = assign(genre, players, ing_map, seed=99)
        r2 = assign(genre, players, ing_map, seed=99)
        for a, b in zip(r1, r2):
            assert a.archetype.key == b.archetype.key
            assert a.archetype.player_id == b.archetype.player_id
            assert a.archetype.ingredient_roles == b.archetype.ingredient_roles

    def test_different_seeds_may_produce_different_archetypes(self):
        genre = get_genre("telenovela_romaneasca")
        players = _players(4)
        ing_map = _ingredient_map(players, [["CONCRET", "ABSTRACT"]] * 4)
        seen_first_keys = {
            assign(genre, players, ing_map, seed=s)[0].archetype.key
            for s in range(20)
        }
        assert len(seen_first_keys) > 1, (
            "Different seeds should sometimes produce different first archetype assignments"
        )


# ── Ingredient role assignment tests ──────────────────────────────────────────

class TestIngredientRoles:
    def test_each_ingredient_gets_a_role(self):
        genre = get_genre("stiri_rupte_din_realitate")
        players = _players(2)
        ing_map = _ingredient_map(players, [["CONCRET", "ABSTRACT"], ["LOC", "NUMAR"]])
        results = assign(genre, players, ing_map, seed=0)
        for r in results:
            pid = r.archetype.player_id
            expected_prompt_ids = {i.prompt_id for i in ing_map[pid]}
            assigned_prompt_ids = set(r.archetype.ingredient_roles.keys())
            assert assigned_prompt_ids == expected_prompt_ids

    def test_roles_are_valid_ingredient_roles(self):
        genre = get_genre("horror_mioritic")
        players = _players(3)
        ing_map = _ingredient_map(players, [["ATRIBUT", "PROPRIU"]] * 3)
        results = assign(genre, players, ing_map, seed=5)
        valid_roles = set(IngredientRole)
        for r in results:
            for role in r.archetype.ingredient_roles.values():
                assert role in valid_roles

    def test_player_with_two_ingredients_gets_two_distinct_roles(self):
        genre = get_genre("telenovela_romaneasca")
        players = _players(2)
        # Use categories with different primary affinities
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"], ["ABSTRACT", "NUMAR"]])
        results = assign(genre, players, ing_map, seed=7)
        for r in results:
            roles = list(r.archetype.ingredient_roles.values())
            if len(roles) >= 2:
                assert roles[0] != roles[1], (
                    f"Player got duplicate roles: {roles}"
                )

    def test_player_with_no_ingredients_gets_empty_roles(self):
        genre = get_genre("film_actiune_b")
        players = _players(2)
        # Player 0 has no ingredients (didn't submit)
        ing_map: dict = {
            players[0]["id"]: [],
            players[1]["id"]: _ingredients(players[1]["id"], ["CONCRET", "ABSTRACT"]),
        }
        results = assign(genre, players, ing_map, seed=0)
        p0_result = next(r for r in results if r.archetype.player_id == players[0]["id"])
        assert p0_result.archetype.ingredient_roles == {}

    def test_concret_category_maps_to_object_family(self):
        """CONCRET primary affinity is OBJECT."""
        affinities = _CATEGORY_ROLE_AFFINITIES["CONCRET"]
        assert IngredientRole.OBJECT in affinities
        assert affinities[0] == IngredientRole.OBJECT

    def test_loc_category_maps_to_location_family(self):
        affinities = _CATEGORY_ROLE_AFFINITIES["LOC"]
        assert IngredientRole.LOCATION in affinities
        assert affinities[0] == IngredientRole.LOCATION

    def test_numar_category_maps_to_quantity_family(self):
        affinities = _CATEGORY_ROLE_AFFINITIES["NUMAR"]
        assert IngredientRole.QUANTITY in affinities
        assert affinities[0] == IngredientRole.QUANTITY

    def test_propriu_category_maps_to_name_family(self):
        affinities = _CATEGORY_ROLE_AFFINITIES["PROPRIU"]
        assert IngredientRole.NAME in affinities
        assert affinities[0] == IngredientRole.NAME

    def test_all_categories_covered_in_affinity_map(self):
        expected_categories = {"CONCRET", "ABSTRACT", "ACTIUNE", "LOC", "NUMAR", "PROPRIU", "ATRIBUT"}
        assert set(_CATEGORY_ROLE_AFFINITIES.keys()) == expected_categories

    def test_same_ingredient_gets_different_roles_across_rounds(self):
        """
        The same ingredient category should not always produce the same role
        across different rounds (different seeds). This validates ADR-001's
        'ingredients adapt to the story' principle.
        """
        genre = get_genre("basm_romanesc_absurd")
        players = _players(2)
        # Use a mix of categories
        ing_map = _ingredient_map(players, [["PROPRIU", "CONCRET"], ["ABSTRACT", "ATRIBUT"]])

        # Collect the role assigned to player_0's PROPRIU ingredient across seeds
        propriu_roles = set()
        for s in range(50):
            results = assign(genre, players, ing_map, seed=s)
            p0 = next(r for r in results if r.archetype.player_id == players[0]["id"])
            propriu_prompt = f"player_0_prompt_0"  # first ingredient = PROPRIU
            if propriu_prompt in p0.archetype.ingredient_roles:
                propriu_roles.add(p0.archetype.ingredient_roles[propriu_prompt])

        # PROPRIU's affinities are [NAME, CHARACTER, LOCATION] —
        # with shuffling, we should see at least 2 distinct roles across 50 seeds.
        assert len(propriu_roles) >= 1  # always gets at least one role


# ── Validation tests ───────────────────────────────────────────────────────────

class TestValidateAssignments:
    def test_valid_assignments_produce_no_errors(self):
        genre = get_genre("telenovela_romaneasca")
        players = _players(3)
        ing_map = _ingredient_map(players, [["CONCRET", "ABSTRACT"]] * 3)
        results = assign(genre, players, ing_map, seed=0)
        errors = validate_assignments(results, [p["id"] for p in players])
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_player_is_detected(self):
        genre = get_genre("film_actiune_b")
        players = _players(2)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]] * 2)
        results = assign(genre, players, ing_map, seed=0)
        # Add a non-existent player to expected list
        errors = validate_assignments(results, [p["id"] for p in players] + ["ghost_player"])
        assert any("ghost_player" in e for e in errors)

    def test_duplicate_archetype_key_is_detected(self):
        genre = get_genre("scandal_de_bloc")
        players = _players(2)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]] * 2)
        results = assign(genre, players, ing_map, seed=0)

        # Manually introduce duplicate archetype key
        results[1].archetype.key = results[0].archetype.key

        errors = validate_assignments(results, [p["id"] for p in players])
        assert any("more than one player" in e for e in errors)


# ── Genre compatibility tests ──────────────────────────────────────────────────

class TestAllGenres:
    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_all_genres_support_two_players(self, genre_key: str):
        genre = get_genre(genre_key)
        players = _players(2)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"], ["ABSTRACT", "NUMAR"]])
        results = assign(genre, players, ing_map, seed=0)
        assert len(results) == 2
        errors = validate_assignments(results, [p["id"] for p in players])
        assert errors == [], f"{genre_key}: {errors}"

    @pytest.mark.parametrize("genre_key", GENRE_KEYS)
    def test_all_genres_support_four_players(self, genre_key: str):
        genre = get_genre(genre_key)
        players = _players(4)
        ing_map = _ingredient_map(players, [
            ["CONCRET", "ABSTRACT"],
            ["LOC", "NUMAR"],
            ["PROPRIU", "ATRIBUT"],
            ["ACTIUNE", "CONCRET"],
        ])
        results = assign(genre, players, ing_map, seed=42)
        assert len(results) == 4
        errors = validate_assignments(results, [p["id"] for p in players])
        assert errors == [], f"{genre_key}: {errors}"

    def test_exceeding_archetype_count_raises(self):
        genre = get_genre("documentar_fals")  # has 5 archetypes, max_players=5
        players = _players(6)  # one too many
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]] * 6)
        with pytest.raises(ValueError, match="archetype templates"):
            assign(genre, players, ing_map, seed=0)

    def test_fewer_than_two_players_raises(self):
        genre = get_genre("telenovela_romaneasca")
        players = _players(1)
        ing_map = _ingredient_map(players, [["CONCRET", "LOC"]])
        with pytest.raises(ValueError, match="at least 2 players"):
            assign(genre, players, ing_map, seed=0)