import { useEffect, useMemo, useRef, useState } from 'react'

import { describeError } from '../api/client'
import { useMyListExport } from '../api/hooks'
import { EXPORT_FORMATS, formatFor } from '../lib/exportFormats'
import { Loading } from './StatusNote'

// Whoever drafts on MFL drafts on MFL every year. Remember the pick.
const FORMAT_KEY = 'whoyagot.exportFormat'

interface Props {
  league: string
  /** Narrows the export the same way it narrows the board behind it. */
  position: string | null
}

/**
 * Your board, on its way somewhere else.
 *
 * Two ways out, because the destinations split two ways: sites that take a
 * paste get the clipboard, sites that take an upload get a file. The preview
 * is deliberately the real text rather than a summary — it is the only thing
 * that tells you the export is what you think it is before you paste it into a
 * draft list you cannot easily undo.
 */
export function ExportPanel({ league, position }: Props) {
  const query = useMyListExport(league, position)
  const [formatKey, setFormatKey] = useState(
    () => localStorage.getItem(FORMAT_KEY) ?? EXPORT_FORMATS[0].key,
  )
  const [copied, setCopied] = useState(false)
  const [clipboardFailed, setClipboardFailed] = useState(false)
  const previewRef = useRef<HTMLTextAreaElement>(null)

  const format = formatFor(formatKey)
  const entries = useMemo(() => query.data ?? [], [query.data])
  const text = useMemo(() => format.build(entries), [format, entries])

  const filename = `whoyagot-${[league, position?.toLowerCase(), format.key]
    .filter(Boolean)
    .join('-')}.${format.extension}`

  useEffect(() => {
    localStorage.setItem(FORMAT_KEY, format.key)
  }, [format.key])

  // The tick is the only feedback a copy gets, so it has to clear itself.
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const chooseFormat = (key: string) => {
    setFormatKey(key)
    setCopied(false)
    setClipboardFailed(false)
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setClipboardFailed(false)
    } catch {
      // The Android webview and any plain-http origin refuse the clipboard.
      // Select the list instead, so the manual copy is one keystroke away.
      setClipboardFailed(true)
      previewRef.current?.select()
    }
  }

  const download = () => {
    const type = format.extension === 'csv' ? 'text/csv' : 'text/plain'
    const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    // Firefox only follows a click on an anchor that is in the document.
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Revoking in the same tick cancels the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <section className="mb-4 border-2 border-ink bg-concrete p-3" aria-label="Export your board">
      <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Destination">
        {EXPORT_FORMATS.map((option) => {
          const active = option.key === format.key
          return (
            <button
              key={option.key}
              type="button"
              aria-pressed={active}
              onClick={() => chooseFormat(option.key)}
              className={[
                'sign shrink-0 rounded-full border-2 px-3 py-1 text-[0.58rem] transition-colors',
                active
                  ? 'border-ink bg-ink text-chalk'
                  : 'border-ink/25 text-ink-soft hover:border-ink hover:text-ink',
              ].join(' ')}
            >
              {option.label}
            </button>
          )
        })}
      </div>

      <p className="mb-2 text-[0.72rem] leading-relaxed text-ink-soft">{format.hint}</p>

      {query.isLoading ? (
        <Loading label="Gathering your board" />
      ) : query.isError ? (
        <p className="sign py-4 text-center text-[0.62rem] text-signal">
          {describeError(query.error)}
        </p>
      ) : (
        <>
          <textarea
            ref={previewRef}
            readOnly
            wrap="off"
            spellCheck={false}
            value={text}
            aria-label={`${format.label} export`}
            onFocus={(event) => event.currentTarget.select()}
            className="tabular h-40 w-full resize-y border-2 border-ink/25 bg-chalk p-2 text-[0.7rem] leading-snug text-ink"
          />

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void copy()}
              className="sign border-2 border-ink px-3 py-1.5 text-[0.62rem] text-ink transition-colors hover:bg-ink hover:text-chalk"
            >
              {copied ? 'Copied ✓' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={download}
              title={filename}
              className="sign border-2 border-ink/25 px-3 py-1.5 text-[0.62rem] text-ink-soft transition-colors hover:border-ink hover:text-ink"
            >
              Download .{format.extension}
            </button>

            <span className="tabular ml-auto text-[0.6rem] uppercase tracking-wider text-ink-soft">
              {[
                `${entries.length} ${entries.length === 1 ? 'player' : 'players'}`,
                position ? `${position} only` : null,
              ]
                .filter(Boolean)
                .join('  ·  ')}
            </span>
          </div>

          {clipboardFailed && (
            <p className="mt-2 text-[0.68rem] leading-relaxed text-signal">
              This browser blocked the clipboard. The list above is selected — copy it by hand,
              or download the file instead.
            </p>
          )}
        </>
      )}
    </section>
  )
}
