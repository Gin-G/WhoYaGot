#!/usr/bin/env python3
"""Leaderboards: the crowd's list, and each user's own."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.utils import team_map
from database.models import Player, PlayerRating, User, UserPlayerRating, Vote
from database.session import get_db
from schemas import RankingEntry, RankingsOut, to_card
from services.security import current_user

router = APIRouter()

# A rating built from two votes is noise. Hide players below this on the global
# board (their rating still exists and still moves — it just isn't ranked yet).
MIN_VOTES_GLOBAL = 5

# The same idea for one person's board, at a threshold their own voting can
# actually reach: a personal ladder is fed by one voter rather than all of them,
# so the global bar would leave a new board empty for hundreds of picks.
MIN_VOTES_PERSONAL = 3


@router.get("", response_model=RankingsOut)
def rankings(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_votes: int = Query(MIN_VOTES_GLOBAL, ge=0),
    db: Session = Depends(get_db),
):
    """The overall list, across every user's votes."""
    league = league.lower()

    q = (
        db.query(Player, PlayerRating)
        .join(PlayerRating, PlayerRating.player_id == Player.id)
        .filter(Player.league == league, Player.active.is_(True))
        .filter(PlayerRating.votes >= min_votes)
    )
    if position:
        q = q.filter(Player.position == position.upper())

    total = q.count()
    rows = q.order_by(PlayerRating.rating.desc()).offset(offset).limit(limit).all()
    teams = team_map(db, league)

    return RankingsOut(
        league=league,
        position=position.upper() if position else None,
        scope="global",
        total=total,
        entries=[
            RankingEntry(
                rank=offset + i + 1,
                player=to_card(player, teams.get(player.team_abbr), rating),
            )
            for i, (player, rating) in enumerate(rows)
        ],
    )


@router.get("/me", response_model=RankingsOut)
def my_rankings(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_votes: int = Query(MIN_VOTES_PERSONAL, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """The signed-in user's own list, from their votes alone."""
    league = league.lower()

    q = (
        db.query(Player, UserPlayerRating)
        .join(UserPlayerRating, UserPlayerRating.player_id == Player.id)
        .filter(UserPlayerRating.user_id == user.id, UserPlayerRating.league == league)
        .filter(UserPlayerRating.votes >= min_votes)
    )
    if position:
        q = q.filter(Player.position == position.upper())

    total = q.count()
    # Paged in Python rather than SQL: the crowd's positions have to be worked
    # out over the whole board, not the slice being returned, or the gap on
    # page two would be measured against fifty players instead of the lot. A
    # personal board is a few hundred rows, so this costs nothing worth saving.
    ranked = q.order_by(UserPlayerRating.rating.desc()).all()
    rows = ranked[offset : offset + limit]
    teams = team_map(db, league)
    ranked_ids = [player.id for player, _ in ranked]
    crowd = _crowd_places(db, league, ranked_ids)
    # Both of these are worked out over the whole board rather than the page,
    # for the same reason: a place is settled by its neighbours, and on a page
    # boundary one of those neighbours is on the other page.
    settled = _settled_ranks(db, user.id, league, ranked_ids)

    return RankingsOut(
        league=league,
        position=position.upper() if position else None,
        scope="personal",
        total=total,
        settled=len(settled),
        entries=[
            RankingEntry(
                rank=offset + i + 1,
                # Positive means the voter has him higher than the crowd does.
                versus_crowd=(
                    crowd[player.id] - (offset + i + 1) if player.id in crowd else None
                ),
                locked=player.id in settled,
                player=to_card(player, teams.get(player.team_abbr), rating),
            )
            for i, (player, rating) in enumerate(rows)
        ],
    )


def _components(edges: list[list[int]], n: int) -> list[int]:
    """Strongly connected components, Tarjan's, iterative to survive a deep board.

    Components come out in reverse topological order, so every edge between two
    of them runs from a higher id to a lower one. `_settled_ranks` leans on that
    to sweep reachability in one pass.
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


def _settled_ranks(
    db: Session, user_id: int, league: str, ranked_ids: list[int]
) -> set[int]:
    """Which of these players sit at a place the voter's own picks have fixed.

    A rating is an estimate: it will happily order two players who have never
    met, and it keeps drifting as neighbouring results come in. A *place* is
    settled when no further voting can move it — when the voter has actually
    shown, by their own picks, that this player belongs under the one above him
    and over the one below. Take Bijan over Gibbs and, if Gibbs is second, first
    place stops being an inference and becomes a result.

    Shown, not necessarily played: picks chain, so beating a player who beat the
    man below settles the same order a direct matchup would.

    Contradictions do not settle anything. Take A over B, B over C and C over A
    and there is no order to fix — that is a disagreement with yourself, and the
    three of them stay open however many times they are dealt. Condensing the
    graph into strongly connected components is what keeps a cycle like that
    from reading as proof in both directions at once.
    """
    n = len(ranked_ids)
    if n < 2:
        return set()

    place = {player_id: i for i, player_id in enumerate(ranked_ids)}
    seen: set[tuple[int, int]] = set()
    edges: list[list[int]] = [[] for _ in range(n)]
    votes = (
        db.query(Vote.winner_id, Vote.loser_id)
        .filter(Vote.user_id == user_id, Vote.league == league)
        .all()
    )
    for winner_id, loser_id in votes:
        won, lost = place.get(winner_id), place.get(loser_id)
        # Votes on players the board no longer carries say nothing about the
        # order of the players it does.
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

    settled = set()
    for i, player_id in enumerate(ranked_ids):
        if sizes[comp[i]] > 1:
            continue
        above = i == 0 or (reach[comp[i - 1]] >> comp[i]) & 1
        below = i == n - 1 or (reach[comp[i]] >> comp[i + 1]) & 1
        if above and below:
            settled.add(player_id)
    return settled


def _crowd_places(db: Session, league: str, player_ids: list[int]) -> dict[int, int]:
    """Where the crowd puts each of these players, ranked among themselves.

    Ranked over exactly the players handed in, rather than read off the global
    board. The two boards do not hold the same people — the crowd's asks for
    five votes and a personal one for three — so lifting positions straight off
    each list would report a gap wherever the lists merely differ in who they
    contain. With one voter and no disagreement possible at all, that alone put
    the two 3.8 places apart on average. Ranking both over the same players
    leaves only what the ratings actually say.
    """
    if not player_ids:
        return {}

    rated = (
        db.query(PlayerRating.player_id)
        .filter(PlayerRating.league == league, PlayerRating.player_id.in_(player_ids))
        .order_by(PlayerRating.rating.desc())
        .all()
    )
    return {player_id: place for place, (player_id,) in enumerate(rated, start=1)}


@router.get("/head-to-head")
def head_to_head(
    player_a: int = Query(..., description="Player ID"),
    player_b: int = Query(..., description="Player ID"),
    db: Session = Depends(get_db),
):
    """How the crowd has split on one specific pairing."""
    from database.models import Vote

    a = db.get(Player, player_a)
    b = db.get(Player, player_b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="unknown player")

    a_wins = (
        db.query(Vote).filter(Vote.winner_id == player_a, Vote.loser_id == player_b).count()
    )
    b_wins = (
        db.query(Vote).filter(Vote.winner_id == player_b, Vote.loser_id == player_a).count()
    )
    total = a_wins + b_wins

    return {
        "player_a": {"id": a.id, "name": a.name, "wins": a_wins},
        "player_b": {"id": b.id, "name": b.name, "wins": b_wins},
        "total_votes": total,
        "player_a_pct": round(a_wins / total, 3) if total else None,
    }
