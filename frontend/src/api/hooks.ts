import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

/** Asks for no position filter, as opposed to saying nothing at all. */
const MIX = 'mix'
import type { League, Matchup, Picks, RankingEntry, Rankings, VoteResult } from './types'

/**
 * A page of a list. Small enough to paint immediately on a phone, big enough
 * that a few hundred rows is two or three reaches rather than a dozen. Both
 * endpoints will serve up to 500, so these are a rendering budget rather than
 * a limit imposed from the other side.
 */
const RANKINGS_PAGE = 100
const PICKS_PAGE = 100

/**
 * Where the next page starts, or undefined once the list is exhausted.
 *
 * A short page means the end, whatever the count says. Checking that as well
 * as the running total stops a list that shrinks underneath us — someone
 * undoes a pick, players drop back below the vote threshold — from asking for
 * the same offset forever.
 */
function nextOffset<T extends { total: number }>(
  pages: T[],
  size: number,
  count: (page: T) => number,
): number | undefined {
  const last = pages[pages.length - 1]
  if (count(last) < size) return undefined
  const loaded = pages.reduce((n, page) => n + count(page), 0)
  return loaded < last.total ? loaded : undefined
}

export function useLeagues() {
  return useQuery({
    queryKey: ['leagues'],
    queryFn: async () => (await apiClient.get<League[]>('/leagues')).data,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * The current pair.
 *
 * Fetched once and then advanced by the vote mutation, which returns the
 * following matchup in the same response — so a pick never costs a round trip
 * before the next pair can render.
 */
export function useMatchup(league: string, position: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['matchup', league, position],
    queryFn: async () => {
      const { data } = await apiClient.get<Matchup>('/matchups/next', {
        params: { league, ...(position ? { position } : {}) },
      })
      return data
    },
    enabled,
    // A matchup is single-use; refetching one on window focus would discard
    // the pair the voter is looking at.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: 1,
  })
}

export function useVote(league: string, position: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (vars: { matchupId: string; winnerId: number }) => {
      const { data } = await apiClient.post<VoteResult>(
        '/matchups/vote',
        { matchup_id: vars.matchupId, winner_id: vars.winnerId },
        // The follow-up comes from what the voter has selected, not from the
        // pair they were just dealt. Without this a mixed session pins itself
        // to whichever position the first same-position pair happened to be.
        { params: { next_position: position ?? MIX } },
      )
      return data
    },
    onSuccess: (result) => {
      if (result.next) {
        queryClient.setQueryData(['matchup', league, position], result.next)
      } else {
        void queryClient.invalidateQueries({ queryKey: ['matchup', league, position] })
      }
      void queryClient.invalidateQueries({ queryKey: ['rankings'] })
    },
  })
}

export function useSkip(league: string, position: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (matchupId: string) => {
      const { data } = await apiClient.post<Matchup>(
        '/matchups/skip',
        { matchup_id: matchupId },
        { params: { next_position: position ?? MIX } },
      )
      return data
    },
    onSuccess: (next) => {
      queryClient.setQueryData(['matchup', league, position], next)
    },
  })
}

/**
 * The picks this voter has made.
 *
 * `playerId` narrows to one player's picks — the question you ask when someone
 * looks misplaced on your board: who did I put him up against, and how did I
 * call each one?
 */
export function usePicks(
  league: string,
  position: string | null,
  playerId: number | null,
  enabled = true,
) {
  return useInfiniteQuery({
    queryKey: ['picks', league, position, playerId],
    queryFn: async ({ pageParam }) => {
      const { data } = await apiClient.get<Picks>('/picks', {
        params: {
          league,
          limit: PICKS_PAGE,
          offset: pageParam,
          ...(position ? { position } : {}),
          ...(playerId ? { player_id: playerId } : {}),
        },
      })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (_last, pages) =>
      nextOffset(pages, PICKS_PAGE, (page) => page.picks.length),
    enabled,
  })
}

/**
 * Both of these rebuild ratings from the surviving votes, so every board the
 * app shows is stale the moment one lands — hence the broad invalidation.
 */
function useAfterPickChange() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['picks'] })
    void queryClient.invalidateQueries({ queryKey: ['rankings'] })
  }
}

export function useUndoPick() {
  const settle = useAfterPickChange()

  return useMutation({
    mutationFn: async (pickId: number) => {
      const { data } = await apiClient.delete<Picks>(`/picks/${pickId}`)
      return data
    },
    onSuccess: settle,
  })
}

export function useRevisePick() {
  const settle = useAfterPickChange()

  return useMutation({
    mutationFn: async (vars: { pickId: number; winnerId: number }) => {
      const { data } = await apiClient.patch<Picks>(`/picks/${vars.pickId}`, {
        winner_id: vars.winnerId,
      })
      return data
    },
    onSuccess: settle,
  })
}

export function useRankings(
  league: string,
  position: string | null,
  scope: 'global' | 'personal',
  enabled = true,
) {
  return useInfiniteQuery({
    queryKey: ['rankings', scope, league, position],
    queryFn: async ({ pageParam }) => {
      const path = scope === 'personal' ? '/rankings/me' : '/rankings'
      const { data } = await apiClient.get<Rankings>(path, {
        params: {
          league,
          limit: RANKINGS_PAGE,
          offset: pageParam,
          ...(position ? { position } : {}),
        },
      })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (_last, pages) =>
      nextOffset(pages, RANKINGS_PAGE, (page) => page.entries.length),
    enabled,
  })
}

/** The API's ceiling on one page of rankings. */
const MAX_PAGE = 500

/**
 * The whole personal board, for handing to another app.
 *
 * The board on screen stops at a hundred because nobody scrolls past that, but
 * an export that silently stopped there would hand over a draft list missing
 * its back half. So this pages until it has every ranked player, and only runs
 * when the export panel is actually open.
 */
export function useMyListExport(league: string, position: string | null) {
  return useQuery({
    queryKey: ['rankings-export', league, position],
    queryFn: async () => {
      const entries: RankingEntry[] = []
      for (;;) {
        const { data } = await apiClient.get<Rankings>('/rankings/me', {
          params: {
            league,
            limit: MAX_PAGE,
            offset: entries.length,
            ...(position ? { position } : {}),
          },
        })
        // An empty page ends it too, so a shrinking board can't spin here.
        if (!data.entries.length) return entries
        entries.push(...data.entries)
        if (entries.length >= data.total) return entries
      }
    },
    staleTime: 30 * 1000,
  })
}
