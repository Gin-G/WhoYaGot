#!/usr/bin/env python3
"""What a voter's own picks have and have not fixed about an order.

A rating is an estimate. It will order two players who have never met, and it
keeps drifting as results land around them. A *place* is something stronger: it
is settled when no further voting can move it, which happens once the voter has
shown this player over the one below him and under the one above.

Shown, not necessarily played. Picks chain, so beating the man who beat him
settles the same order a direct matchup would.

Contradictions settle nothing. Take A over B, B over C and C over A and there is
no order there to fix. Condensing the pick graph into strongly connected
components is what stops a cycle reading as proof in both directions at once —
everything inside one is contested, and stays contested however often it is
dealt, because another vote only adds an edge and never removes one.

Two callers want this: the personal board, to say which places have stopped
moving, and the matchmaker, to deal the pairs that would settle the most.
"""

from typing import Iterable, NamedTuple


class Settling(NamedTuple):
    """The read on one ordering.

    `settled` holds the ids whose place is fixed. `open_boundaries` holds the
    indices i where the order of `order[i]` against `order[i + 1]` has not been
    established and could still be — the gaps worth dealing. A boundary inside a
    cycle is left out of both: it is not settled, and dealing it again would not
    help.
    """

    settled: set[int]
    open_boundaries: list[int]

    def gain(self, i: int, last: int) -> int:
        """How many places settle if boundary `i` is resolved: 0, 1 or 2.

        A boundary at the edge of an already-settled run is worth more than one
        in open country, because the places either side of it are only waiting
        on this one answer.
        """
        established = set(range(last + 1)) - set(self.open_boundaries)
        above = i == 0 or (i - 1) in established
        below = i + 1 > last or (i + 1) in established
        return int(above) + int(below)


def _components(edges: list[list[int]], n: int) -> list[int]:
    """Strongly connected components, Tarjan's, iterative to survive a deep board.

    Components come out in reverse topological order, so every edge between two
    of them runs from a higher id to a lower one. `analyse` leans on that to
    sweep reachability in a single pass.
    """
    order = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack: list[int] = []
    comp = [-1] * n
    counter = 0
    made = 0

    for root in range(n):
        if order[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            v, start = work[-1]
            if start == 0:
                order[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on_stack[v] = True

            descended = False
            for i in range(start, len(edges[v])):
                w = edges[v][i]
                if order[w] == -1:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    descended = True
                    break
                if on_stack[w]:
                    low[v] = min(low[v], order[w])
            if descended:
                continue

            if low[v] == order[v]:
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp[w] = made
                    if w == v:
                        break
                made += 1

            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])

    return comp


def analyse(order: list[int], beats: Iterable[tuple[int, int]]) -> Settling:
    """Read `order` against the picks in `beats`, each a (winner, loser) pair.

    Picks naming anyone outside `order` are dropped: they say nothing about the
    order of the players it does hold, and a chain that only connects through a
    missing player is not a chain here.
    """
    n = len(order)
    if n < 2:
        return Settling(set(), [])

    place = {player_id: i for i, player_id in enumerate(order)}
    edges: list[list[int]] = [[] for _ in range(n)]
    seen: set[tuple[int, int]] = set()
    for winner_id, loser_id in beats:
        won, lost = place.get(winner_id), place.get(loser_id)
        if won is None or lost is None or won == lost or (won, lost) in seen:
            continue
        seen.add((won, lost))
        edges[won].append(lost)

    comp = _components(edges, n)
    count = max(comp) + 1

    sizes = [0] * count
    for c in comp:
        sizes[c] += 1

    successors: list[set[int]] = [set() for _ in range(count)]
    for u in range(n):
        for v in edges[u]:
            if comp[u] != comp[v]:
                successors[comp[u]].add(comp[v])

    # Who each component can reach, as a bitmask. Successors always carry a
    # lower id than the component pointing at them, so one pass upward finds
    # every component's successors already summed.
    reach = [0] * count
    for c in range(count):
        bits = 0
        for d in successors[c]:
            bits |= (1 << d) | reach[d]
        reach[c] = bits

    def established(i: int) -> bool:
        """Has the voter shown order[i] over order[i + 1]?"""
        return comp[i] != comp[i + 1] and bool((reach[comp[i]] >> comp[i + 1]) & 1)

    settled = set()
    for i, player_id in enumerate(order):
        if sizes[comp[i]] > 1:
            continue
        if (i == 0 or established(i - 1)) and (i == n - 1 or established(i)):
            settled.add(player_id)

    # A boundary inside a cycle is dropped: another vote cannot break it, since
    # the contradicting pick stays on record either way. Those are unpicked on
    # the picks screen, not answered again.
    boundaries = [
        i for i in range(n - 1) if comp[i] != comp[i + 1] and not established(i)
    ]
    return Settling(settled, boundaries)
