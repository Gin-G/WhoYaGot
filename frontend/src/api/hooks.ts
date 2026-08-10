import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import type { League, Matchup, Picks, Rankings, VoteResult } from './types'

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
      const { data } = await apiClient.post<VoteResult>('/matchups/vote', {
        matchup_id: vars.matchupId,
        winner_id: vars.winnerId,
      })
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
      const { data } = await apiClient.post<Matchup>('/matchups/skip', { matchup_id: matchupId })
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
  return useQuery({
    queryKey: ['picks', league, position, playerId],
    queryFn: async () => {
      const { data } = await apiClient.get<Picks>('/picks', {
        params: {
          league,
          limit: 200,
          ...(position ? { position } : {}),
          ...(playerId ? { player_id: playerId } : {}),
        },
      })
      return data
    },
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
  return useQuery({
    queryKey: ['rankings', scope, league, position],
    queryFn: async () => {
      const path = scope === 'personal' ? '/rankings/me' : '/rankings'
      const { data } = await apiClient.get<Rankings>(path, {
        params: { league, limit: 100, ...(position ? { position } : {}) },
      })
      return data
    },
    enabled,
  })
}
