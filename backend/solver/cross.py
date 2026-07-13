"""Cross solver: BFS over the 4 D-layer edges abstraction (CONTRACTS.md §7).

Abstraction: the positions + orientations of the 4 cross edge cubies
(DR=4, DF=5, DL=6, DB=7), encoded as one (slot, eo) code per cubie
(``code = slot * 2 + eo`` in ``0..23``). The full abstract space is
``24**4 = 331776`` codes of which ``12*11*10*9*16 = 190080`` are reachable.

A full BFS distance table from the solved abstraction is computed once (over
all 18 face turns, using move actions derived from ``cube.moves.TABLE``) and
cached under ``solver/cache/`` (gitignored; regenerated when missing).

* :func:`solve_cross` walks the distance table downhill from the current
  abstract state, which is exactly the BFS-optimal solution (length equals
  the BFS distance, always <= 8 — the cross "God's number").
* :func:`cross_distance` exposes the table as a heuristic for f2l.py.
"""

from __future__ import annotations

from pathlib import Path

from cube.facelet import CubieState, N_EDGES
from cube.moves import MOVE_TOKENS, TABLE

#: The 4 cross edge cubies (and their home slots): DR, DF, DL, DB.
CROSS_EDGES: tuple[int, ...] = (4, 5, 6, 7)

#: Abstract codes of the solved cross: cubie c in slot c with eo=0.
SOLVED_CROSS_CODES: tuple[int, ...] = tuple(c * 2 for c in CROSS_EDGES)

N_ABSTRACT = 24**4

_CACHE_DIR = Path(__file__).resolve().parent / "cache"
_CROSS_DIST_FILE = _CACHE_DIR / "cross_dist.bin"


# --------------------------------------------------------------------------- #
# Move action on a single (edge slot, eo) code, derived from cube.moves.TABLE
# --------------------------------------------------------------------------- #


def _build_edge_actions() -> dict[str, tuple[int, ...]]:
    """For each move: 24-entry table mapping (slot*2+eo) -> new (slot*2+eo).

    Applying move ``m`` to state ``s`` gives ``s'.ep[i] = s.ep[m.ep[i]]`` and
    ``s'.eo[i] = (s.eo[m.ep[i]] + m.eo[i]) % 2`` (§3.3). So the cubie sitting
    in slot ``j`` moves to the slot ``i`` with ``m.ep[i] == j`` and picks up
    orientation delta ``m.eo[i]``.
    """
    actions: dict[str, tuple[int, ...]] = {}
    for move, t in TABLE.items():
        new_slot = [0] * N_EDGES
        for i, j in enumerate(t.ep):
            new_slot[j] = i
        tbl = [0] * 24
        for j in range(N_EDGES):
            i = new_slot[j]
            for o in (0, 1):
                tbl[j * 2 + o] = i * 2 + ((o + t.eo[i]) % 2)
        actions[move] = tuple(tbl)
    return actions


#: move token -> 24-entry (slot, eo) code action table (all 18 moves).
EDGE_ACTION: dict[str, tuple[int, ...]] = _build_edge_actions()

_ACTIONS_18: tuple[tuple[str, tuple[int, ...]], ...] = tuple(
    (m, EDGE_ACTION[m]) for m in MOVE_TOKENS
)


# --------------------------------------------------------------------------- #
# Abstraction / encoding
# --------------------------------------------------------------------------- #


def cross_codes(state: CubieState) -> tuple[int, int, int, int]:
    """Abstract state: the (slot*2+eo) code of each cross edge cubie 4..7."""
    codes = [-1, -1, -1, -1]
    for slot in range(N_EDGES):
        cubie = state.ep[slot]
        if 4 <= cubie <= 7:
            codes[cubie - 4] = slot * 2 + state.eo[slot]
    if -1 in codes:
        raise ValueError("State is missing a cross edge cubie (invalid ep).")
    return codes[0], codes[1], codes[2], codes[3]


def _encode(codes: tuple[int, int, int, int]) -> int:
    return ((codes[0] * 24 + codes[1]) * 24 + codes[2]) * 24 + codes[3]


# --------------------------------------------------------------------------- #
# BFS distance table (computed once, cached on disk)
# --------------------------------------------------------------------------- #


def _build_distance_table() -> bytearray:
    dist = bytearray([255]) * N_ABSTRACT
    start = SOLVED_CROSS_CODES
    dist[_encode(start)] = 0
    frontier: list[tuple[int, ...]] = [start]
    d = 0
    tables = [tbl for _, tbl in _ACTIONS_18]
    while frontier:
        d += 1
        nxt: list[tuple[int, ...]] = []
        for s in frontier:
            a, b, c, e = s
            for tbl in tables:
                t = (tbl[a], tbl[b], tbl[c], tbl[e])
                i = ((t[0] * 24 + t[1]) * 24 + t[2]) * 24 + t[3]
                if dist[i] == 255:
                    dist[i] = d
                    nxt.append(t)
        frontier = nxt
    # Self-checks: known state count and diameter of the cross abstraction.
    reachable = sum(1 for v in dist if v != 255)
    assert reachable == 12 * 11 * 10 * 9 * 16, reachable
    assert d - 1 == 8, d - 1  # cross God's number is 8
    return dist


_DIST: bytearray | None = None


def _distance_table() -> bytearray:
    """The BFS-from-solved distance table, loading/creating the disk cache."""
    global _DIST
    if _DIST is not None:
        return _DIST
    if _CROSS_DIST_FILE.is_file():
        data = _CROSS_DIST_FILE.read_bytes()
        if len(data) == N_ABSTRACT:
            _DIST = bytearray(data)
            return _DIST
    dist = _build_distance_table()
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CROSS_DIST_FILE.with_suffix(".bin.tmp")
    tmp.write_bytes(bytes(dist))
    tmp.replace(_CROSS_DIST_FILE)
    _DIST = dist
    return _DIST


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def cross_distance(state: CubieState) -> int:
    """Optimal number of face turns to solve the cross from ``state``."""
    d = _distance_table()[_encode(cross_codes(state))]
    if d == 255:
        raise ValueError("Unreachable cross configuration (invalid state).")
    return d


def is_cross_solved(state: CubieState) -> bool:
    """True iff all 4 cross edges are in place and oriented."""
    return all(state.ep[s] == s and state.eo[s] == 0 for s in CROSS_EDGES)


def solve_cross(state: CubieState) -> list[str]:
    """Optimal cross solution as face-turn tokens ([] if already solved).

    Walks the precomputed BFS distance table downhill (each move reduces the
    distance by exactly 1), so ``len(result) == cross_distance(state) <= 8``.
    """
    dist = _distance_table()
    codes = cross_codes(state)
    d = dist[_encode(codes)]
    if d == 255:
        raise ValueError("Unreachable cross configuration (invalid state).")
    moves: list[str] = []
    while d > 0:
        for move, tbl in _ACTIONS_18:
            t = (tbl[codes[0]], tbl[codes[1]], tbl[codes[2]], tbl[codes[3]])
            if dist[_encode(t)] == d - 1:
                moves.append(move)
                codes = t
                d -= 1
                break
        else:  # pragma: no cover - impossible with a consistent BFS table
            raise RuntimeError("BFS distance table is inconsistent.")
    return moves


__all__ = [
    "CROSS_EDGES",
    "SOLVED_CROSS_CODES",
    "EDGE_ACTION",
    "cross_codes",
    "cross_distance",
    "is_cross_solved",
    "solve_cross",
]
