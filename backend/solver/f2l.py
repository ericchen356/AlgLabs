"""F2L solver: greedy slot order, per-slot IDA* with PDB heuristics (§7).

Slots and their pairs (corner cubie id, edge cubie id):

    FR = (DFR=4, FR=8)   FL = (DLF=5, FL=9)   BL = (DBL=6, BL=10)   BR = (DRB=7, BR=11)

Each round, every remaining unsolved slot is solved with IDA* and the
shortest solution is committed (ties broken by the fixed order FR, FL, BL,
BR). The goal of each search is: target pair in place + oriented AND cross
intact AND all previously committed slots intact. Move set: the 15 non-D
face turns.

Search state = 12 small (slot, orientation) codes — the 4 cross edges, the
4 F2L corners and the 4 F2L edges — advanced by per-move lookup tables
derived from ``cube.moves.TABLE``. Heuristic = max of

* the cross BFS distance table (:mod:`solver.cross`, admissible since it is
  computed over the larger 18-move set),
* the target slot's pair PDB, and
* the pair PDBs of every already-committed slot,

where each pair PDB is a BFS-from-solved table over (corner slot, ori) x
(edge slot, eo) = 24 x 24 = 576 codes for that slot's pair, over the 15-move
set. Move pruning: never turn the same face twice in a row, and for
opposite-face pairs a fixed order is enforced (the higher-index face of an
axis may be followed by the lower-index one but not vice versa), killing
transposition duplicates.

The heuristic is 0 exactly at goal states, so the goal test is ``h == 0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cube.facelet import CubieState, N_CORNERS, N_EDGES
from cube.moves import MOVE_TOKENS, TABLE

from solver.cross import EDGE_ACTION, SOLVED_CROSS_CODES, cross_codes, _distance_table

#: Fixed slot order (also the tie-break order): name -> (corner id, edge id).
SLOT_PAIRS: dict[str, tuple[int, int]] = {
    "FR": (4, 8),
    "FL": (5, 9),
    "BL": (6, 10),
    "BR": (7, 11),
}
SLOT_ORDER: tuple[str, ...] = ("FR", "FL", "BL", "BR")

#: Anything deeper than ~14 means a broken goal/heuristic, not a hard case.
_MAX_BOUND = 16


@dataclass
class F2lStep:
    """One committed F2L insertion."""

    slot: str  # 'FR' | 'FL' | 'BL' | 'BR'
    moves: list[str] = field(default_factory=list)  # face-turn tokens, no D
    pair: tuple[int, int] = (0, 0)  # (corner cubie id, edge cubie id)


# --------------------------------------------------------------------------- #
# Move action tables (corners; edge tables come from solver.cross)
# --------------------------------------------------------------------------- #


def _build_corner_actions() -> dict[str, tuple[int, ...]]:
    """Per move: 24-entry table mapping (slot*3+ori) -> new (slot*3+ori)."""
    actions: dict[str, tuple[int, ...]] = {}
    for move, t in TABLE.items():
        new_slot = [0] * N_CORNERS
        for i, j in enumerate(t.cp):
            new_slot[j] = i
        tbl = [0] * 24
        for j in range(N_CORNERS):
            i = new_slot[j]
            for o in (0, 1, 2):
                tbl[j * 3 + o] = i * 3 + ((o + t.co[i]) % 3)
        actions[move] = tuple(tbl)
    return actions


CORNER_ACTION: dict[str, tuple[int, ...]] = _build_corner_actions()

#: The 15 non-D face turns, as (face_index, token, edge_table, corner_table).
#: face_index is the index in "URFDLB"; opposite faces differ by 3.
_FACES = "URFDLB"
MOVES_15: tuple[str, ...] = tuple(m for m in MOVE_TOKENS if m[0] != "D")
_SEARCH_MOVES: tuple[tuple[int, str, tuple[int, ...], tuple[int, ...]], ...] = tuple(
    (_FACES.index(m[0]), m, EDGE_ACTION[m], CORNER_ACTION[m]) for m in MOVES_15
)

#: Solved (slot, ori) codes per slot index 0..3 (FR, FL, BL, BR).
_SOLVED_CORNER = tuple(SLOT_PAIRS[s][0] * 3 for s in SLOT_ORDER)  # (12, 15, 18, 21)
_SOLVED_EDGE = tuple(SLOT_PAIRS[s][1] * 2 for s in SLOT_ORDER)  # (16, 18, 20, 22)


# --------------------------------------------------------------------------- #
# Pair pattern databases (576 entries per slot, over the 15-move set)
# --------------------------------------------------------------------------- #


def _build_pair_pdb(slot_idx: int) -> bytes:
    """BFS distances from the solved pair over (corner code, edge code)."""
    dist = bytearray([255]) * (24 * 24)
    start = (_SOLVED_CORNER[slot_idx], _SOLVED_EDGE[slot_idx])
    dist[start[0] * 24 + start[1]] = 0
    frontier = [start]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for c, e in frontier:
            for _, _, et, ct in _SEARCH_MOVES:
                t = (ct[c], et[e])
                i = t[0] * 24 + t[1]
                if dist[i] == 255:
                    dist[i] = d
                    nxt.append(t)
        frontier = nxt
    return bytes(dist)


#: pair PDBs, indexed by slot index then corner_code * 24 + edge_code.
_PAIR_PDB: tuple[bytes, ...] = tuple(_build_pair_pdb(i) for i in range(4))


# --------------------------------------------------------------------------- #
# Search state: 12 codes
#   s[0:4]  cross edge codes (cubies 4..7)      -- edge (slot*2+eo) codes
#   s[4:8]  F2L corner codes (cubies 4..7)      -- corner (slot*3+ori) codes
#   s[8:12] F2L edge codes (cubies 8..11)       -- edge (slot*2+eo) codes
# --------------------------------------------------------------------------- #


def _abstract(state: CubieState) -> tuple[int, ...]:
    corner = [-1] * 4
    for slot in range(N_CORNERS):
        cubie = state.cp[slot]
        if 4 <= cubie <= 7:
            corner[cubie - 4] = slot * 3 + state.co[slot]
    edge = [-1] * 4
    for slot in range(N_EDGES):
        cubie = state.ep[slot]
        if 8 <= cubie <= 11:
            edge[cubie - 8] = slot * 2 + state.eo[slot]
    return cross_codes(state) + tuple(corner) + tuple(edge)


def _apply(s: tuple[int, ...], et: tuple[int, ...], ct: tuple[int, ...]) -> tuple[int, ...]:
    return (
        et[s[0]], et[s[1]], et[s[2]], et[s[3]],
        ct[s[4]], ct[s[5]], ct[s[6]], ct[s[7]],
        et[s[8]], et[s[9]], et[s[10]], et[s[11]],
    )


def _ida_star(start: tuple[int, ...], slots: tuple[int, ...]) -> list[str]:
    """Shortest 15-move-set sequence solving cross + all pairs in ``slots``.

    ``slots`` are slot indices (0..3); the last one is the new target, the
    rest are committed slots that must be restored by the goal too (they are
    all treated identically: solved-in-goal and PDB-in-heuristic).
    """
    cross_dist = _distance_table()
    pdbs = [(4 + i, 8 + i, _PAIR_PDB[i]) for i in slots]

    def heur(s: tuple[int, ...]) -> int:
        h = cross_dist[((s[0] * 24 + s[1]) * 24 + s[2]) * 24 + s[3]]
        for ci, ei, pdb in pdbs:
            v = pdb[s[ci] * 24 + s[ei]]
            if v > h:
                h = v
        return h

    path: list[str] = []

    def search(s: tuple[int, ...], g: int, bound: int, prev_face: int) -> int:
        h = heur(s)
        if h == 0:
            return -1  # goal: every heuristic component is 0 exactly at goal
        f = g + h
        if f > bound:
            return f
        best = 255
        for face, token, et, ct in _SEARCH_MOVES:
            # No same face twice in a row; for an opposite-face pair only the
            # order lower-index-first is allowed (kills U D vs D U dupes).
            if prev_face >= 0 and face % 3 == prev_face % 3 and face >= prev_face:
                continue
            path.append(token)
            t = search(_apply(s, et, ct), g + 1, bound, face)
            if t == -1:
                return -1
            path.pop()
            if t < best:
                best = t
        return best

    bound = heur(start)
    while True:
        if bound > _MAX_BOUND:  # pragma: no cover - bug detector
            raise RuntimeError(
                f"IDA* exceeded depth {_MAX_BOUND} for slots {slots}; "
                "goal or heuristic is broken."
            )
        t = search(start, 0, bound, -1)
        if t == -1:
            return list(path)
        bound = t


def _slot_solved(s: tuple[int, ...], i: int) -> bool:
    return s[4 + i] == _SOLVED_CORNER[i] and s[8 + i] == _SOLVED_EDGE[i]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def solve_f2l(state_after_cross: CubieState) -> list[F2lStep]:
    """Solve the four F2L pairs greedily; returns the 4 committed steps.

    ``state_after_cross`` must have the cross solved. Each round, every
    remaining slot is solved with IDA* and the shortest solution is committed
    (ties: fixed order FR, FL, BL, BR). Committed steps' moves use only the
    15 non-D face turns; an already-solved slot commits an empty move list.
    """
    s = _abstract(state_after_cross)
    if s[0:4] != SOLVED_CROSS_CODES:
        raise ValueError("solve_f2l requires a state with the cross solved.")

    steps: list[F2lStep] = []
    committed: list[int] = []
    remaining = list(range(4))
    while remaining:
        best_slot = -1
        best_moves: list[str] | None = None
        for i in remaining:
            moves = _ida_star(s, tuple(committed) + (i,))
            if best_moves is None or len(moves) < len(best_moves):
                best_slot, best_moves = i, moves
        assert best_moves is not None
        for token in best_moves:
            s = _apply(s, EDGE_ACTION[token], CORNER_ACTION[token])
        committed.append(best_slot)
        remaining.remove(best_slot)
        name = SLOT_ORDER[best_slot]
        steps.append(F2lStep(slot=name, moves=best_moves, pair=SLOT_PAIRS[name]))
    return steps


def is_f2l_solved(state: CubieState) -> bool:
    """True iff the first two layers are solved (corners 4-7, edges 4-11)."""
    return (
        all(state.cp[i] == i and state.co[i] == 0 for i in range(4, 8))
        and all(state.ep[i] == i and state.eo[i] == 0 for i in range(4, 12))
    )


__all__ = [
    "F2lStep",
    "SLOT_PAIRS",
    "SLOT_ORDER",
    "MOVES_15",
    "CORNER_ACTION",
    "solve_f2l",
    "is_f2l_solved",
]
