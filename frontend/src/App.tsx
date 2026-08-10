import { useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { describeError } from './api/client'
import { useLeagues } from './api/hooks'
import { StatusNote } from './components/StatusNote'
import { TopBar } from './components/TopBar'
import { HistoryPage } from './pages/HistoryPage'
import { MyListPage } from './pages/MyListPage'
import { RankingsPage } from './pages/RankingsPage'
import { VotePage } from './pages/VotePage'

const LEAGUE_KEY = 'whoyagot.league'

export default function App() {
  const leaguesQuery = useLeagues()
  const [league, setLeague] = useState<string>(() => localStorage.getItem(LEAGUE_KEY) ?? 'nfl')
  const [position, setPosition] = useState<string | null>(null)

  const leagues = useMemo(() => leaguesQuery.data ?? [], [leaguesQuery.data])

  // Fall back to whatever league actually has players synced.
  useEffect(() => {
    if (!leagues.length) return
    const current = leagues.find((l) => l.key === league)
    if (!current?.available) {
      const usable = leagues.find((l) => l.available)
      if (usable) setLeague(usable.key)
    }
  }, [leagues, league])

  useEffect(() => {
    localStorage.setItem(LEAGUE_KEY, league)
  }, [league])

  const positions = useMemo(
    () => leagues.find((l) => l.key === league)?.positions ?? [],
    [leagues, league],
  )

  const handleLeagueChange = (key: string) => {
    setLeague(key)
    setPosition(null)
  }

  const shared = {
    league,
    positions,
    position,
    onPositionChange: setPosition,
  }

  // dvh rather than % so the stage tracks a phone's collapsing URL bar.
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-concrete">
      <TopBar leagues={leagues} league={league} onLeagueChange={handleLeagueChange} />

      <main className="min-h-0 flex-1">
        {leaguesQuery.isError ? (
          <StatusNote
            tone="alert"
            title="API unreachable"
            detail={describeError(leaguesQuery.error)}
            action={
              <button
                type="button"
                onClick={() => void leaguesQuery.refetch()}
                className="sign mt-2 border-2 border-ink px-4 py-2 text-[0.65rem] hover:bg-ink hover:text-chalk"
              >
                Try again
              </button>
            }
          />
        ) : (
          <Routes>
            <Route path="/" element={<VotePage {...shared} />} />
            <Route path="/rankings" element={<RankingsPage {...shared} />} />
            <Route path="/my-list" element={<MyListPage {...shared} />} />
            <Route path="/picks" element={<HistoryPage {...shared} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  )
}
