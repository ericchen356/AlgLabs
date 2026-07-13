"""Trainer engine: case enumeration + scramble generation (CONTRACTS.md §11).

Five drillable sets — ``oll``, ``pll``, ``coll``, ``zbll``, ``vls``. A *case*
is an equivalence class of cube states in the canonical frame (centers fixed,
F2L = bottom two layers), taken up to pre/post AUF (``U^a · s · U^b`` as
CubieState composition) — except VLS, whose frame is fixed by the pair
position (no AUF freedom).

Enumeration is the ground truth (§11.1): every raw last-layer state of the
set's shape is canonicalized by taking the lexicographic minimum of its
signature over the 16 AUF compositions; the distinct keys are the cases.
OLL/PLL classes are additionally reconciled 1:1 against the existing
``solver/oll.py`` / ``solver/pll.py`` recognition tables and reuse their ids
(``oll-27``, ``pll-T``) and real names.

Scrambles are computed, never hand-curated (§11.2): a concrete state is built
by randomizing only the case's free parameters (keeping corner/edge
permutation parity equal), a trainer-local last-layer solver produces the
solution (replay-verified before it is returned), and the scramble is its
inverse.

Scramble diversity — two independent multipliers keep users from memorizing
a constant scramble suffix instead of recognizing the cube:

* **Variant tables**: trainer-local ``signature -> [moves, ...]`` tables built
  from every case's primary algorithm PLUS its verified ``alt`` list (§7.1),
  via the same §7 inverse-setup construction as ``solver/oll.py`` /
  ``solver/pll.py``. The trainer solver draws UNIFORMLY among a signature's
  variants, so the OLL/PLL portion of a solution (and hence the scramble's
  prefix/suffix) changes between draws. The recognition tables of the
  walkthrough solver are untouched — it keeps teaching the single canonical
  algorithm.
* **Whole-scramble y-conjugation**: relabeling every token of a scramble
  through the y^j rotation face map (U/D fixed, F->R->B->L->F per y) turns it
  into the y-conjugated scramble. For an F2L-solved state ``S``, y acts on
  the last-layer slots exactly like U, so ``y S y⁻¹ = U S U'`` — the
  pre/post-AUF-quotiented class of every set is preserved. Applied for a
  random j in 0..3 to all sets EXCEPT ``vls`` (see y_relabel below).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import permutations, product
from typing import Any

from cube.facelet import CubieState, cubies_to_facelets, is_solved, multiply
from cube.moves import TABLE, apply_moves, invert, parse_algorithm, to_notation

from solver.f2l import solve_f2l
from solver.oll import (
    AUF_TOKENS,
    OLL_TABLE,
    SOLVED_SIGNATURE,
    f2l_is_solved,
    ll_is_oriented,
)
from solver.oll import signature as oll_signature
from solver.pll import PLL_TABLE, SKIP_SIGNATURES, compute_auf
from solver.pll import signature as pll_signature

# --------------------------------------------------------------------------- #
# Frozen enumeration counts (§11.1) — reconciliation against community numbers
#
# * oll  =  57 : the standard 57 OLL cases (216 orientation signatures = 27
#               corner twists x 8 edge flips, minus solved, in AUF orbits).
# * pll  =  21 : the standard 21 PLL cases (288 parity-consistent permutation
#               signatures, minus the 4-signature solved/skip orbit, in orbits).
# * coll =  42 : community COLL is usually quoted as 40 (H4 Pi6 T6 U6 L6 S6
#               AS6, corners-oriented cases excluded); we INCLUDE the two
#               corners-oriented "O" permutation classes (adjacent / diagonal
#               corner swap) and exclude only the fully-solved-corners class,
#               giving 40 + 2 = 42.
# * zbll = 493 : community ZBLL = 472 "real" cases + the 21 PLLs (its
#               corners-oriented O subset) = 493 non-solved classes.
# * vls  = 216 : 27 corner-orientation x 8 edge-orientation patterns of the
#               post-insert state; no AUF quotient (the FR pair fixes the
#               frame) and the all-oriented pattern IS a case (the insert
#               still has to be performed), so all 216 count.
#
# A mismatch between these constants and the enumeration is a build error.
# --------------------------------------------------------------------------- #

FROZEN_COUNTS: dict[str, int] = {
    "oll": 57,
    "pll": 21,
    "coll": 42,
    "zbll": 493,
    "vls": 216,
}

SET_ORDER: tuple[str, ...] = ("oll", "pll", "coll", "zbll", "vls")

SET_NAMES: dict[str, str] = {
    "oll": "OLL",
    "pll": "PLL",
    "coll": "COLL",
    "zbll": "ZBLL",
    "vls": "VLS",
}

SET_DESCRIPTIONS: dict[str, str] = {
    "oll": "Orient the last layer",
    "pll": "Permute the last layer",
    "coll": "Corners of the last layer, edges oriented",
    "zbll": "Whole last layer in one look (edges oriented)",
    "vls": "Last F2L pair + orientation in one insert",
}

#: OCLL family order used for COLL/ZBLL groups (§11.1).
OCLL_ORDER: tuple[str, ...] = ("O", "H", "Pi", "T", "U", "L", "S", "AS")

#: The canonical R U R' insert whose inverse defines the VLS frame (§11.1).
VLS_INSERT: tuple[str, ...] = ("R", "U", "R'")
VLS_UNINSERT: tuple[str, ...] = ("R", "U'", "R'")  # invert(VLS_INSERT)


class TrainerError(ValueError):
    """A structured trainer API error (unknown set / group / case)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


# --------------------------------------------------------------------------- #
# AUF machinery
# --------------------------------------------------------------------------- #

#: U^k applied to solved, k = 0..3 (identity, U, U2, U').
_U_STATES: tuple[CubieState, ...] = (
    CubieState.solved(),
    TABLE["U"].copy(),
    TABLE["U2"].copy(),
    TABLE["U'"].copy(),
)


def _auf_compose(state: CubieState, a: int, b: int) -> CubieState:
    """``U^a · state · U^b`` as CubieState composition (§11.1)."""
    return multiply(multiply(_U_STATES[a], state), _U_STATES[b])


def _auf_variants(state: CubieState) -> list[CubieState]:
    """All 16 pre/post-AUF compositions of ``state``."""
    return [_auf_compose(state, a, b) for a in range(4) for b in range(4)]


# --------------------------------------------------------------------------- #
# Signatures and state construction
# --------------------------------------------------------------------------- #

Key = tuple  # a set-specific canonical signature (tuple of int tuples)


def _sig_oll(s: CubieState) -> Key:
    return (tuple(s.co[0:4]), tuple(s.eo[0:4]))


def _sig_pll(s: CubieState) -> Key:
    return (tuple(s.cp[0:4]), tuple(s.ep[0:4]))


def _sig_coll(s: CubieState) -> Key:
    return (tuple(s.cp[0:4]), tuple(s.co[0:4]))


def _sig_zbll(s: CubieState) -> Key:
    return (tuple(s.cp[0:4]), tuple(s.co[0:4]), tuple(s.ep[0:4]))


_SIG_FN = {"oll": _sig_oll, "pll": _sig_pll, "coll": _sig_coll,
           "zbll": _sig_zbll, "vls": _sig_oll}


def _canon(sig_fn, state: CubieState) -> Key:
    """Lexicographic-minimum signature over the 16 AUF compositions."""
    return min(sig_fn(v) for v in _auf_variants(state))


def _make_state(
    cp4: tuple[int, ...] | None = None,
    co4: tuple[int, ...] | None = None,
    ep4: tuple[int, ...] | None = None,
    eo4: tuple[int, ...] | None = None,
) -> CubieState:
    """F2L-solved state with the given last-layer arrays (defaults solved)."""
    s = CubieState.solved()
    if cp4 is not None:
        s.cp[0:4] = list(cp4)
    if co4 is not None:
        s.co[0:4] = list(co4)
    if ep4 is not None:
        s.ep[0:4] = list(ep4)
    if eo4 is not None:
        s.eo[0:4] = list(eo4)
    return s


def _perm_parity(perm: tuple[int, ...]) -> int:
    parity = 0
    for i in range(len(perm)):
        for k in range(i + 1, len(perm)):
            if perm[i] > perm[k]:
                parity ^= 1
    return parity


def _all_co4() -> list[tuple[int, ...]]:
    """The 27 corner-orientation patterns of the LL (twist sum = 0 mod 3)."""
    return [
        (a, b, c, (-a - b - c) % 3)
        for a, b, c in product(range(3), repeat=3)
    ]


def _all_eo4() -> list[tuple[int, ...]]:
    """The 8 edge-orientation patterns of the LL (flip sum = 0 mod 2)."""
    return [
        (a, b, c, (a + b + c) % 2)
        for a, b, c in product(range(2), repeat=3)
    ]


_PERMS4: list[tuple[int, ...]] = list(permutations(range(4)))


# --------------------------------------------------------------------------- #
# OCLL family classification (groups for COLL/ZBLL)
# --------------------------------------------------------------------------- #


def _canon_co(co4: tuple[int, ...]) -> tuple[int, ...]:
    """Canonical (lex-min over AUF) corner-orientation pattern."""
    return min(tuple(v.co[0:4]) for v in _auf_variants(_make_state(co4=co4)))


def _build_ocll_families() -> dict[tuple[int, ...], str]:
    """Map canonical corner-orientation pattern -> OCLL family name.

    Derived (never hand-typed) from the existing OLL table: cases 21..27 are
    the edges-oriented OCLL cases H, Pi, U, T, L, AS, S in standard numbering.
    """
    by_case = {21: "H", 22: "Pi", 23: "U", 24: "T", 25: "L", 26: "AS", 27: "S"}
    families: dict[tuple[int, ...], str] = {(0, 0, 0, 0): "O"}
    for sig, (case, _moves) in OLL_TABLE.items():
        if case.id in by_case:
            co4, eo4 = sig
            assert eo4 == (0, 0, 0, 0), f"OLL {case.id} should be edges-oriented"
            key = _canon_co(co4)
            existing = families.get(key)
            assert existing in (None, by_case[case.id]), "OCLL family collision"
            families[key] = by_case[case.id]
    # 1 oriented + 7 twisted families covering all 27 patterns.
    assert set(families.values()) == set(OCLL_ORDER)
    covered = {_canon_co(co4) for co4 in _all_co4()}
    assert covered == set(families), "OCLL families must cover all co patterns"
    return families


_OCLL_FAMILY: dict[tuple[int, ...], str] = _build_ocll_families()


def _ocll_family(co4: tuple[int, ...]) -> str:
    return _OCLL_FAMILY[_canon_co(co4)]


# --------------------------------------------------------------------------- #
# Preview payloads (§11.3)
# --------------------------------------------------------------------------- #

#: U-face positions (local 0..8) holding LL corner stickers vs edge stickers.
_U_CORNER_POS = (0, 2, 6, 8)
_U_EDGE_POS = (1, 3, 5, 7)


def _preview_from_state(state: CubieState, mode: str) -> dict[str, list[str]]:
    """§11.3 preview: U face row-major + the top row of each side face.

    ``mode``:
    * ``"orient"`` (oll/vls): ``"U"`` where the sticker is U-colored, else "x".
    * ``"full"`` (pll/zbll): actual facelet letters everywhere.
    * ``"coll"``: corner positions = actual letters; side edge positions =
      ``"x"`` (edges unconstrained); U-face edge stickers = ``"U"``.
    """
    fs = cubies_to_facelets(state)
    u = list(fs[0:9])
    sides = {"f": list(fs[18:21]), "r": list(fs[9:12]),
             "b": list(fs[45:48]), "l": list(fs[36:39])}
    if mode == "orient":
        u = [c if c == "U" else "x" for c in u]
        sides = {k: [c if c == "U" else "x" for c in v] for k, v in sides.items()}
    elif mode == "coll":
        u = [
            ("U" if i in _U_EDGE_POS else c)
            for i, c in enumerate(u)
        ]
        sides = {k: [v[0], "x", v[2]] for k, v in sides.items()}
    else:
        assert mode == "full"
    return {"u": u, **sides}


_PREVIEW_MODE = {"oll": "orient", "pll": "full", "coll": "coll",
                 "zbll": "full", "vls": "orient"}


# --------------------------------------------------------------------------- #
# Case model + enumeration (§11.1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TrainerCase:
    """One trainer case: a canonical class with fixed + free parameters."""

    set_key: str
    id: str
    name: str
    group: str  # group key
    key: Key  # canonical class signature (id-stability golden target)
    # Canonical fixed LL arrays (None = free parameter, randomized per draw).
    cp4: tuple[int, ...] | None
    co4: tuple[int, ...] | None
    ep4: tuple[int, ...] | None
    eo4: tuple[int, ...] | None
    preview: dict[str, list[str]]

    def key_str(self) -> str:
        return repr(self.key)


def _representative(case: TrainerCase) -> CubieState:
    """Canonical class representative (free perms fixed to identity)."""
    state = _make_state(case.cp4, case.co4, case.ep4, case.eo4)
    if case.set_key == "vls":
        state = apply_moves(state, list(VLS_INSERT))
    return state


def _enumerate_classes(states: list[CubieState], sig_fn) -> dict[Key, Key]:
    """Map every raw signature to its canonical class key."""
    return {sig_fn(s): _canon(sig_fn, s) for s in states}


def _build_oll_cases() -> list[TrainerCase]:
    """57 classes, reconciled 1:1 against solver/oll.py's case table."""
    states = [
        _make_state(co4=co4, eo4=eo4)
        for co4 in _all_co4()
        for eo4 in _all_eo4()
        if (co4, eo4) != ((0, 0, 0, 0), (0, 0, 0, 0))
    ]
    assert len(states) == 215
    class_of = _enumerate_classes(states, _sig_oll)
    # Each class must align with exactly one existing OLL case.
    case_of_class: dict[Key, Any] = {}
    for sig, key in class_of.items():
        case = OLL_TABLE[sig][0]
        existing = case_of_class.get(key)
        assert existing is None or existing.id == case.id, (
            f"OLL class {key} spans cases {existing.id} and {case.id}"
        )
        case_of_class[key] = case
    ids = {c.id for c in case_of_class.values()}
    assert len(ids) == len(case_of_class) == FROZEN_COUNTS["oll"], (
        f"OLL enumeration: {len(case_of_class)} classes over {len(ids)} cases"
    )
    cases = []
    for key, oll_case in sorted(case_of_class.items(), key=lambda kv: kv[1].id):
        co4, eo4 = key
        cases.append(TrainerCase(
            set_key="oll",
            id=f"oll-{oll_case.id}",
            name=oll_case.name,
            group=oll_case.group,
            key=key,
            cp4=None, co4=co4, ep4=None, eo4=eo4,
            preview=_preview_from_state(_make_state(co4=co4, eo4=eo4), "orient"),
        ))
    return cases


def _build_pll_cases() -> list[TrainerCase]:
    """21 classes, reconciled 1:1 against solver/pll.py's case table."""
    solved_key = _canon(_sig_pll, CubieState.solved())
    states = [
        _make_state(cp4=cp4, ep4=ep4)
        for cp4 in _PERMS4
        for ep4 in _PERMS4
        if _perm_parity(cp4) == _perm_parity(ep4)
    ]
    assert len(states) == 288
    class_of = _enumerate_classes(states, _sig_pll)
    case_of_class: dict[Key, Any] = {}
    for sig, key in class_of.items():
        if key == solved_key:
            assert sig in SKIP_SIGNATURES
            continue
        case = PLL_TABLE[sig][0]
        existing = case_of_class.get(key)
        assert existing is None or existing.id == case.id, (
            f"PLL class {key} spans cases {existing.id} and {case.id}"
        )
        case_of_class[key] = case
    ids = {c.id for c in case_of_class.values()}
    assert len(ids) == len(case_of_class) == FROZEN_COUNTS["pll"], (
        f"PLL enumeration: {len(case_of_class)} classes over {len(ids)} cases"
    )
    cases = []
    for key, pll_case in sorted(case_of_class.items(), key=lambda kv: kv[1].id):
        cp4, ep4 = key
        cases.append(TrainerCase(
            set_key="pll",
            id=f"pll-{pll_case.id}",
            name=pll_case.name,
            group="pll",
            key=key,
            cp4=cp4, co4=None, ep4=ep4, eo4=None,
            preview=_preview_from_state(_make_state(cp4=cp4, ep4=ep4), "full"),
        ))
    return cases


def _grouped_classes(
    set_key: str,
    keys: set[Key],
    co4_of_key,
    name_of=None,
) -> list[TrainerCase]:
    """Assemble COLL/ZBLL cases: OCLL grouping + stable per-group numbering."""
    by_group: dict[str, list[Key]] = {g: [] for g in OCLL_ORDER}
    for key in keys:
        by_group[_ocll_family(co4_of_key(key))].append(key)
    cases: list[TrainerCase] = []
    for group in OCLL_ORDER:
        for n, key in enumerate(sorted(by_group[group]), start=1):
            if set_key == "coll":
                cp4, co4 = key
                ep4 = None
                fixed = dict(cp4=cp4, co4=co4, ep4=ep4, eo4=(0, 0, 0, 0))
                preview_state = _make_state(cp4=cp4, co4=co4)
            else:
                cp4, co4, ep4 = key
                fixed = dict(cp4=cp4, co4=co4, ep4=ep4, eo4=(0, 0, 0, 0))
                preview_state = _make_state(cp4=cp4, co4=co4, ep4=ep4)
            name = f"{SET_NAMES[set_key]} {group}{n}"
            if name_of is not None:
                name = name_of(key, group, n) or name
            cases.append(TrainerCase(
                set_key=set_key,
                id=f"{set_key}-{group}-{n}",
                name=name,
                group=group,
                key=key,
                preview=_preview_from_state(preview_state, _PREVIEW_MODE[set_key]),
                **fixed,
            ))
    return cases


def _build_coll_cases() -> list[TrainerCase]:
    """~42 classes of (cp, co) with all edges oriented (§11.1)."""
    solved_key = _canon(_sig_coll, CubieState.solved())
    states = [
        _make_state(cp4=cp4, co4=co4)
        for cp4 in _PERMS4
        for co4 in _all_co4()
    ]
    keys = {_canon(_sig_coll, s) for s in states}
    keys.discard(solved_key)  # exclude the fully-solved-corners class
    assert len(keys) == FROZEN_COUNTS["coll"], (
        f"COLL enumeration: expected {FROZEN_COUNTS['coll']}, got {len(keys)}"
    )
    return _grouped_classes("coll", keys, co4_of_key=lambda k: k[1])


def _build_zbll_cases() -> list[TrainerCase]:
    """493 classes of the full (cp, co, ep) LL with eo = 0 (§11.1)."""
    solved_key = _canon(_sig_zbll, CubieState.solved())
    keys: set[Key] = set()
    for cp4 in _PERMS4:
        cp_par = _perm_parity(cp4)
        for ep4 in _PERMS4:
            if _perm_parity(ep4) != cp_par:
                continue
            for co4 in _all_co4():
                keys.add(_canon(_sig_zbll, _make_state(cp4=cp4, co4=co4, ep4=ep4)))
    keys.discard(solved_key)
    assert len(keys) == FROZEN_COUNTS["zbll"], (
        f"ZBLL enumeration: expected {FROZEN_COUNTS['zbll']}, got {len(keys)}"
    )

    def name_of(key: Key, group: str, n: int) -> str | None:
        if group != "O":
            return None
        # Corners oriented => this IS a PLL: name it after the PLL it equals.
        cp4, _co4, ep4 = key
        from solver.pll import solve_pll  # local: avoid polluting module scope

        step = solve_pll(_make_state(cp4=cp4, ep4=ep4))
        assert step is not None, "solved ZBLL class should have been excluded"
        return step.name

    return _grouped_classes("zbll", keys, co4_of_key=lambda k: k[1], name_of=name_of)


#: The 8 VLS edge-orientation patterns in lexicographic order -> group key.
_VLS_EO_PATTERNS: list[tuple[int, ...]] = sorted(_all_eo4())

_LL_EDGE_NAMES = ("UR", "UF", "UL", "UB")


def _vls_group_label(eo4: tuple[int, ...]) -> str:
    flipped = [_LL_EDGE_NAMES[i] for i, v in enumerate(eo4) if v]
    if not flipped:
        return "no edges flipped"
    if len(flipped) == 4:
        return "all edges flipped"
    return "+".join(flipped) + " flipped"


def _build_vls_cases() -> list[TrainerCase]:
    """216 classes: the raw 27 x 8 orientation patterns of the post-insert
    state — the FR pair fixes the frame, so there is no AUF quotient."""
    cases: list[TrainerCase] = []
    for gi, eo4 in enumerate(_VLS_EO_PATTERNS):
        group = f"eo{gi}"
        for n, co4 in enumerate(sorted(_all_co4()), start=1):
            key = (co4, eo4)
            target = _make_state(co4=co4, eo4=eo4)
            preview_state = apply_moves(target, list(VLS_INSERT))
            cases.append(TrainerCase(
                set_key="vls",
                id=f"vls-{group}-{n}",
                name=f"VLS {group}-{n}",
                group=group,
                key=key,
                cp4=None, co4=co4, ep4=None, eo4=eo4,
                preview=_preview_from_state(preview_state, "orient"),
            ))
    assert len(cases) == FROZEN_COUNTS["vls"]
    return cases


def _build_all() -> dict[str, list[TrainerCase]]:
    cases = {
        "oll": _build_oll_cases(),
        "pll": _build_pll_cases(),
        "coll": _build_coll_cases(),
        "zbll": _build_zbll_cases(),
        "vls": _build_vls_cases(),
    }
    for set_key, lst in cases.items():
        assert len(lst) == FROZEN_COUNTS[set_key]
        assert len({c.id for c in lst}) == len(lst), f"duplicate ids in {set_key}"
        assert len({c.key for c in lst}) == len(lst), f"duplicate keys in {set_key}"
    return cases


#: set key -> ordered case list. Built at import; counts are hard-asserted.
CASES: dict[str, list[TrainerCase]] = _build_all()

#: set key -> case id -> case.
CASE_BY_ID: dict[str, dict[str, TrainerCase]] = {
    set_key: {c.id: c for c in lst} for set_key, lst in CASES.items()
}


def _groups_of(set_key: str) -> list[dict[str, Any]]:
    """Ordered group descriptors {key, name, count} for one set."""
    lst = CASES[set_key]
    order: list[str] = []
    counts: dict[str, int] = {}
    for c in lst:
        if c.group not in counts:
            order.append(c.group)
        counts[c.group] = counts.get(c.group, 0) + 1
    if set_key == "vls":
        names = {
            f"eo{gi}": _vls_group_label(eo4)
            for gi, eo4 in enumerate(_VLS_EO_PATTERNS)
        }
    elif set_key == "pll":
        names = {"pll": "PLL"}
    else:
        names = {g: g for g in order}
    return [{"key": g, "name": names[g], "count": counts[g]} for g in order]


GROUPS: dict[str, list[dict[str, Any]]] = {k: _groups_of(k) for k in SET_ORDER}


# --------------------------------------------------------------------------- #
# Canonical key of an arbitrary state (test/verification surface, §11.5a)
# --------------------------------------------------------------------------- #


def canonical_key_of_state(set_key: str, state: CubieState) -> Key:
    """Canonical class key of ``state`` for ``set_key``.

    Validates the set's structural constraints (raises ``ValueError`` when the
    state is not of the set's shape). For ``vls`` the given state is the
    TRAINABLE state (pair connected in U); the insert is undone first.
    """
    if set_key == "vls":
        target = apply_moves(state.copy(), list(VLS_UNINSERT))
        if not f2l_is_solved(target):
            raise ValueError("vls state: undoing R U R' does not restore F2L")
        return _sig_oll(target)  # no AUF quotient
    if set_key not in CASES:
        raise ValueError(f"unknown set {set_key!r}")
    if not f2l_is_solved(state):
        raise ValueError(f"{set_key} state: first two layers not solved")
    if set_key == "pll" and not ll_is_oriented(state):
        raise ValueError("pll state: last layer not oriented")
    if set_key in ("coll", "zbll") and state.eo[0:4] != [0, 0, 0, 0]:
        raise ValueError(f"{set_key} state: last-layer edges not oriented")
    return _canon(_SIG_FN[set_key], state)


# --------------------------------------------------------------------------- #
# Scramble-diversity machinery: variant tables + y-conjugation
# --------------------------------------------------------------------------- #


def _unique_cases(table: dict) -> list:
    """The distinct case objects of an OLL/PLL recognition table, in the
    (deterministic) order they first appear."""
    seen: dict[Any, Any] = {}
    for case, _moves in table.values():
        seen.setdefault(case.id, case)
    return list(seen.values())


def _build_oll_variants() -> dict[Key, list[list[str]]]:
    """signature -> list of move sequences that orient that signature.

    §7-style inverse-setup construction over [primary] + alt algorithms and
    every pre-AUF k: ``moves = U^k + parse(alg)`` claims the signature of
    ``apply(invert(moves), solved)``. Build-time gates: every setup preserves
    F2L, lands in the CORRECT case of the canonical OLL table, and the
    variant table covers every signature of the canonical table.
    """
    variants: dict[Key, list[list[str]]] = {}
    for case in _unique_cases(OLL_TABLE):
        for alg in [case.alg, *(case.alt or [])]:
            alg_tokens = parse_algorithm(alg)
            for k in range(4):
                moves = AUF_TOKENS[k] + alg_tokens
                s = apply_moves(CubieState.solved(), invert(moves))
                assert f2l_is_solved(s), (
                    f"OLL case {case.id} variant {alg!r}: does not preserve "
                    f"the first two layers (pre-AUF k={k})"
                )
                sig = oll_signature(s)
                entry = OLL_TABLE.get(sig)
                assert entry is not None and entry[0].id == case.id, (
                    f"OLL case {case.id} variant {alg!r}: lands in "
                    f"{'the solved state' if entry is None else f'case {entry[0].id}'}"
                    f" instead of case {case.id} (pre-AUF k={k})"
                )
                bucket = variants.setdefault(sig, [])
                if moves not in bucket:
                    bucket.append(moves)
    assert set(variants) == set(OLL_TABLE), "OLL variant coverage mismatch"
    return variants


def _build_pll_variants() -> dict[Key, list[list[str]]]:
    """signature -> list of move sequences solving that permutation up to AUF.

    Same construction as ``solver/pll.py``: pre-AUF k baked into the stored
    moves, post-AUF j enumerated for coverage but recovered at runtime by
    :func:`solver.pll.compute_auf`.
    """
    variants: dict[Key, list[list[str]]] = {}
    for case in _unique_cases(PLL_TABLE):
        for alg in [case.alg, *(case.alt or [])]:
            alg_tokens = parse_algorithm(alg)
            for k in range(4):
                moves = AUF_TOKENS[k] + alg_tokens
                for j in range(4):
                    s = apply_moves(
                        CubieState.solved(), invert(moves + AUF_TOKENS[j])
                    )
                    assert ll_is_oriented(s), (
                        f"PLL case {case.id} variant {alg!r}: does not "
                        f"preserve F2L + LL orientation (k={k}, j={j})"
                    )
                    sig = pll_signature(s)
                    entry = PLL_TABLE.get(sig)
                    assert entry is not None and entry[0].id == case.id, (
                        f"PLL case {case.id} variant {alg!r}: lands in "
                        f"{'a skip state' if entry is None else f'case {entry[0].id}'}"
                        f" instead of case {case.id} (k={k}, j={j})"
                    )
                    bucket = variants.setdefault(sig, [])
                    if moves not in bucket:
                        bucket.append(moves)
    assert set(variants) == set(PLL_TABLE), "PLL variant coverage mismatch"
    return variants


#: signature -> uniformly drawable solving-move variants. Built at import;
#: the canonical tables in solver/oll.py / solver/pll.py are NOT touched (the
#: walkthrough keeps teaching the single canonical algorithm per case).
OLL_VARIANTS: dict[Key, list[list[str]]] = _build_oll_variants()
PLL_VARIANTS: dict[Key, list[list[str]]] = _build_pll_variants()


def _build_y_face_map() -> dict[str, str]:
    """Face relabel map of one y rotation, derived from the parser's rotation
    frame (never hand-typed): ``parse_algorithm("y F") == ["R"]`` etc., i.e.
    U/D fixed and F->R->B->L->F."""
    face_map = {f: parse_algorithm("y " + f)[0] for f in "URFDLB"}
    assert face_map["U"] == "U" and face_map["D"] == "D"
    assert [face_map[f] for f in "FRBL"] == ["R", "B", "L", "F"]
    return face_map


_Y_FACE_MAP: dict[str, str] = _build_y_face_map()


def y_relabel(moves: list[str], j: int) -> list[str]:
    """Relabel face-turn tokens through the y^j rotation map (U/D fixed).

    ``y_relabel(A, j)`` applied to solved yields the y^j-conjugate of the
    state A yields — for any F2L-solved last-layer state this is the SAME
    pre/post-AUF-quotiented case class (y acts on the LL slots exactly like
    U, so conjugating by y equals conjugating by U). NOT class-preserving for
    ``vls``: its frame is fixed by the unsolved FR slot, and y-conjugation
    moves that slot (FR -> FL -> ...), so the generator skips relabeling for
    the vls set (verified empirically: every j != 0 conjugate leaves the
    class or the vls shape entirely).
    """
    face_map = {f: f for f in "URFDLB"}
    for _ in range(j % 4):
        face_map = {f: _Y_FACE_MAP[face_map[f]] for f in face_map}
    return [face_map[m[0]] + m[1:] for m in moves]


# --------------------------------------------------------------------------- #
# State + scramble generation (§11.2)
# --------------------------------------------------------------------------- #

#: Module-level rng for un-seeded draws (seed query param overrides in tests).
_RNG = random.Random()


def _random_perm4(rng: random.Random) -> list[int]:
    perm = list(range(4))
    rng.shuffle(perm)
    return perm


def _random_perm4_with_parity(rng: random.Random, parity: int) -> tuple[int, ...]:
    perm = _random_perm4(rng)
    if _perm_parity(tuple(perm)) != parity:
        perm[0], perm[1] = perm[1], perm[0]
    return tuple(perm)


def generate_state(case: TrainerCase, rng: random.Random) -> CubieState:
    """A concrete state in ``case``'s class, randomizing ONLY its free params.

    Perm draws keep sign(corner perm) == sign(edge perm); AUF freedom is
    realized as a random ``U^a · s · U^b`` composition (identity for VLS).
    """
    cp4, ep4 = case.cp4, case.ep4
    if cp4 is None and ep4 is None:  # oll, vls: both LL perms free
        cp4 = tuple(_random_perm4(rng))
        ep4 = _random_perm4_with_parity(rng, _perm_parity(cp4))
    elif ep4 is None:  # coll: edge perm free, parity-consistent with cp
        ep4 = _random_perm4_with_parity(rng, _perm_parity(cp4))
    state = _make_state(cp4=cp4, co4=case.co4, ep4=ep4, eo4=case.eo4)
    if case.set_key == "vls":
        return apply_moves(state, list(VLS_INSERT))  # S = S_target · (R U R')
    return _auf_compose(state, rng.randrange(4), rng.randrange(4))


def _solve_ll(state: CubieState, rng: random.Random) -> list[str]:
    """Trainer-local last-layer solve with variant randomization.

    For VLS states the FR pair is first inserted with the F2L engine (the
    other three slots are already solved and commit empty move lists); the
    OLL and PLL portions then draw UNIFORMLY AT RANDOM among the variant
    tables for the state's signatures, followed by the AUF. Defense in depth
    mirrors ``cfop._verify``: the returned moves are replayed against the
    input state and MUST solve it.
    """
    work = state.copy()
    moves: list[str] = []
    if not f2l_is_solved(work):
        # vls: solve the remaining FR pair via the existing F2L machinery.
        for step in solve_f2l(work):
            work = apply_moves(work, step.moves)
            moves.extend(step.moves)
        assert f2l_is_solved(work), "trainer F2L insert failed"
    sig = oll_signature(work)
    if sig != SOLVED_SIGNATURE:
        pick = rng.choice(OLL_VARIANTS[sig])
        work = apply_moves(work, pick)
        moves.extend(pick)
    psig = pll_signature(work)
    if psig not in SKIP_SIGNATURES:
        pick = rng.choice(PLL_VARIANTS[psig])
        work = apply_moves(work, pick)
        moves.extend(pick)
    auf = compute_auf(work)
    if auf is not None:
        work = apply_moves(work, [auf])
        moves.append(auf)
    # MANDATORY defense in depth: replay from the original state.
    assert is_solved(apply_moves(state.copy(), moves)), (
        "trainer LL solve verification failed: the move list does not solve "
        "the generated state — refusing to emit the scramble"
    )
    return moves


_QUARTER_TURNS = {"": 1, "'": 3, "2": 2}
_TURN_SUFFIX = {1: "", 2: "2", 3: "'"}


def _merge_same_face(moves: list[str]) -> list[str]:
    """Merge/cancel adjacent same-face turns (e.g. ``U2 U`` -> ``U'``).

    Purely cosmetic: the result is the same group element, so class
    membership and replay verification are unaffected. Seams between the
    AUF / variant-algorithm / conjugation segments occasionally emit
    adjacent turns of one face, which read as unpolished scrambles.
    """
    out: list[str] = []
    for token in moves:
        face, turns = token[0], _QUARTER_TURNS[token[1:]]
        if out and out[-1][0] == face:
            turns = (turns + _QUARTER_TURNS[out[-1][1:]]) % 4
            out.pop()
            if turns == 0:
                continue
        out.append(face + _TURN_SUFFIX[turns])
    return out


def generate(
    set_key: str,
    case_id: str | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Draw a scramble (§11.2): pick case, randomize free params, solve.

    ``solution`` = the flat move list of the trainer-local LL solve (variant
    randomization per the module docstring), y^j-conjugated for a random j
    (all sets except ``vls`` — see :func:`y_relabel`); ``scramble`` = its
    inverse. Raises :class:`TrainerError` on an unknown set or case id.
    """
    if set_key not in CASES:
        raise TrainerError("unknown_set", f"Unknown trainer set {set_key!r}.")
    rng = rng if rng is not None else _RNG
    if case_id is None:
        case = rng.choice(CASES[set_key])
    else:
        case = CASE_BY_ID[set_key].get(case_id)
        if case is None:
            raise TrainerError(
                "unknown_case", f"Unknown case {case_id!r} in set {set_key!r}."
            )
    state = generate_state(case, rng)
    flat = _solve_ll(state, rng)  # replay-verified internally
    if set_key != "vls":
        # Whole-scramble y-conjugation: same case class, different tokens.
        # Skipped for vls, whose FR-slot frame does not survive conjugation.
        flat = y_relabel(flat, rng.randrange(4))
    flat = _merge_same_face(flat)  # cosmetic: no "U2 U"-style seams
    return {
        "set": set_key,
        "case_id": case.id,
        "name": case.name,
        "group": case.group,
        "scramble": to_notation(invert(flat)),
        "solution": to_notation(flat),
        "preview": case.preview,
    }


# --------------------------------------------------------------------------- #
# API payload helpers (§11.4)
# --------------------------------------------------------------------------- #


def sets_payload() -> dict[str, Any]:
    """``GET /api/trainer/sets`` body."""
    return {
        "sets": [
            {
                "key": set_key,
                "name": SET_NAMES[set_key],
                "count": FROZEN_COUNTS[set_key],
                "description": SET_DESCRIPTIONS[set_key],
                "groups": GROUPS[set_key],
            }
            for set_key in SET_ORDER
        ]
    }


def cases_payload(set_key: str, group: str | None = None) -> dict[str, Any]:
    """``GET /api/trainer/cases`` body; raises :class:`TrainerError`."""
    if set_key not in CASES:
        raise TrainerError("unknown_set", f"Unknown trainer set {set_key!r}.")
    if group is not None and all(g["key"] != group for g in GROUPS[set_key]):
        raise TrainerError(
            "unknown_group", f"Unknown group {group!r} in set {set_key!r}."
        )
    cases = [
        {"id": c.id, "name": c.name, "group": c.group, "preview": c.preview}
        for c in CASES[set_key]
        if group is None or c.group == group
    ]
    return {"set": set_key, "cases": cases}


def scramble_payload(
    set_key: str, case_id: str | None = None, seed: int | None = None
) -> dict[str, Any]:
    """``GET /api/trainer/scramble`` body; raises :class:`TrainerError`.

    ``seed`` (tests only) makes the draw deterministic; otherwise the
    module-level rng is used.
    """
    rng = random.Random(seed) if seed is not None else _RNG
    return generate(set_key, case_id=case_id, rng=rng)


__all__ = [
    "CASES",
    "CASE_BY_ID",
    "FROZEN_COUNTS",
    "GROUPS",
    "OLL_VARIANTS",
    "PLL_VARIANTS",
    "SET_ORDER",
    "TrainerCase",
    "TrainerError",
    "canonical_key_of_state",
    "cases_payload",
    "generate",
    "generate_state",
    "scramble_payload",
    "sets_payload",
    "y_relabel",
]
