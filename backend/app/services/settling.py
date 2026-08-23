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


def _edges(order: list[int], beats: Iterable[tuple[int, int]]) -> list[list[int]]:
    """Who the voter has put over whom, one edge per pair, by weight of picks.

    A pair judged more than once is settled by the balance of it rather than by
    the existence of a single result either way: three for Allen and one for
    Maye is a voter who has made their mind up, not a contradiction. Dead level
    is the real contradiction, and gets no edge at all.

    Picks naming anyone outside `order` are dropped — they say nothing about the
    order of the players it does hold.
    """
    edges: list[list[int]] = [[] for _ in range(len(order))]
    for (winner, loser), margin in _records(order, beats).items():
        edges[winner].append(loser)
    return edges


def _records(
    order: list[int], beats: Iterable[tuple[int, int]]
) -> dict[tuple[int, int], int]:
    """Each judged pair as (winner, loser) -> how far clear, by index.

    Three for Allen and one for Maye is one entry, Allen by two. Dead level
    leaves the pair out: that is the one case where the picks really do say
    nothing.
    """
    place = {player_id: i for i, player_id in enumerate(order)}
    net: dict[tuple[int, int], int] = {}
    for winner_id, loser_id in beats:
        won, lost = place.get(winner_id), place.get(loser_id)
        if won is None or lost is None or won == lost:
            continue
        pair = (won, lost) if won < lost else (lost, won)
        net[pair] = net.get(pair, 0) + (1 if won < lost else -1)

    return {
        ((low, high) if balance > 0 else (high, low)): abs(balance)
        for (low, high), balance in net.items()
        if balance
    }


def order_by_picks(
    seeded: list[int],
    strength: dict[int, float],
    beats: Iterable[tuple[int, int]],
) -> list[int]:
    """Order these players so nobody sits below a player they were taken over.

    A rating is a summary, and summaries lose arguments. Take Allen over Maye
    three times and then watch Maye beat four other people: the ratings have Maye
    ahead on strength of schedule, while the one question the voter actually
    answered about the two of them says the opposite. A board that shows Maye
    first is not reporting their opinion back to them.

    So the picks lead and the rating follows. This is a topological order of the
    pick graph, and where the picks say nothing — most pairs, on most boards —
    the rating breaks the tie, so the familiar order survives everywhere it is
    not actually contradicted.

    Players tangled in a contradiction cannot be separated by their picks, so
    the group keeps its place as a block and sorts by rating inside.
    """
    n = len(seeded)
    if n < 2:
        return list(seeded)

    records = _records(seeded, beats)
    edges: list[list[int]] = [[] for _ in range(n)]
    for winner, loser in records:
        edges[winner].append(loser)
    comp = _components(edges, n)
    count = max(comp) + 1

    members: list[list[int]] = [[] for _ in range(count)]
    for i, c in enumerate(comp):
        members[c].append(i)

    following: list[set[int]] = [set() for _ in range(count)]
    waiting = [0] * count
    for u in range(n):
        for v in edges[u]:
            if comp[u] != comp[v] and comp[v] not in following[comp[u]]:
                following[comp[u]].add(comp[v])
                waiting[comp[v]] += 1

    def rating(i: int) -> float:
        return strength.get(seeded[i], 0.0)

    # Inside a knot the picks contradict each other and no order can honour all
    # of them, so honour the ones held most firmly: each player scores the
    # margins he won by against the rest of the knot, less the margins he lost
    # by. Taking Allen over Maye three times outweighs a single pick against
    # him somewhere down a chain, and the order breaks at the weak link rather
    # than the strong one. Outside a knot this is dead weight and every group
    # scores zero.
    standing = [0] * n
    for (winner, loser), margin in records.items():
        if comp[winner] == comp[loser]:
            standing[winner] += margin
            standing[loser] -= margin

    own = [max(rating(i) for i in members[c]) for c in range(count)]

    # What a group has to outrank, not merely what it is rated. A player who
    # took someone rated far above him has to come out above that player, so he
    # belongs at that height on the board — otherwise everyone in between floats
    # over him on rating alone and the board reads as though the pick never
    # happened. Successors always carry a lower component id, so one pass upward
    # finds them already done.
    height = list(own)
    for c in range(count):
        for d in following[c]:
            height[c] = max(height[c], height[d])

    import heapq

    ready = [(-height[c], -own[c], c) for c in range(count) if waiting[c] == 0]
    heapq.heapify(ready)
    out: list[int] = []
    while ready:
        _, _, c = heapq.heappop(ready)
        for i in sorted(members[c], key=lambda i: (standing[i], rating(i)), reverse=True):
            out.append(seeded[i])
        for d in following[c]:
            waiting[d] -= 1
            if waiting[d] == 0:
                heapq.heappush(ready, (-height[d], -own[d], d))
    return out


def analyse(order: list[int], beats: Iterable[tuple[int, int]]) -> Settling:
    """Read `order` against the picks in `beats`, each a (winner, loser) pair.

    Picks naming anyone outside `order` are dropped: they say nothing about the
    order of the players it does hold, and a chain that only connects through a
    missing player is not a chain here.
    """
    n = len(order)
    if n < 2:
        return Settling(set(), [])

    records = _records(order, beats)
    edges: list[list[int]] = [[] for _ in range(n)]
    for winner, loser in records:
        edges[winner].append(loser)
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
    #
    # A knot is a dead end rather than a link: everyone inside one reaches
    # everyone else there, so a chain allowed to pass through would come out
    # the far side proving whatever it liked. Beating a player caught in a
    # contradiction says he is behind you, and nothing about who is behind him.
    reach = [0] * count
    for c in range(count):
        bits = 0
        for d in successors[c]:
            bits |= 1 << d
            if sizes[d] == 1:
                bits |= reach[d]
        reach[c] = bits

    def established(i: int) -> bool:
        """Has the voter shown order[i] over order[i + 1]?

        A result between the two of them is the whole answer, whatever else
        either is tangled in. Failing that it takes a chain, and a chain is
        only worth as much as its weakest link: one that starts or ends in a
        knot proves nothing about the individual standing in it, since his
        fellows there reach him both ways round.
        """
        if (i, i + 1) in records:
            return True
        if comp[i] == comp[i + 1] or sizes[comp[i]] > 1 or sizes[comp[i + 1]] > 1:
            return False
        return bool((reach[comp[i]] >> comp[i + 1]) & 1)

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
