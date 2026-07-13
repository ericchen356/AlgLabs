"""T17: trainer engine + endpoints (CONTRACTS.md §11.5).

Coverage per §11.5: every OLL/PLL/COLL case, every VLS case, and >=60 sampled
ZBLL cases get seeded draws checking that

(a) applying ``scramble`` to solved lands in the requested case's class
    (re-canonicalized key comparison),
(b) ``solution`` replays the state to solved,
(c) among 4 draws of one case at least 2 distinct scrambles exist,
(d) enumeration counts equal the frozen constants,
(e) ids are stable — golden snapshot of (id -> canonical key) per set,
(f) endpoints: happy path per set, unknown set/case -> 400, case_id targeting.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from cube.facelet import CubieState, is_solved
from cube.moves import MOVE_TOKENS, apply_moves
from solver import trainer

client = TestClient(app)

GOLDEN_PATH = Path(__file__).parent / "golden_trainer_ids.json"

#: Deterministic per-case sampling of ZBLL (>=60 cases per §11.5), spread
#: over every OCLL group by striding the ordered case list.
ZBLL_SAMPLE = trainer.CASES["zbll"][::8]
assert len(ZBLL_SAMPLE) >= 60

DRAWS_PER_CASE = 4  # 3 for (a)/(b) per §11.5, +1 so (c) sees 4 draws


def _seeded_rng(case_id: str, i: int) -> random.Random:
    return random.Random(f"{case_id}/draw-{i}")


def _draws(case: trainer.TrainerCase) -> list[dict]:
    return [
        trainer.generate(case.set_key, case_id=case.id, rng=_seeded_rng(case.id, i))
        for i in range(DRAWS_PER_CASE)
    ]


def _check_case_draws(case: trainer.TrainerCase) -> None:
    """(a) + (b) + (c) for one case."""
    draws = _draws(case)
    for result in draws:
        state = apply_moves(CubieState.solved(), result["scramble"])
        # (a) the scramble lands in the requested case's class.
        assert trainer.canonical_key_of_state(case.set_key, state) == case.key, (
            f"{case.id}: scramble {result['scramble']!r} is not in the class"
        )
        # (b) the solution replays the state to solved.
        assert is_solved(apply_moves(state, result["solution"])), (
            f"{case.id}: solution does not solve the scrambled state"
        )
        # Output alphabet: face-turn tokens only.
        assert all(m in MOVE_TOKENS for m in result["scramble"].split())
        assert all(m in MOVE_TOKENS for m in result["solution"].split())
        assert result["case_id"] == case.id
        assert result["name"] == case.name
        assert result["preview"] == case.preview
    # (c) free-param randomization yields genuinely different scrambles.
    assert len({r["scramble"] for r in draws}) >= 2, (
        f"{case.id}: 4 seeded draws produced identical scrambles"
    )


# --------------------------------------------------------------------------- #
# (a)(b)(c) per set
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("set_key", ["oll", "pll", "coll"])
def test_draws_full_set(set_key: str):
    for case in trainer.CASES[set_key]:
        _check_case_draws(case)


def test_draws_vls_full_set():
    for case in trainer.CASES["vls"]:
        _check_case_draws(case)


def test_draws_zbll_sampled():
    for case in ZBLL_SAMPLE:
        _check_case_draws(case)


# --------------------------------------------------------------------------- #
# (d) enumeration counts frozen
# --------------------------------------------------------------------------- #


def test_enumeration_counts_frozen():
    assert trainer.FROZEN_COUNTS == {
        "oll": 57,
        "pll": 21,
        "coll": 42,
        "zbll": 493,
        "vls": 216,
    }
    for set_key, cases in trainer.CASES.items():
        assert len(cases) == trainer.FROZEN_COUNTS[set_key]
        assert len({c.id for c in cases}) == len(cases)
        assert len({c.key for c in cases}) == len(cases)


def test_group_structure():
    """Community-reconciled group counts + naming conventions."""
    groups = {k: {g["key"]: g["count"] for g in trainer.GROUPS[k]} for k in trainer.SET_ORDER}
    assert groups["coll"] == {"O": 2, "H": 4, "Pi": 6, "T": 6, "U": 6, "L": 6, "S": 6, "AS": 6}
    assert groups["zbll"] == {"O": 21, "H": 40, "Pi": 72, "T": 72, "U": 72, "L": 72, "S": 72, "AS": 72}
    assert groups["pll"] == {"pll": 21}
    assert sum(groups["oll"].values()) == 57
    assert all(count == 27 for count in groups["vls"].values()) and len(groups["vls"]) == 8
    # OLL/PLL reuse the existing modules' ids and real names.
    by_id = trainer.CASE_BY_ID
    assert by_id["oll"]["oll-27"].name == "Sune"
    assert by_id["pll"]["pll-T"].name == "T Perm"
    # ZBLL's corners-oriented group is named after the PLL each case equals.
    zbll_o_names = {c.name for c in trainer.CASES["zbll"] if c.group == "O"}
    pll_names = {c.name for c in trainer.CASES["pll"]}
    assert zbll_o_names == pll_names


# --------------------------------------------------------------------------- #
# (e) id stability golden snapshot
# --------------------------------------------------------------------------- #


def test_golden_id_stability():
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        golden = json.load(fh)
    current = {
        set_key: {c.id: c.key_str() for c in cases}
        for set_key, cases in trainer.CASES.items()
    }
    assert current == golden, (
        "Trainer case ids / canonical keys changed. Ids are STABLE across "
        "releases (records are keyed on them) — do not regenerate the golden "
        "file unless this is an intentional, migration-handled break."
    )


# --------------------------------------------------------------------------- #
# Previews (§11.3)
# --------------------------------------------------------------------------- #


def test_preview_shapes_and_alphabets():
    letters = set("URFDLB")
    for set_key, cases in trainer.CASES.items():
        for case in cases:
            p = case.preview
            assert sorted(p) == ["b", "f", "l", "r", "u"]
            assert len(p["u"]) == 9
            assert all(len(p[side]) == 3 for side in "frbl")
            values = set(p["u"]) | {v for side in "frbl" for v in p[side]}
            if set_key in ("oll", "vls"):
                assert values <= {"U", "x"}
            elif set_key in ("pll", "zbll"):
                assert values <= letters
            else:  # coll
                assert values <= letters | {"x"}
    # COLL: side edge stickers dim, U-face edge stickers oriented.
    for case in trainer.CASES["coll"]:
        assert all(case.preview[side][1] == "x" for side in "frbl")
        assert all(case.preview["u"][i] == "U" for i in (1, 3, 5, 7))


def test_preview_stable_across_draws():
    """The preview comes from the canonical representative, not the draw."""
    for set_key in trainer.SET_ORDER:
        case = trainer.CASES[set_key][0]
        previews = {json.dumps(r["preview"]) for r in _draws(case)}
        assert len(previews) == 1


# --------------------------------------------------------------------------- #
# Scramble diversity: variant tables + y-conjugation
# --------------------------------------------------------------------------- #


def test_variant_tables_coverage_and_preservation():
    """The trainer-local variant tables cover exactly the canonical tables'
    signatures, offer >=2 variants per signature, and every variant solves
    its stage from ANY state with that signature."""
    from solver.oll import OLL_TABLE, ll_is_oriented
    from solver.pll import PLL_TABLE, SKIP_SIGNATURES
    from solver.pll import signature as pll_signature

    assert set(trainer.OLL_VARIANTS) == set(OLL_TABLE)
    assert set(trainer.PLL_VARIANTS) == set(PLL_TABLE)
    for sig, variants in trainer.OLL_VARIANTS.items():
        assert len(variants) >= 2, f"OLL signature {sig}: too few variants"
        co4, eo4 = sig
        for moves in variants:
            s = trainer._make_state(co4=co4, eo4=eo4)
            assert ll_is_oriented(apply_moves(s, moves)), (
                f"OLL variant {moves} does not orient signature {sig}"
            )
    for sig, variants in trainer.PLL_VARIANTS.items():
        assert len(variants) >= 2, f"PLL signature {sig}: too few variants"
        cp4, ep4 = sig
        for moves in variants:
            s = trainer._make_state(cp4=cp4, ep4=ep4)
            after = apply_moves(s, moves)
            assert pll_signature(after) in SKIP_SIGNATURES, (
                f"PLL variant {moves} does not solve signature {sig} up to AUF"
            )


def test_y_relabel_mapping():
    """One y relabels F->R->B->L->F with U/D fixed; j composes cyclically."""
    tokens = ["F", "R2", "B'", "L", "U", "D'", "F2"]
    assert trainer.y_relabel(tokens, 0) == tokens
    assert trainer.y_relabel(tokens, 1) == ["R", "B2", "L'", "F", "U", "D'", "R2"]
    assert trainer.y_relabel(tokens, 2) == ["B", "L2", "F'", "R", "U", "D'", "B2"]
    assert trainer.y_relabel(tokens, 4) == tokens  # y^4 = identity
    # Composition: relabel by 1 twice == relabel by 2.
    assert trainer.y_relabel(trainer.y_relabel(tokens, 1), 1) == trainer.y_relabel(tokens, 2)


@pytest.mark.parametrize("set_key", ["oll", "pll", "coll", "zbll"])
def test_y_relabel_preserves_case_class(set_key: str):
    """A y^j-relabeled scramble lands in the SAME AUF-quotiented class."""
    rng = random.Random(f"y-relabel/{set_key}")
    for case in rng.sample(trainer.CASES[set_key], 3):
        result = trainer.generate(set_key, case_id=case.id, rng=rng)
        scramble = result["scramble"].split()
        for j in range(4):
            state = apply_moves(CubieState.solved(), trainer.y_relabel(scramble, j))
            assert trainer.canonical_key_of_state(set_key, state) == case.key, (
                f"{case.id}: y^{j}-relabeled scramble left the case class"
            )


def test_y_relabel_breaks_vls_class():
    """VLS's frame (the unsolved FR slot) does NOT survive y-conjugation —
    the generator must therefore skip relabeling for vls (documented in
    trainer.y_relabel)."""
    rng = random.Random("y-relabel/vls")
    case = trainer.CASES["vls"][0]
    result = trainer.generate("vls", case_id=case.id, rng=rng)
    scramble = result["scramble"].split()
    for j in range(1, 4):
        state = apply_moves(CubieState.solved(), trainer.y_relabel(scramble, j))
        try:
            key = trainer.canonical_key_of_state("vls", state)
        except ValueError:
            continue  # no longer a vls-shaped state at all — frame broken
        assert key != case.key, "vls class unexpectedly survived y-conjugation"


@pytest.mark.parametrize(
    "set_key,case_id",
    [
        ("oll", "oll-27"),
        ("oll", "oll-21"),
        ("oll", "oll-1"),
        ("pll", "pll-T"),
        ("pll", "pll-H"),
    ],
)
def test_scramble_diversity_gate(set_key: str, case_id: str):
    """Anti-memorization gate: over 16 seeded draws of one case, at least 5
    distinct 6-move scramble suffixes AND 5 distinct 6-move prefixes."""
    prefixes: set[tuple] = set()
    suffixes: set[tuple] = set()
    for i in range(16):
        result = trainer.generate(
            set_key, case_id=case_id, rng=random.Random(f"{case_id}/gate-{i}")
        )
        tokens = result["scramble"].split()
        assert len(tokens) >= 6
        prefixes.add(tuple(tokens[:6]))
        suffixes.add(tuple(tokens[-6:]))
    assert len(suffixes) >= 5, (
        f"{case_id}: only {len(suffixes)} distinct scramble suffixes in 16 draws"
    )
    assert len(prefixes) >= 5, (
        f"{case_id}: only {len(prefixes)} distinct scramble prefixes in 16 draws"
    )


# --------------------------------------------------------------------------- #
# (f) endpoints
# --------------------------------------------------------------------------- #


def test_endpoint_sets():
    body = client.get("/api/trainer/sets").json()
    assert [s["key"] for s in body["sets"]] == list(trainer.SET_ORDER)
    for entry in body["sets"]:
        assert entry["count"] == trainer.FROZEN_COUNTS[entry["key"]]
        assert entry["name"] and entry["description"]
        assert sum(g["count"] for g in entry["groups"]) == entry["count"]
        assert all(g["key"] and g["name"] for g in entry["groups"])


def test_endpoint_cases_and_group_filter():
    body = client.get("/api/trainer/cases", params={"set": "zbll", "group": "Pi"}).json()
    assert body["set"] == "zbll"
    assert len(body["cases"]) == 72
    assert all(c["group"] == "Pi" for c in body["cases"])
    assert all(set(c) == {"id", "name", "group", "preview"} for c in body["cases"])
    # Unfiltered = the whole set, in stable order.
    body = client.get("/api/trainer/cases", params={"set": "oll"}).json()
    assert [c["id"] for c in body["cases"]] == [c.id for c in trainer.CASES["oll"]]


@pytest.mark.parametrize("set_key", list(trainer.SET_ORDER))
def test_endpoint_scramble_happy_path(set_key: str):
    resp = client.get("/api/trainer/scramble", params={"set": set_key, "seed": 42})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"set", "case_id", "name", "group", "scramble", "solution", "preview"}
    assert body["set"] == set_key
    assert body["case_id"] in trainer.CASE_BY_ID[set_key]
    state = apply_moves(CubieState.solved(), body["scramble"])
    assert is_solved(apply_moves(state, body["solution"]))
    # Seeded draws are deterministic (tests-only contract).
    again = client.get("/api/trainer/scramble", params={"set": set_key, "seed": 42}).json()
    assert again == body


def test_endpoint_scramble_case_targeting():
    body = client.get(
        "/api/trainer/scramble", params={"set": "oll", "case_id": "oll-27", "seed": 1}
    ).json()
    assert body["case_id"] == "oll-27" and body["name"] == "Sune"
    state = apply_moves(CubieState.solved(), body["scramble"])
    case = trainer.CASE_BY_ID["oll"]["oll-27"]
    assert trainer.canonical_key_of_state("oll", state) == case.key


def test_endpoint_errors():
    resp = client.get("/api/trainer/scramble", params={"set": "wca"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["valid"] is False and body["errors"][0]["code"] == "unknown_set"

    resp = client.get(
        "/api/trainer/scramble", params={"set": "oll", "case_id": "oll-99"}
    )
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "unknown_case"

    resp = client.get("/api/trainer/cases", params={"set": "nope"})
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "unknown_set"

    resp = client.get("/api/trainer/cases", params={"set": "coll", "group": "Z"})
    assert resp.status_code == 400
    assert resp.json()["errors"][0]["code"] == "unknown_group"


class TestMergeSameFace:
    def test_merges_and_cancels(self):
        from solver.trainer import _merge_same_face

        assert _merge_same_face(["U2", "U"]) == ["U'"]
        assert _merge_same_face(["R", "U", "U'", "R"]) == ["R2"]
        assert _merge_same_face(["F", "F", "F"]) == ["F'"]
        assert _merge_same_face(["R", "U", "R'"]) == ["R", "U", "R'"]

    def test_generated_scrambles_have_no_same_face_seams(self):
        import random

        from solver.trainer import CASES, generate

        rng = random.Random(7)
        for set_key in CASES:
            for _ in range(6):
                toks = generate(set_key, rng=rng)["scramble"].split()
                for a, b in zip(toks, toks[1:]):
                    assert a[0] != b[0], (set_key, toks)
