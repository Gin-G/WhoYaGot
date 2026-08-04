interface Props {
  positions: string[]
  value: string | null
  onChange: (position: string | null) => void
  /** "All" rotates positions randomly while voting; the lists use it as "no filter". */
  allLabel?: string
}

export function PositionChips({ positions, value, onChange, allLabel = 'Mix' }: Props) {
  const options: Array<{ key: string | null; label: string }> = [
    { key: null, label: allLabel },
    ...positions.map((p) => ({ key: p, label: p })),
  ]

  return (
    <div className="flex gap-1.5 overflow-x-auto px-4 py-2" role="group" aria-label="Position">
      {options.map((option) => {
        const active = option.key === value
        return (
          <button
            key={option.key ?? '__all'}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.key)}
            className={[
              'sign shrink-0 rounded-full border-2 px-3 py-1 text-[0.62rem] transition-colors',
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
  )
}
